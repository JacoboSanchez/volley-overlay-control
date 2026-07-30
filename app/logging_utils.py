"""Helpers for redacting PII/secret-bearing values before they reach the log."""
import os
import re
from urllib.parse import urlparse, urlunparse

_REDACT_ENABLED_CACHE: bool | None = None

# Route prefixes whose *next* path segment is an unguessable capability
# token: the overlay/spectator/OBS `public_token`, the public
# match-history token, and the `match_id` in a report link. Anything that
# writes a request path into a log record or an error report has to mask
# these, so the definition lives here with the other redaction helpers
# rather than being restated per call site.
_CAPABILITY_PREFIXES = ("overlay", "follow", "ws", "matches", "match")
_PATH_MASK = "***"

# Matches a capability path only at the start of a value or after
# whitespace, so an embedded occurrence in a log message
# ("… on GET /overlay/abc — RuntimeError") is caught while an unrelated
# authenticated route that merely contains the word
# ("/api/v1/matches/<id>") is left readable for triage.
_CAPABILITY_PATH_RE = re.compile(
    r"(?:(?<=\s)|\A)(/(?:" + "|".join(_CAPABILITY_PREFIXES) + r")/)([^\s/?#]+)",
)


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
    netloc = parts.netloc.rpartition("@")[-1]
    return urlunparse((parts.scheme, netloc, parts.path, "", "", ""))


def mask_capability_tokens(text: str) -> str:
    """Mask capability tokens wherever they appear in *text*.

    **Unconditional** — unlike its siblings here it ignores ``LOG_REDACT``.
    Its callers include the error-reporter path, where the value leaves the
    process for a third-party service; a dev-only "show me raw values"
    switch must not be able to turn that into an exfiltration channel.
    """
    if not text:
        return text
    return _CAPABILITY_PATH_RE.sub(r"\g<1>" + _PATH_MASK, text)


def redact_path(path: str | None) -> str:
    """Mask a capability token in a request path, honouring ``LOG_REDACT``.

    For our own log sinks, where ``LOG_REDACT=0`` is a legitimate local
    debugging choice. Use :func:`mask_capability_tokens` for anything that
    leaves the process.
    """
    if not path:
        return "<none>"
    if not _redact_enabled():
        return path
    return mask_capability_tokens(path)


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
