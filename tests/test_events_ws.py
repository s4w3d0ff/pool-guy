"""EventSub welcome-to-subscribe flow against the twitch-cli mock EventSub server."""

import asyncio
import json
import subprocess
import time
import types
import uuid

from conftest import FakeStorage, _http_json, iso_offset, WS_PORT

SUBS_URL = f"http://127.0.0.1:{WS_PORT}/eventsub/subscriptions"


async def _poll_subscriptions(expected_types, client_id):
    headers = {"Client-ID": client_id}
    deadline = time.monotonic() + 15
    last = []
    while time.monotonic() < deadline:
        try:
            body = await asyncio.to_thread(_http_json, SUBS_URL, "GET", headers)
            subs = body.get("data", [])
        except Exception:
            subs = []
        by_type = {}
        for sub in subs:
            by_type.setdefault(sub.get("type"), []).append(sub)
        if all(
            t in by_type and any(s.get("status") == "enabled" for s in by_type[t])
            for t in expected_types
        ):
            return subs
        last = subs
        await asyncio.sleep(0.25)
    raise AssertionError(
        f"subscriptions not enabled within deadline; server state: {json.dumps(last, indent=2)}"
    )


async def test_welcome_to_subscribe_flow(mock_ws_url, mock_units, mocked_api):
    from poolguy.twitchws import TwitchWebsocket

    partner = mock_units["rich_partner"]
    api = mocked_api(user_id=partner["id"])
    api.storage = FakeStorage()
    api.apiEndpoints["eventsub"] = SUBS_URL

    channels = {
        "channel.ban": [partner["id"]],
        "stream.online": [None],
        "user.update": None,
    }

    ws = TwitchWebsocket(types.SimpleNamespace(), channels=channels, http=api, ws_url=mock_ws_url)
    task = asyncio.create_task(ws.run(paused=True))
    try:
        subs = await _poll_subscriptions(["channel.ban", "stream.online", "user.update"], api.client_id)
    finally:
        if not task.done():
            ws._running = False
            if ws._socket is not None:
                await ws._socket.close()
            try:
                await asyncio.wait_for(task, timeout=10)
            except (asyncio.TimeoutError, Exception):
                task.cancel()

    by_type = {s["type"]: s for s in subs}
    ban = by_type["channel.ban"]
    assert ws._session_id is not None, "welcome message never captured a session id"
    assert ban["condition"] == {"broadcaster_user_id": str(partner["id"])}, (
        f"channel.ban condition wrong: {ban['condition']}"
    )
    assert ban["transport"]["method"] == "websocket", f"transport: {ban['transport']}"
    assert ban["transport"]["session_id"] == ws._session_id, (
        f"sub bound to session {ban['transport']['session_id']} but client holds {ws._session_id}"
    )
    assert ban["status"] == "enabled", f"channel.ban status: {ban['status']}"
    assert ban["version"] == "1", f"channel.ban version: {ban['version']}"

    stream = by_type["stream.online"]
    assert stream["condition"] == {"broadcaster_user_id": str(api.user_id)}, (
        f"stream.online condition wrong: {stream['condition']}"
    )
    assert stream["transport"]["session_id"] == ws._session_id, "stream.online on wrong session"

    update = by_type["user.update"]
    assert update["condition"] == {"user_id": str(api.user_id)}, (
        f"user.update condition wrong: {update['condition']}"
    )


