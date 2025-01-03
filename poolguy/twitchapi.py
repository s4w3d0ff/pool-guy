from .utils import json, os, aiohttp, re
from .utils import ColorLogger, datetime
from .twitchhttp import RequestHandler, urlparse, urlencode

logger = ColorLogger(__name__)

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
    "goals": f"{apiUrlPrefix}/goals",
    "chat": f"{apiUrlPrefix}/chat/messages",
    "conduits": f"{apiUrlPrefix}/eventsub/conduits",
    "shards": f"{apiUrlPrefix}/eventsub/conduits/shards",
    "bits": f"{apiUrlPrefix}/bits/leaderboard",
    "channel_editors": f"{apiUrlPrefix}/channels/editors",
    "channel_emotes": f"{apiUrlPrefix}/chat/emotes",
    "global_emotes": f"{apiUrlPrefix}/chat/emotes/global",
    "channel_badges": f"{apiUrlPrefix}/chat/badges",
    "global_badges": f"{apiUrlPrefix}/chat/badges/global",
    "channel_points": f"{apiUrlPrefix}/channel_points/custom_rewards",
    "categories": f"{apiUrlPrefix}/games",
    "streams": f"{apiUrlPrefix}/streams",
    "stream_markers": f"{apiUrlPrefix}/streams/markers",
    "videos": f"{apiUrlPrefix}/videos",
    "schedule": f"{apiUrlPrefix}/schedule",
    "teams": f"{apiUrlPrefix}/teams",
    "tags": f"{apiUrlPrefix}/tags/streams",
    "automod": f"{apiUrlPrefix}/moderation/enforcements/status",
    "soundtrack": f"{apiUrlPrefix}/soundtrack/current_track",
    "charity": f"{apiUrlPrefix}/charity/campaigns",
    "whispers": f"{apiUrlPrefix}/whispers",
    "extensions": f"{apiUrlPrefix}/extensions/configuration",
    "analytics": f"{apiUrlPrefix}/analytics/extensions",
    "users_follows": f"{apiUrlPrefix}/users/follows",
    "channel_vips": f"{apiUrlPrefix}/channels/vips",
    "blocked_terms": f"{apiUrlPrefix}/moderation/blocked_terms",
    "shield_mode": f"{apiUrlPrefix}/moderation/shield_mode"
}

eventsubdocurl = "https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/"

def fetch_eventsub_types(dir="db/eventsub_versions"):
    # Check if we already have today's data
    filename = f"{dir}/{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    if os.path.exists(filename):
        # Load and return existing data
        logger.info(f"fetch_eventsub_types: loaded {filename}")
        with open(filename, 'r') as f:
            return json.load(f)
    import requests
    from bs4 import BeautifulSoup
    # Ensure db directory exists
    os.makedirs(dir, exist_ok=True)
    response = requests.get(eventsubdocurl)
    logger.info(f"[GET] {eventsubdocurl} [{response.status_code}]")
    if response.status_code != 200:
        raise Exception("Failed to fetch webpage") 
    soup = BeautifulSoup(response.text, "html.parser")
    eventsub_types = {}
    # Locate the table containing subscription types
    table = soup.find("table")
    if not table:
        raise Exception("Failed to locate the table in the webpage")
    # Extract rows from the table body
    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all("td")
        if len(cells) >= 3:
            name = cells[1].find("code").get_text(strip=True)  # Extract 'Name'
            version = cells[2].find("code").get_text(strip=True)  # Extract 'Version'
            eventsub_types[name] = version
    with open(filename, 'w') as f:
        json.dump(eventsub_types, f, indent=4)
    return eventsub_types


eventChannels = fetch_eventsub_types()


