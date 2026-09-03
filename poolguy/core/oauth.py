import os
import random
import webbrowser
import asyncio
import aiohttp
import time
import logging
from urllib.parse import urlparse, urlencode
from aiohttp import web
from .webserver import WebServer, closeBrowser
from .storage import StorageFactory

logger = logging.getLogger(__name__)

tokenEndpoint = "https://id.twitch.tv/oauth2/token"
oauthEndpoint = "https://id.twitch.tv/oauth2/authorize"
validateEndoint = "https://id.twitch.tv/oauth2/validate"
TOKEN_NAME = "twitch"
APP_TOKEN_NAME = "twitch_app"
REFRESH_FAILURE_LIMIT = 5
REFRESH_BACKOFF_BASE_SECONDS = 10
REFRESH_BACKOFF_MAX_SECONDS = 240
VALIDATE_INTERVAL_SECONDS = 3600
EXPIRY_MARGIN_SECONDS = 1800
PUBLIC_REFRESH_TOKEN_TTL_SECONDS = 2592000

class TokenHandler:
    def __init__(
            self, 
            client_id=None, 
            client_secret=None, 
            redirect_uri=None, 
            scopes=None, 
            storage=None, 
            webserver=None, 
            browser=None,
            token_endpoint=None,
            oauth_endpoint=None,
            validate_endpoint=None
        ):
        if not client_id:
            raise ValueError(f"Client id required!")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes or []
        self.client_type = "public" if not client_secret else "confidential"
        self.token_endpoint = token_endpoint or tokenEndpoint
        self.oauth_endpoint = oauth_endpoint or oauthEndpoint
        self.validate_endpoint = validate_endpoint or validateEndoint
        self.storage = storage or StorageFactory.create_storage('sqlite')
        if redirect_uri:
            parsed_uri = urlparse(redirect_uri)
            self.server = webserver or WebServer(parsed_uri.hostname, parsed_uri.port)
            self.server.add_route(f"/{parsed_uri.path.lstrip('/')}", self._callback_handler)
        else:
            self.server = None
        if isinstance(browser, dict):
            self.browser, path = browser.popitem()
            webbrowser.register(self.browser, None, webbrowser.BackgroundBrowser(path))
        else:
            self.browser = browser
        self.user_id = None
        self._granted_scopes = ()
        self._token_lock = asyncio.Lock()
        self._app_lock = asyncio.Lock()
        self._refresh_event = asyncio.Event()
        self._refresh_task = None
        self._state = None
        self._auth_code = None
        self._auth_future = None
        self._token = None
        self._running = False
        
    async def _callback_handler(self, request):
        if request.query.get('state') != self._state:
            return web.Response(text="State mismatch. Authorization failed.", status=400)
        if 'error' in request.query:
            return web.Response(text=f"Authorization failed: {request.query['error']}", status=400)
        self._auth_code = request.query.get('code')
        if self._auth_code and not self._auth_future.done():
            self._auth_future.set_result(self._auth_code)
        return web.Response(text=closeBrowser, content_type='text/html', charset='utf-8')

    async def _get_auth_code(self):
        logger.warning(f"Getting Twitch Oauth code...")
        if not self.server.is_running():
            await self.server.start()
        self._auth_future = asyncio.Future()
        self._state = os.urandom(14).hex()
        params = urlencode({
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(self.scopes),
            'state': self._state
        })
        auth_link = f"{self.oauth_endpoint}?{params}"
        try:
            bro = webbrowser.get(self.browser)
            bro.open(auth_link, new=1)
            logger.warning(f"Waiting for oauth code... {auth_link}")
        except Exception as e:
            logger.exception(f"Couldn't open {self.browser or 'default'} browser! Copy auth link manually:\n{auth_link}")
        await self._auth_future
        if self.server.route_len() <= 1:
            await self.server.stop()
        logger.warning(f"Got oauth code!")

    def _merge_token(self, new):
        if "refresh_token" not in new:
            if self.client_type == "public":
                logger.error(f"Refresh response for public client missing rotated refresh token, grant is dead")
                new["refresh_token"] = ""
                new["refresh_token_expires_at"] = time.time()
            else:
                new["refresh_token"] = (self._token or {}).get("refresh_token", "")
        elif self.client_type == "public":
            new["refresh_token_expires_at"] = time.time() + PUBLIC_REFRESH_TOKEN_TTL_SECONDS
        if isinstance(new.get("scope"), str):
            new["scope"] = [s for s in new["scope"].split(" ") if s]
        return new

    async def _token_request(self, headers, data):
        async with aiohttp.ClientSession() as session:
            async with session.post(self.token_endpoint, headers=headers, data=data) as resp:
                if resp.status != 200:
                    raise Exception(f"Token request failed: {await resp.text()}")
                token = self._merge_token(await resp.json())
                if data.get("grant_type") == "authorization_code":
                    token["requested_scopes"] = list(self.scopes)
                token["expires_time"] = time.time() + int(token["expires_in"])
                await self.storage.save_token(TOKEN_NAME, token)
                self._token = token
                return token

    async def _refresh_with_backoff(self):
        data = {
            'client_id': self.client_id,
            **({'client_secret': self.client_secret} if self.client_secret else {}),
            'grant_type': 'refresh_token',
            'refresh_token': (self._token or {}).get('refresh_token') or ''
                }
        headers = {
            'Accept': 'application/json',
            "Content-Type": "application/x-www-form-urlencoded"
                }
        delay = REFRESH_BACKOFF_BASE_SECONDS
        for attempt in range(REFRESH_FAILURE_LIMIT):
            self._refresh_event.clear()
            try:
                await self._token_request(headers, data)
                return self._token
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception(f"Refresh failed, attempt {attempt + 1}/{REFRESH_FAILURE_LIMIT} (current token kept in use)... {e}")
            finally:
                self._refresh_event.set()
            if attempt == REFRESH_FAILURE_LIMIT - 1:
                break
            if self.client_type == "public":
                expires_at = (self._token or {}).get("refresh_token_expires_at")
                if expires_at and expires_at <= time.time():
                    logger.error(f"Public client refresh token past 30-day expiry, automated recovery impossible")
                    break
            await asyncio.sleep(delay + random.uniform(0, delay / 2))
            delay = min(delay * 2, REFRESH_BACKOFF_MAX_SECONDS)
        logger.error(f"Automated refresh exhausted after {REFRESH_FAILURE_LIMIT} failures, falling back to interactive re-auth")
        await self._get_new_token()

    async def _refresh(self):
        logger.warning(f"Refreshing Twitch token...")
        async with self._token_lock:
            await self._refresh_with_backoff()
        return self._token

    async def _get_new_token(self):
        await self._get_auth_code()
        logger.warning(f"Getting twitch new token...")
        data = {
            'client_id': self.client_id,
            **({'client_secret': self.client_secret} if self.client_secret else {}),
            'code': self._auth_code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.redirect_uri
            }
        heads = {'Accept': 'application/json'}
        return await self._token_request(heads, data)

    async def get_app_token(self):
        if not self.client_secret:
            raise ValueError(f"Client secret required for client credentials grant!")
        async with self._app_lock:
            app = await self.storage.load_token(APP_TOKEN_NAME)
            if app and app.get("access_time", 0) + int(app["expires_in"]) - 60 > time.time():
                return app
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'client_credentials'
                }
            heads = {'Accept': 'application/json'}
            async with aiohttp.ClientSession() as session:
                async with session.post(self.token_endpoint, headers=heads, data=data) as resp:
                    if resp.status != 200:
                        raise Exception(f"App token request failed: {await resp.text()}")
                    app = await resp.json()
            app["token_type"] = "app"
            app["access_time"] = time.time()
            await self.storage.save_token(APP_TOKEN_NAME, app)
            return app

    async def _validate_auth(self):
        logger.info(f'Validating twitch token...')
        heads = {'Authorization': f'OAuth {self._token["access_token"]}'}
        async with aiohttp.ClientSession() as session:
            async with session.get(self.validate_endpoint, headers=heads) as response:
                auth_check = await response.json()
                match response.status:
                    case 200:
                        return True, auth_check
                    case 401:
                        return False, auth_check
                    case _:
                        response.raise_for_status()
                        return response.status

    def _scope_check(self, data):
        granted = [s for s in (data.get("scopes") or []) if isinstance(s, str)]
        missing = [s for s in self._token.get("requested_scopes", []) if s not in granted]
        if missing:
            logger.error(f"Required scopes no longer granted: {missing}")
            return False
        reduced = set(self._granted_scopes) - set(granted)
        if reduced:
            logger.warning(f"Scope reduction detected, lost: {sorted(reduced)}")
        self._granted_scopes = tuple(granted)
        return True

    async def _refresher(self):
        self._running = True
        self._refresh_event.set()
        logger.debug(f"token _refresher started...")
        while self._running:
            result, output = await self._validate_auth()
            if not result:
                logger.info(f'Validation failed: {output}')
                await self._refresh()
                continue
            self.user_id = output.get("user_id")
            if not self._scope_check(output):
                self._token = await self._get_new_token()
                continue
            expires_in = output.get("expires_in")
            if expires_in is None or expires_in <= EXPIRY_MARGIN_SECONDS:
                logger.debug(f"Access token expires in {expires_in}s, refreshing...")
                await self._refresh()
                continue
            try:
                await asyncio.sleep(VALIDATE_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                self._running = False

    async def _run(self):
        self._refresh_task = None
        self._refresh_task = asyncio.create_task(self._refresher())

    async def _login(self, token=None):
        if token:
            self._token = token
        else:
            logger.warning(f"Attempting to load saved token...")
            stored = await self.storage.load_token(TOKEN_NAME)
            self._token = stored or None
        if not self._token:
            logger.warning(f"No saved twitch token, starting interactive auth...")
            self._token = await self._get_new_token()
        result, output = await self._validate_auth()
        if not result:
            logger.warning(f"Stored twitch token invalid at startup ({output}), attempting automatic recovery...")
            self.user_id = None
            await self._refresh()
            result, output = await self._validate_auth()
            if not result:
                raise Exception(f"Twitch token validation failed after refresh/re-auth: {output}")
        logger.warning(f"Loaded token!")
        self.user_id = output.get("user_id")
        if not self._running:
            await self._run()

    async def stop(self):
        self._running = False
        if not self._refresh_task:
            return
        self._refresh_task.cancel()
        try:
            await self._refresh_task
        except asyncio.CancelledError:
            pass
        self._refresh_task = None
        logger.warning(f"token _refresher stopped...")

    async def get_token(self):
        if not self._token:
            await self._login()
        await self._refresh_event.wait()
        return self._token

    async def __call__(self):
        return await self.get_token()
