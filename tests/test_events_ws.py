"""EventSub welcome-to-subscribe flow against the twitch-cli mock EventSub server."""

import asyncio
import json
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
