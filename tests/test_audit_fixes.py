"""Regression tests for .agents/AUDIT.md findings C-01, H-01..H-05, M-01."""
import asyncio
import json as _json
import time


def make_default_handler():
    from poolguy.http import RequestHandler
    return RequestHandler(
        client_id="client-test",
        redirect_uri="http://localhost:5000/callback",
        scopes=["user:read:chat"],
    )


class FakeSleepTracker:
    def __init__(self):
        self.calls = []

    async def __call__(self, seconds):
        self.calls.append(seconds)


class FakeResponse:
    def __init__(self, payload=None, status=200, headers=None):
        self._payload = _json.dumps(payload if payload is not None else {"data": []})
        self.status = status
        self.headers = headers or {}

    async def json(self):
        return _json.loads(self._payload)

    async def text(self):
        return self._payload

    def raise_for_status(self):
        if self.status >= 400:
            import aiohttp
            raise aiohttp.ClientResponseError(
                None, (), status=self.status, message=f"status {self.status}"
            )


def patch_transport(responses):
    import poolguy.http as http_mod

    class _FakeSession:
        def __init__(self):
            self.responses = [FakeResponse(**spec) for spec in responses]
            self.requests = []

        def request(self, method, url, *args, **kwargs):
            self.requests.append((method, url))
            return _Ctx(self.responses.pop(0))

    class _Ctx:
        def __init__(self, response):
            self.response = response

        async def __aenter__(self):
            return self.response

        async def __aexit__(self, *exc):
            return False

    session = _FakeSession()

    class _Sessions:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    orig_session_cls = http_mod.aiohttp.ClientSession
    http_mod.aiohttp.ClientSession = lambda *a, **k: _Sessions()
    return session, lambda: setattr(http_mod.aiohttp, "ClientSession", orig_session_cls)


def make_api_stub():
    from poolguy.twitchapi import TwitchApi, apiEndpoints
    from conftest import FakeStorage

    async def token():
        return {"access_token": "tok-audit"}
    api = TwitchApi.__new__(TwitchApi)
    api.user_id = "12345"
    api.client_id = "client-test"
    api.storage = FakeStorage()
    api._ratelimit_reset_at = 0
    api.token = token
    api.apiEndpoints = {k: v.replace("https://api.twitch.tv", "http://127.0.0.1") for k, v in apiEndpoints.items()}
    return api


#=============================================================================================
# C-01: documented default construction leaves http.storage None
#=============================================================================================

async def test_default_construction_yields_sqlite_storage(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from poolguy.core.storage import SQLiteStorage
    handler = make_default_handler()
    assert isinstance(handler.storage, SQLiteStorage)


async def test_default_construction_dedup_does_not_crash(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from poolguy.twitchws import TwitchWebsocket
    handler = make_default_handler()
    ws = TwitchWebsocket.__new__(TwitchWebsocket)
    ws.http = handler
    meta = {"message_type": "notification", "message_id": "audit-c01"}
    assert await ws._is_duplicate(meta) is False


#=============================================================================================
# H-01: GenericAlert.store crashed on a nonexistent backend method
#=============================================================================================

async def test_generic_alert_store_inserts_and_queries_back(tmp_path):
    from poolguy.eventsub import GenericAlert
    from poolguy.core.storage import StorageFactory
    storage = StorageFactory.create_storage('sqlite', db_path=str(tmp_path / 'audit.db'))
    bot = type("B", (), {"storage": storage})()
    alert = GenericAlert(
        bot, "msg-audit-h01", "channel.ban",
        {"user_id": ["42"], "broadcaster_user_id": "7"}, time.time(),
    )
    await alert.store()
    rows = await storage.query("channel_ban", where="message_id = ?", params=("msg-audit-h01",))
    assert len(rows) == 1
    assert _json.loads(rows[0]["user_id"]) == ["42"]


#=============================================================================================
# H-02: non get/post methods must return a decoded dict supporting r['data']
#=============================================================================================

H02_METHODS = {
    "updateChatSettings": lambda a: a.updateChatSettings(settings={"slow_mode_enabled": True}),
    "unbanUser": lambda a: a.unbanUser(user_id="77"),
    "updateAutomodSettings": lambda a: a.updateAutomodSettings({"block_level": 1}),
    "endGuestStarSession": lambda a: a.endGuestStarSession(),
    "removeModerator": lambda a: a.removeModerator(user_id="77"),
    "removeVIP": lambda a: a.removeVIP(user_id="77"),
    "endPoll": lambda a: a.endPoll(poll_id="p1"),
    "endPrediction": lambda a: a.endPrediction(id="pr1"),
    "cancelRaid": lambda a: a.cancelRaid(),
}


async def test_non_getpost_methods_return_subscriptable_data():
    for name, call in H02_METHODS.items():
        session, restore = patch_transport(
            [{"data": [{"id": name}], "total_cost": 0}]
        )
        try:
            api = make_api_stub()
            r = await call(api)
        finally:
            restore()
        assert isinstance(r, dict), f"{name}: expected decoded dict, got {type(r)}"
        assert r["data"] == [{"id": name}]


#=============================================================================================
# H-03: store=True flag alert must persist through NotificationHandler.__call__
#=============================================================================================

async def test_flag_alert_persists_through_notification_handler(tmp_path):
    from poolguy.eventsub import Alert, NotificationHandler
    from poolguy.core.storage import StorageFactory

    class FlagAlert(Alert):
        queue_skip = True
        store = True

        async def process(self):
            pass

    storage = StorageFactory.create_storage('sqlite', db_path=str(tmp_path / 'audit.db'))
    bot = type("B", (), {"storage": storage})()
    handler = NotificationHandler(bot, storage)
    metadata = {
        "message_id": "flag-audit-1",
        "message_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%f000Z"),
    }
    payload = {
        "subscription": {"type": "channel.ban"},
        "event": {"broadcaster_user_id": "7"},
    }
    await handler(metadata, payload)
    rows = await storage.query("channel_ban", where="message_id = ?", params=("flag-audit-1",))
    assert len(rows) == 1


async def test_custom_async_store_override_fires_once(tmp_path):
    from poolguy.eventsub import Alert, NotificationHandler
    from poolguy.core.storage import StorageFactory

    calls = {"n": 0}

    class CustomAlert(Alert):
        queue_skip = True

        async def process(self):
            pass

        async def store(self):
            calls["n"] += 1

    storage = StorageFactory.create_storage('sqlite', db_path=str(tmp_path / 'audit.db'))
    bot = type("B", (), {"storage": storage})()
    handler = NotificationHandler(bot, storage)
    metadata = {
        "message_id": "custom-audit-1",
        "message_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%f000Z"),
    }
    payload = {"subscription": {"type": "channel.ban"}, "event": {}}
    await handler(metadata, payload)
    assert calls["n"] == 1


