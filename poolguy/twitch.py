from .utils import asyncio, ColorLogger
from .twitchws import Alert, TwitchWS
from .twitchapi import TwitchApi

logger = ColorLogger(__name__)

class TwitchBot:
    def __init__(self, http_creds={}, ws_config={}, alert_objs={}):
        self.ws = TwitchWS(bot=self, creds=http_creds, **ws_config)
        self.http = self.ws.http
        self.app = self.ws.http.server
        self._tasks = []
        self.register_routes()
        if alert_objs:
            for key, value in alert_objs.items():
                self.add_alert_class(key, value)
        self.channelBadges = {}

    async def getChanBadges(self, bid=None, size='image_url_4x'):
        r = await self.http.getGlobalChatBadges()
        r += await self.http.getChannelChatBadges(bid)
        badges = {}
        for i in r:
            badges[i['set_id']] = {b['id']: b[size] for b in i['versions']}
        return badges

    async def add_task(self, coro, *args, **kwargs):
        """ Adds a task to our list of tasks """
        self._tasks.append(asyncio.create_task(coro(*args, **kwargs)))
    
    def add_alert_class(self, name, obj):
        """ Adds alert classes to the AlertFactory cache """
        self.ws.register_alert_class(name, obj)
        
    async def start(self, hold=False, login_browser=None):
        # start OAuth, websocket connection, and queue
        self._tasks = await self.ws.run(login_browser)
        self.channelBadges[str(self.http.user_id)] = await self.getChanBadges()
        await self.after_login()
        if hold:
            # wait/block until tasks complete (should run forever)
            await self.hold()

    async def hold(self):
        try:
            await asyncio.gather(*self._tasks)
        except Exception as e:
            logger.error(f"Error in TwitchBot.start(): {e}")
            await self.ws.close()
            raise e

    async def after_login(self):
        pass

    def register_routes(self):
        pass