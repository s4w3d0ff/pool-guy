import json
import logging
from .http import RequestHandler

logger = logging.getLogger(__name__)

EVENTSUB_VERSIONS = {
    "automod.message.hold": "2",
    "automod.message.update": "2",
    "automod.settings.update": "1",
    "automod.terms.update": "1",
    "channel.ad_break.begin": "1",
    "channel.ban": "1",
    "channel.bits.use": "1",
    "channel.channel_points_automatic_reward_redemption.add": "2",
    "channel.channel_points_custom_reward.add": "1",
    "channel.channel_points_custom_reward.remove": "1",
    "channel.channel_points_custom_reward.update": "1",
    "channel.channel_points_custom_reward_redemption.add": "1",
    "channel.channel_points_custom_reward_redemption.update": "1",
    "channel.charity_campaign.donate": "1",
    "channel.charity_campaign.progress": "1",
    "channel.charity_campaign.start": "1",
    "channel.charity_campaign.stop": "1",
    "channel.chat.clear": "1",
    "channel.chat.clear_user_messages": "1",
    "channel.chat.message": "1",
    "channel.chat.message_delete": "1",
    "channel.chat.notification": "1",
    "channel.chat.user_message_hold": "1",
    "channel.chat.user_message_update": "1",
    "channel.chat_settings.update": "1",
    "channel.cheer": "1",
    "channel.custom_power_up_redemption.add": "1",
    "channel.follow": "2",
    "channel.goal.begin": "1",
    "channel.goal.end": "1",
    "channel.goal.progress": "1",
    "channel.guest_star_guest.update": "beta",
    "channel.guest_star_session.begin": "beta",
    "channel.guest_star_session.end": "beta",
    "channel.guest_star_settings.update": "beta",
    "channel.hype_train.begin": "2",
    "channel.hype_train.end": "2",
    "channel.hype_train.progress": "2",
    "channel.moderate": "2",
    "channel.moderator.add": "1",
    "channel.moderator.remove": "1",
    "channel.poll.begin": "1",
    "channel.poll.end": "1",
    "channel.poll.progress": "1",
    "channel.prediction.begin": "1",
    "channel.prediction.end": "1",
    "channel.prediction.lock": "1",
    "channel.prediction.progress": "1",
    "channel.raid": "1",
    "channel.shared_chat.begin": "1",
    "channel.shared_chat.end": "1",
    "channel.shared_chat.update": "1",
    "channel.shield_mode.begin": "1",
    "channel.shield_mode.end": "1",
    "channel.shoutout.create": "1",
    "channel.shoutout.receive": "1",
    "channel.subscribe": "1",
    "channel.subscription.end": "1",
    "channel.subscription.gift": "1",
    "channel.subscription.message": "1",
    "channel.suspicious_user.message": "1",
    "channel.suspicious_user.update": "1",
    "channel.unban": "1",
    "channel.unban_request.create": "1",
    "channel.unban_request.resolve": "1",
    "channel.update": "2",
    "channel.vip.add": "1",
    "channel.vip.remove": "1",
    "channel.warning.acknowledge": "1",
    "channel.warning.send": "1",
    "conduit.shard.disabled": "1",
    "drop.entitlement.grant": "1",
    "extension.bits_transaction.create": "1",
    "stream.offline": "1",
    "stream.online": "1",
    "user.authorization.grant": "1",
    "user.authorization.revoke": "1",
    "user.update": "1",
    "user.whisper.message": "1",
}

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
    "shield_mode": f"{apiUrlPrefix}/moderation/shield_mode",
    "automod_messages": f"{apiUrlPrefix}/moderation/automod/message",
    "automod_settings": f"{apiUrlPrefix}/moderation/automod/settings",
    "guest_star_settings": f"{apiUrlPrefix}/guest_star/channel_settings",
    "guest_star_session": f"{apiUrlPrefix}/guest_star/session",
    "guest_star_invites": f"{apiUrlPrefix}/guest_star/invites"
}


