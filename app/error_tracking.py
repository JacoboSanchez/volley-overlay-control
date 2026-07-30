"""Optional Sentry error aggregation with privacy-safe defaults.

Setting ``SENTRY_DSN`` enables the official Python SDK. With no DSN this
module is a zero-cost no-op, so self-hosted installations are not required to
run an external service.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)

_SAFE_REQUEST_HEADERS = frozenset(
    {
        "content-type",
        "traceparent",
        "user-agent",
        "x-request-id",
    }
)
_SAFE_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}\Z")
_MAX_SAFE_HEADER_LENGTH = 256


def _safe_header_value(name: str, value: object) -> str | None:
    text = str(value)
    if (
        not text
        or len(text) > _MAX_SAFE_HEADER_LENGTH
        or any(ord(char) < 0x20 or ord(char) > 0x7E for char in text)
    ):
        return None
    if name == "x-request-id" and _SAFE_REQUEST_ID_RE.fullmatch(text) is None:
        return None
    if name == "traceparent" and len(text) != 55:
        return None
    return text


def _sample_rate() -> float:
    raw = os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0").strip()
    try:
        return min(1.0, max(0.0, float(raw)))
    except ValueError:
        logger.warning(
            "Invalid SENTRY_TRACES_SAMPLE_RATE %r; tracing disabled.",
            raw,
        )
        return 0.0


def _redacted_event_url(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<redacted-url>"
    path = parts.path
    for prefix in ("/overlay/", "/follow/", "/ws/", "/match/"):
        if path.startswith(prefix):
            path = f"{prefix}***"
            break
    netloc = parts.netloc.rpartition("@")[-1]
    return urlunsplit((parts.scheme, netloc, path, "", ""))


def _before_send(
    event: dict[str, Any],
    _hint: dict[str, Any],
) -> dict[str, Any]:
    """Drop credentials, request bodies, and capability-bearing URL data."""
    request = event.get("request")
    if not isinstance(request, dict):
        return event
    request["url"] = _redacted_event_url(request.get("url"))
    request.pop("data", None)
    request.pop("cookies", None)
    request["query_string"] = ""
    headers = request.get("headers")
    if isinstance(headers, dict):
        safe_headers: dict[str, str] = {}
        for key, value in headers.items():
            normalized = str(key).lower()
            safe_value = _safe_header_value(normalized, value)
            if normalized in _SAFE_REQUEST_HEADERS and safe_value is not None:
                safe_headers[str(key)] = safe_value
        request["headers"] = safe_headers
    else:
        request.pop("headers", None)
    return event


def _init_sentry(**options: Any) -> None:
    import sentry_sdk

    sentry_sdk.init(**options)


def configure_error_tracking() -> bool:
    """Initialize Sentry when ``SENTRY_DSN`` is configured.

    Returns whether initialization succeeded. Startup remains available when
    the optional integration is missing or misconfigured; the failure is
    logged locally instead of taking the scoreboard offline.
    """
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        _init_sentry(
            dsn=dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT") or None,
            release=os.environ.get("SENTRY_RELEASE") or None,
            traces_sample_rate=_sample_rate(),
            send_default_pii=False,
            max_request_body_size="never",
            include_local_variables=False,
            before_send=_before_send,
        )
    except Exception:
        logger.exception("Sentry initialization failed; continuing without it")
        return False
    logger.info("Sentry error tracking enabled")
    return True
