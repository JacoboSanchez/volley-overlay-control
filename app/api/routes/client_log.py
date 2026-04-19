"""POST /_log — accept a single error/warn record from the SPA.

Rate-limited per peer IP. Unauthenticated by design: the SPA is loaded
by anyone with the page URL, and the endpoint relies on caps + PII
redaction (not auth) to stay safe.
"""

import logging
import time
from collections import OrderedDict, deque
from threading import Lock
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.logging_utils import redact_oid, redact_url

logger = logging.getLogger("app.frontend")
router = APIRouter()


_MAX_PER_WINDOW = 30
_WINDOW_SECONDS = 60.0
_MAX_CLIENTS = 4096
_clients: "OrderedDict[str, deque[float]]" = OrderedDict()
_clients_lock = Lock()


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limited(key: str) -> bool:
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS
    with _clients_lock:
        bucket = _clients.get(key)
        if bucket is None:
            bucket = deque()
            _clients[key] = bucket
            if len(_clients) > _MAX_CLIENTS:
                _clients.popitem(last=False)
        else:
            _clients.move_to_end(key)
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= _MAX_PER_WINDOW:
            return True
        bucket.append(now)
    return False


def _reset_rate_limiter() -> None:
    """Test-only hook to clear the bucket."""
    with _clients_lock:
        _clients.clear()


class ClientLogRecord(BaseModel):
    level: Literal["error", "warn"] = "error"
    message: str = Field(..., min_length=1, max_length=2000)
    stack: Optional[str] = Field(default=None, max_length=8000)
    href: Optional[str] = Field(default=None, max_length=2000)
    user_agent: Optional[str] = Field(default=None, max_length=500)
    oid: Optional[str] = Field(default=None, max_length=200)


_LEVELS = {"error": logging.ERROR, "warn": logging.WARNING}


@router.post("/_log", status_code=status.HTTP_204_NO_CONTENT)
async def post_client_log(record: ClientLogRecord, request: Request) -> Response:
    """Accept a frontend error report. Returns 204 even on rate-limit so
    the SPA's :func:`navigator.sendBeacon` does not retry needlessly."""
    if _rate_limited(_client_key(request)):
        # Tell well-behaved clients they should stop, but keep the body
        # empty so sendBeacon does not surface an error to the user.
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS)

    extras = {
        "frontend_href": redact_url(record.href) if record.href else "-",
        "frontend_ua": record.user_agent or "-",
        "frontend_oid": redact_oid(record.oid) if record.oid else "-",
    }
    logger.log(
        _LEVELS[record.level],
        "[frontend %s] %s%s",
        record.level,
        record.message,
        f"\n{record.stack}" if record.stack else "",
        extra=extras,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
