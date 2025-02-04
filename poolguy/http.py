from .utils import aiohttp, asyncio
from .utils import ColorLogger, urlparse
from .oauth import TokenHandler, WebServer, StorageFactory

logger = ColorLogger(__name__)

class RequestHandler:
    def __init__(self, client_id=None, client_secret=None, redirect_uri=None, scopes=[], webserver=None, storage=None, storage_type='json', browser=None, static_dirs=[], base_dir=None, **kwargs):
        self.client_id = client_id
        # Storage
        self.storage = storage or StorageFactory.create_storage(storage_type, **kwargs)
        # Webserver
        parsed_uri = urlparse(redirect_uri)
        self.server = webserver or WebServer(
            parsed_uri.hostname, parsed_uri.port, static_dirs, base_dir
        )
        # TokenHandler
        self.token_handler = TokenHandler(
            client_id, client_secret, redirect_uri, scopes, self.storage, self.server, browser
        )
        self.user_id = None
    
    async def login(self, token=None):
        await self.token_handler._login(token)
        while not self.user_id:
            await asyncio.sleep(1)
            self.user_id = self.token_handler.user_id

    async def get_headers(self):
        """Generates headers for API requests."""
        token = await self.token_handler.get_token()
        return {
            'Client-ID': self.client_id,
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token["access_token"]}'
        }

    async def api_request(self, method, url, *args, **kwargs):
        """Handles API requests with retry logic for expired tokens or rate limits."""
        kwargs['headers'] = await self.get_headers()
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, *args, **kwargs) as response:
                logger.debug(f"[{method}] {url} {kwargs} [{response.status}]")
                match response.status:
                    case 401:
                        logger.error("Token expired, refreshing...")
                        await self.token_handler._refresh_token()
                        kwargs['headers'] = await self.get_headers()
                        return await self.api_request(method, url, *args, **kwargs)
                    case 429:
                        ratelimit_reset = int(response.headers.get('Ratelimit-Reset'))
                        wait_time = ratelimit_reset - int(time.time()) + 3
                        logger.warning(f"Rate limited, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                        return await self.api_request(method, url, *args, **kwargs)
                response.raise_for_status()
                try:
                    return await response.json()
                except:
                    logger.debug(f"Error decoding JSON, returned full response.")
                    return response
