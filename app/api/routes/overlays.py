"""User overlay management + per-session data endpoints (/overlays, /teams, /links, /styles)."""

import logging
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import overlays_service
from app.api import match_archive
from app.api.dependencies import get_session, verify_api_key
from app.api.session_manager import GameSession
from app.auth.dependencies import require_user
from app.db.engine import get_db
from app.db.models.user import User
from app.env_vars_manager import EnvVarsManager

logger = logging.getLogger(__name__)

router = APIRouter()


class OverlayOut(BaseModel):
    """One of the caller's overlays."""

    oid: str = Field(..., description="Overlay identifier (unique per user) — the name")
    description: str | None = Field(None, description="Optional free-text description")
    public_token: str = Field(..., description="Public overlay-output capability token")
    output_url: str = Field(..., description="Built-in overlay output URL (the local /overlay/<token>)")
    control_token: str | None = Field(None, description="Shareable control capability token")
    control_url: str | None = Field(None, description="Ready-made shareable control-board link")
    public_control: bool = Field(False, description="Allow no-login control via the username+oid URL")
    public_control_url: str | None = Field(None, description="Stable username+oid bookmark link (when enabled)")


class CreateOverlayRequest(BaseModel):
    oid: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(None, max_length=120)


class UpdateOverlayRequest(BaseModel):
    description: str | None = Field(None, max_length=120)
    public_control: bool | None = Field(None, description="Toggle no-login username+oid control")


def _overlay_out(request: Request, overlay, *, username: str | None = None) -> OverlayOut:
    public_url = (EnvVarsManager.get_env_var("OVERLAY_PUBLIC_URL", "") or "").rstrip("/")
    base = public_url or str(request.base_url).rstrip("/")
    local_url = f"{base}/overlay/{overlay.public_token}"
    control_url = (
        f"{base}/board?c={overlay.control_token}" if overlay.control_token else None
    )
    public_control_url = (
        f"{base}/board?u={urllib.parse.quote(username, safe='')}"
        f"&oid={urllib.parse.quote(overlay.oid, safe='')}"
        if (overlay.public_control and username) else None
    )
    return OverlayOut(
        oid=overlay.oid,
        description=overlay.description,
        public_token=overlay.public_token,
        output_url=local_url,
        control_token=overlay.control_token,
        control_url=control_url,
        public_control=overlay.public_control,
        public_control_url=public_control_url,
    )


