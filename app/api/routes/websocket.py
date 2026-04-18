"""WebSocket /ws — real-time state stream for an overlay session."""

import logging

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.api.game_service import GameService
from app.api.session_manager import SessionManager
from app.api.ws_hub import WSHub

logger = logging.getLogger("APIRoutes")

router = APIRouter()


@router.websocket("/ws")
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
        state_data = GameService.get_state(session).model_dump()
        await ws.send_json({"type": "state_update", "data": state_data})

        while True:
            data = await ws.receive_text()
            # Actions go through REST; WS is state-stream + ping/pong only.
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error for OID {oid}: {e}")
    finally:
        WSHub.disconnect(ws, oid)
