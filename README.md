# Pool Guy 🏊‍♂️

A lightweight Twitch bot framework.

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

## Features

- EventSub websocket handling
- Priority queue for EventSub notifications
- Bot command and ratelimit decorators
- Framework to support multiple storage backends
- Rate limiting for commands

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
from poolguy import CommandBot, Alert, ColorLogger
from poolguy.twitch import command, rate_limit

logger = ColorLogger(__name__)


class ExampleBot(CommandBot):
    def __init__(self, *args, **kwargs):
        # Fetch sensitive data from environment variables
        import os
        client_id = os.getenv("CLIENT_ID")
        client_secret = os.getenv("CLIENT_SECRET")
        if not client_id or not client_secret:
            raise ValueError("Environment variables CLIENT_ID and CLIENT_SECRET are required")
        kwargs['client_id'] = client_id
        kwargs['client_secret'] = client_secret
        super().__init__(*args, **kwargs)

    async def send_chat(self, message, channel_id=None):
        r = await self.http.sendChatMessage(message, channel_id)
        if not r[0]['is_sent']:
            logger.error(f"Message not sent! Reason: {r[0]['drop_reason']}")

    @command(name="hi", aliases=["hello"])
    @rate_limit(calls=1, period=10, warn_cooldown=5)
    async def hi(self, user, channel, args):
        await self.send_chat(f"Hi, @{user['username']}", channel["broadcaster_id"])

    async def my_loop(self):
        logger.warning(f'my_loop started')
        while self.ws._connected:
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
        logger.info(f'[Chat] {self.data["chatter_user_name"]}: {self.data["message"]["text"]}', 'purple')


if __name__ == '__main__':
    import logging
    logging.basicConfig(
        format="%(asctime)s-%(levelname)s-[%(name)s] %(message)s",
        datefmt="%I:%M:%S%p",
        level=logging.INFO
    )

    cfg = {
      "redirect_uri": "http://localhost:5000/callback",
      "scopes": [
        "user:read:chat",
        "user:write:chat"
      ]
      "channels": {"channel.chat.message": None}, 
      "storage": "json",
      "browser": {
        "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
      },
      "max_retries": 30,
      "retry_delay": 10,
      "alert_objs": {'channel.chat.message': ChannelChatMessageAlert}
    }

    bot = ExampleBot(**cfg)
    asyncio.run(bot.start())
    
```
More fleshed out example: https://github.com/s4w3d0ff/deezbot
