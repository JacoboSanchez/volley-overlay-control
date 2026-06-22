"""Small helpers shared by the overlay backend strategy."""

import logging
from collections.abc import Callable
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

_LEGACY_PREFIX = "C-"


class OverlayKind(str, Enum):
    """Result of resolving an OID against the local overlay store."""

    EMPTY = "empty"
    CUSTOM = "custom"
    INVALID = "invalid"


def is_custom_overlay(oid: str) -> bool:
    """Return True when *oid* uses the legacy ``C-`` custom overlay prefix.

    Kept for backward compatibility — new code should prefer
    :func:`resolve_overlay_kind`.
    """
    return oid is not None and str(oid).upper().startswith(_LEGACY_PREFIX)


def strip_legacy_prefix(oid: str) -> str:
    """Drop the leading ``C-`` prefix if present, otherwise return as-is."""
    if oid is None:
        return ""
    s = str(oid)
    if s.upper().startswith(_LEGACY_PREFIX):
        return s[len(_LEGACY_PREFIX):]
    return s


def split_custom_oid(oid: str):
    """Extract ``base_id`` and optional ``style`` from an overlay OID.

    Accepts both the legacy ``C-id[/style]`` syntax and the bare
    ``id[/style]`` form.
    """
    raw_id = strip_legacy_prefix(oid)
    parts = raw_id.split('/', 1)
    return parts[0], (parts[1] if len(parts) > 1 else None)


def resolve_overlay_kind(
    oid: str,
    local_overlay_exists: Callable[[str], bool],
) -> OverlayKind:
    """Decide whether *oid* refers to a known local overlay.

    Resolution order:
      1. Empty/None -> ``EMPTY``
      2. An ``id[/style]`` (or legacy ``C-id[/style]``) whose base id exists
         in the local overlay store -> ``CUSTOM``
      3. Anything else -> ``INVALID`` (no auto-creation; overlays are created
         up-front via the "My overlays" page)
    """
    if oid is None or not str(oid).strip():
        return OverlayKind.EMPTY
    bare = strip_legacy_prefix(str(oid).strip()).split('/', 1)[0]
    if bare and local_overlay_exists(bare):
        return OverlayKind.CUSTOM
    return OverlayKind.INVALID


def safe_json(response, default: Any = None) -> Any:
    """Decode *response*'s JSON body, returning *default* on parse error.

    Overlay responses occasionally come back as HTML error pages even on 2xx,
    and a raw ``response.json()`` would raise and bubble up to the request
    handler. Treating malformed bodies as missing payloads degrades gracefully.
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

