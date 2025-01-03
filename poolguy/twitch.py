from .utils import asyncio, ColorLogger
from .twitchws import Alert, TwitchWS, AlertFactory
from .twitchapi import TwitchApi

logger = ColorLogger(__name__)

class TwitchBot:
    def __init__(self, http_creds={}, ws_config={}, alert_objs={}):
        self.ws = TwitchWS(bot=self, creds=http_creds, **ws_config)
        self.http = self.ws.http
        self.app = self.ws.http.app
        self._tasks = []
        self.register_routes()
        if alert_objs:
            for key, value in alert_objs.items():
                self.register_alert_class(key, value)

    async def add_task(self, coro, *args, **kwargs):
        """ Adds a task to our list of tasks """
        self._tasks.append(asyncio.create_task(coro(*args, **kwargs)))
    
    def register_alert_class(self, name, obj):
        """ Adds alert classes to the AlertFactory cache """
        AlertFactory.register_alert_class(name, obj)
        
    async def start(self, hold=False):
        # start webserver
        await self.add_task(self.app.run_task, host=self.http.host, port=self.http.port)
        # wait for login
        await self.http.login()
        # start websocket connection and queue
        await self.add_task(self.ws.alert_queue.process_alerts)
        await self.add_task(self.ws.run)
        await asyncio.sleep(0.5)
        await self.after_init()
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

    async def after_init(self):
        """ Used to execute logic after the webserver and websocket are running and the bot is logged in """
        pass

    def register_routes(self):
        """ Used to register Quart app routes when TwitchBot inits """
        pass