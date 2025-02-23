from .utils import aiohttp, asyncio
from .utils import ColorLogger, urlparse
from .oauth import TokenHandler, WebServer, StorageFactory

logger = ColorLogger(__name__)

class RequestHandler:
    def __init__(self, client_id=None, client_secret=None, redirect_uri=None, scopes=None, storage=None, browser=None, webserver=None, **kwargs):
        self.client_id = client_id
        # Storage
        if isinstance(storage, str):
            self.storage = StorageFactory.create_storage(storage)
        else:
            self.storage = storage
        # Webserver
        parsed_uri = urlparse(redirect_uri)
        self.server = webserver or WebServer(
                host=parsed_uri.hostname, 
                port=parsed_uri.port, 
                **kwargs
            )
        # TokenHandler
        self.token = TokenHandler(
                client_id=client_id, 
                client_secret=client_secret, 
                redirect_uri=redirect_uri, 
                scopes=scopes or [], 
                storage=self.storage, 
                webserver=self.server, 
                browser=browser
            )
        self.user_id = None

    async def shutdown(self):
        try:
            await self.server.stop()
        except Exception as e:
            logger.error(f"{e}")
        try:
            await self.token.stop()
        except Exception as e:
            logger.error(f"{e}")

    async def login(self, token=None):
        await self.token._login(token)
        while not self.user_id:
            await asyncio.sleep(1)
            self.user_id = self.token.user_id
        logger.warning("Authorized with Twitch!")
        
    async def _headers(self):
        """Generates headers for API requests."""
        token = await self.token()
        return {
            'Client-ID': self.client_id,
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token["access_token"]}'
        }

    async def _request(self, method, url, *args, **kwargs):
        """Handles API requests with retry logic for expired tokens or rate limits."""
        kwargs['headers'] = await self._headers()
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, *args, **kwargs) as response:
                logger.debug(f"[{method}] {url} {kwargs} [{response.status}]")
                match response.status:
                    case 401:
                        logger.error("Token expired, refreshing...")
                        await self.token._refresh()
                        kwargs['headers'] = await self._headers()
                        return await self._request(method, url, *args, **kwargs)
                    case 429:
                        ratelimit_reset = int(response.headers.get('Ratelimit-Reset'))
                        wait_time = ratelimit_reset - int(time.time()) + 3
                        logger.warning(f"Rate limited, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                        return await self._request(method, url, *args, **kwargs)
                response.raise_for_status()
                try:
                    return await response.json()
                except:
                    logger.debug(f"Error decoding JSON, returned full response.")
                    return response
