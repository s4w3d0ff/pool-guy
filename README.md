# Pool Guy 🏊‍♂️

A lightweight Twitch bot framework.

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

## Features

- EventSub websocket handling
- Priority queue for EventSub notifications
- Bot command and ratelimit decorators
- Pluggable storage factory (sqlite backend)

## Limitations:
- Conduit/shards are not implimented
- Only uses "[OIDC authorization code grant flow](https://dev.twitch.tv/docs/authentication/#authentication-flows)" for oauth tokens


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
        redirect_uri="http://localhost:5000/callback",
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
## Sharing one storage with another service

`self.storage` (default: sqlite at `db/twitch.db`) keeps one token per name:
`save_token(name, token)` and `load_token(name)`. Another service that also needs an
OAuth token can share it by being handed the same object, in `before_login` (after
pool-guy built its storage, before the bot waits for the Twitch token):

```python
class ExampleBot(CommandBot):
    async def before_login(self):
        # self.storage already holds the "twitch" token; spotifio adds a "spotify" row
        self.spotify.token_handler.storage = self.storage
        await self.spotify.login()
```

spotifio calls `save_token`/`load_token` with keyword arguments only, so a store that
declares them in either order works unchanged. To use your own store instead of the
default sqlite one, pass `storage=` to the bot constructor.

spotifio calls `save_token`/`load_token` with keyword arguments only, so a store that
declares them in either order works unchanged. To use your own store instead of the
default sqlite one, pass `storage=` to the bot constructor.

More fleshed out example: https://github.com/s4w3d0ff/deezbot
