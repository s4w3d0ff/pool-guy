from .utils import asyncio, os, aiohttp
from .utils import ColorLogger, urlparse, wraps
from aiohttp import web

logger = ColorLogger(__name__)

class WebServer:
    def __init__(self, host, port, static_dirs=[]):
        self.app = web.Application()
        self.host = host
        self.port = port
        self._runner = None
        self._site = None
        self._app_task = None
        self.routes = {}
        self.ws_handlers = {}
        self.static_dirs = static_dirs
    
    def is_running(self):
        return True if self._app_task else False

    def add_static_dirs(self):
        if self.is_running():
            logger.warning("Adding a static dir after server started - requires restart to take effect")
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for dir in self.static_dirs:
            static_root = os.path.join(base_dir, dir)
            os.makedirs(static_root, exist_ok=True)
            # Add the main static routes
            self.app.router.add_static(f'/{dir}/', static_root)
            logger.info(f"Added static dir '/{dir}/': {static_root}")

    def add_route(self, path, handler, method='GET', **kwargs):
        """Add a new route to the application."""
        if self.is_running():
            logger.warning("Adding route after server started - requires restart to take effect")
            
        route_info = {
            'handler': handler,
            'method': method,
            'kwargs': kwargs
        }
        self.routes[path] = route_info
        match method:
            case 'GET':
                self.app.router.add_get(path, handler, **kwargs)
            case 'POST':
                self.app.router.add_post(path, handler, **kwargs)
            case 'PUT':
                self.app.router.add_put(path, handler, **kwargs)
            case 'DELETE':
                self.app.router.add_delete(path, handler, **kwargs)
            case _:
                self.app.router.add_route(method, path, handler, **kwargs)
        logger.info(f"Added {method} route for {path}")

    def add_websocket(self, path, handler, **kwargs):
        """Add a new WebSocket endpoint."""
        if self.is_running():
            logger.warning("Adding WebSocket after server started - requires restart to take effect")

        @wraps(handler)
        async def ws_wrapper(request):
            ws = web.WebSocketResponse(**kwargs)
            await ws.prepare(request)
            try:
                await handler(ws, request)
            except Exception as e:
                logger.error(f"WebSocket handler error: {e}")
            finally:
                return ws

        self.ws_handlers[path] = {
            'handler': handler,
            'wrapper': ws_wrapper,
            'kwargs': kwargs
        }
        
        self.app.router.add_get(path, ws_wrapper)
        logger.info(f"Added WebSocket endpoint at {path}")

    async def start(self):
        """Start the web server."""
        if not self._app_task:
            self.add_static_dirs()
            self._runner = web.AppRunner(self.app)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, self.host, self.port)
            self._app_task = asyncio.create_task(self._site.start())
            logger.warning(f"Server started on {self.host}:{self.port}")

    async def stop(self):
        """Stop the web server."""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        self._app_task = None
        logger.warning("Server stopped")

    async def restart(self):
        """Restart the server to apply new routes/websockets or whatever."""
        await self.stop()
        await self.start()
        logger.info("Server restarted.")

    def route(self, path, method='GET', **kwargs):
        """Decorator for registering routes."""
        def decorator(handler):
            self.add_route(path, handler, method, **kwargs)
            return handler
        return decorator

    def websocket(self, path, **kwargs):
        """Decorator for registering WebSocket endpoints."""
        def decorator(handler):
            self.add_websocket(path, handler, **kwargs)
            return handler
        return decorator