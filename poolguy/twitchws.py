import json
import sys
import copy
import asyncio
import websockets
import logging
import uuid
from abc import ABC, abstractmethod
from dateutil import parser
from collections import OrderedDict
from typing import List, Tuple, Dict, Any
from .twitchapi import TwitchApi

logger = logging.getLogger(__name__)

WSURL = "wss://eventsub.wss.twitch.tv/ws?keepalive_timeout_seconds=600"

# for current func name, specify 0 or no argument.
# for name of caller of current func, specify 1.
# for name of caller of caller of current func, specify 2. etc.
# https://stackoverflow.com/a/31615605/3389859
_func_name = lambda n=0: sys._getframe(n + 1).f_code.co_name

def convert2epoch(timestampstr):
    return parser.parse(timestampstr).timestamp()

class Alert(ABC):
    queue_skip = False
    priority = 3
    store = False
    
    def __init__(
            self, 
            bot: 'TwitchBot', # type: ignore
            message_id: str, 
            channel: str, 
            data: Any, 
            timestamp: float
        ):
        self.bot = bot
        self.message_id = message_id
        self.channel = channel
        self.data = copy.deepcopy(data)
        self.timestamp = timestamp

    @abstractmethod
    async def process(self):
        pass

    def to_dict(self):
        return {
            'message_id': self.message_id,
            'channel': self.channel,
            'data': copy.deepcopy(self.data),
            'timestamp': self.timestamp,
            'priority': self.priority
        }
    
    def __lt__(self, other):
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.timestamp < other.timestamp

    def __le__(self, other):
        if self.priority != other.priority:
            return self.priority <= other.priority
        return self.timestamp <= other.timestamp

    def __gt__(self, other):
        if self.priority != other.priority:
            return self.priority > other.priority
        return self.timestamp > other.timestamp

    def __ge__(self, other):
        if self.priority != other.priority:
            return self.priority >= other.priority
        return self.timestamp >= other.timestamp

    def __eq__(self, other):
        if not isinstance(other, Alert):
            return NotImplemented
        return (self.priority == other.priority and 
                self.timestamp == other.timestamp and 
                self.message_id == other.message_id)


class GenericAlert(Alert):
    """Generic alert class for handling unknown alert types."""
    queue_skip = True

    async def process(self):
        logger.warning(f"Processing generic alert for {self.channel} -> {self.message_id}")
        logger.debug(f"Data: {self.data}")
    
    async def store(self):
        out = {}
        for key, value in copy.deepcopy(self.data).items():
            if isinstance(value, list):
                out[key] = json.dumps(value)
            elif isinstance(value, dict):
                for k, v in copy.deepcopy(self.data[key]).items():
                    if isinstance(v, list) or isinstance(v, dict):
                        out[f'{key}_{k}'] = json.dumps(v)
                    else:
                        out[f'{key}_{k}'] = v
            else:
                out[key] = value
        out["timestamp"] = self.timestamp
        out["message_id"] = self.message_id
        await self.bot.storage.insert(
            self.bot.storage.channel_to_table(self.channel),
            out
        )

#=============================================================================================

class AlertFactory:
    """Factory class to create the appropriate Alert instance based on event type."""
    _alert_classes = {}

    @classmethod
    def register_alert_class(cls, channel, alert_class):
        """Register an alert class for a channel"""
        cls._alert_classes[channel] = alert_class
        logger.debug(f"Alert class registered: {channel} = {alert_class}")

    @staticmethod
    def create_alert(bot, message_id, channel, data, timestamp):
        """Create an appropriate Alert instance based on the alert type."""
        if channel in AlertFactory._alert_classes:
            return AlertFactory._alert_classes[channel](bot, message_id, channel, data, timestamp)
        else:
            logger.error(f"No Alert Class found for {channel}")
            return GenericAlert(bot, message_id, channel, data, timestamp)

#=============================================================================================

