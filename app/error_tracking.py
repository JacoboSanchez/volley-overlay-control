"""Optional Sentry error aggregation with privacy-safe defaults.

Setting ``SENTRY_DSN`` enables the official Python SDK. With no DSN this
module is a zero-cost no-op, so self-hosted installations are not required to
run an external service.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.env_vars_manager import EnvVarsManager

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
# Path prefixes whose first segment is an unguessable capability token.
_CAPABILITY_PREFIXES = ("/overlay/", "/follow/", "/ws/", "/matches/", "/match/")
# Span/breadcrumb payload keys that carry a full URL and must be redacted.
_URL_DATA_KEYS = frozenset(
    {
        "http.url",
        "url",
        "url.full",
        "url.path",
    }
)
# Span/breadcrumb payload keys that carry raw query or fragment data.
_DROPPED_DATA_KEYS = frozenset(
    {
        "http.fragment",
        "http.query",
        "url.fragment",
        "url.query",
    }
)


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
    # Parsed by the shared accessor (which warns and falls back to 0.0 —
    # tracing off — on garbage), then clamped here: an out-of-range rate is
    # a fraction the operator meant, so 2.0 means "sample everything"
    # rather than "disable tracing".
    return min(1.0, max(0.0, EnvVarsManager.get_float_env(
        "SENTRY_TRACES_SAMPLE_RATE", 0.0,
    )))


def _redacted_event_url(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<redacted-url>"
    path = _redacted_path(parts.path)
    netloc = parts.netloc.rpartition("@")[-1]
    return urlunsplit((parts.scheme, netloc, path, "", ""))


def _redacted_path(path: str) -> str:
    for prefix in _CAPABILITY_PREFIXES:
        if path.startswith(prefix):
            return f"{prefix}***"
    return path


def _looks_like_url(value: str) -> bool:
    return value.startswith("/") or "://" in value


def _redacted_description(value: object) -> object:
    """Redact URLs in ``"<METHOD> <url>"`` span/transaction descriptions."""
    if not isinstance(value, str):
        return value
    method, separator, target = value.partition(" ")
    if separator and _looks_like_url(target):
        return f"{method} {_redacted_event_url(target)}"
    if _looks_like_url(value):
        return _redacted_event_url(value)
    return value


def _scrub_data(data: object) -> None:
    """Redact URL keys and drop query/fragment keys from a payload mapping."""
    if not isinstance(data, dict):
        return
    for key in list(data):
        normalized = str(key).lower()
        if normalized in _DROPPED_DATA_KEYS:
            data.pop(key)
        elif normalized in _URL_DATA_KEYS:
            data[key] = _redacted_event_url(data[key])


def _scrub_span(span: object) -> None:
    if not isinstance(span, dict):
        return
    if "description" in span:
        span["description"] = _redacted_description(span["description"])
    _scrub_data(span.get("data"))


def _scrub_request(event: dict[str, Any]) -> None:
    request = event.get("request")
    if not isinstance(request, dict):
        return
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


def _scrub_event(event: dict[str, Any]) -> dict[str, Any]:
    """Drop credentials, bodies, and capability-bearing URL data in place."""
    _scrub_request(event)
    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict):
        breadcrumbs = breadcrumbs.get("values")
    if isinstance(breadcrumbs, list):
        for breadcrumb in breadcrumbs:
            if isinstance(breadcrumb, dict):
                _scrub_data(breadcrumb.get("data"))
    return event


def _before_send(
    event: dict[str, Any],
    _hint: dict[str, Any],
) -> dict[str, Any]:
    """Scrub error events before they leave the process."""
    return _scrub_event(event)


def _before_send_transaction(
    event: dict[str, Any],
    _hint: dict[str, Any],
) -> dict[str, Any]:
    """Scrub sampled performance transactions the same way as errors.

    Transactions never pass through ``before_send``, so without this hook a
    nonzero ``SENTRY_TRACES_SAMPLE_RATE`` would ship full query strings and
    capability-bearing paths for every sampled request.
    """
    _scrub_event(event)
    if "transaction" in event:
        event["transaction"] = _redacted_description(event["transaction"])
    for span in event.get("spans") or ():
        _scrub_span(span)
    contexts = event.get("contexts")
    if isinstance(contexts, dict):
        _scrub_span(contexts.get("trace"))
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
    dsn = EnvVarsManager.get_str_env("SENTRY_DSN")
    if not dsn:
        return False
    try:
        _init_sentry(
            dsn=dsn,
            environment=EnvVarsManager.get_str_env("SENTRY_ENVIRONMENT") or None,
            release=EnvVarsManager.get_str_env("SENTRY_RELEASE") or None,
            traces_sample_rate=_sample_rate(),
            send_default_pii=False,
            max_request_body_size="never",
            include_local_variables=False,
            before_send=_before_send,
            before_send_transaction=_before_send_transaction,
        )
    except Exception:
        logger.exception("Sentry initialization failed; continuing without it")
        return False
    logger.info("Sentry error tracking enabled")
    return True
