from .utils import webbrowser, os, asyncio, aiohttp, time, json
from .utils import ColorLogger, closeBrowser, urlparse, urlencode, web
from .webserver import WebServer
from .storage import StorageFactory

logger = ColorLogger(__name__)

tokenEndpoint = "https://id.twitch.tv/oauth2/token"
oauthEndpoint = "https://id.twitch.tv/oauth2/authorize"
validateEndoint = "https://id.twitch.tv/oauth2/validate"

class TokenHandler:
    def __init__(self, client_id=None, client_secret=None, redirect_uri=None, scopes=None, storage=None, webserver=None, browser=None):
        if not client_id or not client_secret:
            raise ValueError(f"Client id and secret required!")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes or []
        #--------
        self.storage = storage or StorageFactory.create_storage('json')
        parsed_uri = urlparse(self.redirect_uri)
        self.server = webserver or WebServer(parsed_uri.hostname, parsed_uri.port)
        self.server.add_route(f"/{parsed_uri.path.lstrip('/')}", self._callback_handler)
        if isinstance(browser, dict):
            self.browser, path = browser.popitem()
            webbrowser.register(self.browser, None, webbrowser.BackgroundBrowser(path))
        else:
            self.browser = browser
        #--------
        self.user_id = None
        self._refresh_event = asyncio.Event()
        self._refresh_task = None
        self._state = None
        self._auth_code = None
        self._auth_future = None
        self._token = None
        self._running = False
        
    async def _callback_handler(self, request):
        """ Handles the oauth code callback """
        if request.query.get('state') != self._state:
            return web.Response(text="State mismatch. Authorization failed.", status=400)
        if 'error' in request.query:
            return web.Response(text=f"Authorization failed: {request.query['error']}", status=400)
        self._auth_code = request.query.get('code')
        if self._auth_code and not self._auth_future.done():
            self._auth_future.set_result(self._auth_code)
        return web.Response(text=closeBrowser, content_type='text/html', charset='utf-8')

    async def _get_auth_code(self):
        """ Opens browser to get oauth code to use for token """
        logger.warning(f"Opening browser to get Oauth code...")
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
        auth_link = f"{oauthEndpoint}?{params}"
        try:
            # open webbrowser with auth link
            bro = webbrowser.get(self.browser)
            bro.open(auth_link, new=1)
            logger.warning(f"Waiting for oauth code... {auth_link}")
        except:
            # cant open webbrowser, show auth link for user to copy/paste
            logger.error(f"Couldn't open {self.browser or 'default'} browser!: \n{auth_link}")
        # wait for auth code
        await self._auth_future
        if self.server.route_len() <= 1:
            # nothing else is registered to the webserver, stop it
            await self.server.stop()
        logger.warning(f"Got oauth code!")

    async def _token_request(self, headers, data):
        """ Base token request method, used for new or refreshing tokens """
        async with aiohttp.ClientSession() as session:
            async with session.post(tokenEndpoint, headers=headers, data=data) as resp:
                if resp.status != 200:
                    raise Exception(f"Token request failed: {await resp.text()}")
                if self._token:
                    # temp store refresh token (incase one isnt sent)
                    r_token = self._token['refresh_token']
                self._token = await resp.json()
                if "refresh_token" not in self._token:
                    self._token['refresh_token'] = r_token 
                self._token["expires_time"] = time.time()+int(self._token['expires_in'])
                await self.storage.save_token(self._token, name="twitch")
                return self._token

    async def _refresh(self):
        """ Refresh oauth token, get new token if refresh fails """
        logger.warning(f"Refreshing token...")
        # pause 'self.get_token'
        self._refresh_event.clear()
        try:
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'refresh_token',
                'refresh_token': self._token['refresh_token']
                }
            headers = {
                'Accept': 'application/json',
                "Content-Type": "application/x-www-form-urlencoded"
                }
            out = await self._token_request(headers, data)
        except Exception as e:
            logger.error(f"Refreshing token failed! {e}")
            out = await self._get_new_token()
        # resume 'self.get_token'
        self._refresh_event.set()
        return out

    async def _get_new_token(self):
        """ Get a new oauth token using the oauth code, get code if we dont have one yet """
        await self._get_auth_code()
        logger.warning(f"Getting new token...")
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': self._auth_code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.redirect_uri
            }
        heads = {'Accept': 'application/json'}
        return await self._token_request(heads, data)

    async def _validate_auth(self):
        """ Validate currently loaded token """
        heads = {'Authorization': f'OAuth {self._token["access_token"]}'}
        async with aiohttp.ClientSession() as session:
            async with session.get(validateEndoint, headers=heads) as response:
                auth_check = await response.json()
                logger.debug(f"Auth validation response: \n{json.dumps(auth_check, indent=2)}")
                match response.status:
                    case 200:
                        return True, auth_check
                    case 401:
                        return False, auth_check
                    case _:
                        response.raise_for_status()
                        return response.status

    async def _refresher(self):
        """ Validates token every hour, refreshes if expires """
        self._running = True
        self._refresh_event.set()
        logger.debug(f"token _refresher started...")
        while self._running:
            logger.info(f'Validating twitch token...')
            result, output = await self._validate_auth()
            if not result: # validate failed
                logger.info(f'Validation failed: {output}')
                await self._refresh()
                continue
            self.user_id = output["user_id"]
            if self._token['expires_time'] <= time.time()+3600:
                # refresh if expiring in the next hour
                await self._refresh()
                continue
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                self._running = False

    async def _run(self):
        """ Starts/creates the _refresher task """
        self._refresh_task = None
        self._refresh_task = asyncio.create_task(self._refresher())

    async def _login(self, token=None):
        """ Checks storage for saved token, gets new token if one isnt found. Starts the token refresher task """
        if token:
            self._token = token
        else:
            logger.warning(f"Attempting to load saved token...")
            self._token = await self.storage.load_token(name="twitch")
        if self._token:
            logger.warning(f"Loaded token!")
        else:
            self._token = await self._get_new_token()
        if not self._running:
            await self._run()
        else:
            result, output = await self._validate_auth()
            if not result: # validate failed
                logger.info(f'Validation failed: {output}')
                await self._refresh()

    async def stop(self):
        """ Stops the _refresher task """
        self._running = False
        self._refresh_task.cancel()
        try:
            await self._refresh_task
        except asyncio.CancelledError:
            pass
        self._refresh_task = None
        logger.warning(f"token _refresher stopped...")

    async def get_token(self):
        """ Returns current token after checking if the token needs to be refreshed """
        if not self._token:
            await self._login()
        # wait for refresh if needed
        await self._refresh_event.wait()
        return self._token

    async def __call__(self):
        return await self.get_token()