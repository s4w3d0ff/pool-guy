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
from collections import OrderedDict
from urllib.parse import urlparse, urlencode
from datetime import datetime

# Third-party imports
import websockets
import aiohttp
from dateutil import parser

closeBrowser = """
<!DOCTYPE html>
<html lang="en">
    <head>
        <script>
            function closeWindow() {
                window.close();
            };
        </script>
    </head>
    <body>
        <button id="closeButton" onclick="closeWindow()">Close Window</button>
        <script>
            document.getElementById("closeButton").click();
        </script>
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

def loadJSON(filename):
    """ Load json file """
    with open(filename, 'r') as f:
        out = json.load(f)
        logger.debug(f"[loadJSON] {filename}")
        return out

def saveJSON(data, filename):
    """ Save data as json to a file """
    with open(filename, 'w') as f:
        out = json.dump(data, f, indent=4)
        logger.debug(f"[saveJSON] {filename}")
        return out

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
        
