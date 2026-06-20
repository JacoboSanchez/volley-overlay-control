"""Unified OID and overlay-id validation tiers.

Different surfaces accept different identifier shapes:

* **API OIDs** (scoreboard sessions) — up to 200 chars, may include ``/`` for
  custom overlay style suffixes (e.g. ``mybroadcast/line``). Rejects ``..``.
* **Overlay IDs** (filesystem / admin CRUD) — 1–64 chars, alphanumeric plus
  ``._-`` only; no path separators.
* **UNO cloud tokens** — exactly 22 alphanumeric characters.

Every module that validates an id should import from here so acceptance rules
stay aligned across API init, overlay persistence, and admin management.
"""

from __future__ import annotations

import re

from app.overlay_backends.utils import (
    UNO_OID_LENGTH,
    matches_uno_format,
    strip_legacy_prefix,
)

# API/session OID: same rules as legacy ``app.api.oid_validation``.
API_OID_PATTERN = re.compile(r"^(?!.*\.\.)[A-Za-z0-9._\-/]{1,200}$")
API_OID_MAX_LENGTH = 200

# Overlay store / admin: filesystem-safe bare id (no slashes).
OVERLAY_ID_PATTERN = re.compile(r"^(?!\.{1,2}$)[A-Za-z0-9._-]{1,64}$")
OVERLAY_ID_MAX_LENGTH = 64

# Admin create uses the overlay-id charset; length capped like the store.
ADMIN_OVERLAY_NAME_PATTERN = OVERLAY_ID_PATTERN


def is_valid_api_oid(value: object) -> bool:
    """Return True iff *value* is a non-empty API OID within bounds."""
    return isinstance(value, str) and API_OID_PATTERN.match(value) is not None


def validate_api_oid(oid: str) -> str:
    """Return *oid* when valid; raise ``ValueError`` otherwise."""
    if not is_valid_api_oid(oid):
        raise ValueError(
            "OID must be 1–200 characters of alphanumerics, hyphens, underscores, "
            "dots, or slashes; '..' is not allowed."
        )
    return oid


def is_valid_overlay_id(value: object) -> bool:
    """Return True iff *value* is a bare overlay id safe for on-disk paths."""
    return isinstance(value, str) and OVERLAY_ID_PATTERN.match(value) is not None


def validate_overlay_id(overlay_id: str) -> str:
    """Return *overlay_id* when valid; raise ``ValueError`` otherwise."""
    if not is_valid_overlay_id(overlay_id):
        raise ValueError(
            "Overlay id must be 1–64 characters using only letters, digits, "
            "'.', '_' or '-' (no spaces)."
        )
    return overlay_id


def is_uno_oid(oid: str) -> bool:
    """Return True when *oid* matches the overlays.uno 22-char token format."""
    return matches_uno_format(oid)


def api_oid_overlay_base(oid: str) -> str | None:
    """Return the overlay-store base segment of an API OID, or ``None``.

    Strips an optional ``/style`` suffix and the legacy ``C-`` prefix, then
    checks whether the remainder is a valid :func:`validate_overlay_id` value.
    Useful to detect API OIDs that cannot map to a local overlay file.
    """
    if not is_valid_api_oid(oid):
        return None
    if oid.count("/") > 1:
        return None
    raw = oid
    if "/" in raw:
        raw = raw.split("/", 1)[0]
    base = strip_legacy_prefix(raw)
    return base if is_valid_overlay_id(base) else None


def api_oid_compatible_with_overlay_store(oid: str) -> bool:
    """True when the bare overlay segment of *oid* passes overlay-id rules."""
    return api_oid_overlay_base(oid) is not None


__all__ = [
    "ADMIN_OVERLAY_NAME_PATTERN",
    "API_OID_MAX_LENGTH",
    "API_OID_PATTERN",
    "OVERLAY_ID_MAX_LENGTH",
    "OVERLAY_ID_PATTERN",
    "UNO_OID_LENGTH",
    "api_oid_compatible_with_overlay_store",
    "api_oid_overlay_base",
    "is_uno_oid",
    "is_valid_api_oid",
    "is_valid_overlay_id",
    "validate_api_oid",
    "validate_overlay_id",
]
