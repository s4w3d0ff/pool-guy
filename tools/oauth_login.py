import asyncio
import logging
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if not os.environ.get("DISPLAY") and pathlib.Path("/tmp/.X11-unix/X1").exists():
    os.environ["DISPLAY"] = ":1"
sys.path.insert(0, str(ROOT))

from poolguy.core.oauth import TokenHandler  # noqa: E402
from poolguy.core.storage import SQLiteStorage  # noqa: E402

BROWSER = {"librewolf": "/usr/bin/librewolf"}
SCOPES = ["user:read:chat", "user:write:chat", "moderator:read:followers"]


def load_env():
    env_path = ROOT / ".env"
    return dict(line.split("=", 1) for line in env_path.read_text().strip().splitlines() if "=" in line)


async def main():
    env = load_env()
    handler = TokenHandler(
        client_id=env["TWITCH_CLIENT_ID"],
        client_secret=env.get("TWITCH_CLIENT_SECRET"),
        redirect_uri="http://localhost:8080/callback",
        scopes=SCOPES,
        storage=SQLiteStorage(str(ROOT / "db" / "twitch.db")),
        browser=dict(BROWSER),
    )
    token = await handler.get_token()
    print(f"login ok: user_id={handler.user_id} scopes={(token or {}).get('scope')}")
    await handler.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
