# Pool Guy 🏊‍♂️

A lightweight Twitch bot framework with event subscription and alert handling capabilities.

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

## 🚀 Features

- Event subscription handling
- Custom alert system
- Twitch chat command integration
- WebSocket-based real-time updates
- Support for multiple storage backends (MongoDB, SQLite)
- Customizable command prefix system
- Rate limiting for commands

## 🛠️ Quick Setup


### Install directly from git:
```bash
pip install git+https://github.com/s4w3d0ff/pool-guy.git
```

### Create a configuration file (e.g., config.json):
```json
{
  "http_config": {
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uri": "http://localhost:5000/callback",
    "scopes": [
      "user:read:chat",
      "user:write:chat"
    ]
  },
  "ws_config": {
      "channels": {"channel.chat.message": [null]}, 
      "queue_skip": ["channel.chat.message"], 
      "storage_type": "json"
  },
  "max_retries": 30,
  "retry_delay": 10,
  "login_browser": {
    "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
  }
}
```

### Simple Command Bot:
```python
from poolguy.utils import asyncio
from poolguy.utils import loadJSON, ctxt
from poolguy import CommandBot, Alert, ColorLogger, cmd_rate_limit

logger = ColorLogger(__name__)

class ChannelChatMessageAlert(Alert):
    """channel.chat.message"""
    async def process(self):
        logger.debug(f'{self.data}')
        text = self.data["message"]["text"]
        user = {
            "user_id": self.data["chatter_user_id"], 
            "username": self.data["chatter_user_name"]
            }
        channel = {
            "broadcaster_id": self.data["broadcaster_user_id"],
            "broadcaster_user_name": self.data["broadcaster_user_name"]
            }
        logger.info(f'[Chat] {user["username"]}: {text}', 'purple')
        if str(user["user_id"]) == str(self.bot.http.user_id):
            logger.debug(f'Own message ignored')
            return
        if self.data["source_broadcaster_user_id"]:
            logger.debug(f'Shared chat message ignored')
            return
        await self.bot.command_check(text, user, channel)

class ExampleBot(CommandBot):
    def __init__(self, *args, **kwargs):
        """
        # Fetch sensitive data from environment variables
        import os
        client_id = os.getenv("CLIENT_ID")
        client_secret = os.getenv("CLIENT_SECRET")
        if not client_id or not client_secret:
            raise ValueError("Environment variables CLIENT_ID and CLIENT_SECRET are required")
        kwargs['http_config']['client_id'] = client_id
        kwargs['http_config']['client_secret'] = client_secret
        """
        super().__init__(*args, **kwargs)

    async def send_chat(self, message, channel_id=None):
        r = await self.http.sendChatMessage(message, channel_id)
        if not r[0]['is_sent']:
            logger.error(f"Message not sent! Reason: {r[0]['drop_reason']}")

    @cmd_rate_limit(calls=1, period=10)
    async def cmd_hi(self, user, channel, args):
        await self.send_chat(f"Hi, @{user['username']}", channel["broadcaster_id"])

    async def my_loop(self):
        logger.warning(f'my_loop started')
        while self.ws.connected:
            await asyncio.sleep(10)
        logger.warning(f'my_loop stopped')

    async def after_login(self):
        await self.add_task(self.my_loop)


if __name__ == '__main__':
    import logging
    fmat = ctxt('%(asctime)s', 'yellow', style='d') + '-%(levelname)s-' + ctxt('[%(name)s]', 'purple', style='d') + ctxt(' %(message)s', 'green', style='d')
    logging.basicConfig(
        format=fmat,
        datefmt="%I:%M:%S%p",
        level=logging.INFO
    )
    cfg = loadJSON('config.json')
    bot = ExampleBot(**cfg, alert_objs={'channel.chat.message': ChannelChatMessageAlert})
    asyncio.run(bot.start())
    
```
More fleshed out example: https://github.com/s4w3d0ff/deezbot
