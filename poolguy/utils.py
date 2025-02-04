import logging
import json
import time
import random
import string
import os
import asyncio
import re
import webbrowser
import threading
from abc import ABC, abstractmethod
from collections import OrderedDict, defaultdict
from urllib.parse import urlparse, urlencode
from datetime import datetime, timedelta, timezone
from functools import wraps
# Third-party imports
import websockets
import aiofiles
import aiohttp
from aiohttp import web
from dateutil import parser

closeBrowser = """
<!DOCTYPE html>
<html lang="en">
<head>
    <script>function closeWindow() {window.close();};</script>
</head>
<body>
    <button id="closeButton" onclick="closeWindow()">Close Window</button>
    <script>document.getElementById("closeButton").click();</script>
</body>
</html>
"""
    
def ctxt(text, color='white', bg='black', style='n'):
    s = {
        'n': 0, #normal
        'b': 1, #bold
        'd': 2, #dim
        'i': 3, #italic
        'u': 4, #underline
        'f': 5  #flash
        }
    c = {'black': 30,'red': 31,'green': 32,'yellow': 33,'blue': 34,'purple': 35,'cyan': 36,'white': 37}
    bg_c = {'black': 40,'red': 41,'green': 42,'yellow': 43,'blue': 44,'purple': 45,'cyan': 46,'white': 47}
    scb = f"\x1b[{s[style]};{c[color]};{bg_c[bg]}m"
    clear = "\x1b[0m"
    return f"{scb}{text}{clear}"

class ColorLogger():
    def __init__(self, name=__name__):
        self._l = logging.getLogger(name)

    def debug(self, msg, c='cyan', b='black', s='d', *args, **kwargs):
        self._l.debug(ctxt(msg, c, b, s), *args, **kwargs)

    def info(self, msg, c='green', b='black', s='d', *args, **kwargs):
        self._l.info(ctxt(msg, c, b, s), *args, **kwargs)

    def warning(self, msg, c='blue', b='black', s='b', *args, **kwargs):
        self._l.warning(ctxt(msg, c, b, s), *args, **kwargs)

    def warn(self, msg, c='blue', b='black', s='b', *args, **kwargs):
        self._l.warning(ctxt(msg, c, b, s), *args, **kwargs)

    def error(self, msg, c='yellow', b='black', s='b', *args, **kwargs):
        self._l.error(ctxt(msg, c, b, s), *args, **kwargs)

    def critical(self, msg, c='red', b='white', s='f', *args, **kwargs):
        self._l.critical(ctxt(msg, c, b, s), *args, **kwargs)

logger = ColorLogger(__name__)


def randString(length=12):
    chars = string.ascii_letters + string.digits
    ranstr = ''.join(random.choice(chars) for _ in range(length))
    return ranstr

def updateFile(file_path, text):
    with open(file_path, "w") as file:
        file.write(text)
        logger.debug(f"[updateFile] {file_path}")

def loadJSON(filename):
    """ Load json file """
    with open(filename, 'r') as f:
        out = json.load(f)
        logger.debug(f"[loadJSON] {filename}")
        return out

def saveJSON(data, filename, str_fmat=False):
    """ Save data as json to a file """
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)
        logger.debug(f"[saveJSON] {filename}")

async def aioUpdateFile(file_path, text):
    async with aiofiles.open(file_path, "w") as file:
        await file.write(text)
        logger.debug(f"[aioUpdateFile] {file_path}")

async def aioLoadJSON(filename):
    async with aiofiles.open(filename, 'r') as file:
        content = await file.read()
        return json.loads(content)

async def aioSaveJSON(data, filename):
    async with aiofiles.open(filename, 'w') as file:
        await file.write(json.dumps(data, indent=4))
        
def delete_file_if_exists(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)

def convert2epoch(timestampstr):
    return parser.parse(timestampstr).timestamp()
    
def randomchars(length):
    return ''.join(random.choice(string.ascii_lowercase) for i in range(length))

def randomfile(dir):
    files = [f for f in os.listdir(dir)]
    return os.path.join(dir, random.choice(files))

class MaxSizeDict(OrderedDict):
    def __init__(self, max_size):
        super().__init__()
        self.max_size = max_size
    
    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        else:
            if len(self) >= self.max_size:
                self.popitem(last=False)
        super().__setitem__(key, value)


class ThreadWithReturn(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._return = None
        self._exception = None

    def run(self):
        try:
            if self._target is not None:
                self._return = self._target(*self._args, **self._kwargs)
        except Exception as e:
            self._exception = e

    def join(self, timeout=None):
        super().join(timeout)
        if self._exception:
            raise self._exception
        return self._return


def cmd_rate_limit(calls=2, period=10, warn_cooldown=5):
    """
    Decorator to rate limit commands per user
    
    Args:
        calls (int): Number of allowed calls
        period (float): Time period in seconds
        warn_cooldown (int): Time between warning messages
        
    Example:
        @cmd_rate_limit(calls=1, period=30)  # Allow 1 call every 30 seconds per user
        async def cmd_somecommand(self, user, channel, args):
            pass
    """
    def decorator(func):
        if not hasattr(func, '_rate_limit_state'):
            func._rate_limit_state = defaultdict(lambda: {"calls": [], "last_warning": 0})
        @wraps(func)
        async def wrapper(self, user, channel, args):
            current_time = time.time()
            user_id = user['user_id']
            state = func._rate_limit_state[user_id]
            # Clean up old calls
            state['calls'] = [t for t in state['calls'] if current_time - t < period]
            # Check if user has exceeded rate limit
            if len(state['calls']) >= calls:
                # Only send warning message every "warn_cooldown" seconds to prevent spam
                if current_time - state['last_warning'] > warn_cooldown:
                    wait_time = period - (current_time - state['calls'][0])
                    await self.http.sendChatMessage(
                        f"@{user['username']} Please wait {wait_time:.1f}s before using this command again.",
                        broadcaster_id=channel["broadcaster_id"]
                    )
                    state['last_warning'] = current_time
                return
            # Add current call to the list
            state['calls'].append(current_time)
            # Execute the command
            return await func(self, user, channel, args)
        return wrapper
    return decorator