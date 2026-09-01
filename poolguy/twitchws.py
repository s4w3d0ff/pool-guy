import json
import sys
import time
import sqlite3
import asyncio
import websockets
import logging
from .eventsub import NotificationHandler, convert2epoch
from .twitchapi import TwitchApi

_func_name = lambda n=0: sys._getframe(n + 1).f_code.co_name

logger = logging.getLogger(__name__)

WSURL = "wss://eventsub.wss.twitch.tv/ws?keepalive_timeout_seconds=600"
REPLAY_WINDOW_SECONDS = 600
SUBSCRIBE_DEADLINE_SECONDS = 10
RECONNECT_CLOSE_WINDOW_SECONDS = 30


class TwitchWebsocket:
    def __init__(self, bot, channels=None, max_reconnect=None, http=None, *args, **kwargs):
        self.http = http or TwitchApi(*args, **kwargs)
        self.channels = channels or {"channel.chat.message": [None]}
        self.max_reconnect = max_reconnect or 20
        self.notification_handler = NotificationHandler(bot, self.http.storage)
        self._socket = None
        self._running = False
        self._session_id = None

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
                if not self._running:
                    break
                await asyncio.sleep(5)

    async def _socket_loop(self):
        logger.info("Connected to twitch websocket")
        while self._running:
            try:
                message = await self._socket.recv()
            except Exception as e:
                logger.error(f"Twitch websocket connection error:\n {e}")
                break
            try:
                await self.handle_message(json.loads(message))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(f"Error handling twitch websocket message:\n{message}\n")
        logger.warning("Twitch websocket disconnected!")

    async def handle_session_welcome(self, metadata, payload):
        logger.info("Session welcome received")
        self._session_id = payload['session']['id']
        started = time.monotonic()
        await self.init_channel_subs()
        elapsed = time.monotonic() - started
        if elapsed > SUBSCRIBE_DEADLINE_SECONDS:
            logger.error(f"Subscription deadline exceeded! {elapsed:.1f}s to complete required subs")
        else:
            logger.info(f"All required subscriptions created in {elapsed:.2f}s")
        asyncio.create_task(self.clear_stale_subs())

    async def handle_session_reconnect(self, metadata, payload):
        logger.error("Websocket needs to reconnect")
        old_socket = self._socket
        socket = await websockets.connect(payload['session']['reconnect_url'])
        welcome = False
        try:
            logger.warning("Waiting for welcome message on new socket...")
            while not welcome:
                message = await asyncio.wait_for(
                    socket.recv(), timeout=RECONNECT_CLOSE_WINDOW_SECONDS
                )
                msg = json.loads(message)
                if msg["metadata"]["message_type"] == 'session_welcome':
                    self._session_id = msg['payload']['session']['id']
                    welcome = True
            self._socket = socket
            logger.info("New websocket connected, old connection will be closed")
        except Exception as e:
            logger.error(f"Error during websocket reconnection: {e}")
            await socket.close()
            raise
        finally:
            if old_socket is not None and old_socket is not socket:
                try:
                    await asyncio.wait_for(
                        old_socket.close(), timeout=RECONNECT_CLOSE_WINDOW_SECONDS
                    )
                except Exception as e:
                    logger.warning(f"Old websocket close failed after {e}")

    async def handle_revocation(self, metadata, payload):
        sub = payload.get('subscription', {})
        logger.warning(
            f"Subscription revoked [id={sub.get('id')} type={sub.get('type')}] "
            f"status: {sub.get('status')}"
        )
        event_type = sub.get('type')
        if event_type not in self.channels:
            return
        condition = sub.get('condition', {})
        try:
            await self.create_event_sub(
                event_type, bid=condition.get('broadcaster_user_id')
            )
            logger.info(f"Re-subscribed to {event_type} after revocation")
        except Exception as e:
            logger.error(f"Failed to re-subscribe to {event_type} after revocation: {e}")

    async def _is_duplicate(self, meta):
        msg_id = meta.get("message_id")
        if not msg_id:
            return False
        ts = meta.get("message_timestamp")
        if ts:
            age = time.time() - convert2epoch(ts)
            if age > REPLAY_WINDOW_SECONDS:
                logger.warning(f"Dropping replayed message {msg_id} (age {age:.0f}s)")
                return True
        try:
            rows = await self.http.storage.query(
                "eventsub_messages", where="message_id = ?", params=(msg_id,)
            )
        except sqlite3.OperationalError as e:
            if "no such table" not in str(e):
                raise
            return False
        if rows:
            logger.debug(f"Duplicate message skipped: {msg_id}")
            return True
        return False

    async def _mark_seen(self, meta):
        msg_id = meta.get("message_id")
        if not msg_id:
            return
        await self.http.storage.insert(
            "eventsub_messages",
            {"message_id": msg_id, "received_at": time.time()}
        )
        cutoff = time.time() - (2 * REPLAY_WINDOW_SECONDS)
        await self.http.storage.delete(
            "eventsub_messages", where="received_at < ?", params=(cutoff,)
        )

    async def handle_message(self, message):
        meta = message["metadata"]
        logger.debug(f"{meta['message_type']}:\n{json.dumps(message, indent=2)}")
        if await self._is_duplicate(meta):
            return
        await self._mark_seen(meta)
        match meta["message_type"]:
            case "session_welcome":
                await self.handle_session_welcome(meta, message["payload"])
            case "session_reconnect":
                await self.handle_session_reconnect(meta, message["payload"])
            case "notification":
                asyncio.create_task(self.notification_handler(meta, message["payload"]))
            case "revocation":
                await self.handle_revocation(meta, message["payload"])
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
        self.notification_handler.register_alert_class(name, obj)

    async def create_event_sub(self, event, bid=None):
        await self.http.createEventSub(event, session_id=self._session_id, bid=bid)

    async def init_channel_subs(self):
        tasks = []
        for chan in self.channels:
            if isinstance(self.channels[chan], list):
                for i in self.channels[chan]:
                    tasks.append(asyncio.create_task(self.create_event_sub(chan, i)))
            else:
                tasks.append(asyncio.create_task(self.create_event_sub(chan)))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Failed to create websocket subscription: {result}")
        logger.warning(f"Subscribed websocket to:\n{json.dumps(list(self.channels.keys()), indent=2)}")

    async def clear_stale_subs(self):
        try:
            r = await self.http.getEventSubs()
        except Exception as e:
            logger.error(f"Failed to list eventsub subscriptions for cleanup: {e}")
            return
        stale = [sub for sub in r['data'] if sub['status'] != 'enabled']
        tasks = []
        for sub in stale:
            logger.info(f"[deleteEventSub](Reason: '{sub['status']}') -> \n{sub['type']}:{sub['condition']}")
            tasks.append(asyncio.create_task(self.http.deleteEventSub(sub['id'])))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Failed to delete stale subscription: {result}")
