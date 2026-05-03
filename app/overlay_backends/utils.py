"""Small helpers shared by the overlay backend strategies."""

import logging
import re
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)

# UNO overlay IDs are exactly 22 mixed-case alphanumeric characters
# (e.g. ``2cIXk2IjHvMuva6Wwele8j``). The format is documented by overlays.uno
# and is what we fall back to when an OID does not match a local custom
# overlay.
UNO_OID_LENGTH = 22
_UNO_OID_PATTERN = re.compile(rf'^[A-Za-z0-9]{{{UNO_OID_LENGTH}}}$')

_LEGACY_PREFIX = "C-"


class OverlayKind(str, Enum):
    """Result of resolving an OID against the available overlay sources."""

    EMPTY = "empty"
    CUSTOM = "custom"
    UNO = "uno"
    INVALID = "invalid"


def is_custom_overlay(oid: str) -> bool:
    """Return True when *oid* uses the legacy ``C-`` custom overlay prefix.

    Kept for backward compatibility — new code should prefer
    :func:`resolve_overlay_kind`.
    """
    return oid is not None and str(oid).upper().startswith(_LEGACY_PREFIX)


def matches_uno_format(oid: str) -> bool:
    """Whether *oid* matches the UNO format (22 alphanumeric characters)."""
    return bool(oid) and bool(_UNO_OID_PATTERN.match(str(oid)))


def strip_legacy_prefix(oid: str) -> str:
    """Drop the leading ``C-`` prefix if present, otherwise return as-is."""
    if oid is None:
        return ""
    s = str(oid)
    if s.upper().startswith(_LEGACY_PREFIX):
        return s[len(_LEGACY_PREFIX):]
    return s


def split_custom_oid(oid: str):
    """Extract ``base_id`` and optional ``style`` from a custom overlay OID.

    Accepts both the legacy ``C-id[/style]`` syntax and the bare
    ``id[/style]`` form used by the new resolver.
    """
    raw_id = strip_legacy_prefix(oid)
    parts = raw_id.split('/', 1)
    return parts[0], (parts[1] if len(parts) > 1 else None)


def resolve_overlay_kind(
    oid: str,
    local_overlay_exists: Callable[[str], bool],
) -> OverlayKind:
    """Decide whether *oid* refers to a custom (local) or UNO overlay.

    Resolution order:
      1. Empty/None -> ``EMPTY``
      2. Legacy ``C-<id>[/style]`` syntax: ``CUSTOM`` iff the overlay
         exists locally, otherwise ``INVALID`` (no auto-creation).
      3. Bare id matching an existing local overlay -> ``CUSTOM``
      4. Otherwise, UNO format (22 alphanumeric chars) -> ``UNO``
      5. Anything else -> ``INVALID``
    """
    if oid is None or not str(oid).strip():
        return OverlayKind.EMPTY
    s = str(oid).strip()
    if s.upper().startswith(_LEGACY_PREFIX):
        bare = s[len(_LEGACY_PREFIX):].split('/', 1)[0]
        if bare and local_overlay_exists(bare):
            return OverlayKind.CUSTOM
        return OverlayKind.INVALID
    bare = s.split('/', 1)[0]
    if bare and local_overlay_exists(bare):
        return OverlayKind.CUSTOM
    if matches_uno_format(s):
        return OverlayKind.UNO
    return OverlayKind.INVALID


def safe_json(response, default: Any = None) -> Any:
    """Decode *response*'s JSON body, returning *default* on parse error.

    Overlay servers occasionally reply with HTML error pages even on 2xx, and
    a raw ``response.json()`` would raise and bubble up to the request
    handler. Treating malformed bodies as missing payloads degrades
    gracefully.
    """
    try:
        return response.json()
    except (ValueError, AttributeError) as exc:
        logger.warning("Non-JSON overlay response: %s", exc)
        return default


def _mock_response(status_code=200, payload=None):
    """Create a minimal response-like object for error paths."""
    body = payload or {}
    return type('MockResponse', (object,), {
        'status_code': status_code,
        'text': '',
        'json': lambda self: body,
    })()
