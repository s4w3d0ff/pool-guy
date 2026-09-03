import aiohttp
import asyncio
import json
import logging 
import time
from urllib.parse import urlparse
from .core import TokenHandler, WebServer, StorageFactory
from .core.logctx import new_request_id, _request_id

logger = logging.getLogger(__name__)

BOT_NAME = "pool-guy"
BOT_VERSION = "0.1.9"


class ApiRequestError(Exception):
    def __init__(self, status, message, url=None):
        super().__init__(f"Twitch API request failed with HTTP {status}: {message}")
        self.status = status
        self.message = message
        self.url = url


class RequestHandler:
    def __init__(
            self, 
            client_id=None, 
            client_secret=None, 
            redirect_uri=None, 
            scopes=None, 
            storage=None, 
            browser=None, 
            webserver=None, 
            **kwargs
        ):
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
        self._ratelimit_reset_at = 0

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
            'Authorization': f'Bearer {token["access_token"]}',
            'User-Agent': f"{BOT_NAME}/{BOT_VERSION}"
        }

    async def _request(self, method, url, *args, **kwargs):
        """Handles API requests with retry logic for expired tokens or rate limits."""
        if not _request_id.get():
            _request_id.set(new_request_id())
        wait = self._ratelimit_reset_at - time.time()
        if wait > 0:
            logger.debug(f"Rate limit budget exhausted, waiting {wait:.1f}s until reset")
            await asyncio.sleep(wait)
        kwargs['headers'] = await self._headers()
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, *args, **kwargs) as response:
                logger.debug(f"[{method}] {url} {kwargs} [{response.status}]")
                remaining = response.headers.get('Ratelimit-Remaining')
                reset = response.headers.get('Ratelimit-Reset')
                if remaining == '0' and reset is not None:
                    self._ratelimit_reset_at = int(reset) + 1
                match response.status:
                    case 401:
                        logger.error("Token expired, refreshing...")
                        old_token = (self.token._token or {}).get("access_token")
                        new_token = await self.token._refresh()
                        if not new_token or new_token.get("access_token") == old_token:
                            raise Exception(f"Twitch auth refresh failed for {url}, token unchanged")
                        kwargs['headers'] = await self._headers()
                        return await self._request(method, url, *args, **kwargs)
                    case 429:
                        ratelimit_reset = int(response.headers.get('Ratelimit-Reset'))
                        wait_time = ratelimit_reset - int(time.time()) + 3
                        logger.warning(f"Rate limited! [{response.headers["X-Cache"]}] {wait_time = }")
                        await asyncio.sleep(wait_time)
                        return await self._request(method, url, *args, **kwargs)
                try:
                    response.raise_for_status()
                except aiohttp.ClientResponseError as e:
                    body = await response.text()
                    message = body[:500] if body else str(e)
                    try:
                        parsed = json.loads(body)
                        if isinstance(parsed, dict):
                            parts = [str(parsed.get(key)) for key in ("error", "message") if parsed.get(key)]
                            if parts:
                                message = ": ".join(parts)
                    except (json.JSONDecodeError, TypeError):
                        pass
                    raise ApiRequestError(response.status, message, url=url) from e
                match method.lower():
                    case "get" | "post":
                        try:
                            return await response.json()
                        except (aiohttp.ContentTypeError, json.JSONDecodeError) as e:
                            logger.warning(f"JSON decode failed for {url}: {e}. Returning raw response!")
                            return response
                    case _:
                        return response