@router.get("/overlays", response_model=list[OverlayOut])
async def list_my_overlays(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Return the overlays owned by the caller."""
    return [
        _overlay_out(request, o, username=user.username)
        for o in overlays_service.list_overlays(db, user.id)
    ]


@router.post("/overlays", response_model=OverlayOut, status_code=201)
async def create_my_overlay(
    body: CreateOverlayRequest,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Register a new overlay for the caller (mints a public output token)."""
    try:
        overlay = overlays_service.create_overlay(
            db, user.id, body.oid,
            description=body.description,
        )
    except overlays_service.OverlayError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return _overlay_out(request, overlay, username=user.username)


@router.patch("/overlays/{oid}", response_model=OverlayOut)
async def update_my_overlay(
    oid: str,
    body: UpdateOverlayRequest,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Edit an overlay's description and no-login control toggle.

    Only the fields present in the request body are changed (``exclude_unset``),
    so a partial PATCH never clobbers settings the caller didn't mention.
    """
    try:
        overlay = overlays_service.update_overlay(
            db, user.id, oid, **body.model_dump(exclude_unset=True),
        )
    except overlays_service.OverlayError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return _overlay_out(request, overlay, username=user.username)


@router.delete("/overlays/{oid}")
async def delete_my_overlay(
    oid: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Delete one of the caller's overlays and its in-process session/state."""
    from app.api.session_manager import SessionManager
    from app.overlay import overlay_state_store
    from app.overlay_key import make_skey

    if not overlays_service.delete_overlay(db, user.id, oid):
        raise HTTPException(status_code=404, detail="Overlay not found.")
    db.commit()
    skey = make_skey(user.id, oid)
    SessionManager.remove(skey)
    await run_in_threadpool(overlay_state_store.delete_overlay, skey)
    # Reports key on the user (FK), not the overlay, so remove this overlay's
    # archived matches explicitly.
    await run_in_threadpool(match_archive.delete_for_oid, skey)
    return {"ok": True}


@router.post("/overlays/{oid}/regenerate-control-token", response_model=OverlayOut)
async def regenerate_control_token(
    oid: str,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Mint a fresh control token for one of the caller's overlays.

    This revokes any previously-shared control link for that board.
    """
    try:
        overlay = overlays_service.regenerate_control_token(db, user.id, oid)
    except overlays_service.OverlayError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return _overlay_out(request, overlay, username=user.username)


# NOTE: ``GET /api/v1/teams`` now lives in app/api/routes/teams.py and returns
# the authenticated user's team list (DB-backed) instead of the env-driven
# predefined catalog.


@router.get("/links", dependencies=[Depends(verify_api_key)])
async def get_links(request: Request,
                    session: GameSession = Depends(get_session)):
    """Return overlay, preview, and spectator links for the session."""
    # ``raw_oid`` for backend resolution; ``skey`` (== session.oid) for
    # per-user archive lookups.
    oid = session.raw_oid
    skey = session.oid
    output = session.conf.output
    links = {}

    if output and output.strip():
        links["overlay"] = output

        # Build a preview-page URL pointing at the SPA /preview route. The
        # in-app preview card consumes the geometry params from this URL, and
        # users can also open it directly as a standalone scalable preview.
        # The in-process overlay reports its own render bounds via postMessage
        # (layout_id=auto); geometry params are ignored there but kept for a
        # uniform URL shape.
        styles: list[str] = []
        try:
            styles = await run_in_threadpool(
                session.backend.get_available_styles, oid
            ) or []
        except Exception:
            logger.exception("Failed to fetch available styles for preview")
            styles = []

        base_url = str(request.base_url).rstrip('/')
        qs_params = {
            "output": output,
            "x": 0.0,
            "y": 0.0,
            "width": 100.0,
            "height": 100.0,
            "layout_id": "auto",
        }
        if len(styles) > 1:
            qs_params["styles"] = ",".join(styles)
        preview_qs = urllib.parse.urlencode(qs_params)
        links["preview"] = f"{base_url}/preview?{preview_qs}"

        # Public spectator (follow) page — the mobile-first read-only view that
        # consumes the OBS WS broadcast over the same public token.
        if session.public_token:
            links["follow"] = f"{base_url}/follow/{session.public_token}"

    # Surface the latest archived match report — but only when the
    # report endpoint is publicly readable. When reports are gated to
    # the owner (cookie) / signed URLs, we deliberately do NOT embed a
    # link here: the spectator-facing ``/links`` payload has no
    # credential to offer, and the owner reaches reports from their
    # account screen instead.
    raw_public = EnvVarsManager.get_env_var("MATCH_REPORT_PUBLIC", "false")
    if str(raw_public).strip().lower() in ("1", "true", "t", "yes", "on"):
        latest = await run_in_threadpool(_latest_match_id_for, skey)
        if latest is not None:
            base_url = str(request.base_url).rstrip('/')
            links["latest_match_report"] = f"{base_url}/match/{latest}/report"
            # Public per-overlay history page, keyed by the unguessable
            # public_token (same capability as the overlay/follow links).
            if session.public_token:
                links["match_history"] = (
                    f"{base_url}/matches/{session.public_token}"
                )

    return links


def _latest_match_id_for(oid: str):
    """Return the most-recent ``match_id`` archived for *oid*, or ``None``."""
    summaries = match_archive.list_matches(oid=oid)
    return summaries[0]["match_id"] if summaries else None


@router.get("/styles", dependencies=[Depends(verify_api_key)])
async def get_styles(session: GameSession = Depends(get_session)):
    """Return available overlay styles."""
    return await run_in_threadpool(session.backend.get_available_styles)


@router.get("/style-capabilities", dependencies=[Depends(verify_api_key)])
async def get_style_capabilities(session: GameSession = Depends(get_session)):
    """Per-style UI capability flags (theme / vertical-anchor support).

    The control UI uses this to only surface the dark/light theme selector
    and the top/center/bottom vertical-anchor control for styles where they
    actually change something.
    """
    return await run_in_threadpool(session.backend.get_style_capabilities)
