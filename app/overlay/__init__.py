"""Overlay serving package — absorbed from volleyball-scoreboard-overlay.

Provides local overlay state management, OBS WebSocket broadcasting,
and HTTP endpoints for serving overlay templates to OBS browser sources.

Singleton instances are created here and shared between the overlay routes
and the LocalOverlayBackend.
"""

import os

from app.overlay.state_store import OverlayStateStore
from app.overlay.broadcast import ObsBroadcastHub

_base_dir = os.path.dirname(os.path.abspath(__file__))
_data_dir = os.path.join(_base_dir, "..", "..", "data")
_templates_dir = os.path.join(_base_dir, "..", "..", "overlay_templates")

overlay_state_store = OverlayStateStore(_data_dir, _templates_dir)
obs_broadcast_hub = ObsBroadcastHub()


def _on_state_changed(overlay_id):
    """Broadcast callback — triggered after every state change."""
    obs_broadcast_hub.schedule_broadcast_from_sync(
        overlay_id, lambda oid=overlay_id: overlay_state_store.get_state(oid)
    )


overlay_state_store.set_broadcast_callback(_on_state_changed)
