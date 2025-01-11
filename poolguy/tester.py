import asyncio
import json
from datetime import datetime, timezone
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
    "channel.ban": {
        "subscription": {
            "id": randString(),
            "type": "channel.ban",
        },
        "event": {
            "user_id": "1234",
            "user_login": "cool_user",
            "user_name": "Cool_User",
            "broadcaster_user_id": "1337",
            "broadcaster_user_login": "cooler_user",
            "broadcaster_user_name": "Cooler_User",
            "moderator_user_id": "1339",
            "moderator_user_login": "mod_user",
            "moderator_user_name": "Mod_User",
            "reason": "Offensive language",
            "banned_at": datetime.now(timezone.utc).isoformat(),
            "ends_at": datetime.now(timezone.utc).isoformat(),
            "is_permanent": False
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