"""Overlay communication backend.

Every overlay is served **in-process** by :class:`LocalOverlayBackend` — there
is no external overlay server or cloud (overlays.uno) support.

The public symbols below are re-exported so existing imports such as
``from app.overlay_backends import LocalOverlayBackend`` keep working.
"""

from app.overlay_backends.base import OverlayBackend
from app.overlay_backends.local import LocalOverlayBackend
from app.overlay_backends.utils import (
    OverlayKind,
    _mock_response,
    is_custom_overlay,
    resolve_overlay_kind,
    split_custom_oid,
    strip_legacy_prefix,
)

__all__ = [
    "LocalOverlayBackend",
    "OverlayBackend",
    "OverlayKind",
    "_mock_response",
    "is_custom_overlay",
    "resolve_overlay_kind",
    "split_custom_oid",
    "strip_legacy_prefix",
]
