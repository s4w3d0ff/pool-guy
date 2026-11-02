import asyncio
import pathlib

from poolguy.core.storage import SQLiteStorage


async def test_query_missing_table_returns_empty(tmp_path):
    storage = SQLiteStorage(str(tmp_path / "fresh.db"))
    assert await storage.query("eventsub_messages") == []
    assert await storage.query("tokens", "name = ?", ("twitch",)) == []


async def test_load_queue_on_fresh_db_returns_none(tmp_path):
    storage = SQLiteStorage(str(tmp_path / "fresh.db"))
    assert await storage.load_queue("alerts") is None


async def test_insert_then_query_roundtrip(tmp_path):
    db_file = tmp_path / "roundtrip.db"
    storage = SQLiteStorage(str(db_file))
    await storage.insert(
        "eventsub_messages", {"message_id": "abc123", "received_at": 1.0}
    )
    rows = await storage.query("eventsub_messages", "message_id = ?", ("abc123",))
    assert len(rows) == 1
    assert rows[0]["message_id"] == "abc123"


async def test_queue_save_load_roundtrip(tmp_path):
    storage = SQLiteStorage(str(tmp_path / "queue.db"))
    await storage.save_queue("alerts", [{"message_id": "m1"}])
    assert await storage.load_queue("alerts") == [{"message_id": "m1"}]


async def test_token_save_load_roundtrip(tmp_path):
    storage = SQLiteStorage(str(tmp_path / "tokens.db"))
    token = {"access_token": "a", "refresh_token": "r", "expires_time": 1}
    await storage.save_token("twitch", token)
    assert await storage.load_token("twitch") == token


async def test_a_missing_token_loads_as_none(tmp_path):
    storage = SQLiteStorage(str(tmp_path / "missing.db"))
    assert await storage.load_token("spotify") is None


async def test_an_unreadable_token_loads_as_none(tmp_path):
    storage = SQLiteStorage(str(tmp_path / "broken.db"))
    await storage.insert("tokens", {"name": "spotify", "token_json": "{not json"})
    assert await storage.load_token("spotify") is None


async def test_token_methods_work_when_another_library_calls_them_by_keyword(tmp_path):
    """spotifio calls save_token(token=..., name=...): the same store serves both services."""
    storage = SQLiteStorage(str(tmp_path / "shared.db"))
    twitch = {"access_token": "twitch-token", "expires_time": 1}
    spotify = {"access_token": "spotify-token", "expires_in": 3600}
    await storage.save_token(name="twitch", token=twitch)
    await storage.save_token(token=spotify, name="spotify")
    assert await storage.load_token(name="twitch") == twitch
    assert await storage.load_token(name="spotify") == spotify
