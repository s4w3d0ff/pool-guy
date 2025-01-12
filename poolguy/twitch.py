from .utils import asyncio, ColorLogger
from .twitchws import Alert, TwitchWS

logger = ColorLogger(__name__)

class TwitchBot:
    def __init__(self, cmd_prefix=['!', '~'], http_creds={}, ws_config={}, alert_objs={}):
        self._prefix = cmd_prefix
        self.ws = TwitchWS(bot=self, creds=http_creds, **ws_config)
        self.http = self.ws.http
        self.app = self.ws.http.server
        self._tasks = []
        self.register_routes()
        if alert_objs:
            for key, value in alert_objs.items():
                self.add_alert_class(key, value)
        self.channelBadges = {}
        self.commands = {}
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
                error_msg = f"Error executing command {command_name}: {str(e)}"
                logger.error(error_msg)
                await self.http.sendChatMessage(
                    f"Failed to execute command: {command_name}", 
                    broadcaster_id=channel["broadcaster_id"]
                )
        else:
            logger.debug(f"Unknown command: {command_name}")

    async def cmd_help(self, user, channel, args):
        """Shows available commands. Usage: !help [command]"""
        if args:
            # Show help for specific command
            command = args[0].lower()
            if command in self.commands:
                help_text = f"{command}: {self.commands[command]['help']}"
            else:
                help_text = f"Unknown command: {command}"
        else:
            # Show list of available commands
            help_text = "Available commands: " + ", ".join(self.commands.keys())
        await self.http.sendChatMessage(help_text, broadcaster_id=channel["broadcaster_id"])

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
        
    async def start(self, hold=True, login_browser=None):
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