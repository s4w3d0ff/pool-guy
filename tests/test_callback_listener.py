"""On-demand OAuth callback listener: mounted only while acquiring a token."""
import asyncio
import socket

import aiohttp
from aiohttp import web

import poolguy.core.oauth as oauth_mod
from conftest import FakeStorage
from poolguy.core.oauth import TokenHandler


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _NoOpenBrowser:
    def open(self, url, new=1):
        return False


async def _start_fake_token_endpoint(port):
    async def token_handler(request):
        return web.json_response({
            "access_token": "fake-at",
            "refresh_token": "fake-rt",
            "expires_in": 3600,
            "scope": "user:read:chat",
        })

    app = web.Application()
    app.router.add_post("/token", token_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    return site, runner


async def test_interactive_auth_mounts_and_unmounts_callback_listener(monkeypatch):
    monkeypatch.setattr(oauth_mod.webbrowser, "get", lambda *a, **k: _NoOpenBrowser())
    callback_port = _free_port()
    token_port = _free_port()
    site, runner = await _start_fake_token_endpoint(token_port)

    handler = TokenHandler(
        client_id="client-abc",
        redirect_uri=f"http://127.0.0.1:{callback_port}/callback",
        scopes=["user:read:chat"],
        storage=FakeStorage(),
        token_endpoint=f"http://127.0.0.1:{token_port}/token",
    )

    task = asyncio.create_task(handler._get_new_token())
    try:
        while not (handler._state and handler._callback_server is not None):
            await asyncio.sleep(0.05)
        url = f"http://127.0.0.1:{callback_port}/callback?code=abc&state={handler._state}"
        async with aiohttp.ClientSession() as session:
            for _ in range(200):
                try:
                    async with session.get(url) as resp:
                        assert resp.status == 200
                        break
                except (aiohttp.ClientConnectionError, ConnectionRefusedError):
                    await asyncio.sleep(0.05)
            else:
                raise AssertionError("callback listener never accepted a connection")

        token = await task
    finally:
        if not task.done():
            task.cancel()
        await site.stop()
        await runner.cleanup()

    assert token["access_token"] == "fake-at"
    stored = await handler.storage.load_token("twitch")
    assert stored and stored["access_token"] == "fake-at"
    assert handler._callback_server is None, "callback listener must be unmounted after exchange"
    try:
        with socket.create_connection(("127.0.0.1", callback_port), timeout=0.5):
            raise AssertionError("callback port still accepting connections")
    except ConnectionRefusedError:
        pass


async def test_login_with_stored_token_never_starts_callback_listener(monkeypatch):
    monkeypatch.setattr(oauth_mod.webbrowser, "get", lambda *a, **k: _NoOpenBrowser())
    handler = TokenHandler(
        client_id="client-abc",
        redirect_uri="http://127.0.0.1:5999/callback",
        scopes=["user:read:chat"],
        storage=FakeStorage(),
    )
    await handler.storage.save_token("twitch", {
        "access_token": "stored-at",
        "refresh_token": "rt",
        "requested_scopes": ["user:read:chat"],
    })

    async def fake_validate():
        return True, {"user_id": "u1", "expires_in": 7200, "scopes": ["user:read:chat"]}

    handler._validate_auth = fake_validate
    await handler._login()

    assert handler.user_id == "u1"
    assert handler._callback_server is None, "steady state must not run a callback listener"
    assert "/callback" not in handler.server.routes, "shared server must have no /callback route"
    await handler.stop()


async def test_stop_callback_is_idempotent_and_safe_when_never_started():
    handler = TokenHandler(
        client_id="client-abc",
        redirect_uri="http://127.0.0.1:5998/callback",
        storage=FakeStorage(),
    )
    await handler.stop_callback()
    assert handler._callback_server is None

    port = _free_port()
    handler._callback_host, handler._callback_port = "127.0.0.1", port
    await handler.start_callback()
    assert handler._callback_server is not None and handler._callback_server.is_running()
    await handler.stop_callback()
    await handler.stop_callback()
    assert handler._callback_server is None
