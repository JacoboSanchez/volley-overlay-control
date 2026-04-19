"""Helpers for redacting PII/secret-bearing values before they reach the log."""
import os
from urllib.parse import urlparse, urlunparse

_REDACT_ENABLED_CACHE: bool | None = None


def _redact_enabled() -> bool:
    """Return True when redaction should run.

    Controlled by ``LOG_REDACT`` (default: on). Set to ``0``/``false``/``no``
    in local dev to see raw values.
    """
    global _REDACT_ENABLED_CACHE
    if _REDACT_ENABLED_CACHE is None:
        raw = os.environ.get("LOG_REDACT", "1").strip().lower()
        _REDACT_ENABLED_CACHE = raw not in ("0", "false", "no", "off", "")
    return _REDACT_ENABLED_CACHE


def _reset_cache_for_tests() -> None:
    global _REDACT_ENABLED_CACHE
    _REDACT_ENABLED_CACHE = None


def redact_url(url: str | None) -> str:
    """Strip credentials, query, and fragment from *url*.

    Signed URLs (S3, GCS, auth tokens in query string) are common in the
    remote-config path and must not hit the log.
    """
    if not url:
        return "<none>"
    if not _redact_enabled():
        return url
    try:
        parts = urlparse(url)
    except ValueError:
        return "<unparseable-url>"
    netloc = parts.hostname or ""
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunparse((parts.scheme, netloc, parts.path, "", "", ""))


def redact_oid(oid: str | None) -> str:
    """Preserve the first 4 characters of *oid* and mask the rest.

    Enough to disambiguate sessions in a log search without exposing the
    full identifier to anyone who gains read access to the logs.
    """
    if not oid:
        return "<none>"
    if not _redact_enabled():
        return oid
    if len(oid) <= 4:
        return "***"
    return f"{oid[:4]}***"
