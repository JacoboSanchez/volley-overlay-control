"""POST /session/init — initialise or re-use a game session for an overlay ID."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import overlays_service
from app.api.dependencies import control_token, get_session
from app.api.game_service import GameService
from app.api.routes.lifespan import get_init_lock
from app.api.schemas import ActionResponse, InitRequest, SetRulesRequest
from app.api.session_manager import GameSession, SessionManager
from app.auth.dependencies import PASSWORD_CHANGE_REQUIRED, current_user
from app.backend import Backend
from app.conf import Conf
from app.db.engine import get_db
from app.db.models.overlay import UserOverlay
from app.db.models.user import User
from app.logging_utils import redact_oid
from app.oid_utils import UNO_OUTPUT_BASE_URL
from app.overlay_backends.utils import matches_uno_format
from app.overlay_key import make_skey
from app.state import State

logger = logging.getLogger(__name__)
router = APIRouter()


def _ensure_user_overlay(db: Session, user: User, oid: str) -> UserOverlay:
    """Return the caller's overlay row for *oid*, auto-creating it.

    Opening a board for an id the user has not added yet simply registers it
    (mints a public OBS token) — the explicit "My overlays" management screen
    is for renaming/removing, not a precondition for use.
    """
    overlay = overlays_service.get_overlay(db, user.id, oid)
    if overlay is None:
        overlay = overlays_service.create_overlay(db, user.id, oid)
        db.commit()
    return overlay


def _resolve_init_overlay(
    db: Session, *, token: str | None, public_user: str | None,
    user: User | None, oid: str,
) -> UserOverlay:
    """Resolve the overlay to initialise from whichever credential is present.

    Operator (token) and public-bookmark (username+oid) modes resolve an
    existing overlay; owner (cookie) mode auto-creates the overlay for a
    not-yet-registered ``oid``.
    """
    if token:
        overlay = overlays_service.get_by_control_token(db, token)
        if overlay is None:
            raise HTTPException(status_code=403, detail="Invalid or revoked control link.")
        return overlay
    if public_user:
        overlay = overlays_service.get_public_by_username_and_oid(db, public_user, oid)
        if overlay is None:
            raise HTTPException(status_code=403, detail="Invalid or revoked control link.")
        return overlay
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    if user.must_change_password:
        raise HTTPException(status_code=409, detail=PASSWORD_CHANGE_REQUIRED)
    return _ensure_user_overlay(db, user, oid)


@router.post("/session/init", response_model=ActionResponse)
async def init_session(
    req: InitRequest,
    token: str | None = Depends(control_token),
    u: str | None = Query(None, description="Username for a public ?u=&oid= board URL"),
    user: User | None = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Initialise (or re-use) a game session for an overlay.

    Reachable by the owner (cookie + ``oid``), an operator holding the overlay's
    control token (``?c=``), or an opted-in public ``?u=&oid=`` bookmark — so a
    board can be bootstrapped after a server restart by whoever opens the link.
    """
    try:
        overlay = _resolve_init_overlay(
            db, token=token, public_user=u, user=user, oid=req.oid,
        )
    except overlays_service.OverlayError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    skey = make_skey(overlay.user_id, overlay.oid)
    is_uno = matches_uno_format(overlay.oid)

    conf = Conf()
    conf.oid = overlay.oid
    conf.user_id = overlay.user_id
    conf.skey = skey
    conf.public_token = overlay.public_token
    # Output URL precedence: explicit request > the overlay's stored output URL
    # (cloud/custom) > auto-resolved at validation time.
    conf.output = req.output_url or overlay.output_url or None
    # Per-overlay default match rules replace the env defaults for a fresh
    # session; the request still wins, and once the board edits the rules they
    # persist in the session meta and win on subsequent inits.
    if overlay.points is not None:
        conf.points = overlay.points
    if overlay.points_last_set is not None:
        conf.points_last_set = overlay.points_last_set
    if overlay.sets is not None:
        conf.sets = overlay.sets
    if req.points_limit is not None:
        conf.points = req.points_limit
    if req.points_limit_last_set is not None:
        conf.points_last_set = req.points_limit_last_set
    if req.sets_limit is not None:
        conf.sets = req.sets_limit

    async with get_init_lock(skey):
        existing = SessionManager.get(skey)
        if existing is not None:
            session = await run_in_threadpool(
                SessionManager.get_or_create,
                skey, conf, None,
                req.points_limit, req.points_limit_last_set, req.sets_limit,
            )
            await run_in_threadpool(GameService.refresh_customization, session)
            logger.debug("Session reused for skey=%s", redact_oid(skey))
            return ActionResponse(success=True, state=GameService.get_state(session))

        # For a local (non-uno) overlay, make sure the per-user overlay state
        # exists so the Backend resolves it as a local/custom overlay.
        if not is_uno:
            from app.overlay import overlay_state_store
            await run_in_threadpool(overlay_state_store.ensure_overlay, skey)

        backend = Backend(conf)
        status = await run_in_threadpool(backend.validate_and_store_model_for_oid, overlay.oid)
        if status != State.OIDStatus.VALID:
            logger.warning(
                "Session init rejected for skey=%s status=%s",
                redact_oid(skey), status.value,
            )
            return ActionResponse(
                success=False,
                state=None,
                message=f"OID validation returned '{status.value}'.",
            )

        await run_in_threadpool(backend.init_ws_client)

        if not conf.output:
            token = await run_in_threadpool(backend.fetch_output_token, overlay.oid)
            if token:
                conf.output = (
                    token if token.startswith("http")
                    else UNO_OUTPUT_BASE_URL + token
                )

        session = await run_in_threadpool(
            SessionManager.get_or_create,
            skey, conf, backend,
            req.points_limit, req.points_limit_last_set, req.sets_limit,
        )
        logger.info("Session created for skey=%s", redact_oid(skey))
    return ActionResponse(success=True, state=GameService.get_state(session))


@router.post(
    "/session/rules",
    response_model=ActionResponse,
    summary="Update match rules (mode, points, sets) for the session",
)
async def set_rules(
    req: SetRulesRequest,
    session: GameSession = Depends(get_session),
):
    """Update match-rule preset for the session.

    All fields are optional. ``mode`` accepts ``"indoor"`` or
    ``"beach"`` and drives the beach side-switch indicator. The
    ``reset_to_defaults`` flag replaces every limit with the
    canonical preset for the resulting mode. Per-field overrides
    in the same call still win, so the UI can switch modes and
    keep one custom limit in a single request.
    """
    async with session.lock:
        return GameService.set_rules(
            session,
            mode=req.mode,
            points_limit=req.points_limit,
            points_limit_last_set=req.points_limit_last_set,
            sets_limit=req.sets_limit,
            reset_to_defaults=req.reset_to_defaults,
        )