class AlertPriorityQueue(asyncio.PriorityQueue):
    """
    A PriorityQueue that allows viewing and removing specific alerts using unique identifiers.
    Can optionally persist its state to JSON storage.
    """
    def __init__(self, maxsize = 0, storage = None):
        super().__init__(maxsize=maxsize)
        self._id_map = {}  # Maps alert_id to (priority, alert)
        self.storage = storage

    async def _load_state(self, bot):
        if not self.storage:
            logger.warning("No storage configured for AlertPriorityQueue.")
            return False
        try:
            saved_items = await self.storage.load_queue("alerts")
        except:
            saved_items = []

        if not saved_items:
            return

        # Remove all current items from the queue and id_map
        while not self.empty():
            await super().get()
        self._id_map.clear()

        # Restore saved items
        for _alert in saved_items:
            alert = AlertFactory.create_alert(
                bot,
                _alert["message_id"],
                _alert["channel"],
                _alert["data"],
                _alert["timestamp"],
            )
            alert_id = str(uuid.uuid4())
            item = (alert.priority, alert)
            await super().put(item)
            self._id_map[alert_id] = item

    async def _save_state(self):
        if self.storage:
            await self.storage.save_queue(
                "alerts",
                [alert.to_dict() for _, alert in self._id_map.values()]
            )

    async def put(self, alert: 'Alert') -> str:
        """
        Put an item into the queue and track it in our ID map.
        Returns the unique identifier assigned to the item.
        """
        alert_id = str(uuid.uuid4())
        item = (alert.priority, alert)
        await super().put(item)
        self._id_map[alert_id] = item
        await self._save_state()
        return alert_id

    async def get(self) -> Tuple[str, 'Alert']:
        """
        Get an item from the queue and remove it from our ID map.
        Returns (alert_id, alert)
        """
        priority, alert = await super().get()
        # Find the alert_id corresponding to this alert instance and priority
        found_id = None
        for key, value in self._id_map.items():
            if value == (priority, alert):
                found_id = key
                break
        if found_id:
            del self._id_map[found_id]
        await self._save_state()
        return found_id, alert

    async def remove_by_id(self, alert_id: str) -> bool:
        """
        Remove a specific item from the queue using its identifier.
        Returns True if the item was found and removed, False otherwise.
        """
        if alert_id not in self._id_map:
            return False

        item_to_remove = self._id_map.pop(alert_id)

        # Rebuild the queue without the removed item
        temp_items = []
        while not self.empty():
            item = await super().get()
            if item != item_to_remove:
                temp_items.append(item)
        for item in temp_items:
            await super().put(item)
        await self._save_state()
        return True

    def get_contents(self) -> List[Dict[str, Any]]:
        """Return a list of current items in the queue as dictionaries."""
        # This will return alerts in arbitrary order, but always by id
        return [
            {"item_id": alert_id, **alert.to_dict()}
            for alert_id, (_, alert) in self._id_map.items()
        ]

    def __len__(self) -> int:
        return len(self._id_map)

#=============================================================================================

class NotificationHandler:
    def __init__(self, bot, storage):
        self.bot = bot
        self.storage = storage
        self._queue = AlertPriorityQueue(storage=self.storage)
        self._running = False
        self._paused = False
        self._task = None

    def register_alert_class(self, name, obj):
        AlertFactory.register_alert_class(name, obj)
        
    async def _loop(self):
        logger.debug(f"NotificationHandler._loop started!")
        self._running = True
        while self._running:
            try:
                if self._paused:
                    await asyncio.sleep(1)
                    continue
                _, alert = await asyncio.wait_for(self._queue.get(), timeout=1)
                await alert.process()
                self._queue.task_done()
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                self._running = False
            except:
                logger.exception("NotificationHandler._loop:\n")
        logger.warning(f"NotificationHandler._loop stopped!")

    async def start(self, paused=False):
        if paused:
            self._paused = True
        # attempt to load state from storage
        await self._queue._load_state(self.bot)
        # start the main loop
        self._task = asyncio.create_task(self._loop())
                
    async def shutdown(self):
        self._running = False
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def current_queue(self):
        """Returns a list of current items in the queue without removing them."""
        return self._queue.get_contents(), self._paused
    
    async def remove_from_queue(self, item_id):
        """Removes an item from the queue by its message_id."""
        await self._queue.remove_by_id(item_id)

    async def __call__(self, metadata, payload):
        event = {
            'message_id': metadata["message_id"],
            'channel': payload['subscription']['type'],
            'data': payload['event'],
            'timestamp': convert2epoch(metadata['message_timestamp'])
        }
        alert = AlertFactory.create_alert(bot=self.bot, **event.copy())
        if self.storage and alert.store and "test_" not in event["message_id"]:
            if asyncio.iscoroutinefunction(alert.store):
                await alert.store()
            else:
                alert.store()
        if not alert.queue_skip:
            await self._queue.put(alert)
        else:
            asyncio.create_task(alert.process())


