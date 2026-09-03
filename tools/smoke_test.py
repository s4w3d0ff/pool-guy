import asyncio
import logging
import os
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from poolguy import TwitchBot  # noqa: E402
from poolguy.core.storage import SQLiteStorage  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_FILE = os.environ.get("SMOKE_DB_FILE", str(ROOT / "db" / "twitch.db"))
BROADCASTER_ID = "REDACTED"
REQUIRED_SCOPES = ("user:read:chat", "user:write:chat")
SUB_DEADLINE_SECONDS = 10
KEEPALIVE_WINDOW_SECONDS = 90
CHAT_MESSAGE = "pool-guy smoke test, safe to ignore"
records = []


class CaptureHandler(logging.Handler):
    def emit(self, record):
        records.append(record.getMessage())


async def wait_sub_enabled(api, event):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        r = await api.getEventSubs()
        for sub in r["data"]:
            if sub["type"] == event and sub["status"] == "enabled":
                return sub
        await asyncio.sleep(2)
    return None


async def run_smoke():
    env_path = ROOT / ".env"
    env = dict(line.split("=", 1) for line in env_path.read_text().strip().splitlines() if "=" in line)

    storage = SQLiteStorage(DB_FILE)
    stored_token = await storage.load_token("twitch")
    if not stored_token:
        print(f"FAIL: no saved token at {DB_FILE}; run tools/oauth_login.py first")
        return 1

    bot = TwitchBot(
        client_id=env["TWITCH_CLIENT_ID"],
        client_secret=env.get("TWITCH_CLIENT_SECRET"),
        redirect_uri="http://localhost:8080/callback",
        scopes=list(REQUIRED_SCOPES),
        storage=storage,
        channels={"channel.chat.message": [BROADCASTER_ID]},
    )

    code = 1
    try:
        await asyncio.wait_for(bot.start(hold=False), timeout=120)
        print(f"login complete, user_id={bot.http.user_id}")

        ws = bot.ws
        welcome_deadline = time.monotonic() + 60
        while not (ws._session_id and tuple(bot.http.token._granted_scopes)) \
                and time.monotonic() < welcome_deadline:
            await asyncio.sleep(0.2)

        granted = tuple(bot.http.token._granted_scopes or ())
        missing = [s for s in REQUIRED_SCOPES if s not in granted]
        print(f"validate: scopes granted {list(granted)}")
        scope_ok = not missing
        if not scope_ok:
            print(f"FAIL: required scopes missing: {missing}")

        welcome_ok = bool(ws._session_id)
        print(f"ws welcome: session_id={ws._session_id}")

        sub = await wait_sub_enabled(bot.http, "channel.chat.message")
        deadline_elapsed = None
        for text in records:
            m = re.search(r"All required subscriptions created in (\d+\.\d+)s", text)
            if m:
                deadline_elapsed = float(m.group(1))
        subs_under_deadline = deadline_elapsed is not None and deadline_elapsed < SUB_DEADLINE_SECONDS
        print(f"subs-created-in {deadline_elapsed}s (limit {SUB_DEADLINE_SECONDS}s)")
        print(f"server-side sub: {sub['id'] if sub else 'never enabled'} condition={sub['condition'] if sub else '-'}")

        await asyncio.sleep(KEEPALIVE_WINDOW_SECONDS)
        socket_closed = ws._socket is None or not ws._running
        print(f"keepalive window: {KEEPALIVE_WINDOW_SECONDS}s, socket still connected={not socket_closed}")

        r = await bot.http.sendChatMessage(CHAT_MESSAGE, BROADCASTER_ID)
        sent_ok = bool(r[0]["is_sent"])
        print(f"chat roundtrip: is_sent={sent_ok}" + ("" if sent_ok else f" drop_reason={r[0].get('drop_reason')}"))

        code = 0 if (scope_ok and welcome_ok and sub is not None and subs_under_deadline
                     and not socket_closed and sent_ok) else 1
    except asyncio.TimeoutError:
        print("FAIL: bot did not reach logged-in state within timeout")
    finally:
        await bot.shutdown()
    return code


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[CaptureHandler(), logging.StreamHandler()])
    return asyncio.run(run_smoke())


if __name__ == "__main__":
    sys.exit(main())
