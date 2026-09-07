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

H02_VERBS = ("patch", "put", "delete")


async def test_non_getpost_methods_return_subscriptable_data():
    for verb in H02_VERBS:
        session, restore = patch_transport(
            [dict(payload={"data": [{"verb": verb}], "total_cost": 0})]
        )
        try:
            api = make_api_stub()
            r = await api._request(verb, f"http://127.0.0.1/{verb}")
        finally:
            restore()
        assert isinstance(r, dict), f"{verb}: expected decoded dict, got {type(r)}"
        assert r["data"] == [{"verb": verb}]


#=============================================================================================
# H-03: store=True flag alert must persist through NotificationHandler.__call__
#=============================================================================================

async def test_flag_alert_persists_through_notification_handler(tmp_path):
    from poolguy.eventsub import Alert, AlertFactory, NotificationHandler
    from poolguy.core.storage import StorageFactory

    class FlagAlert(Alert):
        queue_skip = True
        store = True

        async def process(self):
            pass

    storage = StorageFactory.create_storage('sqlite', db_path=str(tmp_path / 'audit.db'))
    bot = type("B", (), {"storage": storage})()
    handler = NotificationHandler(bot, storage)
    AlertFactory.register_alert_class("audit_flag", FlagAlert)
    try:
        metadata = {
            "message_id": "flag-audit-1",
            "message_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        payload = {
            "subscription": {"type": "audit_flag"},
            "event": {"broadcaster_user_id": "7"},
        }
        await handler(metadata, payload)
    finally:
        AlertFactory._alert_classes.pop("audit_flag", None)
    rows = await storage.query("audit_flag", where="message_id = ?", params=("flag-audit-1",))
    assert len(rows) == 1


async def test_custom_async_store_override_fires_once(tmp_path):
    from poolguy.eventsub import Alert, AlertFactory, NotificationHandler
    from poolguy.core.storage import StorageFactory

    calls = {"n": 0}

    class CustomAlert(Alert):
        queue_skip = True
        store = True

        async def process(self):
            pass

        async def store(self):
            calls["n"] += 1

    storage = StorageFactory.create_storage('sqlite', db_path=str(tmp_path / 'audit.db'))
    bot = type("B", (), {"storage": storage})()
    handler = NotificationHandler(bot, storage)
    AlertFactory.register_alert_class("audit_custom", CustomAlert)
    try:
        metadata = {
            "message_id": "custom-audit-1",
            "message_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        payload = {"subscription": {"type": "audit_custom"}, "event": {}}
        await handler(metadata, payload)
    finally:
        AlertFactory._alert_classes.pop("audit_custom", None)
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


async def test_multiword_message_chunks_without_empty_sends():
    from poolguy.twitch import TwitchBot
    bot = TwitchBot.__new__(TwitchBot)
    rec = _ChatRecorder()
    bot.http = rec
    msg = "a" * 300 + " " + "b" * 250
    await bot.send_chat(msg)
    assert len(rec.sent) == 2, f"expected two chunks, got {rec.sent}"
    assert all(t and t.strip() for t in rec.sent), "empty send emitted during chunking"
    assert "".join(t.strip() for t in rec.sent) == msg.replace(" ", "")

    short = "a" * 10 + " " + "b" * 10
    await bot.send_chat(short)
    assert len(rec.sent) == 3, f"short message should add one more send, got {rec.sent}"


#=============================================================================================
# M-03: stop/restart on a never-started WebServer must not raise
#=============================================================================================

def _free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def test_webserver_stop_and_restart_safe_unstarted():
    from poolguy.core.webserver import WebServer
    srv = WebServer(host="127.0.0.1", port=_free_port())
    await srv.stop()
    assert not srv.is_running()
    await srv.restart()
    assert srv.is_running()
    await srv.stop()
    assert not srv.is_running()


async def test_webserver_normal_cycle_start_stop_restart_stop():
    from poolguy.core.webserver import WebServer
    srv = WebServer(host="127.0.0.1", port=_free_port())
    await srv.start()
    assert srv.is_running()
    await srv.stop()
    assert not srv.is_running()
    await srv.restart()
    assert srv.is_running()
    await srv.stop()
    assert not srv.is_running()


#=============================================================================================
# M-04: storage factory must fail loudly on unknown types
#=============================================================================================

def test_storage_factory_rejects_unknown_types():
    import pytest as _pytest
    from poolguy.core.storage import StorageFactory, SQLiteStorage
    with _pytest.raises(ValueError, match="postgres"):
        StorageFactory.create_storage("postgres")
    assert isinstance(StorageFactory.create_storage('sqlite'), SQLiteStorage)


def test_storage_instance_bypasses_factory():
    from poolguy.http import RequestHandler
    custom = type("C", (), {})()
    handler = RequestHandler(
        client_id="client-test",
        redirect_uri="http://localhost:5000/callback",
        scopes=["user:read:chat"],
        storage=custom,
    )
    assert handler.storage is custom


#=============================================================================================
# L-02: max_reconnect must cap consecutive failed connects in run()
#=============================================================================================

class _ModProxy:
    def __init__(self, real, overrides):
        self._real = real
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._real, name)


