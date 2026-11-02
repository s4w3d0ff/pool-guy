"""RequestHandler webserver injection: none by default, consumer-provided when asked."""
from conftest import FakeStorage
from poolguy.http import RequestHandler


async def test_no_webserver_by_default():
    handler = RequestHandler(
        client_id="client-test",
        redirect_uri="http://localhost:5000/callback",
        storage=FakeStorage(),
    )
    assert handler.server is None, "pool-guy must not run a persistent webserver by default"


async def test_injected_webserver_is_used():
    from poolguy.core.webserver import WebServer
    injected = WebServer(host="192.168.0.5", port=7777)
    handler = RequestHandler(
        client_id="client-test",
        redirect_uri="http://localhost:5000/callback",
        webserver=injected,
        storage=FakeStorage(),
    )
    assert handler.server is injected


async def test_shutdown_without_webserver_is_safe():
    handler = RequestHandler(
        client_id="client-test",
        redirect_uri="http://localhost:5000/callback",
        storage=FakeStorage(),
    )
    await handler.shutdown()
