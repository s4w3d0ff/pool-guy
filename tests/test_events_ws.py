"""EventSub welcome-to-subscribe flow against the twitch-cli mock EventSub server."""

import asyncio
import json
import subprocess
import time
import types

from conftest import FakeStorage, _http_json, WS_PORT

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
