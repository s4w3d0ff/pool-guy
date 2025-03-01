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

logger = logging.getLogger(__name__)

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
    """ OrderedDict subclass with a 'max_size' which restricts the len. As items are added, the oldest items are removed to make room. """
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
    """ threading.Thread subclass that saves the result of the function and returns the result with Thread.join() """
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