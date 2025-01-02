from twitchio.ext import commands
import urllib.parse

from .utils import logging, json, asyncio, time, cfg, re, aiohttp, ColorLogger

cfg = cfg['TWITCH']

logger = ColorLogger(__name__)

oauthLink = f"https://id.twitch.tv/oauth2/authorize?client_id={cfg['client_id']}&redirect_uri={cfg['redirect_uri']}&response_type=code&scope={' '.join(cfg['scopes'])}"
oauthTURL = 'https://id.twitch.tv/oauth2/token'

apiUrlPrefix = "https://api.twitch.tv/helix"

emoteEndpoint = "https://static-cdn.jtvnw.net/emoticons/v2/"

apiEndpoints = {
    "subscriptions": f"{apiUrlPrefix}/subscriptions",
    "polls": f"{apiUrlPrefix}/polls",
    "hype_train": f"{apiUrlPrefix}/hypetrain/events",
    "raids": f"{apiUrlPrefix}/raids",
    "predictions": f"{apiUrlPrefix}/predictions",
    "broadcast": f"{apiUrlPrefix}/channels",
    "redemptions": f"{apiUrlPrefix}/channel_points/custom_rewards/redemptions",
    "commercial": f"{apiUrlPrefix}/channels/commercial",
    "user": f"{apiUrlPrefix}/users",
    "clips": f"{apiUrlPrefix}/clips",
    "banned_users": f"{apiUrlPrefix}/moderation/banned",
    "ban": f"{apiUrlPrefix}/moderation/bans",
    "moderators": f"{apiUrlPrefix}/moderation/moderators",
    "eventsub": f"{apiUrlPrefix}/eventsub/subscriptions",
    "followers": f"{apiUrlPrefix}/channels/followers",
    "emotes": f"{apiUrlPrefix}/chat/emotes/user",
    "goals": f"{apiUrlPrefix}/goals"
    }


async def get_Oauth_token(code):
    logger.warning(f"[Main] Got Oauth Code, getting access token...")
    data = {
            'client_id': cfg["client_id"],
            'client_secret': cfg["client_secret"],
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': cfg['redirect_uri']
        }
    headers = {'Accept': 'application/json'}
    async with aiohttp.ClientSession() as session:
        async with session.post(oauthTURL, data=data, headers=headers) as response:
            response.raise_for_status()
            r = await response.json()
            return {"authtoken": r['access_token'], "rauthtoken": r['refresh_token']}


