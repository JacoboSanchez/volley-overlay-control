"""WebSocket /ws — real-time state stream for an overlay session."""

import logging

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.api.dependencies import check_oid_access
from app.api.game_service import GameService
from app.api.session_manager import SessionManager
from app.api.ws_hub import WSHub
from app.logging_utils import redact_oid

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    oid: str | None = Query(None),
    control: str | None = Query(None),
):
    resolved = oid or control
    if not resolved:
        await ws.close(code=4400, reason="Missing 'oid' (or alias 'control') query parameter.")
        return

    token = ws.query_params.get("token")
    auth_header = f"Bearer {token}" if token else ws.headers.get("authorization", "")

    try:
        check_oid_access(auth_header, resolved)
    except HTTPException as e:
        await ws.close(code=4003, reason=e.detail)
        return

    session = SessionManager.get(resolved)
    if session is None:
        await ws.close(code=4004, reason="No active session for this OID.")
        return

    await WSHub.connect(ws, resolved)
    try:
        state_data = GameService.get_state(session).model_dump()
        await ws.send_json({"type": "state_update", "data": state_data})

        while True:
            data = await ws.receive_text()
            # Actions go through REST; WS is state-stream + ping/pong only.
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error for OID %s", redact_oid(resolved))
    finally:
        WSHub.disconnect(ws, resolved)
