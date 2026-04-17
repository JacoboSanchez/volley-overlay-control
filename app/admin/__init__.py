"""Admin module — overlay management page and CRUD API.

Exposes an HTML page at ``/manage`` plus a REST sub-router under
``/api/v1/admin/`` for creating, listing, updating and deleting predefined
overlays that persist to ``data/managed_overlays.json``.

The admin surface is protected by a single password configured via the
``OVERLAY_MANAGER_PASSWORD`` environment variable. When that variable is
unset or empty, the admin routes return HTTP 503 and the page shows a
helpful error message.
"""

from app.admin.store import OverlaysStore, managed_overlays_store
from app.admin.routes import admin_router, admin_page_router

__all__ = [
    "OverlaysStore",
    "managed_overlays_store",
    "admin_router",
    "admin_page_router",
]