async def _trigger(event, session_id, args):
    cmd = [
        "twitch", "event", "trigger", event, "--transport=websocket",
        f"--session={session_id}", *args,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, (
        f"trigger {event} failed rc={proc.returncode}: {(proc.stdout + proc.stderr).strip()[:200]}"
    )


async def _clear_server_subscriptions(client_id):
    headers = {"Client-ID": client_id}
    body = await asyncio.to_thread(_http_json, SUBS_URL, "GET", headers)
    for sub in body.get("data", []):
        url = f"{SUBS_URL}?id={sub['id']}"
        await asyncio.to_thread(_http_json, url, "DELETE", headers)


async def test_event_dispatch_over_socket(mock_ws_url, mock_units, mocked_api):
    from poolguy.eventsub import Alert, AlertFactory, NotificationHandler
    from poolguy.twitchws import TwitchWebsocket

    partner = mock_units["rich_partner"]
    api = mocked_api(user_id=partner["id"])
    api.storage = FakeStorage()
    api.apiEndpoints["eventsub"] = SUBS_URL

    channels = {
        "channel.ban": [partner["id"]],
        "channel.follow": None,
        "stream.online": None,
        "user.update": None,
    }
    conditions = {
        "channel.ban": {"broadcaster_user_id": str(partner["id"])},
        "channel.follow": {
            "broadcaster_user_id": str(api.user_id),
            "moderator_user_id": str(api.user_id),
        },
        "stream.online": {"broadcaster_user_id": str(api.user_id)},
        "user.update": {"user_id": str(api.user_id)},
    }

    raw_notifications = []
    routed = {}
    orig_call = NotificationHandler.__call__

    actor = next(
        u["id"] for u in mock_units["users"]
        if u.get("broadcaster_type") != "partner" and str(u["id"]) != str(api.user_id)
    )

    async def spy(self, metadata, payload):
        sub = payload.get("subscription", {})
        if sub.get("type") in channels:
            raw_notifications.append((metadata, payload))
        return await orig_call(self, metadata, payload)

    for kind in channels:
        class Recorder(Alert):
            queue_skip = True

            async def process(self):
                routed[kind] = self.data

        AlertFactory.register_alert_class(kind, Recorder)

    await _clear_server_subscriptions(api.client_id)
    NotificationHandler.__call__ = spy
    ws = TwitchWebsocket(types.SimpleNamespace(), channels=channels, http=api, ws_url=mock_ws_url)
    task = asyncio.create_task(ws.run(paused=True))
    try:
        await _poll_subscriptions(list(channels), api.client_id)

        trigger_args = {
            "channel.ban": ["-f", str(actor), "-t", str(partner["id"])],
            "channel.follow": ["-f", str(api.user_id), "-t", str(api.user_id)],
            "stream.online": ["-t", str(api.user_id)],
            "user.update": ["-t", str(api.user_id)],
        }

        for kind in channels:
            await _trigger(kind, ws._session_id, trigger_args[kind])
            end = time.monotonic() + 15
            while (not any(p["subscription"]["type"] == kind for _, p in raw_notifications)
                   or kind not in routed) and time.monotonic() < end:
                await asyncio.sleep(0.2)

        for kind, _ in channels.items():
            matches = [
                (meta, payload) for meta, payload in raw_notifications
                if payload["subscription"]["type"] == kind
            ]
            assert len(matches) >= 1, f"no notification received over socket for {kind}"
            meta, payload = matches[0]
            sub = payload["subscription"]

            assert meta["message_id"], "notification without message_id"
            from poolguy.eventsub import convert2epoch
            age = time.time() - convert2epoch(meta["message_timestamp"])
            assert 0 <= age < 300, f"stale or future timestamp: age {age:.1f}s"

            assert sub["id"], "subscription without id"
            assert sub["status"] == "enabled", f"{kind} status: {sub['status']}"
            from poolguy.twitchapi import EVENTSUB_VERSIONS
            assert sub["version"] == EVENTSUB_VERSIONS[kind], (
                f"{kind} version {sub['version']} != spec {EVENTSUB_VERSIONS[kind]}"
            )
            assert sub["condition"] == conditions[kind], (
                f"{kind} condition {sub['condition']} != expected {conditions[kind]}"
            )
            assert sub["transport"]["method"] == "websocket", f"transport: {sub['transport']}"
            assert ws._session_id and sub["transport"].get("session_id") == ws._session_id, (
                f"{kind} bound to session {sub['transport'].get('session_id')} "
                f"but client holds {ws._session_id}"
            )

            event = payload["event"]
            routed_data = routed.get(kind)
            assert routed_data is not None, (
                f"registered alert class for {kind} never processed the notification"
            )
            assert routed_data == event, "alert data differs from wire event payload"

        ids = {p["subscription"]["id"] for _, p in raw_notifications if p["subscription"]["type"] in channels}
        types_seen = [p["subscription"]["type"] for _, p in raw_notifications]
        assert len(ids) >= len(channels), f"duplicate subscription ids: {ids}"

        ban_event = next(
            p["event"] for _, p in raw_notifications if p["subscription"]["type"] == "channel.ban"
        )
        from poolguy.eventsub import convert2epoch as to_epoch
        assert isinstance(to_epoch(ban_event["banned_at"]), float)
        assert ban_event["ends_at"] is None or isinstance(ban_event["ends_at"], str)
        assert isinstance(ban_event["is_permanent"], bool)
        for key in ("user_id", "moderator_user_id", "broadcaster_user_id"):
            assert ban_event[key], f"channel.ban missing {key}"

        follow_event = next(
            p["event"] for _, p in raw_notifications if p["subscription"]["type"] == "channel.follow"
        )
        to_epoch(follow_event["followed_at"])
        assert follow_event["user_id"], "channel.follow missing user_id"

        online_event = next(
            p["event"] for _, p in raw_notifications if p["subscription"]["type"] == "stream.online"
        )
        assert online_event.get("id"), "stream.online missing stream id"
        to_epoch(online_event["started_at"])
        assert online_event["type"] == "live", f"stream type: {online_event['type']}"

        update_event = next(
            p["event"] for _, p in raw_notifications if p["subscription"]["type"] == "user.update"
        )
        assert update_event.get("user_id"), "user.update missing user_id"
        assert isinstance(update_event.get("email_verified"), bool)
    finally:
        NotificationHandler.__call__ = orig_call
        ws._running = False
        if ws._socket is not None:
            await ws._socket.close()
        try:
            await asyncio.wait_for(task, timeout=10)
        except (asyncio.TimeoutError, Exception):
            task.cancel()


async def test_dedup_and_replay_drop_over_socket(mock_ws_url, mock_units, mocked_api):
    from poolguy.eventsub import Alert, AlertFactory, NotificationHandler
    from poolguy.twitchws import REPLAY_WINDOW_SECONDS, TwitchWebsocket

    partner = mock_units["rich_partner"]
    api = mocked_api(user_id=partner["id"])
    api.storage = FakeStorage()
    api.apiEndpoints["eventsub"] = SUBS_URL

    trigger_args = {"stream.online": ["-t", str(api.user_id)]}

    processed = []
    wire_messages = {}
    orig_call = NotificationHandler.__call__

    async def spy(self, metadata, payload):
        if payload.get("subscription", {}).get("type") in trigger_args:
            mid = metadata["message_id"]
            processed.append(mid)
            wire_messages.setdefault(mid, {"metadata": metadata, "payload": payload})
        return await orig_call(self, metadata, payload)

    for kind in trigger_args:
        class Recorder(Alert):
            queue_skip = True

            async def process(self):
                pass

        AlertFactory.register_alert_class(kind, Recorder)

    NotificationHandler.__call__ = spy
    ws = TwitchWebsocket(types.SimpleNamespace(), channels=dict(trigger_args), http=api, ws_url=mock_ws_url)
    task = asyncio.create_task(ws.run(paused=True))
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            body = await asyncio.to_thread(_http_json, SUBS_URL, "GET", {"Client-ID": api.client_id})
            if all(any(s.get("type") == k and s.get("status") == "enabled" for s in body.get("data", []))
                   for k in trigger_args):
                break
            await asyncio.sleep(0.25)

        sid = ws._session_id

        def trigger(kind):
            proc = subprocess.run(
                ["twitch", "event", "trigger", kind, "--transport=websocket",
                 f"--session={sid}", *trigger_args[kind]],
                capture_output=True, text=True, timeout=30,
            )
            assert proc.returncode == 0, (
                f"trigger failed rc={proc.returncode}: {(proc.stdout + proc.stderr).strip()[:200]}"
            )

        async def wait_for(count):
            end = time.monotonic() + 15
            while len(processed) < count and time.monotonic() < end:
                await asyncio.sleep(0.2)

        trigger("stream.online")
        await wait_for(1)
        assert len(processed) == 1, f"first delivery never processed: {processed}"
        first_mid = wire_messages[processed[0]]["metadata"]["message_id"]
        assert api.storage.messages.get(first_mid), "accepted message not recorded in dedup storage"

        # The mock mints a fresh UUID per trigger; an at-least-once redelivery
        # is the same wire frame arriving twice, so replay it verbatim.
        async def feed(message):
            await ws.handle_message(message)

        first_wire = wire_messages[first_mid]
        await feed(first_wire)
        await asyncio.sleep(1)
        assert processed.count(first_mid) == 1, (
            f"replayed message_id {first_mid} was not dropped: occurrences={processed.count(first_mid)}"
        )

        trigger("stream.online")
        await wait_for(2)
        assert len(processed) == 2, f"fresh id after duplicate was rejected: {processed}"
        new_mid = processed[-1]

        stale_meta = dict(wire_messages[new_mid]["metadata"])
        age_seconds = REPLAY_WINDOW_SECONDS + 300
        stale_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - age_seconds))
        fresh_id = str(uuid.uuid4())
        stale_meta["message_id"] = fresh_id
        stale_meta["message_timestamp"] = stale_ts
        await feed({"metadata": stale_meta, "payload": wire_messages[new_mid]["payload"]})
        await asyncio.sleep(1)
        assert fresh_id not in processed and api.storage.messages.get(fresh_id) is None, (
            f"unknown id with {age_seconds}s-old timestamp was accepted; replay window is {REPLAY_WINDOW_SECONDS}s"
        )
    finally:
        NotificationHandler.__call__ = orig_call
        ws._running = False
        if ws._socket is not None:
            await ws._socket.close()
        try:
            await asyncio.wait_for(task, timeout=10)
        except (asyncio.TimeoutError, Exception):
            task.cancel()



