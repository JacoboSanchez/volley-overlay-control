"""POST /session/init — initialise or re-use a game session for an overlay ID."""

import logging

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import check_oid_access, get_session, verify_api_key
from app.api.game_service import GameService
from app.api.routes.lifespan import get_init_lock
from app.api.schemas import ActionResponse, InitRequest, SetRulesRequest
from app.api.session_manager import GameSession, SessionManager
from app.backend import Backend
from app.conf import Conf
from app.logging_utils import redact_oid
from app.oid_utils import UNO_OUTPUT_BASE_URL
from app.state import State

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/session/init",
    response_model=ActionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def init_session(req: InitRequest, request: Request):
    """Initialise (or re-use) a game session for the given overlay ID."""
    check_oid_access(request.headers.get("authorization", ""), req.oid)

    conf = Conf()
    conf.oid = req.oid
    conf.output = req.output_url if req.output_url else None
    if req.points_limit is not None:
        conf.points = req.points_limit
    if req.points_limit_last_set is not None:
        conf.points_last_set = req.points_limit_last_set
    if req.sets_limit is not None:
        conf.sets = req.sets_limit

    async with get_init_lock(req.oid):
        # Check if session already exists — avoid creating a Backend unnecessarily
        existing = SessionManager.get(req.oid)
        if existing is not None:
            # Update limits if explicitly provided
            session = await run_in_threadpool(
                SessionManager.get_or_create,
                req.oid, conf, None,
                req.points_limit, req.points_limit_last_set, req.sets_limit,
            )
            # Refresh customization from the overlay server so the React UI
            # always sees the latest team names, colors, logos, etc.
            await run_in_threadpool(GameService.refresh_customization, session)
            logger.info("Session reused for oid=%s", redact_oid(req.oid))
            return ActionResponse(success=True, state=GameService.get_state(session))

        # New session: create Backend and validate OID
        backend = Backend(conf)
        status = await run_in_threadpool(backend.validate_and_store_model_for_oid, req.oid)
        if status != State.OIDStatus.VALID:
            logger.warning(
                "Session init rejected for oid=%s status=%s",
                redact_oid(req.oid), status.value,
            )
            return ActionResponse(
                success=False,
                state=None,
                message=f"OID validation returned '{status.value}'.",
            )

        await run_in_threadpool(backend.init_ws_client)

        # Auto-resolve output URL if not explicitly provided
        if not conf.output:
            token = await run_in_threadpool(backend.fetch_output_token, req.oid)
            if token:
                conf.output = (
                    token if token.startswith("http")
                    else UNO_OUTPUT_BASE_URL + token
                )

        session = await run_in_threadpool(
            SessionManager.get_or_create,
            req.oid, conf, backend,
            req.points_limit, req.points_limit_last_set, req.sets_limit,
        )
        logger.info("Session created for oid=%s", redact_oid(req.oid))
    return ActionResponse(success=True, state=GameService.get_state(session))


@router.post(
    "/session/rules",
    response_model=ActionResponse,
    dependencies=[Depends(verify_api_key)],
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
