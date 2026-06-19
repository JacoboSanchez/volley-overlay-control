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
from app.oid_utils import compose_output

logger = logging.getLogger(__name__)

router = APIRouter()


class OverlayOut(BaseModel):
    """One of the caller's overlays."""

    oid: str = Field(..., description="Overlay identifier (unique per user)")
    display_name: str | None = Field(None, description="Friendly label")
    public_token: str = Field(..., description="Public OBS-output capability token")
    output_url: str = Field(..., description="Public /overlay/<token> URL for OBS")


class CreateOverlayRequest(BaseModel):
    oid: str = Field(..., min_length=1, max_length=64)
    display_name: str | None = Field(None, max_length=120)


def _overlay_out(request: Request, overlay) -> OverlayOut:
    public_url = (EnvVarsManager.get_env_var("OVERLAY_PUBLIC_URL", "") or "").rstrip("/")
    base = public_url or str(request.base_url).rstrip("/")
    return OverlayOut(
        oid=overlay.oid,
        display_name=overlay.display_name,
        public_token=overlay.public_token,
        output_url=f"{base}/overlay/{overlay.public_token}",
    )


@router.get("/overlays", response_model=list[OverlayOut])
async def list_my_overlays(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Return the overlays owned by the caller."""
    return [
        _overlay_out(request, o)
        for o in overlays_service.list_overlays(db, user.id)
    ]


@router.post("/overlays", response_model=OverlayOut, status_code=201)
async def create_my_overlay(
    body: CreateOverlayRequest,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Register a new overlay for the caller (mints a public OBS token)."""
    try:
        overlay = overlays_service.create_overlay(
            db, user.id, body.oid, display_name=body.display_name,
        )
    except overlays_service.OverlayError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return _overlay_out(request, overlay)


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
    return {"ok": True}


# NOTE: ``GET /api/v1/teams`` now lives in app/api/routes/teams.py and returns
# the authenticated user's team list (DB-backed) instead of the env-driven
# predefined catalog.


@router.get("/links", dependencies=[Depends(verify_api_key)])
async def get_links(request: Request,
                    session: GameSession = Depends(get_session)):
    """Return control, overlay, and preview links for the session."""
    # ``raw_oid`` for backend/cloud resolution (uno control URL needs the bare
    # token); ``skey`` (== session.oid) for per-user archive lookups.
    oid = session.raw_oid
    skey = session.oid
    output = session.conf.output
    links = {}

    if not session.backend.is_custom_overlay(oid):
        links["control"] = f"https://app.overlays.uno/control/{oid}"

    if output and output.strip():
        overlay_url = (
            output if output.startswith("http")
            else compose_output(output)
        )
        links["overlay"] = overlay_url

        # Build a preview-page URL pointing at the SPA /preview route. The
        # in-app preview card consumes the geometry params from this URL, and
        # users can also open it directly as a standalone scalable preview.
        # Custom overlays use layout_id=auto so the overlay JS reports its
        # render bounds via postMessage; geometry params are ignored in that
        # branch but kept for a uniform URL shape.
        styles: list[str] = []
        if session.backend.is_custom_overlay(oid):
            layout_id = "auto"
            x = y = 0.0
            width = height = 100.0
            try:
                styles = await run_in_threadpool(
                    session.backend.get_available_styles, oid
                ) or []
            except Exception:
                logger.exception("Failed to fetch available styles for preview")
                styles = []
        else:
            layout_id = session.conf.id or ""
            cust = session.customization
            x = cust.get_h_pos()
            y = cust.get_v_pos()
            width = cust.get_width()
            height = cust.get_height()

        base_url = str(request.base_url).rstrip('/')
        qs_params = {
            "output": overlay_url,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "layout_id": layout_id,
        }
        if len(styles) > 1:
            qs_params["styles"] = ",".join(styles)
        preview_qs = urllib.parse.urlencode(qs_params)
        links["preview"] = f"{base_url}/preview?{preview_qs}"

        # Public spectator (follow) page — same backend, mobile-first
        # read-only view that consumes the OBS WS broadcast. Only
        # surfaced for custom overlays where the output key resolves
        # to our own ``/follow/{key}`` route; cloud overlays
        # (overlays.uno) have no equivalent path.
        if session.backend.is_custom_overlay(oid) and session.public_token:
            links["follow"] = f"{base_url}/follow/{session.public_token}"

    # Surface the latest archived match report and a browseable
    # match-history index — but only when the report endpoint is
    # publicly accessible. When the operator gates the routes
    # behind ``OVERLAY_MANAGER_PASSWORD`` we deliberately do NOT
    # embed the token in the URL: the control UI does not have
    # access to that secret, and surfacing a token-bearing URL
    # invites copy-paste leaks into chat tools.
    raw_public = EnvVarsManager.get_env_var("MATCH_REPORT_PUBLIC", "false")
    if str(raw_public).strip().lower() in ("1", "true", "t", "yes", "on"):
        latest = await run_in_threadpool(_latest_match_id_for, skey)
        if latest is not None:
            base_url = str(request.base_url).rstrip('/')
            links["latest_match_report"] = f"{base_url}/match/{latest}/report"
            # The index is a per-overlay listing; only emit when there
            # *is* something to list, so the UI doesn't show a link
            # to an empty page.
            links["match_history"] = (
                f"{base_url}/matches/index.html?oid="
                + urllib.parse.quote(skey, safe="")
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
