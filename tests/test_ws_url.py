"""TwitchWebsocket.ws_url: per-instance EventSub websocket url override."""
from conftest import FakeStorage
from poolguy.twitchws import TwitchWebsocket, WSURL


def make_http_stub():
    return type("H", (), {"storage": FakeStorage(), "user_id": "9"})()


async def test_default_ws_url_is_production_constant():
    ws = TwitchWebsocket(None, channels={}, http=make_http_stub())
    assert ws.ws_url == WSURL


async def test_ws_url_kwarg_overrides_connect_target():
    ws = TwitchWebsocket(
        None,
        channels={},
        http=make_http_stub(),
        ws_url="ws://127.0.0.1:8090/ws",
    )
    assert ws.ws_url == "ws://127.0.0.1:8090/ws"
