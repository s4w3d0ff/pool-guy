import hashlib
import hmac
import json
import logging
from aiohttp import web

logger = logging.getLogger(__name__)


def compute_signature(secret, message_id, timestamp, raw_body):
    """Build the expected 'sha256=<hex>' signature for an EventSub webhook message."""
    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")
    elif not isinstance(raw_body, (bytes, bytearray)):
        raise TypeError(f"raw_body must be bytes or str, got {type(raw_body).__name__}")
    secret_bytes = secret.encode("ascii") if isinstance(secret, str) else secret
    message = (message_id or "").encode() + (timestamp or "").encode() + bytes(raw_body)
    digest = hmac.new(secret_bytes, message, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret, message_id, timestamp, raw_body, signature_header):
    """Constant-time check of the Twitch-Eventsub-Message-Signature header."""
    provided = (signature_header or "").strip()
    if not provided.startswith("sha256=") or len(provided) != 71:
        return False
    expected = compute_signature(secret, message_id, timestamp, raw_body)
    return hmac.compare_digest(expected.encode(), provided.encode())


def make_webhook_handler(secret, on_event=None):
    """aiohttp handler for EventSub webhook transport (challenge echo + notification dispatch).

    Signature is verified over the RAW body before any parsing; invalid signatures
    are rejected with 403 and nothing else is processed.
    """
    async def handler(request: web.Request) -> web.Response:
        raw_body = await request.read()
        message_id = request.headers.get("Twitch-Eventsub-Message-Id", "")
        timestamp = request.headers.get("Twitch-Eventsub-Message-Timestamp", "")
        message_type = request.headers.get("Twitch-Eventsub-Message-Type", "notification")
        signature_header = request.headers.get("Twitch-Eventsub-Message-Signature", "")

        if not verify_signature(secret, message_id, timestamp, raw_body, signature_header):
            logger.warning(f"Rejected EventSub webhook with invalid signature from {request.remote}")
            return web.Response(status=403, text="invalid signature", content_type="text/plain")

        try:
            payload = json.loads(raw_body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Rejected EventSub webhook with unparseable body")
            return web.Response(status=400, text="invalid JSON", content_type="text/plain")

        if message_type == "webhook_callback_verification":
            challenge = str(payload.get("challenge", ""))
            return web.Response(text=challenge, status=200, content_type="text/plain")

        if message_type == "notification" and on_event is not None:
            try:
                await on_event(payload)
            except Exception as e:
                logger.error(f"on_event handler failed for {payload.get('subscription', {}).get('type')}: {e}")
        elif message_type != "revocation":
            logger.warning(f"Ignoring EventSub webhook of type '{message_type}'")

        return web.Response(status=204)

    return handler
