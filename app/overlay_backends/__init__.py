"""Strategy implementations for overlay communication.

Three overlay backends exist:

- :class:`UnoOverlayBackend` — overlays.uno cloud REST API
- :class:`CustomOverlayBackend` — external overlay server (WebSocket + HTTP
  fallback)
- :class:`LocalOverlayBackend` — in-process overlay (no external server)

The public symbols below are re-exported so existing imports such as
``from app.overlay_backends import UnoOverlayBackend`` keep working after the
split into submodules.
"""

from app.overlay_backends.base import OverlayBackend
from app.overlay_backends.uno import UnoOverlayBackend
from app.overlay_backends.custom import CustomOverlayBackend
from app.overlay_backends.local import LocalOverlayBackend
from app.overlay_backends.utils import (
    _mock_response,
    is_custom_overlay,
    split_custom_oid,
)

# Re-exported so ``@patch('app.overlay_backends.AppStorage.<method>')`` keeps
# working in existing tests — patching a class attribute resolves the class
# via this namespace.
from app.app_storage import AppStorage  # noqa: F401  (re-export)

__all__ = [
    "OverlayBackend",
    "UnoOverlayBackend",
    "CustomOverlayBackend",
    "LocalOverlayBackend",
    "is_custom_overlay",
    "split_custom_oid",
    "_mock_response",
    "AppStorage",
]
