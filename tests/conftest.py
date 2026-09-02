import asyncio
import json
import re
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest


API_PORT = 8000
WS_PORT = 8090
MOCK_API_PREFIX = f"http://127.0.0.1:{API_PORT}/mock"
MOCK_WS_URL = f"ws://127.0.0.1:{WS_PORT}/ws"
DEFAULT_SCOPES = ("moderator:read:followers", "user:read:email")


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
    from poolguy.twitchapi import TwitchApi, apiEndpoints
    api = TwitchApi.__new__(TwitchApi)
    api.user_id = "12345"
    api.client_id = "client-abc"
    api.storage = FakeStorage()
    api.apiEndpoints = dict(apiEndpoints)
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


_OWN_SERVER_PATTERNS = (
    re.compile(r"twitch\s+mock-api\s+start\s+-p\s+\d+"),
    re.compile(r"twitch\s+event\s+websocket\s+start-server.*-p\s+\d+"),
)


def _http_json(url, method="GET", headers=None):
    req = urllib.request.Request(url, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def _port_in_use(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _kill_own_stale_servers():
    try:
        out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout
    except (OSError, subprocess.SubprocessError):
        return
    for line in out.splitlines()[1:]:
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        pid, cmdline = parts
        if any(p.search(cmdline) for p in _OWN_SERVER_PATTERNS):
            subprocess.run(["kill", pid], capture_output=True)


def _wait_http(url, timeout=30.0):
    deadline = time.monotonic() + timeout
    while True:
        try:
            return _http_json(url)
        except Exception:
            if time.monotonic() > deadline:
                raise RuntimeError(f"twitch-cli mock server never became healthy at {url}")
            time.sleep(0.5)


def _wait_tcp(port, timeout=30.0):
    deadline = time.monotonic() + timeout
    while True:
        if _port_in_use(port):
            return
        if time.monotonic() > deadline:
            raise RuntimeError(f"twitch-cli mock ws server never came up on port {port}")
        time.sleep(0.5)


@pytest.fixture(scope="session")
def mock_servers(tmp_path_factory):
    _kill_own_stale_servers()
    blocked = [p for p in (API_PORT, WS_PORT) if _port_in_use(p)]
    if blocked:
        raise RuntimeError(f"ports {blocked} still occupied after cleaning our own stale servers; stop them manually")
    gen = subprocess.run(
        ["twitch", "mock-api", "generate", "-c", "20"],
        capture_output=True, text=True, timeout=180,
    )
    if gen.returncode != 0:
        raise RuntimeError(f"twitch mock-api generate failed:\n{(gen.stdout or '') + (gen.stderr or '')}")
    log_api = tmp_path_factory.mktemp("mockapi") / "server.log"
    log_ws = tmp_path_factory.mktemp("mockws") / "server.log"
    with open(log_api, "wb") as fh_api, open(log_ws, "wb") as fh_ws:
        api = subprocess.Popen(
            ["twitch", "mock-api", "start", "-p", str(API_PORT)],
            stdout=fh_api, stderr=subprocess.STDOUT,
        )
        ws = subprocess.Popen(
            ["twitch", "event", "websocket", "start-server", "-p", str(WS_PORT)],
            stdout=fh_ws, stderr=subprocess.STDOUT,
        )
    try:
        _wait_http(f"http://127.0.0.1:{API_PORT}/units/clients")
        _wait_tcp(WS_PORT)
    except Exception:
        api.terminate()
        ws.terminate()
        raise
    yield {"api": api, "ws": ws}
    for proc in (api, ws):
        proc.terminate()
    deadline = time.monotonic() + 10
    for proc in (api, ws):
        try:
            proc.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            proc.kill()
    for proc in (api, ws):
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def mock_api_prefix():
    return MOCK_API_PREFIX


@pytest.fixture(scope="session")
def mock_ws_url():
    return MOCK_WS_URL


@pytest.fixture(scope="session")
def mock_units(mock_servers):
    base = f"http://127.0.0.1:{API_PORT}"
    clients = _http_json(base + "/units/clients")["data"]
    client = next((c for c in clients if not c.get("IsExtension")), clients[0])
    users = _http_json(base + "/units/users?first=100")["data"]
    partners = [u for u in users if u.get("broadcaster_type") == "partner"]
    default_partner = max(partners, key=lambda u: int(u.get("view_count", 0)) or 0)
    token = _mock_user_token(client, default_partner["id"], " ".join(DEFAULT_SCOPES))
    totals = {}
    for partner in partners:
        req = urllib.request.Request(
            base + f"/mock/channels/followers?broadcaster_id={partner['id']}&first=1"
        )
        req.add_header("Authorization", "Bearer " + token)
        req.add_header("Client-ID", client["ID"])
        with urllib.request.urlopen(req, timeout=10) as resp:
            totals[partner["id"]] = json.load(resp)["total"]
    rich_partner = max(partners, key=lambda u: totals[u["id"]])
    return {
        "client": client,
        "users": users,
        "partners": partners,
        "default_partner": default_partner,
        "rich_partner": rich_partner,
        "follower_totals": totals,
    }


def _mock_user_token(client, user_id, scopes):
    qs = urllib.parse.urlencode({
        "client_id": client["ID"],
        "client_secret": client["Secret"],
        "grant_type": "user_token",
        "user_id": user_id,
        "scope": scopes,
    })
    req = urllib.request.Request(f"http://127.0.0.1:{API_PORT}/auth/authorize?{qs}", method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)["access_token"]


@pytest.fixture(scope="session")
def mock_token(mock_units):
    def issue(user_id=None, scopes=None):
        client = mock_units["client"]
        uid = user_id or mock_units["default_partner"]["id"]
        scope_str = " ".join(scopes) if scopes else " ".join(DEFAULT_SCOPES)
        return _mock_user_token(client, uid, scope_str)
    return issue

