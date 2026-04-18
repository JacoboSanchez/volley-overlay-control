"""Admin routes — custom overlay manager page and CRUD endpoints.

Two routers are exported:

* ``admin_page_router`` — serves the standalone HTML page at ``/manage``.
* ``admin_router`` — mounted under ``/api/v1/admin`` with JSON endpoints
  for listing, creating, copying and deleting custom overlays (the ones
  handled in-process by ``LocalOverlayBackend`` and persisted to
  ``data/overlay_state_{id}.json``).

Predefined overlay catalogues are configured outside the app, either via
the ``PREDEFINED_OVERLAYS`` environment variable or the remote
configurator, and are not editable from this surface.

All JSON endpoints require the ``OVERLAY_MANAGER_PASSWORD`` environment
variable to be set and the request to include a matching
``Authorization: Bearer <password>`` header.
"""

import os
import re
import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.env_vars_manager import EnvVarsManager

logger = logging.getLogger("AdminRoutes")

_PAGE_PATH = os.path.join(os.path.dirname(__file__), "static", "overlays.html")

# Custom overlay IDs are used as filenames and URL path components, so
# only allow the characters that cannot collide with the filesystem or
# HTTP path parsing. The ``C-`` prefix is added automatically when the
# overlay is used as an OID.
_OVERLAY_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CustomOverlayCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Overlay id (without the C- prefix)")
    copy_from: Optional[str] = Field(
        None,
        description="Optional existing overlay id to clone configuration from",
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _get_admin_password() -> Optional[str]:
    password = EnvVarsManager.get_env_var("OVERLAY_MANAGER_PASSWORD", None)
    if password is None:
        return None
    password = password.strip()
    return password or None


def require_admin(authorization: str = Header(None)) -> None:
    """Validate the admin Bearer token."""
    password = _get_admin_password()
    if password is None:
        raise HTTPException(
            status_code=503,
            detail="Overlay management is disabled. Set OVERLAY_MANAGER_PASSWORD to enable it.",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing admin password. Use 'Authorization: Bearer <password>'.",
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token, password):
        raise HTTPException(status_code=403, detail="Invalid admin password.")


def _validate_overlay_id(value: str) -> str:
    name = (value or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Overlay name is required.")
    if not _OVERLAY_ID_PATTERN.fullmatch(name):
        raise HTTPException(
            status_code=400,
            detail="Overlay name may only contain letters, digits, '-', '_' and '.'.",
        )
    return name


def _overlay_store():
    from app.overlay import overlay_state_store
    return overlay_state_store


# ---------------------------------------------------------------------------
# Page router
# ---------------------------------------------------------------------------


admin_page_router = APIRouter(tags=["Admin"])


@admin_page_router.get("/manage", include_in_schema=False)
def manage_overlays_page():
    """Serve the standalone custom-overlay manager page."""
    if not os.path.isfile(_PAGE_PATH):
        raise HTTPException(status_code=500, detail="Admin page template not found.")
    return FileResponse(
        _PAGE_PATH,
        media_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# ---------------------------------------------------------------------------
# API router
# ---------------------------------------------------------------------------


admin_router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


@admin_router.get("/status")
def admin_status():
    """Report whether overlay management is enabled on this server."""
    return {"enabled": _get_admin_password() is not None}


@admin_router.post("/login")
def admin_login(_: None = Depends(require_admin)):
    """Validate the admin password. Returns ``{"ok": true}`` on success."""
    return {"ok": True}


@admin_router.get("/custom-overlays", dependencies=[Depends(require_admin)])
def list_custom_overlays():
    """Return every custom overlay persisted on disk.

    Each entry carries the overlay id (the part after the ``C-`` prefix),
    its derived output key and the corresponding OID clients should use
    when pointing the scoreboard at the overlay.
    """
    store = _overlay_store()
    return [
        {
            "id": entry["id"],
            "oid": f"C-{entry['id']}",
            "output_key": entry["output_key"],
        }
        for entry in store.list_overlays()
    ]


@admin_router.post("/custom-overlays", dependencies=[Depends(require_admin)])
def create_custom_overlay(payload: CustomOverlayCreate):
    """Create a new custom overlay, optionally cloning an existing one."""
    name = _validate_overlay_id(payload.name)
    store = _overlay_store()

    if store.overlay_exists(name):
        raise HTTPException(
            status_code=409, detail=f"Overlay '{name}' already exists.",
        )

    if payload.copy_from:
        source = _validate_overlay_id(payload.copy_from)
        if not store.overlay_exists(source):
            raise HTTPException(
                status_code=404,
                detail=f"Source overlay '{source}' not found.",
            )
        store.copy_overlay(source, name)
    else:
        store.create_overlay(name)

    return {
        "id": name,
        "oid": f"C-{name}",
        "output_key": store.get_output_key(name),
    }


@admin_router.delete("/custom-overlays/{name}", dependencies=[Depends(require_admin)])
async def delete_custom_overlay(name: str):
    """Remove a custom overlay and its persisted state."""
    name = _validate_overlay_id(name)
    store = _overlay_store()
    existed = store.delete_overlay(name)
    if not existed:
        raise HTTPException(status_code=404, detail=f"Overlay '{name}' not found.")
    try:
        from app.overlay import obs_broadcast_hub
        await obs_broadcast_hub.cleanup_overlay(name)
    except Exception:
        pass
    return {"ok": True}
