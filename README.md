# Pool Guy 🏊‍♂️

A lightweight Twitch bot framework.

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

## Features

- EventSub websocket handling
- Priority queue for EventSub notifications
- Bot command and ratelimit decorators
- Pluggable storage factory (sqlite backend)
- On-demand OAuth callback listener: no webserver runs unless you inject one or an interactive token acquisition is in progress

## Limitations:
- Conduit/shards are not implimented
- Only uses "[OIDC authorization code grant flow](https://dev.twitch.tv/docs/authentication/#authentication-flows)" for oauth tokens


## Webserver model

pool-guy does not run a persistent webserver by default. The only HTTP surface it creates on its own is the OAuth callback listener: when an interactive token acquisition starts, pool-guy binds a short-lived server to exactly the host and port named in `redirect_uri`, waits for the authorization code, exchanges it, and tears the server down. If a valid token is already stored, no server ever comes up.

If you want your bot class to also serve its own routes (a dashboard or API), create a `WebServer` yourself and pass it through with the `webserver=` keyword argument:

```python
from poolguy import CommandBot
from poolguy.core.webserver import WebServer

app = WebServer('0.0.0.0', 5000)   # host, port; optional static_dirs / base_dir
bot = ExampleBot(
    client_id=os.getenv("CLIENT_ID"),
    client_secret=os.getenv("CLIENT_SECRET"),
    redirect_uri="http://localhost:8472/callback",
    webserver=app,
    ...
)
```

The injected server is used as-is (pool-guy never changes its host or port), and `bot.app` references it. You own starting it; `RequestHandler.shutdown()` stops it if it is still running when the bot shuts down. Without an injected webserver, `bot.app` stays `None` and no persistent HTTP surface exists at all.

Keep `redirect_uri` on a different port than any server you inject: a wildcard bind (for example `0.0.0.0`) holds every loopback address for that port, so a callback listener on the same port cannot bind while the injected server is up.


## Quick Setup

### Install from pypi:
```bash
pip install poolguy
```

### Install directly from git:
```bash
pip install git+https://github.com/s4w3d0ff/pool-guy.git
```

### Simple Command Bot:
```python
import asyncio
import logging
from poolguy import CommandBot, Alert, command, rate_limit

logger = logging.getLogger(__name__)


class ExampleBot(CommandBot):
    @command(name="hi", aliases=["hello"])
    @rate_limit(calls=1, period=10, warn_cooldown=5)
    async def hi(self, user, channel, args):
        await self.send_chat(f"Hi, @{user['username']}", channel["broadcaster_id"])

    async def my_loop(self):
        logger.warning(f'my_loop started')
        while self.ws._running:
            await asyncio.sleep(10)
            logger.info(f"loop")
        logger.warning(f'my_loop stopped')

    async def after_login(self):
        await self.add_task(self.my_loop)


class ChannelChatMessageAlert(Alert):
    """channel.chat.message"""
    queue_skip = True
    store = False
    priority = 3

    async def process(self):
        logger.debug(f'{self.data}')
        await self.bot.command_check(self.data)
        logger.info(f'[Chat] {self.data["chatter_user_name"]}: {self.data["message"]["text"]}')


if __name__ == '__main__':
    import os
    from rich.logging import RichHandler
    logging.basicConfig(
        format="%(message)s",
        datefmt="%X",
        level=logging.INFO,
        handlers=[RichHandler(rich_tracebacks=True)]
    )
    bot = ExampleBot(
        client_id=os.getenv("CLIENT_ID"),
        client_secret=os.getenv("CLIENT_SECRET"),
        redirect_uri="http://localhost:8472/callback",   # must match the URI registered in your Twitch dev console
        scopes=[
            "user:read:chat",
            "user:write:chat"
        ],
        channels={
            "channel.chat.message": None
        },
        browser={
            "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
        },
        alert_objs={
            "channel.chat.message": ChannelChatMessageAlert
        }
    )
    asyncio.run(bot.start())
    
```
More fleshed out example: https://github.com/s4w3d0ff/deezbot
