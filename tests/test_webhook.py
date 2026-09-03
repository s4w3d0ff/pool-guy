"""EventSub webhook verification: signature, challenge echo, dispatch."""
import asyncio
import hashlib
import hmac
import json

from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient

SECRET = "test-secret-123"


def sig(mid, ts, body):
    msg = mid.encode() + ts.encode() + body
    return "sha256=" + hmac.new(SECRET.encode(), msg, hashlib.sha256).hexdigest()


def forged_sig(mid, ts, body, secret=b"other-secret"):
    msg = mid.encode() + ts.encode() + body
    return "sha256=" + hmac.new(secret, msg, hashlib.sha256).hexdigest()


async def make_client(on_event):
    app = web.Application()
    from poolguy.webhook import make_webhook_handler
    app.router.add_post("/eventsub", make_webhook_handler(SECRET, on_event=on_event))
    return TestClient(TestServer(app))


async def test_valid_challenge_echoes_200_with_exact_text():
    body = json.dumps({"challenge": "abc-challenge-xyz", "subscription": {}}).encode()

    async def on_event(payload):
        raise AssertionError("verification must not dispatch")

    headers = {
        "Twitch-Eventsub-Message-Id": "m1",
        "Twitch-Eventsub-Message-Timestamp": "t1",
        "Twitch-Eventsub-Message-Type": "webhook_callback_verification",
        "Twitch-Eventsub-Message-Signature": sig("m1", "t1", body),
    }
    async with await make_client(on_event) as client:
        r = await client.post("/eventsub", data=body, headers=headers)
        assert r.status == 200
        text = await r.text()
        assert text == "abc-challenge-xyz"


async def test_tampered_body_fails():
    body = json.dumps({"challenge": "c1", "subscription": {}}).encode()

    async def on_event(payload):
        pass

    headers = {
        "Twitch-Eventsub-Message-Id": "m2",
        "Twitch-Eventsub-Message-Timestamp": "t2",
        "Twitch-Eventsub-Message-Type": "webhook_callback_verification",
        "Twitch-Eventsub-Message-Signature": sig("m2", "t2", body),
    }
    tampered = body[:-3] + b"1}"
    async with await make_client(on_event) as client:
        r = await client.post("/eventsub", data=tampered, headers=headers)
        assert r.status == 403


async def test_wrong_secret_fails():
    body = json.dumps({"challenge": "c2", "subscription": {}}).encode()

    async def on_event(payload):
        pass

    headers = {
        "Twitch-Eventsub-Message-Id": "m3",
        "Twitch-Eventsub-Message-Timestamp": "t3",
        "Twitch-Eventsub-Message-Type": "webhook_callback_verification",
        "Twitch-Eventsub-Message-Signature": forged_sig("m3", "t3", body),
    }
    async with await make_client(on_event) as client:
        r = await client.post("/eventsub", data=body, headers=headers)
        assert r.status == 403


async def test_missing_signature_header_fails():
    body = json.dumps({"challenge": "c3"}).encode()

    async def on_event(payload):
        pass

    headers = {
        "Twitch-Eventsub-Message-Id": "m4",
        "Twitch-Eventsub-Message-Timestamp": "t4",
        "Twitch-Eventsub-Message-Type": "webhook_callback_verification",
    }
    async with await make_client(on_event) as client:
        r = await client.post("/eventsub", data=body, headers=headers)
        assert r.status == 403


async def test_valid_notification_dispatched_to_callback():
    body = json.dumps({
        "subscription": {"type": "channel.follow"},
        "event": {"user_id": "1"},
    }).encode()
    events = []

    async def on_event(payload):
        events.append(payload)

    headers = {
        "Twitch-Eventsub-Message-Id": "m5",
        "Twitch-Eventsub-Message-Timestamp": "t5",
        "Twitch-Eventsub-Message-Type": "notification",
        "Twitch-Eventsub-Message-Signature": sig("m5", "t5", body),
    }
    async with await make_client(on_event) as client:
        r = await client.post("/eventsub", data=body, headers=headers)
        assert r.status == 204
        assert events[0]["subscription"]["type"] == "channel.follow"


async def test_compute_signature_matches_independent_impl():
    from poolguy.webhook import compute_signature
    body = b'{"challenge":"zz"}'
    expected = sig("id1", "ts1", body)
    assert compute_signature(SECRET, "id1", "ts1", body) == expected


async def test_cli_signed_traffic_against_live_handler(mock_units):
    import socket

    from poolguy.webhook import make_webhook_handler

    def free_port():
        for port in (8094, 8095, 8096, 8097):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    continue
            except OSError:
                return port
        raise RuntimeError("no free local port for webhook signed-traffic test")

    port = free_port()
    broadcaster = mock_units["rich_partner"]["id"]
    callback_url = f"http://127.0.0.1:{port}/eventsub/"
    events = []
    received = asyncio.Event()

    async def on_event(payload):
        events.append(payload)
        received.set()

    app = web.Application()
    handler = make_webhook_handler(SECRET, on_event=on_event)
    app.router.add_post("/eventsub", handler)
    app.router.add_post("/eventsub/", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        p = await asyncio.create_subprocess_exec(
            "twitch", "event", "verify-subscription", "channel.follow",
            "-b", str(broadcaster), "-F", callback_url, "-s", SECRET,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(p.communicate(), timeout=30)
        combined = (out + err).decode().lower()
        assert p.returncode == 0, f"verify-subscription failed: {(out + err).decode()}"
        assert "valid response" in combined and "200" in combined, (out + err).decode()

        t = await asyncio.create_subprocess_exec(
            "twitch", "event", "trigger", "channel.follow", "-T", "webhook",
            "-F", callback_url, "-s", SECRET,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(t.communicate(), timeout=30)
        assert t.returncode == 0, f"trigger failed: {(out + err).decode()}"
        await asyncio.wait_for(received.wait(), timeout=15)
        assert events[0]["subscription"]["type"] == "channel.follow", json.dumps(events[0])
    finally:
        await runner.cleanup()
