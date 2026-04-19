"""POST /session/init — initialise or re-use a game session for an overlay ID."""

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import check_oid_access, verify_api_key
from app.api.game_service import GameService
from app.api.schemas import ActionResponse, InitRequest
from app.api.session_manager import SessionManager
from app.api.routes.lifespan import get_init_lock
from app.backend import Backend
from app.conf import Conf
from app.oid_utils import UNO_OUTPUT_BASE_URL
from app.state import State

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
            return ActionResponse(success=True, state=GameService.get_state(session))

        # New session: create Backend and validate OID
        backend = Backend(conf)
        status = await run_in_threadpool(backend.validate_and_store_model_for_oid, req.oid)
        if status != State.OIDStatus.VALID:
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
    return ActionResponse(success=True, state=GameService.get_state(session))
