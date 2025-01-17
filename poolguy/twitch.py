import aiofiles
from aiohttp import web
from aiohttp import WSMsgType, WSServerHandshakeError
from .utils import asyncio, ColorLogger, cmd_rate_limit, webbrowser
from .twitchws import Alert, TwitchWS
from .tester import inject_custom_twitchws_message, inject_twitchws_message, test_meta_data, test_payloads

logger = ColorLogger(__name__)

class TwitchBot:
    def __init__(self, http_config={}, ws_config={}, alert_objs={}, max_retries=3, retry_delay=30, login_browser=None, load_test_routes=False):
        self.http_config = http_config
        self.ws_config = ws_config
        self.alert_objs = alert_objs
        self.ws = None
        self.http = None
        self.app = None
        self._tasks = []
        self.commands = {}
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        if isinstance(login_browser, dict):
            self.login_browser, path = login_browser.popitem()
            webbrowser.register(self.login_browser, None, webbrowser.BackgroundBrowser(path))
        else:
            self.login_browser = login_browser
        self.retry_count = 0
        self.is_running = False
        # optional test routes
        self.load_test_routes = load_test_routes

    async def add_task(self, coro, *args, **kwargs):
        """ Adds a task to our list of tasks """
        self._tasks.append(asyncio.create_task(coro(*args, **kwargs)))
    
    def add_alert_class(self, name, obj):
        """ Adds alert classes to the AlertFactory cache """
        self.ws.register_alert_class(name, obj)
    
    async def start(self, hold=True):
        self.is_running = True
        self.ws = TwitchWS(bot=self, creds=self.http_config, **self.ws_config)
        self.http = self.ws.http
        self.app = self.ws.http.server
        self.register_routes()
        if self.load_test_routes:
            self._register_test_routes()
        if self.alert_objs:
            for key, value in self.alert_objs.items():
                self.add_alert_class(key, value)
        # start OAuth, websocket connection, and queue
        self._tasks = await self.ws.run(login_browser=self.login_browser)
        await self.after_login()
        if hold:
            await self.hold()

    async def shutdown(self, reset=True):
        """Gracefully shutdown the bot"""
        logger.warning("Shutting down TwitchBot...")
        if not reset:
            self.is_running = False
        logger.warning("Closing TwitchWS...")
        await self.ws.close()
        # Clear all tasks
        logger.warning("Clearing tasks...")
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()
        logger.warning("TwitchBot shutdown complete")

    async def restart(self):
        """Restart the bot after shutdown"""
        logger.warning(f"Restarting TwitchBot in {self.retry_delay} seconds...")
        await asyncio.sleep(self.retry_delay)
        await self.start()

    async def hold(self):
        """Hold until something happens, cleanup shutdown, restart if needed"""
        try:
            await self.ws._disconnect_event.wait() # wait for ws to disconnect
        except asyncio.CancelledError: # tasks cancelled, this is fine
            logger.warning("Bot tasks cancelled")
        except Exception as e: # unexpected error, complete shutdown
            logger.error(f"Error in TwitchBot.hold(): {e}")
        await self.shutdown()
        if self.is_running: # we shutdown but are still running
            self.retry_count += 1 # try again?
            logger.warning(f"WebSocket disconnected. Attempt {self.retry_count} of {self.max_retries}")
            if self.retry_count <= self.max_retries: # havent hit max retries
                await self.restart() # start again
            else:
                logger.error(f"Max retry attempts ({self.max_retries}) reached. Shutting down permanently.")


    async def after_login(self):
        """Use to execute logic after everything is setup and right before we 'self.hold' """
        pass
        
    def register_routes(self):
        """Use to register app routes from a subclass when the webserver is being setup"""
        pass

    #=====================================================================
    #=====================================================================
    def _register_test_routes(self):
        @self.app.route('/testui')
        async def testui(request):
            async with aiofiles.open('templates/testui.html', 'r', encoding='utf-8') as f:
                template = await f.read()
                return web.Response(
                    text=template,
                    content_type='text/html',
                    charset='utf-8'
                )
                
        @self.app.route("/testcheer/{amount}/{anon}")
        async def testcheer(request):
            payload = test_payloads["channel.cheer"]
            payload["event"]["bits"] = int(request.match_info['amount'])
            payload["event"]["is_anonymous"] = False if request.match_info['anon'] == 'False' else True
            await inject_custom_twitchws_message(
                self.ws, 
                {"metadata": test_meta_data(), "payload": payload}
            )
            return web.json_response({"status": True})
        
        @self.app.route("/testsub/{tier}/{gifted}")
        async def testsub(request):
            payload = test_payloads["channel.subscribe"]
            payload["event"]["tier"] = request.match_info['tier'],
            payload["event"]["is_gift"] = False if request.match_info['gifted'] == 'False' else True
            await inject_custom_twitchws_message(
                self.ws, 
                {"metadata": test_meta_data(), "payload": payload}
            )
            return web.json_response({"status": True})


        @self.app.route("/testsubgift/{amount}/{tier}/{anon}")
        async def testsubgift(request):
            payload = test_payloads["channel.subscription.gift"]
            payload["event"]["total"] = int(request.match_info['amount']),
            payload["event"]["tier"] = request.match_info['tier'],
            payload["event"]["is_anonymous"] = False if request.match_info['anon'] == 'False' else True
            await inject_custom_twitchws_message(
                self.ws, 
                {"metadata": test_meta_data(), "payload": payload}
            )
            return web.json_response({"status": True})

        @self.app.route("/testsubmessage/{months}/{tier}/{streak}/{duration}")
        async def testsubmessage(request):
            payload = test_payloads["channel.subscription.message"]
            payload["event"]["tier"] = request.match_info['tier'],
            payload["event"]["cumulative_months"] = int(request.match_info['months']),
            payload["event"]["streak_months"] = int(request.match_info['streak']),
            payload["event"]["duration_months"] = int(request.match_info['duration'])
            await inject_custom_twitchws_message(
                self.ws, 
                {"metadata": test_meta_data(), "payload": payload}
            )
            return web.json_response({"status": True})
        logger.info(f"[_register_test_routes]: Done")



