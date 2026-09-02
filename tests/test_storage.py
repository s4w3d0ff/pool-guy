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
