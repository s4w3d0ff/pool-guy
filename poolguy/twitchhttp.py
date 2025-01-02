import webbrowser
from quart import Quart, request
from urllib.parse import urlparse, urlencode
from .utils import aiohttp, ColorLogger, asyncio, closeBrowser

logger = ColorLogger(__name__)

tokenEndpoint = "https://id.twitch.tv/oauth2/token"
oauthEndpoint="https://id.twitch.tv/oauth2/authorize"
validateEndoint="https://id.twitch.tv/oauth2/validate"

class RequestHandler:
    def __init__(self, client_id, client_secret, redirect_uri, scopes, app=None):
        self.app = app or Quart("webserver")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self.token = None
        self._token_event = asyncio.Event()
        self.emotes = {}
        self.login_info = None
        self.user_id = None
        # Parse redirect URI to get host, port, and path
        parsed_uri = urlparse(redirect_uri)
        self.callback_path = parsed_uri.path.lstrip('/')  # Remove leading slash (why?)
        self.host = parsed_uri.hostname
        self.port = parsed_uri.port
        # Register callback route
        self._register_callback_route()

    def _register_callback_route(self):
        """Registers the dynamic callback route based on redirect_uri."""
        @self.app.route(f'/{self.callback_path}')
        async def callback():
            """Handles the OAuth callback."""
            code = request.args.get('code')
            if not code:
                logger.error("No code provided in callback.")
                return "Error: No code provided", 400
            
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
                    # Set the event to signal token acquisition
                    self._token_event.set()
            return closeBrowser

    async def start_oauth_flow(self):
        """Starts the OAuth flow by opening the browser and waits for token acquisition."""
        if not self.token:
            webbrowser.open(self.get_auth_url())
            # Wait for the token to be set in the callback
            await self._token_event.wait()

    async def login(self):
        await self.start_oauth_flow()
        await self.validate_auth()
        # Get login info
        r = await self.getUsers()
        self.login_info = r[0]
        self.user_id = self.login_info['id']
        logger.warning(f'Logged in as {self.login_info}')

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
        auth_check = await self.api_request("GET", validateEndoint)
        logger.info(f"Auth validation response: {auth_check}")

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
                logger.info("OAuth token refreshed.")
                await self.validate_auth()
                return self.token

    async def api_request(self, method, url, *args, **kwargs):
        """Handles API requests with retry logic for expired tokens or rate limits."""
        kwargs['headers'] = self.get_headers()
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, *args, **kwargs) as response:
                logger.info(f"[{method}] {url} [{response.status}]")
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
                except Exception as e:
                    logger.error(f"Error decoding JSON: {e}")
                    return response