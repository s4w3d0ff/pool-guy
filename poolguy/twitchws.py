import json
import sys
import asyncio
import websockets
import logging
from .eventsub import NotificationHandler, MaxSizeDict
from .twitchapi import TwitchApi

# for current func name, specify 0 or no argument.
# for name of caller of current func, specify 1.
# for name of caller of caller of current func, specify 2. etc.
# https://stackoverflow.com/a/31615605/3389859
_func_name = lambda n=0: sys._getframe(n + 1).f_code.co_name

logger = logging.getLogger(__name__)

WSURL = "wss://eventsub.wss.twitch.tv/ws?keepalive_timeout_seconds=600"

class TwitchWebsocket:
    """ Handles EventSub Websocket connection and subscriptions """
    def __init__(self, bot, channels=None, max_reconnect=None, http=None, *args, **kwargs):
        self.http = http or TwitchApi(*args, **kwargs)
        self.channels = channels or {"channel.chat.message": [None]}
        self.max_reconnect = max_reconnect or 20
        self.notification_handler = NotificationHandler(bot, self.http.storage)
        self._socket = None
        self._running = False
        self._session_id = None
        self._seen_messages = MaxSizeDict(15)

    async def run(self, token=None, paused=False):
        self._running = True
        await self.notification_handler.start(paused=paused)
        if not self.http.user_id:
            await self.http.login(token)
        while self._running:
            try:
                self._session_id = None
                self._socket = await websockets.connect(WSURL)
                await self._socket_loop()
            except Exception as e:
                logger.error(f"Exception in socket loop:\n{e}")

    async def _socket_loop(self):
        logger.info(f"Connected to twitch websocket")
        while self._running:
            try:
                message = await self._socket.recv()
            except Exception as e:
                logger.error(f"Twitch websocket conenction error:\n {e}")
                break
            try:
                await self.handle_message(json.loads(message))
            except:
                logger.exception(f"Error handling twitch websocket message:\n{message}\n")
        logger.warning("Twitch websocket disconnected!")

    async def handle_session_welcome(self, metadata, payload):
        logger.info(f"Session welcome recieved")
        self._session_id = payload['session']['id']
        current_subs = await self.clear_stale_subs(self._session_id)
        if not current_subs:
            await self.init_channel_subs()

    async def handle_session_reconnect(self, metadata, payload):
        logger.error("Websocket needs to reconnect")
        socket = await websockets.connect(payload['session']['reconnect_url'])
        try:
            welcome = None
            logger.warning("Waiting for welcome message on new socket...")
            while not welcome:
                message = await socket.recv()
                msg = json.loads(message)
                if msg["metadata"]["message_type"] == 'session_welcome':
                    welcome = True
                    self._session_id = msg['payload']['session']['id']
                    self._socket = socket
                    logger.error("New websocket connected!")
        except Exception as e:
            logger.error(f"Error during websocket reconnection: {e}")
            await socket.close()
            raise e
        finally:
            if not welcome:
                await socket.close()

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
                case "notification":
                    asyncio.create_task(self.notification_handler(meta, message["payload"]))
                case "session_keepalive":
                    pass
                case "close":
                    logger.warning("Twitch websocket received close message")
                case _:
                    logger.error(f"Unexpected message in socket: [{meta['message_type']}]\n{json.dumps(message, indent=2)}")

    async def close(self):
        self._running = False
        await self.notification_handler.shutdown()

    def add_alert_class(self, name, obj):
        """ Adds alert classes to the AlertFactory cache """
        self.notification_handler.register_alert_class(name, obj)

    async def create_event_sub(self, event, bid=None):
        await self.http.createEventSub(event, session_id=self._session_id, bid=bid)

    async def init_channel_subs(self):
        for chan in self.channels:
            if isinstance(self.channels[chan], list):
                for i in self.channels[chan]:
                    await self.create_event_sub(chan, i)
            else:
                await self.create_event_sub(chan)
            await asyncio.sleep(0.2)
        logger.warning(f"Subscribed websocket to:\n{json.dumps(list(self.channels.keys()), indent=2)}")

    async def clear_stale_subs(self, session_id=None):
        """ Unsubscribe from all events """
        r = await self.http.getEventSubs()
        tasks = []
        out = []
        for sub in r['data']:
            if "session_id" in sub["transport"] and session_id:
                if session_id == sub["transport"]["session_id"]:
                    out.append(sub)
            if sub['status'] == "enabled":
                continue
            else:
                logger.info(f"[deleteEventSub](Reason: '{sub['status']}') -> \n{sub['type']}:{sub['condition']} ")
                tasks.append(asyncio.create_task(self.http.deleteEventSub(sub['id'])))
        await asyncio.gather(*tasks)
        return out