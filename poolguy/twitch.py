from .utils import asyncio, ColorLogger
from .twitchws import Alert, TwitchWS
from .twitchapi import TwitchApi

logger = ColorLogger(__name__)

class TwitchBot:
    def __init__(self, creds={}, channels={"channel.chat.message"}, queue_skip={"channel.chat.message"}, storage_type='json'):
        self.ws = TwitchWS(bot=self, creds=creds, channels=channels, queue_skip=queue_skip, storage_type='json')
        self.http = self.ws.http
        self.app = self.ws.http.app
        self._tasks = []

    async def start(self, hold=False):
        # start webserver
        self._tasks.append(asyncio.create_task(self.app.run_task(
                host=self.http.host, 
                port=self.http.port)))
        # wait for login
        await self.http.login()
        # start websocket connection and queue
        self._tasks.append(asyncio.create_task(self.ws.alert_queue.process_alerts()))
        self._tasks.append(asyncio.create_task(self.ws.run()))
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

    @self.app.route('/')
    async def index():
        if not self.http.token:
            await self.start()

#================================================
#================================================
    @self.app.route('/hidescene/<source>')
    async def hide_source(source):
        """ route to hide a scene """
        r = self.obsws.hideSource(source)
        return jsonify(r)

    @self.app.route('/showscene/<source>')
    async def show_source(source):
        """ route to show a scene """
        r = self.obsws.showSource(source)
        return jsonify(r)

    @self.app.route('/alertqueue/<action>')
    async def alert_queue(action):
        match action:
            case "pause":
                self.ws.alert_queue.pause()
            case "resume":
                self.ws.alert_queue.resume()
            case _:
                pass
        return jsonify('')
#================================================
#================================================