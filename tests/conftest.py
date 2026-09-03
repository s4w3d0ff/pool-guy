import asyncio
from datetime import datetime, timedelta, timezone


class FakeStorage:
    """In-memory stand-in for SQLiteStorage (message dedup + token tables)."""

    def __init__(self):
        self.messages = {}
        self.tokens = {}
        self.queues = {}
        self.queries = []
        self.save_token_failures = 0

    async def query(self, table, where=None, params=()):
        self.queries.append((table, where, tuple(params)))
        if table == "eventsub_messages" and where == "message_id = ?":
            mid = params[0]
            return [{"message_id": mid}] if mid in self.messages else []
        return []

    async def insert(self, table, data, upsert=True):
        if table == "eventsub_messages":
            self.messages[data["message_id"]] = data.get("received_at")

    async def delete(self, table, where=None, params=()):
        pass

    async def save_token(self, name, token):
        if self.save_token_failures > 0:
            self.save_token_failures -= 1
            raise RuntimeError("simulated storage failure")
        self.tokens[name] = dict(token)

    async def get_token(self, name):
        row = self.tokens.get(name)
        return dict(row) if row else None

    async def load_token(self, name):
        return await self.get_token(name)


def make_api():
    from poolguy.twitchapi import TwitchApi
    api = TwitchApi.__new__(TwitchApi)
    api.user_id = "12345"
    api.client_id = "client-abc"
    api.storage = FakeStorage()
    return api


def make_ws():
    from poolguy.twitchws import TwitchWebsocket
    ws = TwitchWebsocket.__new__(TwitchWebsocket)
    ws._running = True
    ws._session_id = None
    ws.http = type("H", (), {"storage": FakeStorage()})()
    return ws


def make_handler(client_secret=None):
    from poolguy.core.oauth import TokenHandler
    storage = FakeStorage()
    handler = TokenHandler(
        client_id="client-abc",
        client_secret=client_secret,
        scopes=["moderator:manage:bans"],
        storage=storage,
    )
    return handler


def iso_offset(seconds):
    dt = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
