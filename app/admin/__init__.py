"""Admin module — custom overlay manager page and CRUD API.

Exposes an HTML page at ``/manage`` plus a REST sub-router under
``/api/v1/admin/`` for listing, creating, deleting and copying custom
(``C-`` prefixed) overlays served by the in-process overlay engine.

The admin surface is protected by a single password configured via the
``OVERLAY_MANAGER_PASSWORD`` environment variable. When that variable is
unset or empty, the admin routes return HTTP 503 and the page shows a
helpful error message.
"""

from app.admin.routes import admin_page_router, admin_router

__all__ = [
    "admin_router",
    "admin_page_router",
]
