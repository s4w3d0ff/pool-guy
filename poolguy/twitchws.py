from .utils import json, asyncio, websockets
from .utils import MaxSizeDict, ColorLogger, ABC
from .utils import convert2epoch, abstractmethod
from .twitchapi import TwitchApi
from typing import List, Tuple, Any

logger = ColorLogger(__name__)

websocketURL = "wss://eventsub.wss.twitch.tv/ws?keepalive_timeout_seconds=600"

class TwitchWebsocket:
    """ Handles EventSub Websocket connection and subscriptions """
    def __init__(self, bot, channels={"channel.chat.message": [None]}, http=None, *args, **kwargs):
        self.http = http or TwitchApi(*args, **kwargs)
        self.channels = channels
        self.notification_handler = NotificationHandler(bot, self.http.storage)
        self._socket = None
        self._connected = False
        self._session_id = None
        self._seen_messages = MaxSizeDict(30)
        self._socket_task = None
        self._disconnect_event = asyncio.Event()

    async def _socket_loop(self):
        self._socket = await websockets.connect(websocketURL)
        self._connected = True
        self._disconnect_event.clear()
        logger.debug(f"Connecting Websocket: {websocketURL}")
        while self._connected:
            try:
                message = await self._socket.recv()
                await self.handle_message(message)
            except websockets.exceptions.ConnectionClosed as e:
                logger.error(f"WebSocket connection closed: {e}")
                break
            except Exception as e:
                logger.error(f"[socket_loop] {e}")
                break
        try:
            await self._socket.close()
        except:
            pass
        self._connected = False
        self._disconnect_event.set()
        logger.warning(f"Websocket connection closed...")

    async def run(self, token=None):
        await self.notification_handler.start()
        if not self.http.user_id:
            await self.http.login(token)
        logger.info(f"Clearing orphaned event subs")
        await self.http.unsubAllEvents()
        if not self._socket_task:
            self._socket_task = asyncio.create_task(self._socket_loop())

    async def close(self):
        self._connected = False
        self._socket_task.cancel()
        try:
            await self._socket_task
        except asyncio.CancelledError:
            pass
        await self.http.shutdown()
        await self.notification_handler.shutdown()

    async def handle_session_welcome(self, metadata, payload):
        logger.info(f"Session welcome recieved")
        if not self._session_id: # incase multiple welcome messages are recieved
            self._session_id = payload['session']['id']
            logger.debug(f"{self._session_id = }")
            # subscribe to init channels
            for chan in self.channels:
                if isinstance(self.channels[chan], list):
                    for i in self.channels[chan]:
                        await self.http.createEventSub(chan, self._session_id, i)
                else:
                    await self.http.createEventSub(chan, self._session_id)
                await asyncio.sleep(0.2)
            logger.warning(f"Subscribed websocket to:\n{json.dumps(list(self.channels.keys()), indent=2)}")

    async def handle_session_reconnect(self, metadata, payload):
        logger.error("Websocket needs to reconnect")
        new_websocket = await websockets.connect(payload['session']['reconnect_url'])
        try:
            welcome = None
            logger.warning("Waiting for welcome message on new socket...")
            while not welcome:
                message = await new_websocket.recv()
                msg = json.loads(message)
                if msg["metadata"]["message_type"] == 'session_welcome':
                    welcome = True
                    self._session_id = msg['payload']['session']['id']
                    self._socket = new_websocket
                    logger.error("New websocket connected!")
        except Exception as e:
            logger.error(f"Error during websocket reconnection: {e}")
            await new_websocket.close()
            raise e
        finally:
            if not welcome:
                await new_websocket.close()

    async def handle_message(self, message):
        msg = json.loads(message)
        meta = msg["metadata"]
        logger.debug(f"{meta['message_type']}:\n{json.dumps(msg, indent=2)}")
        if meta["message_id"] not in self._seen_messages:
            self._seen_messages[meta["message_id"]] = msg
            match meta["message_type"]:
                case "session_welcome": 
                    await self.handle_session_welcome(meta, msg["payload"])
                case "session_reconnect": 
                    await self.handle_session_reconnect(meta, msg["payload"])
                case "notification":
                    await self.notification_handler(meta, msg["payload"])
                case "session_keepalive":
                    pass
                case "close": 
                    await self.close()
                case _:
                    logger.error(f"Unexpected message in socket: [{meta['message_type']}]\n{json.dumps(msg, indent=2)}")

    def add_alert_class(self, name, obj):
        """ Adds alert classes to the AlertFactory cache """
        self.notification_handler.register_alert_class(name, obj)


#=============================================================================================

class ViewablePriorityQueue(asyncio.PriorityQueue):
    """
    A PriorityQueue that allows viewing its contents without removing items.
    """
    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize=maxsize)
        # Use a separate list to track items for viewing
        self._items: List[Tuple[Any, Any]] = []

    async def put(self, item: Tuple[Any, Any]) -> None:
        """Put an item into the queue and track it in our viewable list."""
        await super().put(item)
        self._items.append(item)
        # Keep items sorted by priority
        self._items.sort(key=lambda x: x[0])

    async def get(self) -> Tuple[Any, Any]:
        """Get an item from the queue and remove it from our viewable list."""
        item = await super().get()
        self._items.remove(item)
        return item

    def get_contents(self) -> List[Tuple[Any, Any]]:
        """Return a list of current items in the queue."""
        return self._items.copy()  # Return a copy to prevent external modifications

    def __len__(self) -> int:
        """Return the number of items in the queue."""
        return len(self._items)

#=============================================================================================

class NotificationHandler:
    def __init__(self, bot, storage):
        self.bot = bot
        self.storage = storage
        self._queue = ViewablePriorityQueue()
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
                _, alert = await self._queue.get()
                await alert.process()
                self._queue.task_done()
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                self._running = False
        logger.warning(f"NotificationHandler._loop stopped!")

    async def start(self):
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
        return self._queue.get_contents()

    async def __call__(self, metadata, payload):
        event = {
            'message_id': metadata["message_id"],
            'channel': payload['subscription']['type'],
            'data': payload['event'],
            'timestamp': convert2epoch(metadata['message_timestamp'])
        }
        alert = AlertFactory.create_alert(bot=self.bot, **event)
        if self.storage and alert.store and "test_" not in event["message_id"]:
            await self.storage.save_alert(**event)
        if not alert.queue_skip:
            await self._queue.put((alert.priority, alert))
        else:
            asyncio.create_task(alert.process())


#=============================================================================================

class Alert(ABC):
    queue_skip = False
    store = True
    priority = 3
    
    def __init__(self, bot, message_id, channel, data, timestamp):
        self.bot = bot
        self.message_id = message_id
        self.channel = channel
        self.data = data
        self.timestamp = timestamp

    @abstractmethod
    async def process(self):
        pass

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
    priority = 4
    
    async def process(self):
        logger.warning(f"Processing generic alert for {self.channel} -> {self.message_id}")
        logger.debug(f"Data: {self.data}")


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