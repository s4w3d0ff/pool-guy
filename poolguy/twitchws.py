from .utils import json, asyncio, websockets
from .utils import MaxSizeDict, ColorLogger, ABC
from .utils import convert2epoch, abstractmethod
from .twitchstorage import StorageFactory
from .twitchapi import TwitchApi

logger = ColorLogger(__name__)

websocketURL = "wss://eventsub.wss.twitch.tv/ws?keepalive_timeout_seconds=600"

class TwitchWS:
    def __init__(self, bot=None, http=None, queue=None, creds={}, channels={"channel.chat.message": [None]}, queue_skip={"channel.chat.message"}, **kwargs):
        self.bot = bot
        self.http = http or TwitchApi(**creds, **kwargs)
        self.storage = self.http.storage
        self.alert_queue = queue or StorageAlertQueue(bot=bot, storage=self.storage)
        self.channels = channels
        self.queue_skip = queue_skip
        self.socket = None
        self.connected = False
        self.session_id = None
        self.seen_messages = MaxSizeDict(20)
        self._queue_task = None
        self._socket_task = None
        self._disconnect_event = asyncio.Event()

    def register_alert_class(self, name, obj):
        """ Adds alert classes to the AlertFactory cache """
        AlertFactory.register_alert_class(name, obj)

    async def run(self, login_browser=None):
        await self.http.login(login_browser)
        logger.info(f"Clearing orphaned event subs")
        await self.http.unsubAllEvents()
        if not self._socket_task:
            self._queue_task = asyncio.create_task(self.alert_queue.process_alerts())
            self._socket_task = asyncio.create_task(self.socket_loop())
        return [self.http.server._app_task, self._queue_task, self._socket_task]

    async def socket_loop(self):
        self.socket = await websockets.connect(websocketURL)
        self.connected = True
        self._disconnect_event.clear()
        logger.debug(f"[socket_loop] started...")
        while self.connected:
            try:
                message = await self.socket.recv()
                await self.handle_message(message)
            except websockets.exceptions.ConnectionClosed as e:
                logger.error(f"[socket_loop] WebSocket connection closed: {e}")
                break
            except Exception as e:
                logger.error(f"[socket_loop] {e}")
                break
        self.connected = False
        self._disconnect_event.set()
        logger.warning(f"[socket_loop] socket closed...")

    async def close(self):
        # stop socket
        logger.warning(f"[close] closing socket...")
        self.connected = False
        try:
            await self.socket.close()
        except:
            pass
        # stop webserver app
        try:
            logger.warning(f"[close] stopping webserver...")
            await self.http.server.stop()
        except Exception as e:
            logger.error(f"{e}")
        # stop queue
        logger.warning(f"[close] stopping alert_queue...")
        self.alert_queue.is_running = False
        # TODO: add a way to save anything left in the queue during shutdown
        
    async def after_init_welcome(self):
        for chan in self.channels:
            if isinstance(self.channels[chan], list):
                for i in self.channels[chan]:
                    await self.http.createEventSub(chan, self.session_id, i)
            else:
                await self.http.createEventSub(chan, self.session_id)
            await asyncio.sleep(0.2)
        logger.warning(f"Subscribed websocket to:\n{json.dumps(list(self.channels.keys()), indent=2)}")

    async def handle_session_welcome(self, metadata, payload):
        logger.info(f"Session welcome recieved")
        if not self.session_id:
            self.session_id = payload['session']['id']
            logger.debug(f"session_id: {self.session_id}")
            await self.after_init_welcome()

    async def handle_session_reconnect(self, metadata, payload):
        logger.error("Websocket needs to reconnect")
        new_websocket = await websockets.connect(payload['session']['reconnect_url'])
        try:
            welcome = None
            logger.warning("Waiting for welcome message from new websocket...")
            while not welcome:
                message = await new_websocket.recv()
                msg = json.loads(message)
                if msg["metadata"]["message_type"] == 'session_welcome':
                    welcome = True
                    self.session_id = msg['payload']['session']['id']
                    self.socket = new_websocket
                    logger.warning("New websocket connected!")
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
        msgtype = meta["message_type"]
        msgid = meta["message_id"]
        timestamp = convert2epoch(meta['message_timestamp'])
        logger.debug(f"{msgtype}:\n{json.dumps(msg, indent=2)}")
        if meta["message_id"] not in self.seen_messages:
            self.seen_messages[msgid] = msg
            match msgtype:
                case "session_welcome": 
                    await self.handle_session_welcome(meta, msg["payload"])
                case "session_reconnect": 
                    await self.handle_session_reconnect(meta, msg["payload"])
                case "close": 
                    await self.socket.close()
                case "notification":
                    noto_type = msg['payload']['subscription']['type']
                    noto_event = msg["payload"]['event']
                    if self.alert_queue:
                        if noto_type in self.queue_skip:
                            alert = AlertFactory.create_alert(
                                    bot=self.bot,
                                    alert_id=msgid,
                                    alert_type=noto_type,
                                    data=noto_event,
                                    timestamp=timestamp
                                )
                            asyncio.create_task(alert.process())
                        else:
                            await self.alert_queue.add_alert(msgid, noto_type, noto_event, timestamp)
                case _:
                    pass