#=============================================================================================
# H-04: 429 without Ratelimit-Reset header must not crash int(None)
#=============================================================================================

async def test_429_without_reset_header_retries_bounded():
    tracker = FakeSleepTracker()
    responses = [dict(status=429, headers={}), dict(payload={"data": ["ok"]})]
    session, restore = patch_transport(responses)
    import poolguy.http as http_mod
    try:
        api = make_api_stub()

        async def bounded_sleep(sec):
            await tracker(sec)
            assert 0 <= sec <= 65, f"unbounded wait on headerless 429: {sec}"
        orig_sleep = http_mod.asyncio.sleep
        http_mod.asyncio.sleep = bounded_sleep
        try:
            r = await api._request("get", "http://127.0.0.1/t")
        finally:
            http_mod.asyncio.sleep = orig_sleep
    finally:
        restore()
    assert r == {"data": ["ok"]}
    assert len(session.requests) == 2
    assert tracker.calls and all(0 <= s <= 65 for s in tracker.calls)


async def test_429_with_headers_waits_until_reset():
    now = int(time.time())
    reset_hdr = str(now + 5)
    responses = [
        dict(status=429, headers={"Ratelimit-Reset": reset_hdr, "X-Cache": "MISS"}),
        dict(payload={"data": ["ok"]}),
    ]
    session, restore = patch_transport(responses)
    tracker = FakeSleepTracker()
    import poolguy.http as http_mod
    try:
        api = make_api_stub()

        async def bounded_sleep(sec):
            await tracker(sec)
        orig_sleep = http_mod.asyncio.sleep
        http_mod.asyncio.sleep = bounded_sleep
        try:
            r = await api._request("get", "http://127.0.0.1/t")
        finally:
            http_mod.asyncio.sleep = orig_sleep
    finally:
        restore()
    assert r == {"data": ["ok"]}
    assert len(session.requests) == 2
    expected = max(int(reset_hdr) - int(time.time()) + 3, 0)
    assert abs(tracker.calls[0] - expected) <= 4


#=============================================================================================
# H-05: one transient validate error must not kill the refresher task
#=============================================================================================

async def test_refresher_survives_transient_validate_error(monkeypatch):
    from conftest import make_handler
    from poolguy.core.oauth import VALIDATE_INTERVAL_SECONDS
    handler = make_handler()
    handler._token = {"access_token": "tok", "requested_scopes": []}
    calls = {"n": 0}

    async def fake_validate():
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("transient validation error")
        return True, {"user_id": "9", "expires_in": 86400}
    handler._validate_auth = fake_validate

    sleeps = FakeSleepTracker()

    async def bounded_sleep(sec):
        await sleeps(sec)
        if len(sleeps.calls) >= 2:
            handler._running = False
    monkeypatch.setattr("asyncio.sleep", bounded_sleep)
    try:
        await handler._refresher()
    finally:
        pass
    assert calls["n"] == 2, "second validation iteration never ran"
    assert len(sleeps.calls) >= 1
    assert sleeps.calls[0] == VALIDATE_INTERVAL_SECONDS


#=============================================================================================
# M-01: send_chat must not POST an empty message
#=============================================================================================

class _ChatRecorder:
    def __init__(self):
        self.sent = []

    async def sendChatMessage(self, text, channel_id=None):
        self.sent.append(text)
        return [{"is_sent": True}]


async def test_long_spaceless_token_single_nonempty_send():
    from poolguy.twitch import TwitchBot
    bot = TwitchBot.__new__(TwitchBot)
    rec = _ChatRecorder()
    bot.http = rec
    await bot.send_chat("x" * 450)
    assert len(rec.sent) == 1, f"expected exactly one send, got {rec.sent}"
    assert all(t and t.strip() for t in rec.sent)
    assert "".join(rec.sent).strip() == "x" * 450


async def test_clean_400char_word_single_send():
    from poolguy.twitch import TwitchBot
    bot = TwitchBot.__new__(TwitchBot)
    rec = _ChatRecorder()
    bot.http = rec
    await bot.send_chat("y" * 400)
    assert len(rec.sent) == 1, f"expected exactly one send, got {rec.sent}"
    assert all(t and t.strip() for t in rec.sent)
