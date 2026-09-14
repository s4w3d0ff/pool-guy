"""RequestHandler explicit host/port bind, with redirect_uri fallback."""
from conftest import FakeStorage
from poolguy.http import RequestHandler


async def test_explicit_host_port_bind_wins_over_redirect_uri():
    handler = RequestHandler(
        client_id="client-test",
        redirect_uri="http://localhost:5000/callback",
        host="127.0.0.1",
        port=6001,
        storage=FakeStorage(),
    )
    assert handler.server.host == "127.0.0.1"
    assert handler.server.port == 6001


async def test_bind_falls_back_to_redirect_uri_without_host_port():
    handler = RequestHandler(
        client_id="client-test",
        redirect_uri="http://localhost:5000/callback",
        storage=FakeStorage(),
    )
    assert handler.server.host == "localhost"
    assert handler.server.port == 5000


async def test_injected_webserver_takes_precedence_over_host_port():
    from poolguy.core.webserver import WebServer
    injected = WebServer(host="192.168.0.5", port=7777)
    handler = RequestHandler(
        client_id="client-test",
        redirect_uri="http://localhost:5000/callback",
        host="127.0.0.1",
        port=6001,
        webserver=injected,
        storage=FakeStorage(),
    )
    assert handler.server is injected
