from .utils import asyncio, aiofiles, webbrowser, aiohttp, time
from .utils import ColorLogger, defaultdict, web, wraps
from .twitchws import Alert, TwitchWS

logger = ColorLogger(__name__)

class TwitchBot:
    def __init__(self, http_config={}, ws_config={}, alert_objs={}, max_retries=3, retry_delay=30, login_browser=None, storage=None, static_dirs=[], base_dir=None):
        self.http_config = http_config
        self.ws_config = ws_config
        self.alert_objs = alert_objs
        self.storage = storage
        self.ws = None
        self.http = None
        self.app = None
        self._tasks = []
        self.static_dirs = static_dirs
        self.base_dir = base_dir
        self.retry_count = 0
        self.is_running = False
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        if isinstance(login_browser, dict):
            self.login_browser, path = login_browser.popitem()
            webbrowser.register(self.login_browser, None, webbrowser.BackgroundBrowser(path))
        else:
            self.login_browser = login_browser

    async def add_task(self, coro, *args, **kwargs):
        """ Adds a task to our list of tasks """
        self._tasks.append(asyncio.create_task(coro(*args, **kwargs)))
    
    def add_alert_class(self, name, obj):
        """ Adds alert classes to the AlertFactory cache """
        self.ws.register_alert_class(name, obj)
    
    async def start(self, hold=True):
        self.is_running = True
        self._setup()
        await self.before_login()
        # start OAuth, websocket connection, and queue
        self._tasks = await self.ws.run()
        await self.after_login()
        if hold:
            await self.hold()
    
    def _setup(self):
        self.ws = TwitchWS(bot=self, creds=self.http_config, **self.ws_config, storage=self.storage, static_dirs=self.static_dirs, base_dir=self.base_dir, browser=self.login_browser)
        self.http = self.ws.http
        self.app = self.ws.http.server
        self.storage = self.ws.storage
        self.register_routes()
        if self.alert_objs:
            for key, value in self.alert_objs.items():
                self.add_alert_class(key, value)

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
            if task and not task.done():
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

    async def before_login(self):
        """Use to execute logic before login"""
        pass
        
    async def after_login(self):
        """Use to execute logic after everything is setup and right before we 'self.hold'"""
        pass
        
    def register_routes(self):
        """Use to register app routes from a subclass when the webserver is being setup"""
        pass



def command(name=None, aliases=None):
    """
    Command decorator to mark methods as bot commands
    
    Args:
        name (str): Override the command name (defaults to method name)
        aliases (list): List of alternative names for the command
    """
    def decorator(func):
        func._is_command = True
        func._command_name = name or func.__name__.lower()
        func._command_aliases = aliases or []
        return func
    return decorator

def rate_limit(calls=2, period=10, warn_cooldown=5):
    """
    Rate limit decorator for bot commands
    
    Args:
        calls (int): Number of allowed calls
        period (float): Time period in seconds
        warn_cooldown (int): Time between warning messages
    """
    def decorator(func):
        if not hasattr(func, '_rate_limit_state'):
            func._rate_limit_state = defaultdict(lambda: {"calls": [], "last_warning": 0})
        
        @wraps(func)
        async def wrapper(self, user, channel, args):
            current_time = time.time()
            user_id = user['user_id']
            state = func._rate_limit_state[user_id]
            
            # Clean up old calls
            state['calls'] = [t for t in state['calls'] if current_time - t < period]
            
            # Check if user has exceeded rate limit
            if len(state['calls']) >= calls:
                # Only send warning message every warn_cooldown seconds
                if current_time - state['last_warning'] > warn_cooldown:
                    wait_time = period - (current_time - state['calls'][0])
                    await self.http.sendChatMessage(
                        f"@{user['username']} Please wait {wait_time:.1f}s before using this command again.",
                        broadcaster_id=channel["broadcaster_id"]
                    )
                    state['last_warning'] = current_time
                return
            
            # Add current call to the list
            state['calls'].append(current_time)
            
            # Execute the command
            return await func(self, user, channel, args)
        return wrapper
    return decorator



class CommandBot(TwitchBot):
    def __init__(self, cmd_prefix=['!', '~'], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._prefix = cmd_prefix
        self._commands = {}
        self._register_commands()

    def _register_commands(self):
        """Register all methods decorated with @command"""
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if hasattr(attr, '_is_command'):
                cmd_name = attr._command_name
                aliases = attr._command_aliases
                
                # Register main command
                self._commands[cmd_name] = {
                    'handler': attr,
                    'help': attr.__doc__ or 'No help available.',
                    'aliases': aliases or []
                }
                
                # Register aliases
                if aliases:
                    for alias in aliases:
                        self._commands[alias.lower()] = {
                            'handler': attr,
                            'help': f'Alias for {cmd_name}. {attr.__doc__ or "No help available."}',
                            'aliases': []
                        }
            
                logger.info(f"Registered command: {cmd_name} with aliases: {aliases or []}")

    async def command_check(self, data):
        """Check if message starts with command prefix, handle command if needed"""
        if data["source_broadcaster_user_id"]:
            return
        message = data["message"]["text"]
        if any(message.startswith(prefix) for prefix in self._prefix):
            user = {
                "user_id": data["chatter_user_id"], 
                "username": data["chatter_user_name"]
            }
            channel = {
                "broadcaster_id": data["broadcaster_user_id"],
                "broadcaster_user_name": data["broadcaster_user_name"]
            }
            await self._handle_command(message, user, channel)
            return True
        return False

    async def _handle_command(self, message, user, channel):
        """Handle bot commands"""
        command_text = message[1:].strip()
        parts = command_text.split()
        command_name = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        if command_name in self._commands:
            try:
                await self._commands[command_name]['handler'](user, channel, args)
                logger.debug(f"Executed command: {command_name}")
            except Exception as e:
                logger.error(f"Error executing command {command_name}: {str(e)}")
                await self.http.sendChatMessage(
                    f"Failed to execute command: {command_name}", 
                    broadcaster_id=channel["broadcaster_id"]
                )
        else:
            logger.debug(f"Unknown command: {command_name}")

    @command()
    @rate_limit(calls=1, period=30, warn_cooldown=15)
    async def commands(self, user, channel, args):
        """Shows available commands. Usage: !commands [command]"""
        if args:
            # Show help for specific command
            command = args[0].lower()
            if command in self._commands:
                help_text = f"{command}: {self._commands[command]['help']}"
                if self._commands[command]['aliases']:
                    help_text += f" (Aliases: {', '.join(self._commands[command]['aliases'])})"
            else:
                help_text = f"Unknown command: '{command}' Available commands: " + ", ".join(
                    [cmd for cmd in self._commands.keys() if not any(
                        cmd in self._commands[other]['aliases'] 
                        for other in self._commands
                    )]
                )
        else:
            # Only show main commands, not aliases
            main_commands = [cmd for cmd in self._commands.keys() if not any(
                cmd in self._commands[other]['aliases'] 
                for other in self._commands
            )]
            help_text = f"Command Prefix: {', '.join(self._prefix)} Commands: {', '.join(main_commands)}"
        await self.http.sendChatMessage(help_text, broadcaster_id=channel["broadcaster_id"])