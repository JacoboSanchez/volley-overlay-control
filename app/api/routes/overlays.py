"""User overlay management + per-session data endpoints (/overlays, /teams, /links, /styles)."""

import logging
import urllib.parse
from functools import partial
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import overlays_service
from app.api import match_archive
from app.api.dependencies import get_session
from app.api.overlay_links_service import build_overlay_links
from app.api.pagination import PAGINATED_RESPONSES, Page, PageDep, with_total
from app.api.schemas import CreateOverlayRequest, OverlayOut, UpdateOverlayRequest
from app.api.session_manager import GameSession, SessionManager
from app.auth.dependencies import require_user
from app.db.engine import after_commit, after_rollback, get_db
from app.db.models.overlay import UserOverlay
from app.db.models.user import User
from app.env_vars_manager import EnvVarsManager
from app.overlay_lifecycle import (
    OverlayLifecycleLease,
    overlay_lifecycle_gate,
    release_after_transaction,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _delete_overlay_runtime(
    skey: str,
    lifecycle_lease: OverlayLifecycleLease | None = None,
) -> None:
    """Remove non-database state after the overlay row is durably deleted."""
    from app.api import session_persistence
    from app.overlay import overlay_state_store
    from app.overlay_executor import get_overlay_executor

    try:
        # Closing the session first prevents its backend from accepting any
        # more background work. Run deletion as the next item in the same
        # keyed FIFO, after every already-accepted push. The lifecycle claim
        # rejects same-OID create/init work until this barrier has completed.
        SessionManager.remove(skey)

        def _delete_persisted_runtime() -> None:
            # Reap once more at the lifecycle barrier. The first removal
            # stops the known session before queued work drains; this second
            # removal guarantees no session admitted by already-running work
            # survives when the exclusive deletion claim is released.
            SessionManager.remove(skey)
            session_persistence.delete_session_meta(skey)
            overlay_state_store.delete_overlay(skey)
            # Reports key on the user (FK), not the overlay, so remove this
            # overlay's archived matches explicitly.
            match_archive.delete_for_oid(skey)

        get_overlay_executor().run_after_pending(skey, _delete_persisted_runtime)
    finally:
        if lifecycle_lease is not None:
            lifecycle_lease.release()


def _overlay_out(
    request: Request,
    overlay: UserOverlay,
    *,
    username: str | None = None,
) -> OverlayOut:
    public_url = (EnvVarsManager.get_env_var("OVERLAY_PUBLIC_URL", "") or "").rstrip("/")
    base = public_url or str(request.base_url).rstrip("/")
    local_url = f"{base}/overlay/{overlay.public_token}"
    control_url = f"{base}/board?c={overlay.control_token}" if overlay.control_token else None
    public_control_url = (
        f"{base}/board?u={urllib.parse.quote(username, safe='')}&oid={urllib.parse.quote(overlay.oid, safe='')}"
        if (overlay.public_control and username)
        else None
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
        is_favorite=overlay.is_favorite,
    )


@router.get(
    "/overlays",
    response_model=list[OverlayOut],
    responses=PAGINATED_RESPONSES,
)
def list_my_overlays(
    request: Request,
    response: Response,
    user: User = Depends(require_user),
    db: Session = Depends(get_db, scope="function"),
    page: Page = PageDep,
) -> list[OverlayOut]:
    """Return the overlays owned by the caller."""
    with_total(response, overlays_service.count_overlays(db, user.id))
    return [
        _overlay_out(request, o, username=user.username)
        for o in overlays_service.list_overlays(
            db,
            user.id,
            limit=page.limit,
            offset=page.offset,
        )
    ]


@router.post("/overlays", response_model=OverlayOut, status_code=201)
def create_my_overlay(
    body: CreateOverlayRequest,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db, scope="function"),
) -> OverlayOut:
    """Register a new overlay for the caller (mints a public output token)."""
    from app.overlay_key import make_skey

    normalized_oid = overlays_service.normalize_oid(body.oid)
    lifecycle_lease = overlay_lifecycle_gate.begin_use(
        make_skey(user.id, normalized_oid),
    )
    release_after_transaction(db, lifecycle_lease)
    overlay = overlays_service.create_overlay(
        db,
        user.id,
        normalized_oid,
        description=body.description,
    )
    return _overlay_out(request, overlay, username=user.username)


@router.patch("/overlays/{oid}", response_model=OverlayOut)
def update_my_overlay(
    oid: str,
    body: UpdateOverlayRequest,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db, scope="function"),
) -> OverlayOut:
    """Edit an overlay's display name, favorite state, and control toggle.

    Only the fields present in the request body are changed (``exclude_unset``),
    so a partial PATCH never clobbers settings the caller didn't mention.
    """
    overlay = overlays_service.update_overlay(
        db,
        user.id,
        oid,
        **body.model_dump(exclude_unset=True),
    )
    return _overlay_out(request, overlay, username=user.username)


@router.delete("/overlays/{oid}")
def delete_my_overlay(
    oid: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, bool]:
    """Delete one of the caller's overlays and its in-process session/state.

    Sync handler — the whole body (DB delete, state-store and archive file
    removal) is blocking work and runs in the threadpool.
    """
    from app.overlay_key import make_skey

    skey = make_skey(user.id, oid)
    lifecycle_lease = overlay_lifecycle_gate.begin_delete(skey)
    # On rollback no runtime deletion runs, but the exclusive claim must still
    # be released. The commit callback releases it only after queued work and
    # persisted runtime cleanup have completed.
    after_rollback(db, lifecycle_lease.release)
    if not overlays_service.delete_overlay(db, user.id, oid):
        raise HTTPException(status_code=404, detail="Overlay not found.")
    after_commit(
        db,
        partial(_delete_overlay_runtime, skey, lifecycle_lease),
    )
    return {"ok": True}


@router.post("/overlays/{oid}/regenerate-control-token", response_model=OverlayOut)
def regenerate_control_token(
    oid: str,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db, scope="function"),
) -> OverlayOut:
    """Mint a fresh control token for one of the caller's overlays.

    This revokes any previously-shared control link for that board.
    """
    overlay = overlays_service.regenerate_control_token(db, user.id, oid)
    return _overlay_out(request, overlay, username=user.username)


# NOTE: ``GET /api/v1/teams`` now lives in app/api/routes/teams.py and returns
# the authenticated user's team list (DB-backed) instead of the env-driven
# predefined catalog.


@router.get("/links")
async def get_links(
    request: Request,
    session: GameSession = Depends(get_session),
) -> dict[str, str]:
    """Return overlay, preview, spectator, and public-report links."""
    return await build_overlay_links(request, session)


@router.get("/styles")
async def get_styles(
    session: GameSession = Depends(get_session),
) -> list[str]:
    """Return available overlay styles."""
    return await run_in_threadpool(session.backend.get_available_styles)


@router.get("/style-capabilities")
async def get_style_capabilities(
    session: GameSession = Depends(get_session),
) -> dict[str, Any]:
    """Per-style UI capability flags (theme / vertical-anchor support).

    The control UI uses this to only surface the dark/light theme selector
    and the top/center/bottom vertical-anchor control for styles where they
    actually change something.
    """
    return await run_in_threadpool(session.backend.get_style_capabilities)