#=============================================================================================
#=============================================================================================
class Alert(ABC):
    def __init__(self, bot, alert_id, alert_type, data, timestamp):
        self.bot = bot
        self.alert_id = alert_id
        self.alert_type = alert_type
        self.data = data
        self.timestamp = timestamp
        
    @abstractmethod
    async def process(self):
        """Process the alert. Must be implemented by subclasses."""
        pass

    def to_dict(self):
        """Convert alert to dictionary format for JSON storage."""
        return {
            'type': self.alert_type,
            'timestamp': self.timestamp,
            'data': self.data
        }

    @classmethod
    def from_dict(cls, alert_id, data):
        """Create an alert instance from dictionary data."""
        return cls(
            alert_id=alert_id,
            alert_type=data['type'],
            data=data['data'],
            timestamp=data['timestamp']
        )

#=============================================================================================
#=============================================================================================
class GenericAlert(Alert):
    """Generic alert class for handling unknown alert types."""
    def __init__(self, bot, alert_id, alert_type, data, timestamp):
        super().__init__(bot, alert_id, alert_type, data, timestamp)
    
    async def process(self):
        """Process a generic alert."""
        logger.warn(f"Processing generic alert for {self.alert_type} -> {self.alert_id}")
        logger.info(f"Data: {self.data}")

#=============================================================================================
#=============================================================================================
class AlertFactory:
    """Factory class to create the appropriate Alert instance based on event type."""
    _alert_classes = {}  # Cache for alert classes

    @classmethod
    def register_alert_class(cls, alert_type, alert_class):
        """Register an alert class for a specific type"""
        cls._alert_classes[alert_type] = alert_class

    @staticmethod
    def create_alert(bot, alert_id, alert_type, data, timestamp):
        """Create an appropriate Alert instance based on the alert type."""
        # First check if we have a registered class for this type
        if alert_type in AlertFactory._alert_classes:
            return AlertFactory._alert_classes[alert_type](bot, alert_id, alert_type, data, timestamp)

        # Fall back to the old method
        def get_alert_class_name(event_type):
            parts = event_type.split('.')
            class_parts = [part.title().replace('-', '') for part in parts]
            return ''.join(class_parts) + 'Alert'
        
        logger.warn(f"{get_alert_class_name(alert_type)} wasn't found! 'GenericAlert' used instead...")
        return GenericAlert(bot, alert_id, alert_type, data, timestamp)

#=============================================================================================
#=============================================================================================
class AlertQueue:
    def __init__(self, bot, delay=0.1):
        self.bot = bot
        self.queue = asyncio.Queue()
        self.is_processing = True
        self.is_running = False
        self.delay = delay

    async def process_alerts(self):
        self.is_running = True
        logger.debug(f"[AlertQueue] process_alerts started...")
        while self.is_running:
            if not self.is_processing:
                await asyncio.sleep(self.delay)
                continue
            try:
                alert_id, alert_data = await self.queue.get()
                alert = AlertFactory.create_alert(
                    bot=self.bot,
                    alert_id=alert_id,
                    alert_type=alert_data['type'],
                    data=alert_data['data'],
                    timestamp=alert_data['timestamp']
                )
                await alert.process()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing alert {alert_id}: {e}")
            self.queue.task_done()
            await asyncio.sleep(self.delay)
        try:
            self.queue.task_done()
        except:
            pass
        logger.warning(f"[AlertQueue] process_alerts ended")
        self.is_running = False

    async def add_alert(self, alert_id, alert_type, data, timestamp):
        alert_data = {
            'type': alert_type,
            'data': data,
            'timestamp': timestamp
        }
        await self.queue.put((alert_id, alert_data))

    def pause(self):
        self.is_processing = False
        logger.warning(f"[AlertQueue] process_alerts paused...")

    def resume(self):
        self.is_processing = True
        logger.warning(f"[AlertQueue] process_alerts resumed...")

#=============================================================================================
#=============================================================================================
class StorageAlertQueue(AlertQueue):
    def __init__(self, bot, delay=0.1, storage=None, **kwargs):
        super().__init__(bot, delay)
        self.storage = storage or StorageFactory.create_storage(**kwargs)

    async def add_alert(self, alert_id, alert_type, data, timestamp):
        alert_data = {
            'type': alert_type,
            'data': data,
            'timestamp': timestamp
        }
        await self.storage.save_alert(alert_id, alert_data)
        await self.queue.put((alert_id, alert_data))