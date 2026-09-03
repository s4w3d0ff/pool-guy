import contextvars
import logging
import uuid
from typing import Optional

_request_id: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar("twitch_request_id", default=None)

REQUEST_LOG_FORMAT = "[%(asctime)s] [%(name)s] [%(levelname)s] [reqid=%(reqid)s] %(message)s"


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


from weakref import WeakSet


class RequestLogFilter(logging.Filter):
    def filter(self, record):
        record.reqid = _request_id.get() or "-"
        return True


_installed_handlers: "WeakSet[logging.Handler]" = WeakSet()


def install():
    """Attach the request-id filter to root handlers (idempotent; re-call after configuring logging)."""
    for handler in list(logging.getLogger().handlers):
        if handler not in _installed_handlers:
            handler.addFilter(RequestLogFilter())
            _installed_handlers.add(handler)
