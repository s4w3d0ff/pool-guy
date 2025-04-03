import asyncio
import os
import logging
from functools import wraps
from aiohttp import web

logger = logging.getLogger(__name__)

class WebServer:
    """WebServer class for serving web pages and handling requests."""
    def __init__(self, host, port, static_dirs=None, base_dir=None):
        self.app = web.Application()
        self.host = host
        self.port = port
        self._runner = None
        self._site = None
        self._app_task = None
        self.routes = {}
        self.ws_handlers = {}
        self.static_dirs = static_dirs or []
        self.base_dir = base_dir or os.path.expanduser('~')

    def is_running(self):
        """Check if the server is running."""
        return True if self._app_task else False

    def route_len(self):
        """Return the total number of routes."""
        return len(self.routes)+len(self.ws_handlers)+len(self.static_dirs)

    def add_static_dirs(self):
        """Add static directories to the web server."""
        if self.is_running():
            logger.warning("Adding a static dir after server started - requires restart to take effect")
        for dir in self.static_dirs:
            static_root = os.path.join(self.base_dir, dir)
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
                logger.error(f"{path} WebSocket handler error: {e}")
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
        self._app_task.cancel()
        try:
            await self._app_task
        except asyncio.CancelledError:
            pass
        self._app_task = None
        logger.warning("Server stopped")

    async def restart(self):
        """Restart the server to apply new routes/websockets or whatever."""
        await self.stop()
        await self.start()
        logger.info("Server restarted.")

def route(path, method='GET', **kwargs):
    """
    Route decorator to mark methods as HTTP endpoints
    
    Args:
        path (str): URL path for the route
        method (str): HTTP method (GET, POST, etc)
        **kwargs: Additional arguments passed to the router
    """
    def decorator(func):
        func._is_route = True
        func._route_path = path
        func._route_method = method
        func._route_kwargs = kwargs
        return func
    return decorator

def websocket(path, **kwargs):
    """
    WebSocket decorator to mark methods as WebSocket endpoints
    
    Args:
        path (str): URL path for the WebSocket endpoint
        **kwargs: Additional arguments passed to the WebSocket handler
    """
    def decorator(func):
        func._is_websocket = True
        func._ws_path = path
        func._ws_kwargs = kwargs
        return func
    return decorator