"""Message dedup: repeated message_id skipped, replay window enforced."""
from conftest import make_ws, iso_offset, FakeStorage


def msg(mid, ts=None):
    meta = {"message_type": "notification", "message_id": mid}
    if ts is not None:
        meta["message_timestamp"] = ts
    return {"metadata": meta, "payload": {}}


async def test_fresh_message_marked_seen():
    ws = make_ws()
    m = msg("m1")
    assert await ws._is_duplicate(m["metadata"]) is False
    await ws._mark_seen(m["metadata"])
    assert "m1" in ws.http.storage.messages


async def test_repeated_message_id_skipped():
    ws = make_ws()
    m = msg("dup-1")
    assert await ws._is_duplicate(m["metadata"]) is False
    await ws._mark_seen(m["metadata"])
    assert await ws._is_duplicate(m["metadata"]) is True


async def test_duplicate_survives_across_instances_with_shared_storage():
    storage = FakeStorage()
    ws1 = make_ws()
    ws2 = make_ws()
    ws1.http.storage = storage
    ws2.http.storage = storage

    m = msg("persist-1")
    assert await ws1._is_duplicate(m["metadata"]) is False
    await ws1._mark_seen(m["metadata"])
    assert await ws2._is_duplicate(m["metadata"]) is True


async def test_message_older_than_replay_window_dropped():
    from poolguy.twitchws import REPLAY_WINDOW_SECONDS
    ws = make_ws()
    old_ts = iso_offset(-(REPLAY_WINDOW_SECONDS + 30))
    m = msg("replay-1", ts=old_ts)
    assert await ws._is_duplicate(m["metadata"]) is True


async def test_fresh_timestamp_accepted():
    from poolguy.twitchws import REPLAY_WINDOW_SECONDS
    ws = make_ws()
    fresh_ts = iso_offset(-(REPLAY_WINDOW_SECONDS // 2))
    m = msg("fresh-1", ts=fresh_ts)
    assert await ws._is_duplicate(m["metadata"]) is False


async def test_mark_seen_prunes_old_rows():
    ws = make_ws()
    deleted = []

    async def fake_delete(table, where=None, params=()):
        deleted.append((table, where))

    ws.http.storage.delete = fake_delete
    await ws._mark_seen(msg("prune-1")["metadata"])
    assert ("eventsub_messages", "received_at < ?") in deleted


async def test_message_without_id_not_deduped():
    ws = make_ws()
    meta = {"message_type": "notification"}
    assert await ws._is_duplicate(meta) is False
