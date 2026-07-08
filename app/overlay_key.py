"""Storage-key helpers for per-user overlays.

Every persistence surface that used to be keyed by a bare ``oid``
(``OverlayStateStore``, ``action_log``, ``session_persistence``,
``match_archive``, ``SessionManager``) is now keyed by a *storage key*
``skey = f"{user_id}:{oid}"`` so two users can own the same ``oid``
independently.

The ``oid`` component is still validated with
:func:`app.id_validation.validate_overlay_id` at the API boundary; the
composite key is then trusted as filesystem-safe because ``user_id`` is an
integer and the helpers downstream hash the key into a hex filename anyway.
"""

from __future__ import annotations

import re

from app.id_validation import OVERLAY_ID_MAX_LENGTH, is_valid_overlay_id

# ``<int>:<overlay_id>`` — the only shape a storage key may take.
_SKEY_PATTERN = re.compile(rf"^[0-9]+:[A-Za-z0-9._-]{{1,{OVERLAY_ID_MAX_LENGTH}}}$")


def make_skey(user_id: int, oid: str) -> str:
    """Compose the internal storage key for *(user_id, oid)*."""
    return f"{user_id}:{oid}"


def is_valid_skey(value: object) -> bool:
    """Return True iff *value* is a well-formed storage key.

    Rejects the ``..`` overlay-id traversal case via
    :func:`is_valid_overlay_id` on the parsed ``oid`` component.
    """
    if not isinstance(value, str):
        return False
    if _SKEY_PATTERN.match(value) is None:
        return False
    _, _, oid = value.partition(":")
    return is_valid_overlay_id(oid)


def split_skey(skey: str) -> tuple[int, str]:
    """Return ``(user_id, oid)`` parsed from a storage key.

    Raises ``ValueError`` for a malformed key.
    """
    if not is_valid_skey(skey):
        raise ValueError(f"Invalid storage key: {skey!r}")
    user_part, _, oid = skey.partition(":")
    return int(user_part), oid