class CommandBot(TwitchBot):
    def __init__(self, cmd_prefix=['!', '~'], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._prefix = cmd_prefix
        # Register commands
        self._register_commands()

    def _register_commands(self):
        """Register all command handlers"""
        # Get all methods that start with cmd_
        for method_name in dir(self):
            if method_name.startswith('cmd_'):
                command_name = method_name[4:]  # Remove 'cmd_' prefix
                method = getattr(self, method_name)
                self.commands[command_name] = {
                    'handler': method,
                    'help': method.__doc__ or 'No help available.'
                }
        logger.info(f"Commands Registered: \n{list(self.commands.keys())}")

    async def command_check(self, message, user, channel):
        """Check if message starts with command prefix, handle command if needed"""
        if any(message.startswith(prefix) for prefix in self._prefix):
            await self._handle_command(message, user, channel)
            return True
        else:
            return False

    async def _handle_command(self, message, user, channel):
        """Handle bot commands"""
        # Remove prefix and split into command and args
        command_text = message[1:].strip()
        parts = command_text.split()
        command_name = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        if command_name in self.commands:
            try:
                await self.commands[command_name]['handler'](user, channel, args)
                logger.debug(f"Executed command: {command_name}")
            except Exception as e:
                logger.error(f"Error executing command {command_name}: {str(e)}")
                await self.http.sendChatMessage(
                    f"Failed to execute command: {command_name}", 
                    broadcaster_id=channel["broadcaster_id"]
                )
        else:
            logger.debug(f"Unknown command: {command_name}")

    @cmd_rate_limit(calls=3, period=30, warn_cooldown=15)
    async def cmd_help(self, user, channel, args):
        """Shows available commands. Usage: !help [command]"""
        if args:
            # Show help for specific command
            command = args[0].lower()
            if command in self.commands:
                help_text = f"{command}: {self.commands[command]['help']}"
            else:
                help_text = f"Unknown command: '{command}' Available commands: " + ", ".join(self.commands.keys())
        else:
            help_text = "Available commands: " + ", ".join(self.commands.keys())
        await self.http.sendChatMessage(help_text, broadcaster_id=channel["broadcaster_id"])