import json
import logging
import asyncio
from contextlib import asynccontextmanager
from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, Depends, Header, Request, WebSocket, WebSocketDisconnect, Query, HTTPException

from app.api.schemas import (
    InitRequest, TeamActionRequest, SetScoreRequest, SetSetsRequest,
    ServeRequest, VisibilityRequest, SimpleModeRequest,
    ActionResponse, GameStateResponse,
)
from app.api.dependencies import verify_api_key, get_session
from app.api.session_manager import SessionManager, GameSession
from app.api.game_service import GameService
from app.api.ws_hub import WSHub
from app.conf import Conf
from app.backend import Backend
from app.state import State
from app.customization import Customization
from app.authentication import PasswordAuthenticator
from app.env_vars_manager import EnvVarsManager
from app.oid_utils import extract_oid, compose_output, UNO_OUTPUT_BASE_URL
from app.admin.store import managed_overlays_store

logger = logging.getLogger("APIRoutes")

_cleanup_task = None
_init_locks = {}

def _get_init_lock(oid: str):
    if oid not in _init_locks:
        _init_locks[oid] = asyncio.Lock()
    return _init_locks[oid]


async def _session_cleanup_loop():
    """Periodically remove expired sessions."""
    while True:
        await asyncio.sleep(3600)  # Run every hour
        try:
            removed = SessionManager.cleanup_expired()
            if removed:
                logger.info("Session cleanup removed %d expired sessions", removed)
            
            # Clean up un-needed locks to prevent memory leaks
            to_remove = [oid for oid, lock in _init_locks.items() if not lock.locked()]
            for oid in to_remove:
                del _init_locks[oid]
        except Exception:
            logger.exception("Error during session cleanup")


@asynccontextmanager
async def router_lifespan(app):
    global _cleanup_task
    _cleanup_task = asyncio.create_task(_session_cleanup_loop())
    yield
    if _cleanup_task:
        _cleanup_task.cancel()
    SessionManager.clear()

api_router = APIRouter(prefix="/api/v1", tags=["Scoreboard API v1"], lifespan=router_lifespan)

# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