class BaseBot(commands.Bot):
    def __init__(self, rtoken=None, *args, **kwargs):
        super().__init__(prefix=cfg['prefix'], client_secret=cfg["client_secret"], *args, **kwargs)
        self.TOKEN = {'token': kwargs.get('token'), 'rtoken': rtoken}
        self.emotes = {}

    def getHeads(self):
        return {
                'Client-ID': cfg["client_id"], 
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.TOKEN["token"]}'
                }

    async def afterReady(self):
        self.emotes = await self.get7tvEmotes()

    async def event_ready(self):
        logger.warning(f'Bot logged in as [{self.nick}]')
        await self.join_channels([self.nick])
        #await self.afterReady()

    async def event_command_error(self, context: commands.Context, error: Exception):
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.ArgumentParsingFailed):
            await context.send(error.message)
        elif isinstance(error, commands.MissingRequiredArgument):
            await context.send("You're missing an argument: " + error.name) 
        else:
            logger.error(f"[Bot] Command Error {error}")

    async def sendPOST(self, url, *args, **kwargs):
        async with aiohttp.ClientSession() as session:
            async with session.post(url, *args, **kwargs) as r:
                logger.info(f"[POST] {url.replace(apiUrlPrefix, '')[:42]} [{r.status}]")
                match r.status:
                    case 401: # Access token expired 
                        logger.error(f"[POST] {url.replace(apiUrlPrefix, '')[:42]} Token Expired")
                        r = await self.refresh_oauth_token()
                        kwargs['headers']['Authorization'] = f'Bearer {self.TOKEN["token"]}'
                        r = await self.sendPOST(url, *args, **kwargs) # try again
                    case 429: # Rate limited
                        ratelimit_reset = int(r.headers.get('Ratelimit-Reset'))
                        wait_time = ratelimit_reset - int(time.time()) + 3
                        logger.error(f"[POST] {url.replace(apiUrlPrefix, '')[:42]} Ratelimit, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                        r = await self.sendPOST(url, *args, **kwargs) # try again
                    case _:
                        r.raise_for_status()
                try:
                    out = await r.json()
                except:
                    logger.error(f"[POST] {url.replace(apiUrlPrefix, '')[:42]}\n{json.dumps(r, indent=2)}")
                    out = r
                return out


    async def sendGET(self, url, *args, **kwargs):
        async with aiohttp.ClientSession() as session:
            async with session.get(url, *args, **kwargs) as r:
                logger.info(f"[GET] {url.replace(apiUrlPrefix, '')[:42]} [{r.status}]")
                match r.status:
                    case 401: # Access token expired 
                        logger.error(f"[GET] {url.replace(apiUrlPrefix, '')[:42]} Token Expired")
                        r = await self.refresh_oauth_token()
                        kwargs['headers']['Authorization'] = f'Bearer {self.TOKEN["token"]}'
                        r = await self.sendGET(url, *args, **kwargs) # try again
                    case 429: # Rate limited
                        ratelimit_reset = int(r.headers.get('Ratelimit-Reset'))
                        wait_time = ratelimit_reset - int(time.time()) + 3
                        logger.error(f"[GET] {url.replace(apiUrlPrefix, '')[:42]} Ratelimit, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                        r = await self.sendGET(url, *args, **kwargs) # try again
                    case _:
                        r.raise_for_status()
                try:
                    out = await r.json()
                except:
                    logger.error(f"[GET] {url.replace(apiUrlPrefix, '')[:42]}\n{json.dumps(r, indent=2)}")
                    out = r
                return out

    async def refresh_oauth_token(self):
        logger.warning(f"Refreshing oauth token...")
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': urllib.parse.quote(self.TOKEN['rtoken']),
            'client_id': cfg["client_id"],
            'client_secret': cfg["client_secret"]
            }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        async with aiohttp.ClientSession() as session:
            async with session.post(oauthTURL, data=data, headers=headers) as r:
                r.raise_for_status()
                r = await r.json()
                self.TOKEN = {'token': r['access_token'], 'rtoken': r['refresh_token']}
                self._connection._token = r['access_token']
                logger.warning(f"Got new oauth token!")
                return r

    async def timeoutViewer(self, userid, duration, reason=''):
        r = await self.sendPOST(
            apiEndpoints['ban'], 
            headers=self.getHeads(),
            data=json.dumps(
                {
                    'broadcaster_id': self.user_id,
                    'moderator_id': self.user_id,
                    'data': {'user_id': str(userid), 'duration': duration, 'reason': reason}
                }
                ))

    async def getGoals(self):
        url = apiEndpoints['goals'] + f"?broadcaster_id={self.user_id}"
        r = await self.sendGET(url, headers=self.getHeads())
        gcfg = cfg["goalIDs"]
        return [{'gid': g['id'], 'gname': gcfg[g['id']], 'current': int(g['current_amount']), 'target': int(g['target_amount'])} for g in r['data']]

    async def getSubList(self, nametype="user_name"):
        surl = apiEndpoints['subscriptions'] + f'?broadcaster_id={self.user_id}&first=100'
        r = await self.sendGET(surl, headers=self.getHeads())
        s = r['data']
        page = r['pagination']
        subs = {'t1': [], 't2': [], 't3': []}
        for i in s:
            subs['t' + i['tier'][0]].append(i[nametype])
        while "cursor" in page:
            r = await self.sendGET(surl + f"&after={page['cursor']}", headers=self.getHeads())
            s = r['data']
            page = r['pagination']
            for i in s:
                subs['t' + i['tier'][0]].append(i[nametype])
        return subs

    async def getFollowerList(self, nametype="user_name"):
        furl = apiEndpoints['followers'] + f'?broadcaster_id={self.user_id}&first=100'
        r = await self.sendGET(furl, headers=self.getHeads())
        s = r['data']
        page = r['pagination']
        followers = []
        for i in s:
            followers.append(i[nametype])
        while "cursor" in page:
            r = await self.sendGET(furl + f"&after={page['cursor']}", headers=self.getHeads())
            s = r['data']
            page = r['pagination']
            for i in s:
                followers.append(i[nametype])
        return followers

        
    async def get7tvEmotes(self):
        cdnurl = "https://cdn.7tv.app/emote/"
        emotes = {}
        async with aiohttp.ClientSession() as session:
            async with session.get("https://7tv.io/v3/emote-sets/global") as response:
                response.raise_for_status()
                rmotes = await response.json()
                rmotes = rmotes['emotes']
                for e in rmotes:
                    emotes[e['name']] = cdnurl + e['id'] + "/4x.webp"

            async with session.get("https://7tv.io/v3/users/twitch/" + str(self.user_id)) as response:
                response.raise_for_status()
                rmotes = await response.json()
                rmotes = rmotes['emote_set']['emotes']
                for e in rmotes:
                    emotes[e['name']] = cdnurl + e['id'] + "/4x.webp"
        return emotes
        
    async def parseTTVEmote(self, id, format, theme_mode="dark", scale="3.0"):
        return f'<img height="40px" src="{emoteEndpoint}{id}/{format}/{theme_mode}/{scale}">'

    async def parse7TVEmotes(self, text):
        for name, url in self.emotes.items():
            text = re.sub(r'\b' + re.escape(name) + r'\b', f'<img height="40px" src="{url}">', text)
        return text
        
    @commands.command(name="help", aliases=["commands"])
    async def help_command(self, ctx: commands.Context):
        prefix = str(self._prefix).replace("'", "").replace("[", "").replace("]", "")
        commlist = str([k for k in self.commands.keys()]).replace("'", "").replace("[", "").replace("]", "")
        await ctx.reply(f"Prefix: {prefix} | Commands: {commlist}")
        