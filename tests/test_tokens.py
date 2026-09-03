"""Token lifecycle: rotation rules, bounded waits, startup validation."""
import asyncio
import json
import time

from conftest import make_handler


async def test_rotation_replaces_stored_refresh_token():
    handler = make_handler(client_secret="sec")
    handler._token = {"access_token": "old-at", "refresh_token": "old-rt"}
    merged = handler._merge_token({
        "access_token": "new-at",
        "refresh_token": "rotated-rt",
        "expires_in": 3600,
        "scope": "a b",
    })
    assert merged["refresh_token"] == "rotated-rt"


async def test_confidential_client_keeps_old_refresh_token_when_none_returned():
    handler = make_handler(client_secret="sec")
    handler._token = {"access_token": "old-at", "refresh_token": "old-rt"}
    merged = handler._merge_token({"access_token": "new-at", "expires_in": 3600})
    assert merged["refresh_token"] == "old-rt"


async def test_public_client_missing_rotation_marks_grant_dead():
    handler = make_handler(client_secret=None)
    handler._token = {"access_token": "old-at", "refresh_token": "old-rt"}
    before = time.time()
    merged = handler._merge_token({"access_token": "new-at", "expires_in": 3600})
    assert merged["refresh_token"] == ""
    assert merged["refresh_token_expires_at"] <= before + 1


async def test_public_client_rotated_token_gets_30day_ttl():
    handler = make_handler(client_secret=None)
    merged = handler._merge_token({
        "access_token": "new-at",
        "refresh_token": "rot-1",
        "expires_in": 3600,
    })
    assert merged["refresh_token_expires_at"] > time.time() + 2_591_000


async def test_refresh_event_set_when_storage_save_raises(monkeypatch):
    import poolguy.core.oauth as oauthmod
    handler = make_handler(client_secret="sec")
    handler._token = {"access_token": "keep-me", "refresh_token": "rt-1"}
    handler.storage.save_token_failures = 99

    async def failing_request(headers, data):
        try:
            await handler.storage.save_token("twitch", {})
            return None
        except RuntimeError as e:
            raise RuntimeError(f"save failed: {e}")

    handler._token_request = failing_request
    new_token_calls = []

    async def fake_new_token():
        new_token_calls.append(1)

    monkeypatch.setattr(handler, "_get_new_token", fake_new_token)
    sleeps = []

    async def record_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(oauthmod.asyncio, "sleep", record_sleep)

    await handler._refresh_with_backoff()

    assert handler._refresh_event.is_set(), "event must be set even when storage save raises"
    assert len(sleeps) == 4, f"5 attempts => 4 backoff sleeps, got {len(sleeps)}"
    bases = [s for s in sleeps]
    assert all(b >= 10 * (2 ** i) - 1 for i, b in enumerate(bases)), bases
    assert new_token_calls == [1], "interactive re-auth only after backoff exhaustion"
    assert handler._token["access_token"] == "keep-me", "old token kept during failures"


async def test_public_client_dead_grant_breaks_backoff_early(monkeypatch):
    import poolguy.core.oauth as oauthmod
    handler = make_handler(client_secret=None)
    handler._token = {
        "access_token": "stale",
        "refresh_token": "",
        "refresh_token_expires_at": time.time() - 1,
    }

    attempts = []

    async def failing_request(headers, data):
        attempts.append(1)
        raise RuntimeError("nope")

    handler._token_request = failing_request
    monkeypatch.setattr(handler, "_get_new_token", lambda: _noop())

    sleeps = []

    async def record_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(oauthmod.asyncio, "sleep", record_sleep)

    await handler._refresh_with_backoff()
    assert attempts == [1], f"dead public grant must break after first failure, got {len(attempts)}"
    assert sleeps == []


async def _noop():
    return None


async def test_startup_validation_revoked_token_takes_reauth_path():
    handler = make_handler(client_secret="sec")
    stored = {"access_token": "revoked-at", "refresh_token": "rt", "requested_scopes": ["moderator:manage:bans"]}
    await handler.storage.save_token("twitch", dict(stored))

    events = []
    validate_results = iter([
        (False, {"status": 401}),
        (True, {"user_id": "u9", "expires_in": 3600, "scopes": ["moderator:manage:bans"]}),
        (True, {"user_id": "u9", "expires_in": 3600, "scopes": ["moderator:manage:bans"]}),
    ])

    async def fake_validate():
        result = next(validate_results)
        events.append(f"validate:{result[0]}")
        return result

    reauths = []

    async def fake_new_token():
        reauths.append(1)
        events.append("reauth")
        handler._token = {"access_token": "fresh-at", "refresh_token": "rt2"}
        return handler._token

    handler._validate_auth = fake_validate
    handler._get_new_token = fake_new_token

    await handler._login()

    assert events == ["validate:False", "reauth", "validate:True"], events
    assert reauths == [1]
    assert handler.user_id == "u9"
    assert handler._token["access_token"] == "fresh-at"
    await handler.stop()


async def test_get_token_wait_bounded_under_slow_storage():
    handler = make_handler(client_secret="sec")
    stored = {"access_token": "ok-at", "refresh_token": "rt", "requested_scopes": ["moderator:manage:bans"]}
    await handler.storage.save_token("twitch", dict(stored))

    async def slow_validate():
        await asyncio.sleep(0.3)
        return (True, {"user_id": "u1", "expires_in": 7200, "scopes": ["moderator:manage:bans"]})

    handler._validate_auth = slow_validate

    started = time.monotonic()
    token = await asyncio.wait_for(handler.get_token(), timeout=5)
    elapsed = time.monotonic() - started
    assert token["access_token"] == "ok-at"
    assert elapsed < 3, f"get_token blocked too long: {elapsed:.2f}s"
    await handler.stop()


async def test_app_token_grant_against_mock_auth_endpoint(mock_units):
    handler = make_handler(
        client_secret=mock_units["client"]["Secret"],
    )
    handler.client_id = mock_units["client"]["ID"]
    handler.token_endpoint = f"http://127.0.0.1:8000/auth/token"

    token = await handler.get_app_token()

    assert token.get("access_token"), json.dumps(token)
    assert token["token_type"] == "app"
    stored = await handler.storage.load_token("twitch_app")
    assert stored and stored.get("access_token") == token["access_token"]