@api_router.post("/session/init", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def init_session(req: InitRequest, request: Request):
    """Initialise (or re-use) a game session for the given overlay ID."""
    from app.api.dependencies import check_oid_access
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

    async with _get_init_lock(req.oid):
        # Check if session already exists — avoid creating a Backend unnecessarily
        existing = SessionManager.get(req.oid)
        if existing is not None:
            # Update limits if explicitly provided
            session = SessionManager.get_or_create(
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

        session = SessionManager.get_or_create(
            req.oid, conf, backend,
            req.points_limit, req.points_limit_last_set, req.sets_limit,
        )
    return ActionResponse(success=True, state=GameService.get_state(session))


# ---------------------------------------------------------------------------
# State queries
# ---------------------------------------------------------------------------


@api_router.get("/state", response_model=GameStateResponse,
                dependencies=[Depends(verify_api_key)])
async def get_state(session: GameSession = Depends(get_session)):
    return GameService.get_state(session)


@api_router.get("/customization",
                dependencies=[Depends(verify_api_key)])
async def get_customization(session: GameSession = Depends(get_session)):
    return await run_in_threadpool(GameService.refresh_customization, session)


@api_router.get("/config",
                dependencies=[Depends(verify_api_key)])
async def get_config(session: GameSession = Depends(get_session)):
    return {
        "points_limit": session.points_limit,
        "points_limit_last_set": session.points_limit_last_set,
        "sets_limit": session.sets_limit,
    }


# ---------------------------------------------------------------------------
# Game actions
# ---------------------------------------------------------------------------


@api_router.post("/game/add-point", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def add_point(req: TeamActionRequest,
                    session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.add_point(session, req.team, req.undo)


@api_router.post("/game/add-set", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def add_set(req: TeamActionRequest,
                  session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.add_set(session, req.team, req.undo)


@api_router.post("/game/add-timeout", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def add_timeout(req: TeamActionRequest,
                      session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.add_timeout(session, req.team, req.undo)


@api_router.post("/game/change-serve", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def change_serve(req: ServeRequest,
                       session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.change_serve(session, req.team)


@api_router.post("/game/set-score", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def set_score(req: SetScoreRequest,
                    session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.set_score(session, req.team, req.set_number, req.value)


@api_router.post("/game/set-sets", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def set_sets(req: SetSetsRequest,
                   session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.set_sets_value(session, req.team, req.value)


@api_router.post("/game/reset", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def reset_game(session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.reset(session)


# ---------------------------------------------------------------------------
# Display controls
# ---------------------------------------------------------------------------


@api_router.post("/display/visibility", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def set_visibility(req: VisibilityRequest,
                         session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.set_visibility(session, req.visible)


@api_router.post("/display/simple-mode", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def set_simple_mode(req: SimpleModeRequest,
                          session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.set_simple_mode(session, req.enabled)


# ---------------------------------------------------------------------------
# Customization
# ---------------------------------------------------------------------------


@api_router.put("/customization", response_model=ActionResponse,
                dependencies=[Depends(verify_api_key)])
async def update_customization(data: dict,
                               session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.update_customization(session, data)


# ---------------------------------------------------------------------------
# Predefined data (teams, themes, links)
# ---------------------------------------------------------------------------


@api_router.get("/overlays",
                dependencies=[Depends(verify_api_key)])
async def get_overlays(authorization: str = Header(None)):
    """Return predefined overlays available for selection.

    Merges two sources:

    * ``PREDEFINED_OVERLAYS`` env var (read-only, configured at startup).
    * Overlays managed through the ``/manage`` admin page, persisted in
      ``data/managed_overlays.json``.

    When a name exists in both, the managed overlay wins. Entries are
    filtered by ``allowed_users`` using the caller's identity when user
    authentication is enabled.
    """
    merged: dict = {}

    overlays_json = EnvVarsManager.get_env_var('PREDEFINED_OVERLAYS', None)
    if overlays_json and overlays_json.strip():
        try:
            env_overlays = json.loads(overlays_json)
            if isinstance(env_overlays, dict):
                merged.update(env_overlays)
            else:
                logger.warning("PREDEFINED_OVERLAYS is not a JSON object")
        except json.JSONDecodeError:
            logger.warning("PREDEFINED_OVERLAYS contains invalid JSON")

    # Managed overlays (file-backed) override env-defined ones with the same
    # name so edits from the admin page take effect immediately.
    merged.update(managed_overlays_store.as_dict())

    if not merged:
        return []

    # Identify the calling user for allowed_users filtering
    current_user = None
    if PasswordAuthenticator.do_authenticate_users() and authorization:
        token = authorization.removeprefix("Bearer ").strip()
        current_user = PasswordAuthenticator.get_username_for_api_key(token)

    return [
        {"name": name, "oid": extract_oid(config.get('control', ''))}
        for name, config in merged.items()
        if config.get('allowed_users') is None
        or (current_user and current_user in config.get('allowed_users'))
    ]


@api_router.get("/teams",
                dependencies=[Depends(verify_api_key)])
async def get_teams():
    """Return predefined team names with icon/color data."""
    await run_in_threadpool(Customization.refresh)
    return Customization.predefined_teams


@api_router.get("/themes",
                dependencies=[Depends(verify_api_key)])
async def get_themes():
    """Return available theme definitions."""
    await run_in_threadpool(Customization.refresh)
    return Customization.THEMES


@api_router.get("/links",
                dependencies=[Depends(verify_api_key)])
async def get_links(request: Request,
                    session: GameSession = Depends(get_session)):
    """Return control, overlay, and preview links for the session."""
    oid = session.oid
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

        # Custom overlays need a preview URL for the frontend preview card.
        # The preview URL encodes geometry hints; the OverlayPreview component
        # uses postMessage bounds for actual positioning.
        if session.backend.is_custom_overlay(oid):
            links["preview"] = f"{overlay_url}?layout_id=auto"

    return links


@api_router.get("/styles",
                dependencies=[Depends(verify_api_key)])
async def get_styles(session: GameSession = Depends(get_session)):
    """Return available overlay styles."""
    return await run_in_threadpool(session.backend.get_available_styles)


# ---------------------------------------------------------------------------
# WebSocket — real-time state stream
# ---------------------------------------------------------------------------


@api_router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, oid: str = Query(...)):
    from app.api.dependencies import check_oid_access
    token = ws.query_params.get("token")
    auth_header = f"Bearer {token}" if token else ws.headers.get("authorization", "")
    
    try:
        check_oid_access(auth_header, oid)
    except HTTPException as e:
        await ws.close(code=4003, reason=e.detail)
        return

    session = SessionManager.get(oid)
    if session is None:
        await ws.close(code=4004, reason="No active session for this OID.")
        return

    await WSHub.connect(ws, oid)
    try:
        # Send current state immediately on connect
        state_data = GameService.get_state(session).model_dump()
        await ws.send_json({"type": "state_update", "data": state_data})

        # Keep connection alive; client may send pings or action requests
        while True:
            data = await ws.receive_text()
            # For now we only support ping/pong; actions go through REST
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error for OID {oid}: {e}")
    finally:
        WSHub.disconnect(ws, oid)
