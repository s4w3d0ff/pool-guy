"""REST hardening: pagination immutability, proactive rate limit, chat limit."""
import json
import time
import asyncio

from conftest import make_api


async def test_continue_page_fetches_all_pages_and_keeps_caller_params():
    api = make_api()
    captured = []

    async def fake_request(method, url, *args, **kwargs):
        p = kwargs.get("params") or {}
        captured.append(dict(p))
        if p.get("after") == "c0":
            return {"data": ["b1", "b2"], "pagination": {"cursor": "c1"}}
        if p.get("after") == "c1":
            return {"data": ["b3"], "pagination": {}}
        raise AssertionError(f"unexpected params {p}")

    api._request = fake_request
    caller_params = {"first": 50, "user_id": "42"}
    snapshot = dict(caller_params)

    out = await api._continuePage("get", "https://x/streams", {"cursor": "c0"}, params=caller_params)

    assert out == ["b1", "b2", "b3"], f"all pages must be returned, got {out}"
    assert caller_params == snapshot, f"caller params mutated: {caller_params}"
    assert captured[0] == {"first": 50, "user_id": "42", "after": "c0"}
    assert captured[1] == {"first": 50, "user_id": "42", "after": "c1"}


async def test_continue_page_stops_at_empty_pagination():
    api = make_api()

    async def fake_request(method, url, *args, **kwargs):
        return {"data": ["only"], "pagination": {}}

    api._request = fake_request
    out = await api._continuePage("get", "https://x", {}, params={"first": 10})
    assert out == []


async def test_getstreams_follows_same_helper_without_mutating_kwargs():
    api = make_api()
    captured = []

    async def fake_request(method, url, *args, **kwargs):
        p = kwargs.get("params") or {}
        captured.append(dict(p))
        if "after" in p:
            return {"data": ["s2"], "pagination": {}}
        return {"data": ["s1"], "pagination": {"cursor": "cs1"}}

    api._request = fake_request
    kwargs = {"user_id": "7"}
    snapshot = dict(kwargs)
    out = await api.getStreams(**kwargs)
    assert out == ["s1", "s2"]
    assert kwargs == snapshot, f"getStreams mutated its kwargs: {kwargs}"
    assert captured[0] == {"user_id": "7", "first": 100}
    assert captured[1] == {"user_id": "7", "first": 100, "after": "cs1"}


async def test_proactive_ratelimit_sleep_before_next_request():
    import aiohttp
    import poolguy.http as httpmod
    from poolguy.http import RequestHandler

    h = RequestHandler.__new__(RequestHandler)
    h.client_id = "cid"
    h._ratelimit_reset_at = 0
    h.user_id = None

    async def fake_token():
        return {"access_token": "t"}

    h.token = fake_token

    sleeps = []
    real_sleep = asyncio.sleep

    async def spy_sleep(d):
        sleeps.append(d)
        await real_sleep(min(d, 0.01))

    class Resp:
        def __init__(self, headers):
            self.status = 200
            self.headers = headers

        async def json(self):
            return {"ok": True}

        def raise_for_status(self):
            pass

    responses = iter([
        Resp({"Ratelimit-Remaining": "0", "Ratelimit-Reset": str(int(time.time()) + 3)}),
        Resp({}),
    ])

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def request(self, method, url, *args, **kwargs):
            resp = next(responses)

            class Ctx:
                async def __aenter__(s2):
                    return resp

                async def __aexit__(s2, *a):
                    return False

            return Ctx()

    real_session = httpmod.aiohttp.ClientSession
    httpmod.aiohttp.ClientSession = lambda *a, **k: FakeSession()
    httpmod.asyncio.sleep = spy_sleep
    try:
        r1 = await h._request("get", "https://x/one")
        r2 = await h._request("get", "https://x/two")
    finally:
        httpmod.aiohttp.ClientSession = real_session
        httpmod.asyncio.sleep = real_sleep

    assert sleeps and sleeps[0] >= 1, f"expected proactive sleep before second request, got {sleeps}"
    assert r2 == {"ok": True}


async def test_no_proactive_wait_when_budget_remains():
    import poolguy.http as httpmod
    from poolguy.http import RequestHandler

    h = RequestHandler.__new__(RequestHandler)
    h.client_id = "cid"
    h._ratelimit_reset_at = 0

    async def fake_token():
        return {"access_token": "t"}

    h.token = fake_token

    sleeps = []
    real_sleep = asyncio.sleep

    async def spy_sleep(d):
        sleeps.append(d)
        await real_sleep(min(d, 0.01))

    class Resp:
        status = 200
        headers = {"Ratelimit-Remaining": "5"}

        async def json(self):
            return {"ok": True}

        def raise_for_status(self):
            pass

    import aiohttp

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def request(self, method, url, *args, **kwargs):
            class Ctx:
                async def __aenter__(s2):
                    return Resp()

                async def __aexit__(s2, *a):
                    return False

            return Ctx()

    real_session = httpmod.aiohttp.ClientSession
    httpmod.aiohttp.ClientSession = lambda *a, **k: FakeSession()
    httpmod.asyncio.sleep = spy_sleep
    try:
        await h._request("get", "https://x/one")
        r2 = await h._request("get", "https://x/two")
    finally:
        httpmod.aiohttp.ClientSession = real_session
        httpmod.asyncio.sleep = real_sleep

    assert sleeps == [], f"no sleep expected when budget remains, got {sleeps}"


async def test_chat_limit_truncates_at_500():
    api = make_api()
    captured = {}

    async def fake_request(method, url, *args, **kwargs):
        captured["payload"] = json.loads(kwargs.get("data"))
        return {"data": [{"id": "1"}]}

    api._request = fake_request
    long_msg = "x" * 501
    await api.sendChatMessage(long_msg)
    assert len(captured["payload"]["message"]) == 500

    exact = "y" * 500
    await api.sendChatMessage(exact)
    assert captured["payload"]["message"] == exact