def _make_ws(max_reconnect=3):
    from conftest import FakeStorage
    from poolguy.twitchws import TwitchWebsocket
    http_stub = type("H", (), {"storage": FakeStorage(), "user_id": "9"})()
    ws = TwitchWebsocket(None, channels={}, http=http_stub, max_reconnect=max_reconnect)

    async def _no_start(paused=False):
        pass

    ws.notification_handler.start = _no_start
    return ws


async def test_run_gives_up_after_max_reconnect_failed_connects(monkeypatch, caplog):
    import asyncio as _asyncio
    import logging
    import poolguy.twitchws as twitchws_mod
    from conftest import FakeStorage

    ws = _make_ws(max_reconnect=3)
    attempts = []
    sleeps = []

    async def boom(url):
        attempts.append(1)
        raise ConnectionRefusedError("stub connect failure")

    async def no_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(twitchws_mod, "websockets", _ModProxy(twitchws_mod.websockets, {"connect": boom}))
    monkeypatch.setattr(twitchws_mod, "asyncio", _ModProxy(_asyncio, {"sleep": no_sleep}))

    with caplog.at_level(logging.ERROR, logger="poolguy.twitchws"):
        await ws.run()

    assert len(attempts) == 3, f"expected exactly 3 connect attempts, got {len(attempts)}"
    assert "Giving up" in caplog.text, "no give-up error log was emitted"
    assert not ws._running


async def test_run_recovers_when_failures_stay_under_cap(monkeypatch, caplog):
    import asyncio as _asyncio
    import logging
    import poolguy.twitchws as twitchws_mod

    ws = _make_ws(max_reconnect=3)
    attempts = []
    sleeps = []
    loop_calls = {"n": 0}

    async def flaky(url):
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionRefusedError("stub connect failure")

    async def no_sleep(seconds):
        sleeps.append(seconds)

    async def _loop_once():
        loop_calls["n"] += 1
        ws._running = False

    monkeypatch.setattr(twitchws_mod, "websockets", _ModProxy(twitchws_mod.websockets, {"connect": flaky}))
    monkeypatch.setattr(twitchws_mod, "asyncio", _ModProxy(_asyncio, {"sleep": no_sleep}))
    ws._socket_loop = _loop_once

    with caplog.at_level(logging.ERROR, logger="poolguy.twitchws"):
        await ws.run()

    assert len(attempts) == 3, f"expected 2 failures then a recovered connect, got {len(attempts)}"
    assert loop_calls["n"] == 1, "socket loop was not reached after the successful reconnect"
    assert "Giving up" not in caplog.text, "run() gave up although failures stayed under the cap"
