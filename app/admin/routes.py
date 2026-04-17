"""Admin routes — overlay management page and CRUD endpoints.

Two routers are exported:

* ``admin_page_router`` — serves the standalone HTML page at ``/manage``.
* ``admin_router`` — mounted under ``/api/v1/admin`` with JSON endpoints
  for creating, listing, updating and deleting managed overlays.

All JSON endpoints require the ``OVERLAY_MANAGER_PASSWORD`` environment
variable to be set and the request to include a matching
``Authorization: Bearer <password>`` header.
"""

import os
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.admin.store import managed_overlays_store
from app.env_vars_manager import EnvVarsManager

logger = logging.getLogger("AdminRoutes")

_PAGE_PATH = os.path.join(os.path.dirname(__file__), "static", "overlays.html")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class OverlayPayload(BaseModel):
    name: str = Field(..., min_length=1, description="Display name of the overlay")
    control: str = Field(..., min_length=1, description="Control token or URL")
    output: Optional[str] = Field(None, description="Optional output token or URL")
    allowed_users: Optional[List[str]] = Field(
        None, description="Optional list of usernames allowed to see this overlay"
    )


class OverlayUpdatePayload(OverlayPayload):
    new_name: Optional[str] = Field(
        None, description="Rename the overlay to this value (optional)"
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
    if token != password:
        raise HTTPException(status_code=403, detail="Invalid admin password.")


# ---------------------------------------------------------------------------
# Page router
# ---------------------------------------------------------------------------


admin_page_router = APIRouter(tags=["Admin"])


@admin_page_router.get("/manage", include_in_schema=False)
def manage_overlays_page():
    """Serve the standalone overlay management page."""
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
    """Report whether overlay management is enabled on this server.

    Does not leak the password — just indicates whether an admin password
    is configured so the management UI can show a helpful message when
    the feature is disabled.
    """
    return {"enabled": _get_admin_password() is not None}


@admin_router.post("/login")
def admin_login(_: None = Depends(require_admin)):
    """Validate the admin password. Returns ``{"ok": true}`` on success."""
    return {"ok": True}


@admin_router.get("/overlays", dependencies=[Depends(require_admin)])
def list_overlays():
    """Return all managed overlays."""
    return managed_overlays_store.list()


@admin_router.post("/overlays", dependencies=[Depends(require_admin)])
def create_overlay(payload: OverlayPayload):
    try:
        return managed_overlays_store.create(
            payload.name,
            {
                "control": payload.control,
                "output": payload.output,
                "allowed_users": payload.allowed_users,
            },
        )
    except KeyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@admin_router.put("/overlays/{name}", dependencies=[Depends(require_admin)])
def update_overlay(name: str, payload: OverlayUpdatePayload):
    try:
        return managed_overlays_store.update(
            name,
            {
                "control": payload.control,
                "output": payload.output,
                "allowed_users": payload.allowed_users,
            },
            new_name=payload.new_name,
        )
    except KeyError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg else 409
        raise HTTPException(status_code=status, detail=msg)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@admin_router.delete("/overlays/{name}", dependencies=[Depends(require_admin)])
def delete_overlay(name: str):
    try:
        managed_overlays_store.delete(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True}
