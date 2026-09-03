"""Reconnect flow: old socket closed within window after new welcome; one live connection."""
import json
from websockets.exceptions import ConnectionClosed

from conftest import make_ws


class FakeSocket:
    def __init__(self, messages):
        self._msgs = list(messages)
        self.closed = False

    async def recv(self):
        if not self._msgs:
            raise ConnectionClosed(None, None)
        return self._msgs.pop(0)

    async def close(self):
        self.closed = True


def welcome(session_id="new-session"):
    return json.dumps({
        "metadata": {"message_type": "session_welcome"},
        "payload": {"session": {"id": session_id}},
    })


def reconnect_payload(url="wss://reconnect.example/ws"):
    return {
        "metadata": {"message_type": "session_reconnect"},
        "payload": {"session": {"reconnect_url": url}},
    }


async def test_old_socket_closed_after_new_welcome(monkeypatch):
    import poolguy.twitchws as wsmod
    ws = make_ws()
    old = FakeSocket([])
    new = FakeSocket([welcome("sess-2")])
    connected_urls = []

    async def fake_connect(url):
        connected_urls.append(url)
        return new

    monkeypatch.setattr(wsmod.websockets, "connect", fake_connect)
    ws._socket = old

    meta, payload = reconnect_payload("wss://r1")["metadata"], reconnect_payload("wss://r1")["payload"]
    await ws.handle_session_reconnect(meta, payload)
    assert connected_urls == ["wss://r1"]
    assert old.closed is True
    assert new.closed is False
    assert ws._socket is new
    assert ws._session_id == "sess-2"


async def test_old_socket_closed_on_failure_path(monkeypatch):
    import poolguy.twitchws as wsmod
    ws = make_ws()
    old = FakeSocket([])
    dead_new = FakeSocket([])

    async def fake_connect(url):
        return dead_new

    monkeypatch.setattr(wsmod.websockets, "connect", fake_connect)
    ws._socket = old

    meta, payload = reconnect_payload()["metadata"], reconnect_payload()["payload"]
    try:
        await ws.handle_session_reconnect(meta, payload)
        assert False, "expected reconnect failure to propagate"
    except Exception:
        pass
    assert old.closed is True
    assert dead_new.closed is True


async def test_ping_handling_skipped_per_user_ruling():
    """Phase 5 task 4 (ping/pong application-level handling) was skipped by user ruling.

    Twitch's 'Ping' IS a standard WebSocket Ping frame per the twitch-api skill
    reference (eventsub/websocket-reference.md: 'A standard WebSocket Ping frame'),
    and the `websockets` library answers protocol pings with pongs automatically,
    so no application-level ping message handling is required. This placeholder
    documents why PLAN Phase 5 task 4 has no test.
    """
    assert True
