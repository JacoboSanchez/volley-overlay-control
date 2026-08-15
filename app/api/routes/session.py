"""POST /session/init — initialise or re-use a game session for an overlay ID."""

import logging

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from app import overlays_service
from app.api.dependencies import BoardAccess, board_access, get_mutation_session
from app.api.game_service import GameService
from app.api.routes.lifespan import get_init_lock
from app.api.schemas import ActionResponse, InitRequest, SetRulesRequest
from app.api.session_manager import GameSession, SessionManager
from app.api.state_snapshot import get_state_snapshot
from app.backend import Backend
from app.conf import Conf
from app.logging_utils import redact_oid
from app.overlay_key import is_valid_skey, make_skey, split_skey
from app.overlay_lifecycle import overlay_lifecycle_gate, release_after_transaction
from app.state import State

logger = logging.getLogger(__name__)
router = APIRouter()


def _resolve_init_skey(req_oid: str, access: BoardAccess) -> str:
    """Resolve one init target while claiming its transaction lifecycle.

    Owner mode can derive the prospective storage key before its overlay row
    exists, so it claims first. Capability modes resolve first, then claim;
    if deletion began between those operations the fail-fast claim rejects
    the request before it can recreate runtime state.
    """
    lifecycle_lease = None
    if (
        access.token is None
        and access.public_user is None
        and access.user is not None
    ):
        candidate = make_skey(access.user.id, (req_oid or "").strip())
        if is_valid_skey(candidate):
            lifecycle_lease = overlay_lifecycle_gate.begin_use(candidate)

    try:
        skey = access.resolve_skey(
            req_oid,
            ensure_owner_overlay=True,
        )
        if lifecycle_lease is None:
            lifecycle_lease = overlay_lifecycle_gate.begin_use(skey)
        release_after_transaction(access.db, lifecycle_lease)
        return skey
    except BaseException:
        if lifecycle_lease is not None:
            lifecycle_lease.release()
        raise


@router.post("/session/init", response_model=ActionResponse)
async def init_session(
    req: InitRequest,
    access: BoardAccess = Depends(board_access),
) -> ActionResponse:
    """Initialise (or re-use) a game session for an overlay.

    Reachable by the owner (cookie + ``oid``), an operator holding the overlay's
    control token (``?c=``), or an opted-in public ``?u=&oid=`` bookmark — so a
    board can be bootstrapped after a server restart by whoever opens the link.
    """
    skey = await run_in_threadpool(_resolve_init_skey, req.oid, access)
    owner_id, overlay_oid = split_skey(skey)
    overlay = await run_in_threadpool(
        overlays_service.get_overlay,
        access.db,
        owner_id,
        overlay_oid,
    )
    assert overlay is not None  # resolve_skey returned an existing/flushed row

    conf = Conf()
    conf.oid = overlay.oid
    conf.user_id = overlay.user_id
    conf.skey = skey
    conf.public_token = overlay.public_token
    # A fresh session starts from the env-default match rules; the request can
    # still override them, and once the board edits the rules (via
    # POST /session/rules) they persist in the session meta and win on
    # subsequent inits.
    if req.points_limit is not None:
        conf.points = req.points_limit
    if req.points_limit_last_set is not None:
        conf.points_last_set = req.points_limit_last_set
    if req.sets_limit is not None:
        conf.sets = req.sets_limit

    async with get_init_lock(skey):
        existing = SessionManager.get(skey)
        if existing is not None:
            # Re-init may update explicit rule limits and refresh the
            # customization fingerprint. Treat both as one mutation so a
            # concurrent state read cannot observe the transition halfway.
            async with existing.lock:
                session = await run_in_threadpool(
                    SessionManager.get_or_create,
                    skey, conf, None,
                    req.points_limit, req.points_limit_last_set, req.sets_limit,
                )
                await run_in_threadpool(GameService.refresh_customization, session)
            logger.debug("Session reused for skey=%s", redact_oid(skey))
            state = await get_state_snapshot(session)
            return ActionResponse(success=True, state=state)

        # Make sure the per-user overlay state exists so the Backend resolves
        # it as a local overlay.
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

        # Resolve the built-in OBS overlay URL (always the local /overlay/<token>).
        conf.output = await run_in_threadpool(backend.fetch_output_token, overlay.oid)

        session = await run_in_threadpool(
            SessionManager.get_or_create,
            skey, conf, backend,
            req.points_limit, req.points_limit_last_set, req.sets_limit,
        )
        logger.info("Session created for skey=%s", redact_oid(skey))
    state = await get_state_snapshot(session)
    return ActionResponse(success=True, state=state)


@router.post(
    "/session/rules",
    response_model=ActionResponse,
    summary="Update match rules (mode, points, sets) for the session",
)
async def set_rules(
    req: SetRulesRequest,
    session: GameSession = Depends(get_mutation_session),
) -> ActionResponse:
    """Update match-rule preset for the session.

    All fields are optional. ``mode`` accepts ``"indoor"`` or
    ``"beach"`` and drives the beach side-switch indicator. The
    ``reset_to_defaults`` flag replaces every limit with the
    canonical preset for the resulting mode. Per-field overrides
    in the same call still win, so the UI can switch modes and
    keep one custom limit in a single request.
    """
    return await run_in_threadpool(
        GameService.set_rules,
        session,
        mode=req.mode,
        points_limit=req.points_limit,
        points_limit_last_set=req.points_limit_last_set,
        sets_limit=req.sets_limit,
        reset_to_defaults=req.reset_to_defaults,
    )
