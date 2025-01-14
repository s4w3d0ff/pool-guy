from datetime import datetime, timezone
from .utils import json, asyncio
from .utils import randString

test_payloads = {
    "channel.follow": {
        "subscription": {
            "id": randString(),
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
            "id": randString(),
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
            "message": "pogchamp",
            "bits": 1000
        }
    },
    "channel.subscribe": {
        "subscription": {
            "id": randString(),
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
            "id": randString(),
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
            "id": randString(),
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
    "channel.goal.progress": {},
    "channel.hype_train.progress": {},
    "channel.hype_train.end": {}
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