class TwitchApi(RequestHandler):
    #============================================================================
    # EventSub Methods ================================================================
    async def createEventSub(self, event, session_id, bid=None):
        uid = str(self.user_id)
        if bid:
            bid = str(bid)
        match event:
            case 'channel.follow':
                condition = {'broadcaster_user_id': bid or uid, 'moderator_user_id': uid}
            case 'channel.chat.message':
                condition = {'broadcaster_user_id': bid or uid, 'user_id': uid}
            case 'channel.chat.clear':
                condition = {'broadcaster_user_id': bid or uid, 'user_id': uid}
            case 'channel.raid':
                condition = {'to_broadcaster_user_id': uid}
            case 'channel.shield_mode.begin':
                condition = {'broadcaster_user_id': bid or uid, 'moderator_user_id': uid}
            case 'channel.shield_mode.end':
                condition = {'broadcaster_user_id': bid or uid, 'moderator_user_id': uid}
            case 'user.update':
                condition = {'user_id': uid}
            case 'user.authorization.grant':
                condition = {'client_id': str(self.client_id)}
            case 'user.authorization.revoke':
                condition = {'client_id': str(self.client_id)}
            case _:
                condition = {'broadcaster_user_id': bid or uid}
        logger.info(f'[createEventSub] -> {event} condition:{condition}')
        try:
            data = {
                "type": event,
                "version": str(eventChannels[event]),
                "condition": condition,
                "transport": {'method': 'websocket', 'session_id': session_id}
            }
            r = await self.api_request("post", apiEndpoints['eventsub'], data=json.dumps(data))
            logger.debug(f"data: \n{json.dumps(data)}")
            logger.debug(f"response: \n{r}")
            return r
        except Exception as e:
            logger.error(f"Failed to create EventSub subscription: \n{e}")
            logger.error(f"Request data was: \n{json.dumps(data)}")
            raise

    async def deleteEventSub(self, id):
        try:
            r = await self.api_request("delete", f"{apiEndpoints['eventsub']}?id={id}")
            return True
        except:
            return False

    async def getEventSubs(self, status=None, type=None):
        params = {}
        if status:
            params["status"] = status
        if type:
            params["type"] = type
        r = await self.api_request("get", apiEndpoints['eventsub'], params=params)
        return r
    
    #============================================================================
    # Channel Methods ================================================================
    async def getChannelInfo(self, broadcaster_id=None):
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self.api_request("get", apiEndpoints['broadcast'], params=params)
        return r['data']

    async def getFollowedChannels(self, user_id=None, broadcaster_id=None):
        params = {
            "user_id": user_id or self.user_id,
            "broadcaster_id": broadcaster_id
        }
        r = await self.api_request("get", apiEndpoints['users_follows'], params=params)
        return r['data']

    async def getChannelFollowers(self, broadcaster_id=None, first='all'):
        if first != 'all':
            params = {"broadcaster_id": broadcaster_id or self.user_id, "first":first}
            r = await self.api_request("get", apiEndpoints['followers'], params=params)
            return r['data']
        params = {"broadcaster_id": broadcaster_id or self.user_id, "first":100}
        r = await self.api_request("get", apiEndpoints['followers'], params=params)
        page = r['pagination']
        followers = r['data']
        while "cursor" in page:
            params['after'] = page['cursor']
            r = await self.api_request("get", apiEndpoints['followers'], params=params)
            page = r['pagination']
            followers += r['data']
        return followers

    #============================================================================
    # Chat Methods ================================================================
    async def sendChatMessage(self, message, broadcaster_id=None, sender_id=None):
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "sender_id": sender_id or self.user_id,
            "message": message
        }
        r = await self.api_request("post", apiEndpoints['chat'], data=json.dumps(data))
        return r['data']

    async def getChatters(self, broadcaster_id=None, moderator_id=None):
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "moderator_id": moderator_id or self.user_id
        }
        r = await self.api_request("get", f"{apiEndpoints['chat']}/chatters", params=params)
        return r['data']

    async def getChatSettings(self, broadcaster_id=None, moderator_id=None):
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "moderator_id": moderator_id or self.user_id
        }
        r = await self.api_request("get", f"{apiEndpoints['chat']}/settings", params=params)
        return r['data']

    async def updateChatSettings(self, broadcaster_id=None, settings=None):
        data = settings or {}
        data["broadcaster_id"] = broadcaster_id or self.user_id
        r = await self.api_request("patch", f"{apiEndpoints['chat']}/settings", data=json.dumps(data))
        return r['data']

    async def sendAnnouncement(self, broadcaster_id=None, message="", color="primary"):
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "message": message,
            "color": color
        }
        r = await self.api_request("post", f"{apiEndpoints['chat']}/announcements", data=json.dumps(data))
        return r['data']

    async def sendShoutout(self, from_broadcaster_id=None, to_broadcaster_id=None, moderator_id=None):
        data = {
            "from_broadcaster_id": from_broadcaster_id or self.user_id,
            "to_broadcaster_id": to_broadcaster_id,
            "moderator_id": moderator_id or self.user_id
        }
        r = await self.api_request("post", f"{apiEndpoints['chat']}/shoutouts", data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Clips Methods ================================================================
    async def createClip(self, broadcaster_id=None):
        data = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self.api_request("post", apiEndpoints['clips'], data=json.dumps(data))
        return r['data']

    async def getClips(self, broadcaster_id=None, game_id=None, clip_id=None):
        params = {}
        if broadcaster_id:
            params["broadcaster_id"] = broadcaster_id
        if game_id:
            params["game_id"] = game_id
        if clip_id:
            params["id"] = clip_id
        r = await self.api_request("get", apiEndpoints['clips'], params=params)
        return r['data']
        
    #============================================================================
    # Commercial Methods ================================================================
    async def startCommercial(self, broadcaster_id=None, length=30):
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "length": length
        }
        r = await self.api_request("post", apiEndpoints['commercial'], data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Bits Methods ================================================================
    async def getBitsLeaderboard(self, count=10, period="all", started_at=None):
        params = {
            "count": count,
            "period": period
        }
        if started_at:
            params["started_at"] = started_at
        r = await self.api_request("get", apiEndpoints['bits'], params=params)
        return r['data']
        
    #============================================================================
    # Games Methods ================================================================
    async def getTopGames(self, first=20):
        params = {"first": first}
        r = await self.api_request("get", apiEndpoints['categories'], params=params)
        return r['data']
        
    #============================================================================
    # Goals Methods ================================================================
    async def getCreatorGoals(self, broadcaster_id=None):
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self.api_request("get", apiEndpoints['goals'], params=params)
        return r['data']
        
    #============================================================================
    # Hype Train Methods ================================================================
    async def getHypeTrainEvents(self, broadcaster_id=None):
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self.api_request("get", apiEndpoints['hype_train'], params=params)
        return r['data']
        
    #============================================================================
    # Moderation Methods ================================================================
    async def getBannedUsers(self, broadcaster_id=None):
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self.api_request("get", apiEndpoints['banned_users'], params=params)
        return r['data']

    async def banUser(self, broadcaster_id=None, user_id=None, reason=None, duration=None):
        data = {
            "data": {
                "user_id": user_id,
                "reason": reason
            }
        }
        if duration:
            data["data"]["duration"] = duration
        r = await self.api_request("post", apiEndpoints['ban'], data=json.dumps(data))
        return r['data']

    async def unbanUser(self, broadcaster_id=None, user_id=None):
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self.api_request("delete", apiEndpoints['ban'], params=params)
        return r['data']
        
    #============================================================================
    # Moderator Methods ================================================================
    async def getModerators(self, broadcaster_id=None):
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self.api_request("get", apiEndpoints['moderators'], params=params)
        return r['data']

    async def addModerator(self, broadcaster_id=None, user_id=None):
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self.api_request("post", apiEndpoints['moderators'], data=json.dumps(data))
        return r['data']

    async def removeModerator(self, broadcaster_id=None, user_id=None):
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self.api_request("delete", apiEndpoints['moderators'], params=params)
        return r['data']
        
    #============================================================================
    # VIP Methods ================================================================
    async def getVIPs(self, broadcaster_id=None):
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self.api_request("get", apiEndpoints['channel_vips'], params=params)
        return r['data']

    async def addVIP(self, broadcaster_id=None, user_id=None):
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self.api_request("post", apiEndpoints['channel_vips'], data=json.dumps(data))
        return r['data']

    async def removeVIP(self, broadcaster_id=None, user_id=None):
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self.api_request("delete", apiEndpoints['channel_vips'], params=params)
        return r['data']
        
    #============================================================================
    # Chat Warning ================================================================
    async def warnUser(self, broadcaster_id=None, user_id=None, reason=None):
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id,
            "reason": reason
        }
        r = await self.api_request("post", f"{apiEndpoints['chat']}/warnings", data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Poll Methods ================================================================
    async def getPolls(self, broadcaster_id=None):
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self.api_request("get", apiEndpoints['polls'], params=params)
        return r['data']

    async def createPoll(self, broadcaster_id=None, title=None, choices=None, duration=300):
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "title": title,
            "choices": choices,
            "duration": duration
        }
        r = await self.api_request("post", apiEndpoints['polls'], data=json.dumps(data))
        return r['data']

    async def endPoll(self, broadcaster_id=None, poll_id=None, status="TERMINATED"):
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "id": poll_id,
            "status": status
        }
        r = await self.api_request("patch", apiEndpoints['polls'], data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Prediction Methods ================================================================
    async def getPredictions(self, broadcaster_id=None):
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self.api_request("get", apiEndpoints['predictions'], params=params)
        return r['data']

    async def createPrediction(self, broadcaster_id=None, title=None, outcomes=None, prediction_window=300):
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "title": title,
            "outcomes": outcomes,
            "prediction_window": prediction_window
        }
        r = await self.api_request("post", apiEndpoints['predictions'], data=json.dumps(data))
        return r['data']

    async def endPrediction(self, broadcaster_id=None, id=None, status="RESOLVED", winning_outcome_id=None):
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "id": id,
            "status": status
        }
        if winning_outcome_id:
            data["winning_outcome_id"] = winning_outcome_id
        r = await self.api_request("patch", apiEndpoints['predictions'], data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Raid Methods ================================================================
    async def startRaid(self, from_broadcaster_id=None, to_broadcaster_id=None):
        data = {
            "from_broadcaster_id": from_broadcaster_id or self.user_id,
            "to_broadcaster_id": to_broadcaster_id
        }
        r = await self.api_request("post", apiEndpoints['raids'], data=json.dumps(data))
        return r['data']

    async def cancelRaid(self, broadcaster_id=None):
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self.api_request("delete", apiEndpoints['raids'], params=params)
        return r['data']
        
    #============================================================================
    # Search Methods ================================================================
    async def searchCategories(self, query, first=20):
        params = {"query": query, "first": first}
        r = await self.api_request("get", f"{apiEndpoints['categories']}/search", params=params)
        return r['data']

    async def searchChannels(self, query, first=20, live_only=False):
        params = {
            "query": query,
            "first": first,
            "live_only": live_only
        }
        r = await self.api_request("get", f"{apiEndpoints['broadcast']}/search", params=params)
        return r['data']
        
    #============================================================================
    # Stream Methods ================================================================
    async def getStreams(self, first=100, **kwargs):
        kwargs['first'] = first
        query_string = urlencode(kwargs, doseq=True)
        baseurl = f"{apiEndpoints['streams']}?{query_string}"
        r = await self.api_request("get", baseurl)
        data = r['data']
        page = r['pagination']
        while "cursor" in page:
            nurl = baseurl + f'&after={page['cursor']}'
            r = await self.api_request("get", nurl)
            s = r['data']
            page = r['pagination']
            data += r['data']
        return data

    async def getFollowedStreams(self, user_id=None, first=20):
        params = {
            "user_id": user_id or self.user_id,
            "first": first
        }
        r = await self.api_request("get", f"{apiEndpoints['streams']}/followed", params=params)
        return r['data']

    async def createStreamMarker(self, description=None):
        data = {
            "user_id": self.user_id,
            "description": description
        }
        r = await self.api_request("post", apiEndpoints['stream_markers'], data=json.dumps(data))
        return r['data']

    async def getStreamMarkers(self, user_id=None, video_id=None, first=20):
        params = {
            "user_id": user_id,
            "video_id": video_id,
            "first": first
        }
        r = await self.api_request("get", apiEndpoints['stream_markers'], params=params)
        return r['data']
        
    #============================================================================
    # Subscription Methods ================================================================
    async def getBroadcasterSubscriptions(self, broadcaster_id=None, first='all'):
        if first != 'all':
            params = {"broadcaster_id": broadcaster_id or self.user_id, "first": first}
            r = await self.api_request("get", apiEndpoints['subscriptions'], params=params)
            return r['data']
        params = {"broadcaster_id": broadcaster_id or self.user_id, "first": 100}
        r = await self.api_request("get", apiEndpoints['subscriptions'], params=params)
        s = r['data']
        page = r['pagination']
        subs = {'t1': [], 't2': [], 't3': []}
        for i in s:
            subs['t' + i['tier'][0]].append(i["user_name"])
        while "cursor" in page:
            params['after'] = page['cursor']
            r = await self.api_request("get", apiEndpoints['subscriptions'], params=params)
            s = r['data']
            page = r['pagination']
            for i in s:
                subs['t' + i['tier'][0]].append(i["user_name"])
        return subs

    async def checkUserSubscription(self, broadcaster_id, user_id=None):
        params = {
            "broadcaster_id": broadcaster_id,
            "user_id": user_id or self.user_id
        }
        r = await self.api_request("get", apiEndpoints['subscriptions'], params=params)
        return r['data']
        
    #============================================================================
    # Tag Methods ================================================================
    async def getAllStreamTags(self, first=20):
        params = {"first": first}
        r = await self.api_request("get", apiEndpoints['tags'], params=params)
        return r['data']

    async def getStreamTags(self, broadcaster_id=None):
        params = {
            "broadcaster_id": broadcaster_id or self.user_id
        }
        r = await self.api_request("get", apiEndpoints['tags'], params=params)
        return r['data']
        
    #============================================================================
    # User Methods ================================================================
    async def getUsers(self, ids=None, logins=None):
        params = {}
        if ids:
            params["id"] = ids if isinstance(ids, list) else [ids]
        if logins:
            params["login"] = logins if isinstance(logins, list) else [logins]
        r = await self.api_request("get", apiEndpoints['user'], params=params)
        return r['data']

    async def sendWhisper(self, to_user_id, message):
        data = {
            "from_user_id": self.user_id,
            "to_user_id": to_user_id,
            "message": message
        }
        r = await self.api_request("post", apiEndpoints['whispers'], data=json.dumps(data))
        return r['data']
        
    #=========================================================================
    # Extras ===================================================================

    async def unsubAllEvents(self):
        r = await self.getEventSubs()
        for sub in r['data']:
            if sub['status'] == "enabled":
                continue
            else:
                logger.info(f"{sub['type']}[{sub['status']}]: {sub['condition']}")
                await self.deleteEventSub(sub['id'])
        logger.warning(f"Removed all inactive websocket subs")

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