class TwitchApi(RequestHandler):
    def __init__(self, *args, api_prefix=None, **kwargs):
        prefix = api_prefix or apiUrlPrefix
        self.apiEndpoints = {
            key: value.replace(apiUrlPrefix, prefix)
            for key, value in apiEndpoints.items()
        }
        super().__init__(*args, **kwargs)
    async def _continuePage(self, method, url, page, params=None):
        """ Helper function to handle pagination in Twitch API calls """
        out = []
        while "cursor" in page:
            next_params = dict(params or {})
            next_params['after'] = page['cursor']
            r = await self._request(method, url, params=next_params)
            out += r['data']
            page = r['pagination'] if 'pagination' in r else {}
        return out
        
    #============================================================================
    # EventSub Methods ================================================================
    BROADCASTER_ONLY_EVENTS = (
        'channel.ad_break.begin',
        'channel.ban',
        'channel.bits.use',
        'channel.channel_points_automatic_reward_redemption.add',
        'channel.channel_points_custom_reward.add',
        'channel.channel_points_custom_reward.remove',
        'channel.channel_points_custom_reward.update',
        'channel.channel_points_custom_reward_redemption.add',
        'channel.channel_points_custom_reward_redemption.update',
        'channel.charity_campaign.donate',
        'channel.charity_campaign.progress',
        'channel.charity_campaign.start',
        'channel.charity_campaign.stop',
        'channel.cheer',
        'channel.custom_power_up_redemption.add',
        'channel.goal.begin',
        'channel.goal.end',
        'channel.goal.progress',
        'channel.hype_train.begin',
        'channel.hype_train.end',
        'channel.hype_train.progress',
        'channel.moderator.add',
        'channel.moderator.remove',
        'channel.poll.begin',
        'channel.poll.progress',
        'channel.poll.end',
        'channel.prediction.begin',
        'channel.prediction.progress',
        'channel.prediction.lock',
        'channel.prediction.end',
        'channel.shared_chat.begin',
        'channel.shared_chat.update',
        'channel.shared_chat.end',
        'channel.subscribe',
        'channel.subscription.end',
        'channel.subscription.gift',
        'channel.subscription.message',
        'channel.unban',
        'channel.update',
        'channel.vip.add',
        'channel.vip.remove',
        'stream.online',
        'stream.offline',
    )

    BROADCASTER_MODERATOR_EVENTS = (
        'automod.message.hold',
        'automod.message.update',
        'automod.settings.update',
        'automod.terms.update',
        'channel.follow',
        'channel.guest_star_session.begin',
        'channel.guest_star_session.end',
        'channel.guest_star_guest.update',
        'channel.guest_star_settings.update',
        'channel.moderate',
        'channel.shield_mode.begin',
        'channel.shield_mode.end',
        'channel.shoutout.create',
        'channel.shoutout.receive',
        'channel.suspicious_user.message',
        'channel.suspicious_user.update',
        'channel.unban_request.create',
        'channel.unban_request.resolve',
        'channel.warning.acknowledge',
        'channel.warning.send',
    )

    CHAT_USER_EVENTS = (
        'channel.chat.clear',
        'channel.chat.clear_user_messages',
        'channel.chat.message',
        'channel.chat.message_delete',
        'channel.chat.notification',
        'channel.chat.user_message_hold',
        'channel.chat.user_message_update',
        'channel.chat_settings.update',
    )

    NO_AUTH_REQUIRED_EVENTS = (
        'channel.raid',
        'channel.shared_chat.begin',
        'channel.shared_chat.end',
        'channel.shared_chat.update',
        'channel.update',
        'stream.offline',
        'stream.online',
    )

    EVENTSUB_MAX_TOTAL_COST_DEFAULT = 10

    async def _get_eventsub_version(self, name):
        """Get eventsub version by name from the static map, storage as fallback."""
        if name in EVENTSUB_VERSIONS:
            return EVENTSUB_VERSIONS[name]
        out = await self.storage.query("subpub_versions", where="name = ?", params=(name,))
        return out[0]['version'] if out else None

    async def _sync_eventsub_costs(self):
        """Persist the worst-case cost of every known event type to storage."""
        for name in EVENTSUB_VERSIONS:
            cost = 1 if name in self.NO_AUTH_REQUIRED_EVENTS else 0
            await self.storage.insert(
                "eventsub_costs", {"name": name, "cost": str(cost)}
            )

    async def _eventsub_cost(self, event):
        """Worst-case subscription cost: no-auth-required types count 1 unless authorized."""
        if not await self.storage.query("eventsub_costs"):
            await self._sync_eventsub_costs()
        rows = await self.storage.query(
            "eventsub_costs", where="name = ?", params=(event,)
        )
        return int(rows[0]["cost"]) if rows else 0

    async def _eventsub_budget_key(self):
        client_id = getattr(self, "client_id", None) or "unknown"
        user_id = self.user_id or "no_user"
        return f"{client_id}_{user_id}"

    async def _sync_eventsub_budget(self, response):
        """Persist authoritative cost totals returned by Twitch in subscription responses."""
        if not isinstance(response, dict) or "total_cost" not in response:
            return
        await self.storage.insert("eventsub_budget", {
            "name": await self._eventsub_budget_key(),
            "total_cost": str(int(response["total_cost"])),
            "max_total_cost": str(
                int(response.get("max_total_cost", self.EVENTSUB_MAX_TOTAL_COST_DEFAULT))
            ),
        })

    async def _check_eventsub_budget(self, event):
        """Raise before POST when the worst-case cost would exceed the remaining budget."""
        cost = await self._eventsub_cost(event)
        if not cost:
            return
        key = await self._eventsub_budget_key()
        rows = await self.storage.query(
            "eventsub_budget", where="name = ?", params=(key,)
        )
        total = int(rows[0]["total_cost"]) if rows else 0
        max_total = (
            int(rows[0]["max_total_cost"]) if rows
            else self.EVENTSUB_MAX_TOTAL_COST_DEFAULT
        )
        if total + cost > max_total:
            raise ValueError(
                f"EventSub budget exhausted for {key}: total {total}/{max_total}, "
                f"requested cost {cost} for {event}"
            )

    async def _determine_eventsub_condition(self, event, bid=None):
        """Determine the event condition based on the event type per spec."""
        uid = str(self.user_id)
        if bid:
            bid = str(bid)
        match event:
            case e if e in self.BROADCASTER_ONLY_EVENTS:
                return {'broadcaster_user_id': bid or uid}
            case e if e in self.BROADCASTER_MODERATOR_EVENTS:
                return {'broadcaster_user_id': bid or uid, 'moderator_user_id': uid}
            case e if e in self.CHAT_USER_EVENTS:
                return {'broadcaster_user_id': bid or uid, 'user_id': uid}
            case 'channel.raid':
                return {'to_broadcaster_user_id': uid}
            case 'user.update' | 'user.whisper.message':
                return {'user_id': uid}
            case 'user.authorization.grant' | 'user.authorization.revoke' | 'conduit.shard.disabled':
                return {'client_id': str(self.client_id)}
            case 'extension.bits_transaction.create':
                return {'extension_client_id': str(self.client_id)}
            case _:
                logger.error(f"Unsupported eventsub type for condition: {event}")
                raise ValueError(f"Cannot determine condition for eventsub type: {event}")

    async def createEventSub(self, event, session_id, bid=None):
        """ Create an EventSub subscription """
        version = await self._get_eventsub_version(event)
        if not version:
            logger.error(f"No known version for eventsub type: {event}")
            raise ValueError(f"Unknown eventsub type: {event}")
        await self._check_eventsub_budget(event)
        data = json.dumps({
            "type": event,
            "version": version,
            "condition": await self._determine_eventsub_condition(event, bid),
            "transport": {'method': 'websocket', 'session_id': session_id}
        })
        logger.debug(f'Sending [createEventSub] -> {data}')
        r = await self._request("post", self.apiEndpoints['eventsub'], data=data)
        await self._sync_eventsub_budget(r)
        return r

    async def deleteEventSub(self, id):
        try:
            r = await self._request("delete", f"{self.apiEndpoints['eventsub']}?id={id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete eventsub subscription {id}: {e}")
            return False

    async def getEventSubs(self, status=None, type=None):
        params = {}
        if status:
            params["status"] = status
        if type:
            params["type"] = type
        r = await self._request("get", self.apiEndpoints['eventsub'], params=params)
        await self._sync_eventsub_budget(r)
        return r

    #============================================================================
    # Badges Methods ================================================================
    async def getGlobalChatBadges(self):
        """ Get global chat badges """
        r = await self._request("get", self.apiEndpoints['global_badges'])
        return r['data']
        
    async def getChannelChatBadges(self, broadcaster_id=None):
        """ Get channel chat badges """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", self.apiEndpoints['channel_badges'], params=params)
        return r['data']

    #============================================================================
    # Channel Methods ================================================================
    async def getChannelInfo(self, broadcaster_id=None):
        """ Get channel information """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", self.apiEndpoints['broadcast'], params=params)
        return r['data']

    async def getFollowedChannels(self, user_id=None, broadcaster_id=None):
        """ Get followed channels """
        params = {
            "user_id": user_id or self.user_id,
            "broadcaster_id": broadcaster_id
        }
        r = await self._request("get", self.apiEndpoints['users_follows'], params=params)
        return r['data']

    async def getChannelFollowers(self, broadcaster_id=None, first=None):
        """ Get channel followers """
        method = "get"
        url = self.apiEndpoints['followers']
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
        url = self.apiEndpoints['schedule']
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
            "message": message[:500] # 500 char limit
        }
        r = await self._request("post", self.apiEndpoints['chat'], data=json.dumps(data))
        return r['data']

    async def getChatters(self, broadcaster_id=None, moderator_id=None):
        """ Get the list of chatters in the channel """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "moderator_id": moderator_id or self.user_id
        }
        r = await self._request("get", f"{self.apiEndpoints['chat']}/chatters", params=params)
        return r['data']

    async def getChatSettings(self, broadcaster_id=None, moderator_id=None):
        """ Get the chat settings for the channel """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "moderator_id": moderator_id or self.user_id
        }
        r = await self._request("get", f"{self.apiEndpoints['chat']}/settings", params=params)
        return r['data']

    async def updateChatSettings(self, broadcaster_id=None, settings=None):
        """ Update the chat settings for the channel """
        data = settings or {}
        data["broadcaster_id"] = broadcaster_id or self.user_id
        r = await self._request("patch", f"{self.apiEndpoints['chat']}/settings", data=json.dumps(data))
        return r['data']

    async def sendAnnouncement(self, broadcaster_id=None, message="", color="primary"):
        """ Send an announcement to the channel's chat """
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "message": message,
            "color": color
        }
        r = await self._request("post", f"{self.apiEndpoints['chat']}/announcements", data=json.dumps(data))
        return r['data']

    async def sendShoutout(self, to_broadcaster_id=None, from_broadcaster_id=None, moderator_id=None):
        """ Send a shoutout to another channel """
        data = {
            "from_broadcaster_id": from_broadcaster_id or self.user_id,
            "to_broadcaster_id": to_broadcaster_id,
            "moderator_id": moderator_id or self.user_id
        }
        r = await self._request("post", f"{self.apiEndpoints['chat']}/shoutouts", data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Clips Methods ================================================================
    async def createClip(self, broadcaster_id=None):
        """ Create a clip from the broadcaster's stream """
        data = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("post", self.apiEndpoints['clips'], data=json.dumps(data))
        return r['data']

    async def getClips(self, broadcaster_id=None, game_id=None, clip_id=None, first=None):
        """ Get clips from the broadcaster's channel """
        method = "get"
        url = self.apiEndpoints['clips']
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
        r = await self._request("post", self.apiEndpoints['commercial'], data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Bits Methods ================================================================
    async def getBitsLeaderboard(self, count=10, period="all", started_at=None):
        """ Get the Bits leaderboard for a broadcaster """
        method = "get"
        url = self.apiEndpoints['bits']
        params = {"count": count, "period": period}
        if started_at:
            params["started_at"] = started_at
        r = await self._request(method, url, params=params)
        return r['data']

    async def getCheermotes(self, broadcaster_id=None):
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", self.apiEndpoints['cheermotes'], params=params)
        return r['data']  

    #============================================================================
    # Games Methods ================================================================
    async def getTopGames(self, first=None):
        """ Get the top games for a broadcaster """
        method = "get"
        url = self.apiEndpoints['categories']+"/top"
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
        r = await self._request("get", self.apiEndpoints['goals'], params=params)
        return r['data']
        
    #============================================================================
    # Hype Train Methods ================================================================
    async def getHypeTrainEvents(self, broadcaster_id=None):
        """ Get the hype train events for a broadcaster """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", self.apiEndpoints['hype_train'], params=params)
        return r['data']
        
    #============================================================================
    # Moderation Methods ================================================================
    async def getBannedUsers(self, broadcaster_id=None):
        """ Get the banned users for a broadcaster """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", self.apiEndpoints['banned_users'], params=params)
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
        r = await self._request("post", self.apiEndpoints['ban'], params=params, data=json.dumps(data))
        return r['data']

    async def unbanUser(self, broadcaster_id=None, user_id=None):
        """ Unban a user from the channel """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self._request("delete", self.apiEndpoints['ban'], params=params)
        return r['data']
        
    #============================================================================
    # AutoMod Methods ================================================================
    async def manageHeldAutomodMessage(self, msg_id, action):
        """ Allow or deny a message held by AutoMod (action ALLOW/DENY) """
        data = {
            "user_id": self.user_id,
            "msg_id": msg_id,
            "action": action
        }
        r = await self._request("post", self.apiEndpoints['automod_messages'], data=json.dumps(data))
        return r['data']

    async def getAutomodSettings(self, broadcaster_id=None, moderator_id=None):
        """ Get the AutoMod settings for a channel """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "moderator_id": moderator_id or self.user_id
        }
        r = await self._request("get", self.apiEndpoints['automod_settings'], params=params)
        return r['data']

    async def updateAutomodSettings(self, settings, broadcaster_id=None, moderator_id=None):
        """ Update AutoMod settings; PUT is a full overwrite so pass complete field set """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "moderator_id": moderator_id or self.user_id
        }
        r = await self._request("put", self.apiEndpoints['automod_settings'], params=params, data=json.dumps(settings))
        return r['data']

    #============================================================================
    # Guest Star Methods ================================================================
    async def getGuestStarSettings(self, broadcaster_id=None, moderator_id=None):
        """ Get the Guest Star channel settings (beta) """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "moderator_id": moderator_id or self.user_id
        }
        r = await self._request("get", self.apiEndpoints['guest_star_settings'], params=params)
        return r

    async def updateGuestStarSettings(self, settings=None, broadcaster_id=None):
        """ Update the Guest Star channel settings (beta); body fields optional """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        data = json.dumps(settings or {})
        r = await self._request("put", self.apiEndpoints['guest_star_settings'], params=params, data=data)
        return r

    async def getGuestStarSession(self, broadcaster_id=None, moderator_id=None):
        """ Get the active Guest Star session (beta) """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "moderator_id": moderator_id or self.user_id
        }
        r = await self._request("get", self.apiEndpoints['guest_star_session'], params=params)
        return r['data']

    async def createGuestStarSession(self, broadcaster_id=None):
        """ Create a Guest Star session (beta); broadcaster must be in the call interface """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("post", self.apiEndpoints['guest_star_session'], params=params)
        return r['data']

    async def endGuestStarSession(self, session_id=None, broadcaster_id=None):
        """ End a Guest Star session (beta) """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "session_id": session_id
        }
        r = await self._request("delete", self.apiEndpoints['guest_star_session'], params=params)
        return r['data']

    async def getGuestStarInvites(self, session_id=None, broadcaster_id=None, moderator_id=None):
        """ Get pending Guest Star invites for a session (beta) """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "moderator_id": moderator_id or self.user_id,
            "session_id": session_id
        }
        r = await self._request("get", self.apiEndpoints['guest_star_invites'], params=params)
        return r['data']

    async def sendGuestStarInvite(self, user_id=None, session_id=None, broadcaster_id=None, moderator_id=None):
        """ Send a Guest Star invite to a user (beta) """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "moderator_id": moderator_id or self.user_id,
            "session_id": session_id,
            "user_id": user_id
        }
        r = await self._request("post", self.apiEndpoints['guest_star_invites'], params=params)
        return r

    async def deleteGuestStarInvite(self, user_id=None, session_id=None, broadcaster_id=None, moderator_id=None):
        """ Revoke a pending Guest Star invite (beta) """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "moderator_id": moderator_id or self.user_id,
            "session_id": session_id,
            "user_id": user_id
        }
        r = await self._request("delete", self.apiEndpoints['guest_star_invites'], params=params)
        return r

    #============================================================================
    # Moderator Methods ================================================================
    async def getModerators(self, broadcaster_id=None):
        """ Get moderators of the channel """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", self.apiEndpoints['moderators'], params=params)
        return r['data']

    async def addModerator(self, broadcaster_id=None, user_id=None):
        """ Add a moderator to the channel """
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self._request("post", self.apiEndpoints['moderators'], data=json.dumps(data))
        return r['data']

    async def removeModerator(self, broadcaster_id=None, user_id=None):
        """ Remove a moderator from the channel """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self._request("delete", self.apiEndpoints['moderators'], params=params)
        return r['data']
        
    #============================================================================
    # VIP Methods ================================================================
    async def getVIPs(self, broadcaster_id=None):
        """ Get a list of VIPs for the channel """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("get", self.apiEndpoints['channel_vips'], params=params)
        return r['data']

    async def addVIP(self, broadcaster_id=None, user_id=None):
        """ Add a VIP to the channel """
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self._request("post", self.apiEndpoints['channel_vips'], data=json.dumps(data))
        return r['data']

    async def removeVIP(self, broadcaster_id=None, user_id=None):
        """ Remove a VIP from the channel """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id
        }
        r = await self._request("delete", self.apiEndpoints['channel_vips'], params=params)
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
        r = await self._request("post", f"{self.apiEndpoints['chat']}/warnings", data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Poll Methods ================================================================
    async def getPolls(self, broadcaster_id=None, first=None):
        """ Get polls for a channel """
        method = "get"
        url = self.apiEndpoints['polls']
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
        r = await self._request("post", self.apiEndpoints['polls'], data=json.dumps(data))
        return r['data']

    async def endPoll(self, broadcaster_id=None, poll_id=None, status="TERMINATED"):
        """ End a poll for a channel """
        data = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "id": poll_id,
            "status": status
        }
        r = await self._request("patch", self.apiEndpoints['polls'], data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Prediction Methods ================================================================
    async def getPredictions(self, broadcaster_id=None, first=None):
        """ Get predictions for a channel """
        method = "get"
        url = self.apiEndpoints['predictions']
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
        r = await self._request("post", self.apiEndpoints['predictions'], data=json.dumps(data))
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
        r = await self._request("patch", self.apiEndpoints['predictions'], data=json.dumps(data))
        return r['data']
        
    #============================================================================
    # Raid Methods ================================================================
    async def startRaid(self, from_broadcaster_id=None, to_broadcaster_id=None):
        """ Start a raid to another channel """
        data = {
            "from_broadcaster_id": from_broadcaster_id or self.user_id,
            "to_broadcaster_id": to_broadcaster_id
        }
        r = await self._request("post", self.apiEndpoints['raids'], data=json.dumps(data))
        return r['data']

    async def cancelRaid(self, broadcaster_id=None):
        """ Cancel a raid """
        params = {"broadcaster_id": broadcaster_id or self.user_id}
        r = await self._request("delete", self.apiEndpoints['raids'], params=params)
        return r['data']
        
    #============================================================================
    # Search Methods ================================================================
    async def searchCategories(self, query, first=None):
        """ Search for categories """
        method = "get"
        url = f"{self.apiEndpoints['categories']}/search"
        params = {"query": query, "first": first or 20}
        r = await self._request(method, url, params=params)
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, url, r['pagination'], params=params)
        return out

    async def searchChannels(self, query, first=None, live_only=False):
        """ Search for channels """
        method = "get"
        url = f"{self.apiEndpoints['broadcast']}/search"
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
        params = dict(kwargs)
        params['first'] = first or 100
        r = await self._request("get", self.apiEndpoints['streams'], params=params)
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage("get", self.apiEndpoints['streams'], r['pagination'], params=params)
        return out

    async def getFollowedStreams(self, user_id=None, first=None):
        """ Get followed streams """
        method = "get"
        url = f"{self.apiEndpoints['streams']}/followed"
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
        r = await self._request("post", self.apiEndpoints['stream_markers'], data=json.dumps(data))
        return r['data']

    async def getStreamMarkers(self, user_id=None, video_id=None, first=None):
        """ Get stream markers """
        method = "get"
        url = self.apiEndpoints['stream_markers']
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
        url = self.apiEndpoints['subscriptions']
        params = {"broadcaster_id": broadcaster_id or self.user_id, "first": first or 100}
        if user_id:
            if isinstance(user_id, list):
                params["user_id"] = user_id[:100]  # Limit to max 100 IDs
            else:
                params["user_id"] = [user_id]  # Single ID as list
        r = await self._request(method, url, params=params)
        out = r['data']
        if 'cursor' in r['pagination'] and not first:
            out += await self._continuePage(method, url, r['pagination'], params=params)
        return out

    async def checkUserSubscription(self, broadcaster_id=None, user_id=None):
        """ Check if a user is subscribed to a broadcaster """
        params = {
            "broadcaster_id": broadcaster_id or self.user_id,
            "user_id": user_id or self.user_id
        }
        r = await self._request("get", self.apiEndpoints['subscriptions'], params=params)
        return r['data']
        
    #============================================================================
    # Tag Methods ================================================================
    async def getAllStreamTags(self, first=None):
        """ Get all stream tags """
        method = "get"
        url = self.apiEndpoints['tags']
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
        r = await self._request("get", self.apiEndpoints['tags'], params=params)
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
        r = await self._request("get", self.apiEndpoints['user'], params=params)
        return r['data']

    async def sendWhisper(self, to_user_id, message):
        """ Send a whisper to a user """
        data = {
            "from_user_id": self.user_id,
            "to_user_id": to_user_id,
            "message": message
        }
        r = await self._request("post", self.apiEndpoints['whispers'], data=json.dumps(data))
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
                
        r = await self._request("patch", self.apiEndpoints['broadcast'], data=json.dumps(data))
        return r