async def test_revocation_resubscribes_injected_frame(mock_ws_url, mock_units, mocked_api, caplog):
    import logging

    from poolguy.twitchws import TwitchWebsocket

    partner = mock_units["rich_partner"]
    api = mocked_api(user_id=partner["id"])
    api.storage = FakeStorage()
    api.apiEndpoints["eventsub"] = SUBS_URL

    channels = {"channel.ban": [partner["id"]]}
    headers = {"Client-ID": api.client_id}

    body = _http_json(SUBS_URL, "GET", headers)
    for sub in body.get("data", []):
        await asyncio.to_thread(_http_json, f"{SUBS_URL}?id={sub['id']}", "DELETE", headers)

    ws = TwitchWebsocket(types.SimpleNamespace(), channels=channels, http=api, ws_url=mock_ws_url)
    task = asyncio.create_task(ws.run(paused=True))
    try:
        subs = await _poll_subscriptions(["channel.ban"], api.client_id)
        ban_sub = next(
            s for s in subs if s.get("type") == "channel.ban" and s.get("status") == "enabled"
        )

        rc = subprocess.run(
            ["twitch", "event", "websocket", "subscription",
             "--status=user_removed", f"--subscription={ban_sub['id']}"],
            capture_output=True, text=True, timeout=30,
        )
        assert rc.returncode == 0, (
            f"revocation status change failed rc={rc.returncode}: {(rc.stdout + rc.stderr).strip()[:200]}"
        )

        revoked = dict(ban_sub)
        revoked["status"] = "user_removed"
        frame = {
            "metadata": {
                "message_type": "revocation",
                "message_id": str(uuid.uuid4()),
                "message_timestamp": iso_offset(0),
            },
            "payload": {"subscription": revoked},
        }

        with caplog.at_level(logging.WARNING, logger="poolguy.twitchws"):
            await ws.handle_message(frame)

        end = time.monotonic() + 15
        fresh = None
        while time.monotonic() < end:
            subs_now = _http_json(SUBS_URL, "GET", headers).get("data", [])
            candidates = [
                s for s in subs_now
                if s.get("type") == "channel.ban" and s["id"] != ban_sub["id"]
                and s.get("status") == "enabled"
            ]
            if candidates:
                fresh = candidates[0]
                break
            await asyncio.sleep(0.25)
        assert fresh is not None, (
            f"no re-subscription after revocation of {ban_sub['id']}: "
            f"{json.dumps(_http_json(SUBS_URL, 'GET', headers), indent=2)}"
        )
        assert fresh["condition"].get("broadcaster_user_id") == partner["id"]
        assert any(ban_sub["id"] in r.message and "revoked" in r.message.lower() for r in caplog.records), (
            f"no revocation log recorded: {[r.message for r in caplog.records]}"
        )
    finally:
        ws._running = False
        if ws._socket is not None:
            await ws._socket.close()
        try:
            await asyncio.wait_for(task, timeout=10)
        except (asyncio.TimeoutError, Exception):
            task.cancel()