#=============================================================================================
class MaxSizeDict(OrderedDict):
    """ OrderedDict subclass with a 'max_size' which restricts the len. 
    As items are added, the oldest items are removed to make room. """
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

#========================================================================================

class TwitchWebsocket:
    """ Handles EventSub Websocket connection and subscriptions """
    def __init__(self, bot, channels=None, max_reconnect=None, http=None, *args, **kwargs):
        self.http = http or TwitchApi(*args, **kwargs)
        self.channels = channels or {"channel.chat.message": [None]}
        self.max_reconnect = max_reconnect or 20
        self.notification_handler = NotificationHandler(bot, self.http.storage)
        self._socket = None
        self._connected = False
        self._running = False
        self._session_id = None
        self._seen_messages = MaxSizeDict(15)
        self._socket_task = None

    async def _socket_loop(self):
        self._socket = await websockets.connect(WSURL)
        logger.info(f"Connected to twitch websocket: {WSURL}")
        self._connected = True
        while self._connected and self._running:
            try:
                message = await self._socket.recv()
            except Exception as e:
                logger.error(f"Twitch websocket receiving error:\n {e}")
                self._connected = False
                continue
            try:
                asyncio.create_task(self.handle_message(json.loads(message)))
            except:
                logger.exception(f"Error handling twitch websocket message:\n{message}\n")
        logger.warning("Twitch websocket disconnected!")

    async def run(self, token=None, paused=False):
        self._running = True
        await self.notification_handler.start(paused=paused)
        if not self.http.user_id:
            await self.http.login(token)
        while self._running:
            try:
                self._session_id = None
                await self._socket_loop()
            except:
                logger.exception("Exception in socket loop:\n")

    async def close(self):
        self._running = False
        await self._socket.close()
        await self.http.shutdown()
        await self.notification_handler.shutdown()

    async def handle_session_reconnect(self, metadata, payload):
        logger.error("Twitch websocket needs to reconnect")
        new_websocket = await websockets.connect(payload['session']['reconnect_url'])
        try:
            logger.warning("Waiting for welcome message on new socket...")
            message = await new_websocket.recv()
            msg = json.loads(message)
            if msg["metadata"]["message_type"] == 'session_welcome':
                self._session_id = msg['payload']['session']['id']
                self._socket = new_websocket
                logger.error("New websocket connected!")
        except:
            logger.exception(f"Error during websocket reconnection:\n")
            self._connected = False
            await new_websocket.close()

    async def handle_session_welcome(self, metadata, payload):
        logger.info(f"Session welcome recieved")
        self._session_id = payload['session']['id']
        current_subs = await self.http.unsubAllEvents(self._session_id)
        if not current_subs:
            # subscribe to init channels
            for chan in self.channels:
                if isinstance(self.channels[chan], list):
                    for i in self.channels[chan]:
                        await self.http.createEventSub(chan, self._session_id, i)
                else:
                    await self.http.createEventSub(chan, self._session_id)
                await asyncio.sleep(0.2)
        logger.warning(f"Subscribed websocket to:\n{json.dumps(list(self.channels.keys()), indent=2)}")

    async def handle_message(self, message):
        meta = message["metadata"]
        logger.debug(f"{meta['message_type']}:\n{json.dumps(message, indent=2)}")
        if meta["message_id"] not in self._seen_messages:
            self._seen_messages[meta["message_id"]] = message
            match meta["message_type"]:
                case "session_welcome": 
                    await self.handle_session_welcome(meta, message["payload"])
                case "session_reconnect": 
                    await self.handle_session_reconnect(meta, message["payload"])
                    #asyncio.create_task(self.handle_session_reconnect(meta, message["payload"]))
                case "notification":
                    asyncio.create_task(self.notification_handler(meta, message["payload"]))
                case "session_keepalive":
                    pass
                case "close": 
                    await self.close()
                case _:
                    logger.error(f"Unexpected message in socket: [{meta['message_type']}]\n{json.dumps(message, indent=2)}")

    def add_alert_class(self, name, obj):
        """ Adds alert classes to the AlertFactory cache """
        self.notification_handler.register_alert_class(name, obj)

    async def create_event_sub(self, event, bid=None):
        await self.http.createEventSub(event, session_id=self._session_id, bid=bid)