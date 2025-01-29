from .utils import json, asyncio, aiofiles, aiohttp
from .utils import randString, datetime, timezone, timedelta
from .utils import ColorLogger, web
from .twitchws import TwitchWS
from .twitch import CommandBot

logger = ColorLogger(__name__)


test_payloads = {
    "channel.follow": {
        "subscription": {
            "id": "test_"+randString(),
            "type": "channel.follow"
        },
        "event": {
            "user_id": "1234",
            "user_login": "deez_nutz_test",
            "user_name": "Deez_Nutz_Test",
            "broadcaster_user_id": "1337",
            "broadcaster_user_login": "cooler_user",
            "broadcaster_user_name": "Cooler_User",
            "followed_at": datetime.now(timezone.utc).isoformat()
        }
    },
    "channel.cheer": {
        "subscription": {
            "id": "test_"+randString(),
            "type": "channel.cheer",
        },
        "event": {
            "is_anonymous": False,
            "user_id": "1234",
            "user_login": "cool_user",
            "user_name": "Cool_User",
            "broadcaster_user_id": "1337",
            "broadcaster_user_login": "cooler_user",
            "broadcaster_user_name": "Cooler_User",
            "message": "pogchamp woot woot awooga",
            "bits": 1000
        }
    },
    "channel.subscribe": {
        "subscription": {
            "id": "test_"+randString(),
            "type": "channel.subscribe"
        },
        "event": {
            "user_id": "1234",
            "user_login": "cool_user",
            "user_name": "Cool_User",
            "broadcaster_user_id": "1337",
            "broadcaster_user_login": "cooler_user",
            "broadcaster_user_name": "Cooler_User",
            "tier": "1000",
            "is_gift": False
        }
    },
    "channel.subscription.gift": {
        "subscription": {
            "id": "test_"+randString(),
            "type": "channel.subscription.gift"
        },
        "event": {
            "user_id": "1234",
            "user_login": "cool_user",
            "user_name": "Cool_User",
            "broadcaster_user_id": "1337",
            "broadcaster_user_login": "cooler_user",
            "broadcaster_user_name": "Cooler_User",
            "total": 1000,
            "tier": "1000",
            "cumulative_total": None, # null if anonymous or not shared by the user
            "is_anonymous": False
        }
    },
    "channel.subscription.message": {
        "subscription": {
            "id": "test_"+randString(),
            "type": "channel.subscription.message"
        },
        "event": {
            "user_id": "1234",
            "user_login": "cool_user",
            "user_name": "Cool_User",
            "broadcaster_user_id": "1337",
            "broadcaster_user_login": "cooler_user",
            "broadcaster_user_name": "Cooler_User",
            "tier": "1000",
            "message": {
                "text": "Love the stream! FevziGG",
                "emotes": [
                    {
                        "begin": 23,
                        "end": 30,
                        "id": "302976485"
                    }
                ]
            },
            "cumulative_months": 5,
            "streak_months": 3, # null if not shared
            "duration_months": 6
        }
    },
    "channel.goal.progress": {
        "subscription": {
            "id": "test_"+randString(),
            "type": "channel.goal.progress"
        },
        "event": {
            "id": "1234",
            "broadcaster_user_id": "1337",
            "broadcaster_user_login": "cooler_user",
            "broadcaster_user_name": "Cooler_User",
            "type": "follower",
            "description": "Follow Goal",
            "current_amount": 7,
            "target_amount": 10,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": None
        }
    },
    "channel.hype_train.progress": {
        "subscription": {
            "id": "test_"+randString(),
            "type": "channel.hype_train.progress"
        },
        "event": {
            "id": "1234",
            "broadcaster_user_id": "1337",
            "broadcaster_user_login": "cooler_user",
            "broadcaster_user_name": "Cooler_User",
            "level": 2,
            "total": 137,
            "progress": 37,
            "goal": 100,
            "top_contributions": [
                {
                    "user_id": "123",
                    "user_login": "cool_user",
                    "user_name": "Cool_User",
                    "type": "bits",
                    "total": 50
                },
                {
                    "user_id": "456",
                    "user_login": "cooler_user2",
                    "user_name": "Cooler_User2",
                    "type": "subscription",
                    "total": 30
                }
            ],
            "last_contribution": {
                "user_id": "123",
                "user_login": "cool_user",
                "user_name": "Cool_User",
                "type": "bits",
                "total": 50
            },
            "started_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        }
    },
    "channel.hype_train.end": {
        "subscription": {
            "id": "test_"+randString(),
            "type": "channel.hype_train.end"
        },
        "event": {
            "id": "1234",
            "broadcaster_user_id": "1337",
            "broadcaster_user_login": "cooler_user",
            "broadcaster_user_name": "Cooler_User",
            "level": 3,
            "total": 437,
            "top_contributions": [
                {
                    "user_id": "123",
                    "user_login": "cool_user",
                    "user_name": "Cool_User",
                    "type": "bits",
                    "total": 200
                },
                {
                    "user_id": "456",
                    "user_login": "cooler_user2",
                    "user_name": "Cooler_User2",
                    "type": "subscription",
                    "total": 100
                }
            ],
            "started_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "cooldown_ends_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        }
    },
    "channel.chat.notification": {
        "subscription": {
            "id": "test_"+randString(),
            "type": "channel.chat.notification"
        },
        "event": {
            "broadcaster_user_id": "1971641",
            "broadcaster_user_login": "streamer",
            "broadcaster_user_name": "streamer",
            "chatter_user_id": "49912639",
            "chatter_user_login": "viewer23",
            "chatter_user_name": "viewer23",
            "chatter_is_anonymous": False,
            "color": "",
            "badges": [],
            "system_message": "viewer23 subscribed at Tier 1. They've subscribed for 10 months!",
            "message_id": "test_"+randString(),
            "message": {
                "text": "",
                "fragments": []
            },
            "notice_type": "resub",
            "sub": None,
            "resub": {
                "cumulative_months": 10,
                "duration_months": 0,
                "streak_months": None,
                "sub_plan": "1000",
                "is_gift": False,
                "gifter_is_anonymous": None,
                "gifter_user_id": None,
                "gifter_user_name": None,
                "gifter_user_login": None
            },
            "sub_gift": None,
            "community_sub_gift": None,
            "gift_paid_upgrade": None,
            "prime_paid_upgrade": None,
            "pay_it_forward": None,
            "raid": None,
            "unraid": None,
            "announcement": None,
            "bits_badge_tier": None,
            "charity_donation": None,
            "shared_chat_sub": None,
            "shared_chat_resub": None,
            "shared_chat_sub_gift": None,
            "shared_chat_community_sub_gift": None,
            "shared_chat_gift_paid_upgrade": None,
            "shared_chat_prime_paid_upgrade": None,
            "shared_chat_pay_it_forward": None,
            "shared_chat_raid": None,
            "shared_chat_announcement": None,
            "source_broadcaster_user_id": None,
            "source_broadcaster_user_login": None,
            "source_broadcaster_user_name": None,
            "source_message_id": None,
            "source_badges": None
        }
    }
}

def test_meta_data():
    return {
            "message_id": 'test_'+randString(),
            "message_type": "notification",
            "message_timestamp": datetime.now(timezone.utc).isoformat()
    }

async def inject_twitchws_message(ws, message_type):
    """Inject a test message into the WebSocket instance"""
    if message_type in test_payloads:
        msg = {"metadata": test_meta_data(), "payload": test_payloads[message_type]}
        await inject_custom_twitchws_message(ws, msg)
    else:
        raise ValueError(f"Unknown message type: {message_type} not in 'test_messages'")

async def inject_custom_twitchws_message(ws, message):
    """Inject a custom message into the WebSocket instance"""
    if isinstance(message, dict):
        message = json.dumps(message)
    await ws.handle_message(message)


class Tester(CommandBot):
    async def before_login(self):
        self._register_test_routes()
    
    def _register_test_routes(self):
        @self.app.route('/testui')
        async def testui(request):
            async with aiofiles.open('templates/testui.html', 'r', encoding='utf-8') as f:
                template = await f.read()
                return web.Response(text=template, content_type='text/html', charset='utf-8')
                
        @self.app.route("/testcheer/{amount}/{anon}")
        async def testcheer(request):
            payload = test_payloads["channel.cheer"]
            payload["event"]["bits"] = int(request.match_info['amount'])
            payload["event"]["is_anonymous"] = False if request.match_info['anon'] == 'False' else True
            await inject_custom_twitchws_message(
                self.ws, 
                {"metadata": test_meta_data(), "payload": payload}
            )
            return web.json_response({"status": True})
        
        @self.app.route("/testsub/{tier}/{gifted}")
        async def testsub(request):
            payload = test_payloads["channel.subscribe"]
            payload["event"]["tier"] = request.match_info['tier']
            payload["event"]["is_gift"] = False if request.match_info['gifted'] == 'False' else True
            await inject_custom_twitchws_message(
                self.ws, 
                {"metadata": test_meta_data(), "payload": payload}
            )
            return web.json_response({"status": True})


        @self.app.route("/testsubgift/{amount}/{tier}/{anon}")
        async def testsubgift(request):
            payload = test_payloads["channel.subscription.gift"]
            payload["event"]["total"] = int(request.match_info['amount'])
            payload["event"]["tier"] = request.match_info['tier']
            payload["event"]["is_anonymous"] = False if request.match_info['anon'] == 'False' else True
            await inject_custom_twitchws_message(
                self.ws, 
                {"metadata": test_meta_data(), "payload": payload}
            )
            return web.json_response({"status": True})

        @self.app.route("/testsubmessage/{months}/{tier}/{streak}/{duration}")
        async def testsubmessage(request):
            payload = test_payloads["channel.subscription.message"]
            payload["event"]["tier"] = request.match_info['tier']
            payload["event"]["cumulative_months"] = int(request.match_info['months'])
            payload["event"]["streak_months"] = int(request.match_info['streak'])
            payload["event"]["duration_months"] = int(request.match_info['duration'])
            await inject_custom_twitchws_message(
                self.ws, 
                {"metadata": test_meta_data(), "payload": payload}
            )
            return web.json_response({"status": True})

        @self.app.route("/testgoal/{type}/{current}/{target}")
        async def testgoal(request):
            payload = test_payloads["channel.goal.progress"]
            payload["event"]["type"] = request.match_info['type']
            payload["event"]["current_amount"] = int(request.match_info['current'])
            payload["event"]["target_amount"] = int(request.match_info['target'])
            await inject_custom_twitchws_message(
                self.ws, 
                {"metadata": test_meta_data(), "payload": payload}
            )
            return web.json_response({"status": True})

        @self.app.route("/testhypetrain/{level}/{total}/{progress}")
        async def testhypetrain(request):
            payload = test_payloads["channel.hype_train.progress"]
            payload["event"]["level"] = int(request.match_info['level'])
            payload["event"]["total"] = int(request.match_info['total'])
            payload["event"]["progress"] = int(request.match_info['progress'])
            payload["event"]["goal"] = 100 * int(request.match_info['level']) #Goal increases with level
            await inject_custom_twitchws_message(
                self.ws, 
                {"metadata": test_meta_data(), "payload": payload}
            )
            return web.json_response({"status": True})

        @self.app.route("/testhypetrainend/{level}/{total}")
        async def testhypetrainend(request):
            payload = test_payloads["channel.hype_train.end"]
            payload["event"]["level"] = int(request.match_info['level'])
            payload["event"]["total"] = int(request.match_info['total'])
            await inject_custom_twitchws_message(
                self.ws, 
                {"metadata": test_meta_data(), "payload": payload}
            )
            return web.json_response({"status": True})

        @self.app.route("/testchatnoto")
        async def testchatnoto(request):
            payload = test_payloads["channel.chat.notification"]
            await inject_custom_twitchws_message(
                self.ws, 
                {"metadata": test_meta_data(), "payload": payload}
            )
            return web.json_response({"status": True})

        logger.info(f"[_register_test_routes]: Done")