from .utils import aiohttp, asyncio, webbrowser, json, os
from .utils import ColorLogger, closeBrowser, urlparse, urlencode
from .webserver import WebServer
from aiohttp import web

logger = ColorLogger(__name__)

tokenEndpoint = "https://id.twitch.tv/oauth2/token"
oauthEndpoint = "https://id.twitch.tv/oauth2/authorize"
validateEndoint = "https://id.twitch.tv/oauth2/validate"

class RequestHandler:
    def __init__(self, client_id, client_secret, redirect_uri, scopes):
        # Parse redirect URI to get host, port, and path
        parsed_uri = urlparse(redirect_uri)
        self.callback_path = parsed_uri.path.lstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self.token = None
        self._token_event = asyncio.Event()
        self.login_info = None
        self.user_id = None
        
        # Initialize web server
        self.server = WebServer(parsed_uri.hostname, parsed_uri.port)
        
        # Register callback route
        self.server.add_route(f'/{self.callback_path}', self.callback_handler)

    async def callback_handler(self, request):
        """Handles the OAuth callback."""
        code = request.query.get('code')
        if not code:
            logger.error("No code provided in callback.")
            return web.Response(text="Error: No code provided", status=400)
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                tokenEndpoint,
                data={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'code': code,
                    'grant_type': 'authorization_code',
                    'redirect_uri': self.redirect_uri
                },
                headers={'Accept': 'application/json'}
            ) as response:
                response.raise_for_status()
                token_data = await response.json()
                self.token = {
                    "access_token": token_data['access_token'],
                    "refresh_token": token_data['refresh_token']
                }
                logger.info("Access token obtained and stored.")
                self._token_event.set()
                
        return web.Response(
            text=closeBrowser,
            content_type='text/html',
            charset='utf-8'
        )

    async def login(self, browser=None):
        """Start the server and initiate OAuth flow."""
        await self.server.start()
        if not self.token:
            await self.start_oauth_flow(browser)
        if not self.login_info:
            self.login_info = await self.validate_auth()
        self.user_id = self.login_info['user_id']
        logger.debug(f'Logged in as: \n{json.dumps(self.login_info, indent=2)}')
        return self.login_info

    async def start_oauth_flow(self, browser=None):
        """Starts the OAuth flow by opening the browser and waits for token acquisition."""
        bro = webbrowser.get(browser)
        bro.open(self.get_auth_url(), new=1)
        # Wait for the token to be set in the callback
        await self._token_event.wait()
        logger.warning("OAuth flow finished.")
    
    def get_auth_url(self):
        """Generates the OAuth authorization URL."""
        params = urlencode({
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(self.scopes)
        })
        return f"{oauthEndpoint}?{params}"

    def get_headers(self):
        """Generates headers for API requests."""
        return {
            'Client-ID': self.client_id,
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.token.get("access_token")}'
        }
    
    async def validate_auth(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(validateEndoint, headers={'Authorization': f'OAuth {self.token.get("access_token")}'}) as response:
                response.raise_for_status()
                auth_check = await response.json()
        logger.debug(f"Auth validation response: \n{json.dumps(auth_check, indent=2)}")
        return auth_check

    async def refresh_oauth_token(self):
        """Refreshes the OAuth token using the refresh token."""
        logger.warning("Refreshing OAuth token...")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                tokenEndpoint,
                data={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'grant_type': 'refresh_token',
                    'refresh_token': self.token.get('refresh_token')
                },
                headers={'Accept': 'application/json'}
            ) as response:
                response.raise_for_status()
                token_data = await response.json()
                self.token = {
                    "access_token": token_data['access_token'],
                    "refresh_token": token_data['refresh_token']
                }
                logger.warning("OAuth token refreshed.")
                await self.validate_auth()
                return self.token

    async def api_request(self, method, url, *args, **kwargs):
        """Handles API requests with retry logic for expired tokens or rate limits."""
        kwargs['headers'] = self.get_headers()
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, *args, **kwargs) as response:
                logger.debug(f"[{method}] {url} {kwargs} [{response.status}]")
                match response.status:
                    case 401:
                        logger.error("Token expired, refreshing...")
                        await self.refresh_oauth_token()
                        kwargs['headers']['Authorization'] = f'Bearer {self.token["access_token"]}'
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