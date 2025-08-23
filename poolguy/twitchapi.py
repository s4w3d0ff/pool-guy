import json
import aiohttp
import re
import asyncio
import logging
from urllib.parse import urlencode
from .http import RequestHandler

logger = logging.getLogger(__name__)

apiUrlPrefix = "https://api.twitch.tv/helix"
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
    "cheermotes": f"{apiUrlPrefix}/bits/cheermotes",
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

async def fetch_eventsub_versions(eventsubdocurl="https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/"):
    """Fetch and parse Twitch Eventsub documentation to extract event channels. This is dumb, but it works for now."""
    # Fetch HTML content
    async with aiohttp.ClientSession() as session:
        async with session.get(eventsubdocurl) as response:
            logger.info(f"[GET] {eventsubdocurl} [{response.status}]")
            if response.status != 200:
                raise Exception("Failed to fetch webpage")
            html_content = await response.text()

    # Locate the `<tbody>` section
    h1_pattern = r'<h1 id="subscription-types">Subscription Types</h1>'
    tbody_pattern = r'<tbody>(.*?)</tbody>'
    tbody_match = re.search(f'{h1_pattern}.*?{tbody_pattern}', html_content, re.S)

    if not tbody_match:
        logger.error("Could not locate the <tbody> section under Subscription Types.")
        raise ValueError("Unable to locate the <tbody> section under Subscription Types.")
    
    out = []
    tbody_content = tbody_match.group(1)
    # Extract rows from the `<tbody>` section
    rows = re.findall(r'<tr>(.*?)</tr>', tbody_content, re.S)
    logger.debug(f"Extracted rows: {rows}")
    for row in rows:
        # Extract text from <code> tags, ignoring attributes like class
        codes = re.findall(r'<code[^>]*>(.*?)</code>', row)
        logger.debug(f"Extracted codes from row: {codes}")
        if len(codes) >= 2:
            subtype, version = codes[0], codes[1]
            if len(subtype) > 4 and len(version) < 5:
                out.append({
                    "name": subtype,
                    "version": version
                })
    if not out:
        logger.error(f"No valid subscription types found. Rows extracted: {rows}")
        raise ValueError("No valid subscription types found.")
    return out


