"""Suite must never leave the machine: non-local hosts are refused, local allowed."""
import asyncio

import aiohttp
from aiohttp import web


async def test_nonlocal_http_refused_by_guard():
    async with aiohttp.ClientSession() as session:
        try:
            await asyncio.wait_for(
                session.get("https://api.twitch.tv/helix/users"), timeout=10
            )
        except Exception as e:
            assert "non-local" in str(e), f"expected guard refusal, got: {type(e).__name__}: {e}"
        else:
            raise AssertionError("guard allowed a non-local HTTP request")


async def test_nonlocal_websocket_refused_by_guard():
    import websockets

    try:
        await asyncio.wait_for(
            websockets.connect("wss://eventsub.wss.twitch.tv/ws"), timeout=10
        )
    except Exception as e:
        assert "non-local" in str(e), f"expected guard refusal, got: {type(e).__name__}: {e}"
    else:
        raise AssertionError("guard allowed a non-local websocket connect")


async def test_local_http_allowed_by_guard():
    async def ok(request):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/ping", ok)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = next(iter(site._server.sockets)).getsockname()[1]
    try:
        async with aiohttp.ClientSession() as session:
            r = await asyncio.wait_for(
                session.get(f"http://127.0.0.1:{port}/ping"), timeout=10
            )
        assert r.status == 200
    finally:
        await runner.cleanup()
