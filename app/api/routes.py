import logging
import urllib.parse
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query

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
from app.oid_dialog import OidDialog

logger = logging.getLogger("APIRoutes")

api_router = APIRouter(prefix="/api/v1", tags=["Scoreboard API v1"])

# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


@api_router.post("/session/init", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def init_session(req: InitRequest):
    """Initialise (or re-use) a game session for the given overlay ID."""
    conf = Conf()
    conf.oid = req.oid
    # Clear env-var default — API sessions resolve output per-OID, not from
    # the UNO_OVERLAY_OUTPUT env var (which is for NiceGUI single-overlay mode).
    conf.output = req.output_url if req.output_url else None
    if req.points_limit is not None:
        conf.points = req.points_limit
    if req.points_limit_last_set is not None:
        conf.points_last_set = req.points_limit_last_set
    if req.sets_limit is not None:
        conf.sets = req.sets_limit

    # Check if session already exists — avoid creating a Backend unnecessarily
    existing = SessionManager.get(req.oid)
    if existing is not None:
        # Update limits if explicitly provided
        session = SessionManager.get_or_create(
            req.oid, conf, None,
            req.points_limit, req.points_limit_last_set, req.sets_limit,
        )
        return ActionResponse(success=True, state=GameService.get_state(session))

    # New session: create Backend and validate OID
    backend = Backend(conf)
    status = backend.validate_and_store_model_for_oid(req.oid)
    if status != State.OIDStatus.VALID:
        return ActionResponse(
            success=False,
            state=None,
            message=f"OID validation returned '{status.value}'.",
        )

    backend.init_ws_client()

    # Auto-resolve output URL if not explicitly provided (mirrors NiceGUI startup)
    if not conf.output:
        token = backend.fetch_output_token(req.oid)
        if token:
            conf.output = (
                token if token.startswith("http")
                else OidDialog.UNO_OUTPUT_BASE_URL + token
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
    return GameService.get_customization(session)


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
    return GameService.add_point(session, req.team, req.undo)


@api_router.post("/game/add-set", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def add_set(req: TeamActionRequest,
                  session: GameSession = Depends(get_session)):
    return GameService.add_set(session, req.team, req.undo)


@api_router.post("/game/add-timeout", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def add_timeout(req: TeamActionRequest,
                      session: GameSession = Depends(get_session)):
    return GameService.add_timeout(session, req.team, req.undo)


@api_router.post("/game/change-serve", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def change_serve(req: ServeRequest,
                       session: GameSession = Depends(get_session)):
    return GameService.change_serve(session, req.team)


@api_router.post("/game/set-score", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def set_score(req: SetScoreRequest,
                    session: GameSession = Depends(get_session)):
    return GameService.set_score(session, req.team, req.set_number, req.value)


@api_router.post("/game/set-sets", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def set_sets(req: SetSetsRequest,
                   session: GameSession = Depends(get_session)):
    return GameService.set_sets_value(session, req.team, req.value)


@api_router.post("/game/reset", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def reset_game(session: GameSession = Depends(get_session)):
    return GameService.reset(session)


# ---------------------------------------------------------------------------
# Display controls
# ---------------------------------------------------------------------------


@api_router.post("/display/visibility", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def set_visibility(req: VisibilityRequest,
                         session: GameSession = Depends(get_session)):
    return GameService.set_visibility(session, req.visible)


@api_router.post("/display/simple-mode", response_model=ActionResponse,
                 dependencies=[Depends(verify_api_key)])
async def set_simple_mode(req: SimpleModeRequest,
                          session: GameSession = Depends(get_session)):
    return GameService.set_simple_mode(session, req.enabled)


# ---------------------------------------------------------------------------
# Customization
# ---------------------------------------------------------------------------


@api_router.put("/customization", response_model=ActionResponse,
                dependencies=[Depends(verify_api_key)])
async def update_customization(data: dict,
                               session: GameSession = Depends(get_session)):
    return GameService.update_customization(session, data)


# ---------------------------------------------------------------------------
# Predefined data (teams, themes, links)
# ---------------------------------------------------------------------------


@api_router.get("/teams",
                dependencies=[Depends(verify_api_key)])
async def get_teams():
    """Return predefined team names with icon/color data."""
    Customization.refresh()
    return Customization.predefined_teams


@api_router.get("/themes",
                dependencies=[Depends(verify_api_key)])
async def get_themes():
    """Return available theme definitions."""
    Customization.refresh()
    return Customization.THEMES


@api_router.get("/links",
                dependencies=[Depends(verify_api_key)])
async def get_links(session: GameSession = Depends(get_session)):
    """Return control, overlay, and preview links for the session."""
    oid = session.oid
    output = session.conf.output
    cust = session.customization
    links = {}

    if not session.backend.is_custom_overlay(oid):
        links["control"] = f"https://app.overlays.uno/control/{oid}"

    if output and output.strip():
        # compose_output prepends the uno base URL for bare tokens;
        # full URLs (custom overlays) are used as-is.
        overlay_url = (
            output if output.startswith("http")
            else PasswordAuthenticator.compose_output(output)
        )
        links["overlay"] = overlay_url

        # Pass the full overlay URL and geometry so the preview link is
        # read-only — no control token exposed.
        encoded_output = urllib.parse.quote(overlay_url, safe='')
        posx = cust.get_h_pos()
        posy = cust.get_v_pos()
        width = cust.get_width()
        height = cust.get_height()
        layout_id = session.conf.id if hasattr(session.conf, 'id') else ''
        links["preview"] = (
            f"./preview?output={encoded_output}&width={width}"
            f"&height={height}&x={posx}&y={posy}&layout_id={layout_id}"
        )

    return links


@api_router.get("/styles",
                dependencies=[Depends(verify_api_key)])
async def get_styles(session: GameSession = Depends(get_session)):
    """Return available overlay styles."""
    return session.backend.get_available_styles()


# ---------------------------------------------------------------------------
# WebSocket — real-time state stream
# ---------------------------------------------------------------------------


@api_router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, oid: str = Query(...)):
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
    finally:
        WSHub.disconnect(ws, oid)
