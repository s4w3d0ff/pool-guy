from .utils import json, asyncio, websockets
from .utils import MaxSizeDict, ColorLogger, ABC, abstractmethod
from .twitchstorage import StorageFactory
from .twitchapi import TwitchApi

logger = ColorLogger(__name__)

websocketURL = "wss://eventsub.wss.twitch.tv/ws?keepalive_timeout_seconds=600"

class TwitchWS:
    def __init__(self, bot=None, http=None, queue=None, creds={}, channels={"channel.chat.message": [None]}, queue_skip={"channel.chat.message"}, storage_type='json'):
        self.bot = bot
        self.http = http or TwitchApi(**creds)
        self.alert_queue = queue or AlertQueue(bot=bot, storage_type=storage_type)
        self.channels = channels
        self.queue_skip = queue_skip
        self.socket = None
        self.connected = False
        self.session_id = None
        self.seen_messages = MaxSizeDict(42)

    async def socket_loop(self):
        self.socket = await websockets.connect(websocketURL)
        self.connected = True
        logger.info(f"[socket_loop:{self.session_id}] socket_loop started")
        while self.connected:
            try:
                message = await self.socket.recv()
                await self.handle_message(message)
            except Exception as e:
                logger.error(f"[socket_loop] {e}")
                await self.socket.close()
                raise e
            await asyncio.sleep(0.1)

    async def close(self):
        self.is_running = False
        self.connected = False
        await self.socket.close()
        self.socket = None

    async def run(self):
        await self.socket_loop()

    async def after_init_welcome(self):
        logger.warning(f"Clearing orphaned event subs")
        await self.http.unsubAllEvents()
        logger.warning(f"Subscribing websocket to: {self.channels}")
        for chan in self.channels:
            for i in self.channels[chan]:
                await self.http.createEventSub(chan, self.session_id, i)
            await asyncio.sleep(0.2)
        logger.warning(f"Subscribed websocket to:\n{json.dumps(list(self.channels), indent=2)}")

    async def handle_session_welcome(self, metadata, payload):
        logger.warning(f"Session welcome recieved")
        if not self.session_id:
            self.session_id = payload['session']['id']
            logger.warning(f"session_id: {self.session_id}")
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
        if meta["message_id"] not in self.seen_messages:
            logger.debug(f"{msgtype}:\n{json.dumps(meta, indent=2)}")
            self.seen_messages[meta["message_id"]] = msg
            match msgtype:
                case "notification":
                    noto_type = msg['payload']['subscription']['type']
                    noto_event = msg["payload"]['event']
                    if self.alert_queue:
                        if noto_type in self.queue_skip:
                            alert = AlertFactory.create_alert(
                                    bot=self.bot,
                                    alert_id=None,
                                    alert_type=noto_type,
                                    data=noto_event,
                                    meta=meta
                                )
                            asyncio.create_task(alert.process())
                        else:
                            await self.alert_queue.add_alert(noto_type, noto_event, meta)
                case "session_welcome": 
                    await self.handle_session_welcome(meta, msg["payload"])
                case "session_reconnect": 
                    await self.handle_session_reconnect(meta, msg["payload"])
                case "close": 
                    await self.socket.close()
                case _:
                    pass

#=============================================================================================
#=============================================================================================
class Alert(ABC):
    def __init__(self, bot, alert_id, alert_type, data, meta):
        self.bot = bot
        self.aid = alert_id
        self.atype = alert_type
        self.data = data
        self.meta = meta

        # Register the routes
        self.register_routes()
    
    @abstractmethod
    def register_routes(self):
        pass
        
    @abstractmethod
    async def process(self):
        """Process the alert. Must be implemented by subclasses."""
        pass

    def to_dict(self):
        """Convert alert to dictionary format for JSON storage."""
        return {
            'type': self.atype,
            'data': self.data,
            'meta': self.meta
        }

    @classmethod
    def from_dict(cls, alert_id, data):
        """Create an alert instance from dictionary data."""
        return cls(
            alert_id=alert_id,
            alert_type=data['type'],
            data=data['data'],
            meta=data['meta']
        )

#=============================================================================================
#=============================================================================================
class GenericAlert(Alert):
    """Generic alert class for handling unknown alert types."""
    def __init__(self, bot, alert_id, alert_type, data, meta):
        super().__init__(bot, alert_id, alert_type, data, meta)
    
    def register_routes(self):
        logger.debug(f"register_routes: No routes to register")
    
    async def process(self):
        """Process a generic alert."""
        logger.warn(f"Processing generic alert {self.aid} of type {self.atype}")
        logger.info(f"Data: {self.data}")
        logger.debug(f"Meta: {self.meta}")

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
    def create_alert(bot, alert_id, alert_type, data, meta):
        """Create an appropriate Alert instance based on the alert type."""
        # First check if we have a registered class for this type
        if alert_type in AlertFactory._alert_classes:
            return AlertFactory._alert_classes[alert_type](bot, alert_id, alert_type, data, meta)

        # Fall back to the old method
        def get_alert_class_name(event_type):
            parts = event_type.split('.')
            class_parts = [part.title().replace('-', '') for part in parts]
            return ''.join(class_parts) + 'Alert'
        
        logger.warn(f"{get_alert_class_name(alert_type)} wasn't found! 'GenericAlert' used instead...")
        return GenericAlert(bot, alert_id, alert_type, data, meta)

#=============================================================================================
#=============================================================================================
class AlertQueue:
    def __init__(self, bot, **kwargs):
        self.bot = bot
        self.queue = asyncio.Queue()
        self.is_processing = True
        self.is_running = False
        self._current_id = 0
        self.storage = StorageFactory.create_storage(**kwargs)

    async def process_alerts(self):
        self.is_running = True
        while self.is_running:
            if not self.is_processing:
                await asyncio.sleep(1)
                continue
            try:
                alert_id, alert_data = await self.queue.get()
                alert = AlertFactory.create_alert(
                    bot=self.bot,
                    alert_id=alert_id,
                    alert_type=alert_data['type'],
                    data=alert_data['data'],
                    meta=alert_data['meta']
                )
                await alert.process()
                self.queue.task_done()
            except asyncio.CancelledError:
                self.queue.task_done()
                break
            except Exception as e:
                self.queue.task_done()
                Logger.error(f"Error processing alert {alert_id}: {e}")

    async def add_alert(self, alert_type, data, meta):
        self._current_id += 1
        alert_data = {
            'type': alert_type,
            'data': data,
            'meta': meta
        }
        self.storage.save_alert(self._current_id, alert_data)
        await self.queue.put((self._current_id, alert_data))
        return self._current_id

    def pause(self):
        self.is_processing = False

    def resume(self):
        self.is_processing = True

    async def skip_alert(self, alert_id):
        self.pause()
        new_queue = asyncio.Queue()
        while not self.queue.empty():
            current_id, data = await self.queue.get()
            if current_id != alert_id:
                await new_queue.put((current_id, data))
            self.queue.task_done()
        self.queue = new_queue
        self.resume()

    async def replay_alert(self, date, alert_id):
        alerts = self.storage.load_alerts(date)
        if alert_id not in alerts:
            raise ValueError(f"Alert {alert_id} not found in {date}")
        alert_data = alerts[alert_id]
        await self.queue.put((int(alert_id), alert_data))