class TwitchApi(RequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_flag = False
        
    async def _continuePage(self, method, url, page, **kwargs):
        """ Helper function to handle pagination in Twitch API calls """
        out = []
        while "cursor" in page:
            if 'params' in kwargs:
                kwargs['params']['after'] = page['cursor']
            if 'data' in kwargs:
                data = json.loads(kwargs['data'])
                data['after'] = page['cursor']
                kwargs['data'] = json.dumps(data)
            r = await self._request(method, url, **kwargs)
            out += r['data']
            page = r['pagination']
        return out
        
    #============================================================================
    # EventSub Methods ================================================================
    async def _get_eventsub_version(self, name):
        """Get eventsub version by name, updates once per initialization."""
        if not self._init_flag:
            o = await fetch_eventsub_versions()
            logger.debug(f"{o = }")
            for item in o:
                await self.storage.insert("subpub_versions", item)
            self._init_flag = True
        out = await self.storage.query("subpub_versions", where="name = ?", params=(name,))
        return out[0]['version'] if out else None

    async def _determine_eventsub_condition(self, event, bid=None):
        """Determine the event condition based on the event type."""
        uid = str(self.user_id)
        if bid:
            bid = str(bid)
        match event:
            case 'channel.chat.message_delete' | 'channel.chat.clear_user_messages' | 'channel.chat.notification' | 'channel.chat.clear':
                condition = {'broadcaster_user_id': bid or uid, 'user_id': uid}
            case 'channel.chat.message':
                condition = {'broadcaster_user_id': bid or uid, 'user_id': uid}
            case 'channel.raid':
                condition = {'to_broadcaster_user_id': uid}
            case 'channel.follow' | 'channel.shield_mode.begin' | 'channel.shield_mode.end' | 'channel.suspicious_user.message':
                condition = {'broadcaster_user_id': bid or uid, 'moderator_user_id': uid}
            case 'user.update':
                condition = {'user_id': uid}
            case 'user.authorization.grant' | 'user.authorization.revoke':
                condition = {'client_id': str(self.client_id)}
            case _:
                condition = {'broadcaster_user_id': bid or uid}
        return condition

    async def createEventSub(self, event, session_id, bid=None):
        """ Create an EventSub subscription """
        try:
            data = json.dumps({
                "type": event,
                "version": await self._get_eventsub_version(event),
                "condition": await self._determine_eventsub_condition(event, bid),
                "transport": {'method': 'websocket', 'session_id': session_id}
            })
            logger.debug(f'Sending [createEventSub] -> {data}')
            return await self._request("post", apiEndpoints['eventsub'], data=data)
        except Exception as e:
            logger.exception(f"Failed to create EventSub subscription: \n")
            raise

    async def deleteEventSub(self, id):
        try:
            r = await self._request("delete", f"{apiEndpoints['eventsub']}?id={id}")
            return True
        except:
            return False

    async def getEventSubs(self, status=None, type=None):
        params = {}
        if status:
            params["status"] = status
        if type:
            params["type"] = type
        r = await self._request("get", apiEndpoints['eventsub'], params=params)
        return r

    #============================================================================
    # Badges Methods ================================================================
    async def getGlobalChatBadges(self):
        """ Get global chat badges """
        r = await self._request("get", apiEndpoints['global_badges'])
        return r['data']
        
    async def getChannelChatBadges(self, broadcaster_id=None):
        """ Get channel chat badges """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", apiEndpoints['channel_badges'], params=params)
        return r['data']

    #============================================================================
    # Channel Methods ================================================================
    async def getChannelInfo(self, broadcaster_id=None):
        """ Get channel information """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", apiEndpoints['broadcast'], params=params)
        return r['data']

    async def getFollowedChannels(self, user_id=None, broadcaster_id=None):
        """ Get followed channels """
        params = {
            "user_id": user_id or self.user_id,
            "broadcaster_id": broadcaster_id
        }
        r = await self._request("get", apiEndpoints['users_follows'], params=params)
        return r['data']

    async def getChannelFollowers(self, broadcaster_id=None, first=None):
        """ Get channel followers """
        method = "get"
        url = apiEndpoints['followers']
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        if first:
            params["first"] = first
        r = await self._request(method, url, params=params)
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, url, r['pagination'], params=params)
        return out

    async def getChannelStreamSchedule(self, broadcaster_id=None, first=None):
        """ Get channel stream schedule """
        method = "get"
        url = apiEndpoints['schedule']
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        if first:
            params["first"] = first
        r = await self._request(method, url, params=params)
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, url, r['pagination'], params=params)
        return out


    #============================================================================
    # Chat Methods ================================================================
    async def sendChatMessage(self, message, broadcaster_id=None):
        """ Send a chat message to the channel """
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "sender_id": self.user_id,
            "message": message[:399] # 400 char limit
        }
        r = await self._request("post", apiEndpoints['chat'], data=json.dumps(data))
        return r['data']

    async def getChatters(self, broadcaster_id=None, moderator_id=None):
        """ Get the list of chatters in the channel """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "moderator_id": moderator_id or self.user_id
        }
        r = await self._request("get", f"{apiEndpoints['chat']}/chatters", params=params)
        return r['data']

    async def getChatSettings(self, broadcaster_id=None, moderator_id=None):
        """ Get the chat settings for the channel """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "moderator_id": moderator_id or self.user_id
        }
        r = await self._request("get", f"{apiEndpoints['chat']}/settings", params=params)
        return r['data']

    async def updateChatSettings(self, broadcaster_id=None, settings=None):
        """ Update the chat settings for the channel """
        data = settings or {}
        data["broadcaster_id"] = broadcaster_id or self.user_id
        r = await self._request("patch", f"{apiEndpoints['chat']}/settings", data=json.dumps(data))
        return r['data']

    async def sendAnnouncement(self, broadcaster_id=None, message="", color="primary"):
        """ Send an announcement to the channel's chat """
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "message": message,
            "color": color
        }
        r = await self._request("post", f"{apiEndpoints['chat']}/announcements", data=json.dumps(data))
        return r['data']

    async def sendShoutout(self, to_broadcaster_id=None, from_broadcaster_id=None, moderator_id=None):
        """ Send a shoutout to another channel """
        data = {
            "from_broadcaster_id": from_broadcaster_id or self.user_id,
            "to_broadcaster_id": to_broadcaster_id,
            "moderator_id": moderator_id or self.user_id
        }
        r = await self._request("post", f"{apiEndpoints['chat']}/shoutouts", data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Clips Methods ================================================================
    async def createClip(self, broadcaster_id=None):
        """ Create a clip from the broadcaster's stream """
        data = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("post", apiEndpoints['clips'], data=json.dumps(data))
        return r['data']

    async def getClips(self, broadcaster_id=None, game_id=None, clip_id=None, first=None):
        """ Get clips from the broadcaster's channel """
        method = "get"
        url = apiEndpoints['clips']
        params = {
            "first": first or 20,
            "broadcaster_id": broadcaster_id or self.user_id,
        }
        if game_id:
            params["game_id"] = game_id
        if clip_id:
            params["id"] = clip_id
        r = await self._request(method, url, params=params)
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, url, r['pagination'], params=params)
        return out
        
    #============================================================================
    # Commercial Methods ================================================================
    async def startCommercial(self, broadcaster_id=None, length=30):
        """ Start a commercial on the broadcaster's channel """
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "length": length
        }
        r = await self._request("post", apiEndpoints['commercial'], data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Bits Methods ================================================================
    async def getBitsLeaderboard(self, count=10, period="all", started_at=None):
        """ Get the Bits leaderboard for a broadcaster """
        method = "get"
        url = apiEndpoints['bits']
        params = {"count": count, "period": period}
        if started_at:
            params["started_at"] = started_at
        r = await self._request(method, url, params=params)
        return r['data']

    async def getCheermotes(self, broadcaster_id=None):
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", apiEndpoints['cheermotes'], params=params)
        return r['data']  

    #============================================================================
    # Games Methods ================================================================
    async def getTopGames(self, first=None):
        """ Get the top games for a broadcaster """
        method = "get"
        url = apiEndpoints['categories']+"/top"
        params = {"first": first or 20}
        r = await self._request(method, url, params=params)
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, url, r['pagination'], params=params)
        return out


    #============================================================================
    # Goals Methods ================================================================
    async def getCreatorGoals(self, broadcaster_id=None):
        """ Get the goals for a broadcaster """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", apiEndpoints['goals'], params=params)
        return r['data']
        
    #============================================================================
    # Hype Train Methods ================================================================
    async def getHypeTrainEvents(self, broadcaster_id=None):
        """ Get the hype train events for a broadcaster """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", apiEndpoints['hype_train'], params=params)
        return r['data']
        
    #============================================================================
    # Moderation Methods ================================================================
    async def getBannedUsers(self, broadcaster_id=None):
        """ Get the banned users for a broadcaster """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", apiEndpoints['banned_users'], params=params)
        return r['data']

    async def banUser(self, broadcaster_id=None, user_id=None, reason=None, duration=None):
        """ Ban a user from the channel """
        data = {
            "data": {
                "user_id": user_id,
                "reason": reason
            }
        }
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "moderator_id": self.user_id,
        }
        if duration:
            data["data"]["duration"] = duration
        r = await self._request("post", apiEndpoints['ban'], params=params, data=json.dumps(data))
        return r['data']

    async def unbanUser(self, broadcaster_id=None, user_id=None):
        """ Unban a user from the channel """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self._request("delete", apiEndpoints['ban'], params=params)
        return r['data']
        
    #============================================================================
    # Moderator Methods ================================================================
    async def getModerators(self, broadcaster_id=None):
        """ Get moderators of the channel """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", apiEndpoints['moderators'], params=params)
        return r['data']

    async def addModerator(self, broadcaster_id=None, user_id=None):
        """ Add a moderator to the channel """
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self._request("post", apiEndpoints['moderators'], data=json.dumps(data))
        return r['data']

    async def removeModerator(self, broadcaster_id=None, user_id=None):
        """ Remove a moderator from the channel """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self._request("delete", apiEndpoints['moderators'], params=params)
        return r['data']
        
    #============================================================================
    # VIP Methods ================================================================
    async def getVIPs(self, broadcaster_id=None):
        """ Get a list of VIPs for the channel """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", apiEndpoints['channel_vips'], params=params)
        return r['data']

    async def addVIP(self, broadcaster_id=None, user_id=None):
        """ Add a VIP to the channel """
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self._request("post", apiEndpoints['channel_vips'], data=json.dumps(data))
        return r['data']

    async def removeVIP(self, broadcaster_id=None, user_id=None):
        """ Remove a VIP from the channel """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self._request("delete", apiEndpoints['channel_vips'], params=params)
        return r['data']
        
    #============================================================================
    # Chat Warning ================================================================
    async def warnUser(self, broadcaster_id=None, user_id=None, reason=None):
        """ Warn a user in the chat """
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id,
            "reason": reason
        }
        r = await self._request("post", f"{apiEndpoints['chat']}/warnings", data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Poll Methods ================================================================
    async def getPolls(self, broadcaster_id=None, first=None):
        """ Get polls for a channel """
        method = "get"
        url = apiEndpoints['polls']
        params = {"broadcaster_id": broadcaster_id or self.user_id, "first": first or 20}
        r = await self._request(method, url, params=params)
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, url, r['pagination'], params=params)
        return out

    async def createPoll(self, broadcaster_id=None, title=None, choices=None, duration=300):
        """ Create a poll for a channel """
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "title": title,
            "choices": choices,
            "duration": duration
        }
        r = await self._request("post", apiEndpoints['polls'], data=json.dumps(data))
        return r['data']

    async def endPoll(self, broadcaster_id=None, poll_id=None, status="TERMINATED"):
        """ End a poll for a channel """
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "id": poll_id,
            "status": status
        }
        r = await self._request("patch", apiEndpoints['polls'], data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Prediction Methods ================================================================
    async def getPredictions(self, broadcaster_id=None, first=None):
        """ Get predictions for a channel """
        method = "get"
        url = apiEndpoints['predictions']
        params = {"broadcaster_id": broadcaster_id or self.user_id, "first": first or 20}
        r = await self._request(method, url, params=params)
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, url, r['pagination'], params=params)
        return out

    async def createPrediction(self, broadcaster_id=None, title=None, outcomes=None, prediction_window=300):
        """ Create a prediction for a channel """
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "title": title,
            "outcomes": outcomes,
            "prediction_window": prediction_window
        }
        r = await self._request("post", apiEndpoints['predictions'], data=json.dumps(data))
        return r['data']

    async def endPrediction(self, broadcaster_id=None, id=None, status="RESOLVED", winning_outcome_id=None):
        """ End a prediction for a channel """
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "id": id,
            "status": status
        }
        if winning_outcome_id:
            data["winning_outcome_id"] = winning_outcome_id
        r = await self._request("patch", apiEndpoints['predictions'], data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Raid Methods ================================================================
    async def startRaid(self, from_broadcaster_id=None, to_broadcaster_id=None):
        """ Start a raid to another channel """
        data = {
            "from_broadcaster_id": from_broadcaster_id or self.user_id,
            "to_broadcaster_id": to_broadcaster_id
        }
        r = await self._request("post", apiEndpoints['raids'], data=json.dumps(data))
        return r['data']

    async def cancelRaid(self, broadcaster_id=None):
        """ Cancel a raid """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("delete", apiEndpoints['raids'], params=params)
        return r['data']
        
    #============================================================================
    # Search Methods ================================================================
    async def searchCategories(self, query, first=None):
        """ Search for categories """
        method = "get"
        url = f"{apiEndpoints['categories']}/search"
        params = {"query": query, "first": first or 20}
        r = await self._request(method, url, params=params)
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, url, r['pagination'], params=params)
        return out

    async def searchChannels(self, query, first=None, live_only=False):
        """ Search for channels """
        method = "get"
        url = f"{apiEndpoints['broadcast']}/search"
        params = {"query": query, "first": first or 20, "live_only": live_only}
        r = await self._request(method, url, params=params)
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, url, r['pagination'], params=params)
        return out
        
    #============================================================================
    # Stream Methods ================================================================
    async def getStreams(self, first=None, **kwargs):
        """ Get streams """
        method = "get"
        url = apiEndpoints['streams']
        kwargs['first'] = first or 100
        query_string = urlencode(kwargs, doseq=True)
        r = await self._request(method, f"{url}?{query_string}")
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, f"{url}?{query_string}", r['pagination'], params=kwargs)
        return out

    async def getFollowedStreams(self, user_id=None, first=None):
        """ Get followed streams """
        method = "get"
        url = f"{apiEndpoints['streams']}/followed"
        params = {"user_id": user_id or self.user_id}
        if first:
            params["first"] = first
        r = await self._request(method, url, params=params)
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, url, r['pagination'], params=params)
        return out

    async def createStreamMarker(self, description=None):
        """ Create a stream marker """
        data = {
            "user_id": self.user_id,
            "description": description
        }
        r = await self._request("post", apiEndpoints['stream_markers'], data=json.dumps(data))
        return r['data']

    async def getStreamMarkers(self, user_id=None, video_id=None, first=None):
        """ Get stream markers """
        method = "get"
        url = apiEndpoints['stream_markers']
        params = {"user_id": user_id, "video_id": video_id, "first": first or 20}
        r = await self._request(method, url, params=params)
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, url, r['pagination'], params=params)
        return out
        
    #============================================================================
    # Subscription Methods ================================================================
    async def getBroadcasterSubscriptions(self, user_id=None, broadcaster_id=None, first=None):
        """ Get broadcaster subscriptions """
        method = "get"
        url = apiEndpoints['subscriptions']
        params = {"broadcaster_id": broadcaster_id or self.user_id, "first": first or 100}
        if user_id:
            if isinstance(user_id, list):
                params["user_id"] = user_id[:100]  # Limit to max 100 IDs
            else:
                params["user_id"] = [user_id]  # Single ID as list
        r = await self._request(method, url, params=params)
        out = r['data']
        if 'pagination' in r and 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, url, r['pagination'], params=params)
        return out

    async def checkUserSubscription(self, broadcaster_id=None, user_id=None):
        """ Check if a user is subscribed to a broadcaster """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id or self.user_id
        }
        r = await self._request("get", apiEndpoints['subscriptions'], params=params)
        return r['data']
        
    #============================================================================
    # Tag Methods ================================================================
    async def getAllStreamTags(self, first=None):
        """ Get all stream tags """
        method = "get"
        url = apiEndpoints['tags']
        params = {"first": first or 20}
        r = await self._request(method, url, params=params)
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, url, r['pagination'], params=params)
        return out

    async def getStreamTags(self, broadcaster_id=None):
        """ Get stream tags for a broadcaster """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id
        }
        r = await self._request("get", apiEndpoints['tags'], params=params)
        return r['data']
        
    #============================================================================
    # User Methods ================================================================
    async def getUsers(self, ids=None, logins=None):
        """ Get user information """
        params = {}
        if ids:
            params["id"] = ids if isinstance(ids, list) else [ids]
        if logins:
            params["login"] = logins if isinstance(logins, list) else [logins]
        r = await self._request("get", apiEndpoints['user'], params=params)
        return r['data']

    async def sendWhisper(self, to_user_id, message):
        """ Send a whisper to a user """
        data = {
            "from_user_id": self.user_id,
            "to_user_id": to_user_id,
            "message": message
        }
        r = await self._request("post", apiEndpoints['whispers'], data=json.dumps(data))
        return r['data']

    async def modifyChannelInfo(self, broadcaster_id=None, **kwargs):
        """ Modify channel information """
        data = {"broadcaster_id": broadcaster_id or self.user_id}
        # Add optional parameters if provided
        valid_params = [
            'game_id', 'broadcaster_language', 'title',
            'delay', 'tags', 'content_classification_labels'
        ]
        for param in valid_params:
            if param in kwargs:
                data[param] = kwargs[param]
                
        r = await self._request("patch", apiEndpoints['broadcast'], data=json.dumps(data))
        return r
  
    #=========================================================================
    # Extras ===================================================================
    async def unsubAllEvents(self, session_id=None):
        """ Unsubscribe from all events """
        r = await self.getEventSubs()
        tasks = []
        out = []
        for sub in r['data']:
            if "session_id" in sub["transport"] and session_id:
                if session_id == sub["transport"]["session_id"]:
                    out.append(sub)
            if sub['status'] == "enabled":
                continue
            else:
                logger.info(f"[deleteEventSub](Reason: '{sub['status']}') -> \n{sub['type']}:{sub['condition']} ")
                tasks.append(asyncio.create_task(self.deleteEventSub(sub['id'])))
        await asyncio.gather(*tasks)
        return out