async def test_reconnect_over_real_socket(mock_ws_url, mock_units, mocked_api):
    from poolguy.eventsub import Alert, AlertFactory, NotificationHandler
    from poolguy.twitchws import TwitchWebsocket

    partner = mock_units["rich_partner"]
    api = mocked_api(user_id=partner["id"])
    api.storage = FakeStorage()
    api.apiEndpoints["eventsub"] = SUBS_URL

    channels = {
        "stream.online": None,
        "channel.ban": [partner["id"]],
    }
    processed = []
    orig_call = NotificationHandler.__call__
    headers = {"Client-ID": api.client_id}

    async def spy(self, metadata, payload):
        if payload.get("subscription", {}).get("type") in channels:
            processed.append(payload["subscription"]["type"])
        return await orig_call(self, metadata, payload)

    class Recorder(Alert):
        queue_skip = True

        async def process(self):
            pass

    for kind in channels:
        AlertFactory.register_alert_class(kind, Recorder)

    body = _http_json(SUBS_URL, "GET", headers)
    for sub in body.get("data", []):
        await asyncio.to_thread(_http_json, f"{SUBS_URL}?id={sub['id']}", "DELETE", headers)

    NotificationHandler.__call__ = spy
    ws = TwitchWebsocket(types.SimpleNamespace(), channels=channels, http=api, ws_url=mock_ws_url)
    task = asyncio.create_task(ws.run(paused=True))
    try:
        subs = await _poll_subscriptions(list(channels), api.client_id)
        original_ids = {
            s["id"] for s in subs if s.get("type") in channels and s.get("status") == "enabled"
        }
        old_sid = ws._session_id
        assert old_sid

        t0 = time.monotonic()
        proc = subprocess.run(
            ["twitch", "event", "websocket", "reconnect"],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode == 0, (
            f"reconnect command failed rc={proc.returncode}: {(proc.stdout + proc.stderr).strip()[:200]}"
        )

        new_sid = None
        end = time.monotonic() + 30
        while time.monotonic() < end:
            if ws._session_id and ws._session_id != old_sid:
                new_sid = ws._session_id
                break
            await asyncio.sleep(0.2)
        assert new_sid, (
            f"client never followed session_reconnect; still on {old_sid} "
            f"{time.monotonic() - t0:.1f}s after reconnect command"
        )

        rebound = None
        end = time.monotonic() + 30
        while time.monotonic() < end:
            active = [
                s for s in _http_json(SUBS_URL, "GET", headers).get("data", [])
                if s.get("type") in channels and s.get("status") == "enabled"
            ]
            if len(active) == len(channels) \
               and all(s["transport"].get("session_id") == new_sid for s in active) \
               and {s["id"] for s in active} == original_ids:
                rebound = active
                break
            await asyncio.sleep(0.25)
        assert rebound is not None, (
            f"subscriptions not re-bound to session {new_sid}: "
            f"{json.dumps(_http_json(SUBS_URL, 'GET', headers), indent=2)}"
        )

        trigger = subprocess.run(
            ["twitch", "event", "trigger", "stream.online", "--transport=websocket",
             f"--session={new_sid}", "-t", str(api.user_id)],
            capture_output=True, text=True, timeout=30,
        )
        assert trigger.returncode == 0, (
            f"post-reconnect trigger failed rc={trigger.returncode}: "
            f"{(trigger.stdout + trigger.stderr).strip()[:200]}"
        )
        end = time.monotonic() + 15
        while "stream.online" not in processed and time.monotonic() < end:
            await asyncio.sleep(0.2)
        assert "stream.online" in processed, f"no event dispatched after reconnect; processed={processed}"
    finally:
        NotificationHandler.__call__ = orig_call
        ws._running = False
        if ws._socket is not None:
            await ws._socket.close()
        try:
            await asyncio.wait_for(task, timeout=10)
        except (asyncio.TimeoutError, Exception):
            task.cancel()


async def test_subscribe_deadline_require_subscription(tmp_path, mock_units, mocked_api, caplog):
    import logging

    from conftest import _port_in_use, _wait_tcp
    from poolguy.twitchws import TwitchWebsocket

    free_port = next(p for p in (8091, 8092, 8093) if not _port_in_use(p))
    log_file = tmp_path / "deadline-server.log"
    with open(log_file, "wb") as fh:
        server = subprocess.Popen(
            ["twitch", "event", "websocket", "start-server", "-p", str(free_port), "-S"],
            stdout=fh, stderr=subprocess.STDOUT,
        )
    try:
        await asyncio.to_thread(_wait_tcp, free_port)

        api = mocked_api()
        api.storage = FakeStorage()
        ws = TwitchWebsocket(types.SimpleNamespace(), http=api, ws_url=f"ws://127.0.0.1:{free_port}/ws")
        ws.channels = {}
        task = asyncio.create_task(ws.run(paused=True))
        try:
            with caplog.at_level(logging.ERROR, logger="poolguy.twitchws"):
                seen_sessions = []
                end = time.monotonic() + 40
                while len(seen_sessions) < 2 and time.monotonic() < end:
                    if ws._session_id and ws._session_id not in seen_sessions:
                        seen_sessions.append(ws._session_id)
                    await asyncio.sleep(0.2)
            assert len(seen_sessions) >= 2, (
                f"client never cycled past the deadline close; sessions={seen_sessions}; "
                f"server log:\n{log_file.read_text()[-800:]}"
            )
            closes = [r for r in caplog.records if "connection error" in r.message.lower()]
            assert any("unused" in r.message.lower() for r in closes), (
                f"no deadline close reason logged: {[c.message[:200] for c in closes]}"
            )
            assert not any(
                "Exception in socket loop" in r.message for r in caplog.records
            ), "run loop crashed instead of handling the deadline close"
        finally:
            ws._running = False
            if ws._socket is not None:
                await ws._socket.close()
            try:
                await asyncio.wait_for(task, timeout=10)
            except (asyncio.TimeoutError, Exception):
                task.cancel()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
