"""WebSocket /ws — real-time state stream for an overlay session.

Authenticated by the same session cookie as the REST API (browsers send
cookies on same-origin WebSocket upgrades), and addressed by the per-user
storage key so a client only ever streams a session it owns.
"""

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.game_service import GameService
from app.api.session_manager import SessionManager
from app.api.ws_hub import WSHub, WSHubFull
from app.auth import sessions
from app.db.engine import session_scope
from app.logging_utils import redact_oid
from app.overlay_key import make_skey

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_skey(ws: WebSocket, oid: str) -> str | None:
    """Resolve the cookie session to the caller's storage key, or ``None``."""
    raw = ws.cookies.get(sessions.COOKIE_NAME)
    if not raw:
        return None
    with session_scope() as db:
        user = sessions.resolve_session(db, raw)
        if user is None:
            return None
        return make_skey(user.id, oid)


@router.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    oid: str | None = Query(None, description="Overlay ID"),
    control: str | None = Query(None, description="Alias of `oid` for backward compatibility"),
):
    resolved = oid or control
    if not resolved:
        await ws.close(code=4400, reason="Missing 'oid' (or alias 'control') query parameter.")
        return

    skey = _resolve_skey(ws, resolved)
    if skey is None:
        await ws.close(code=4003, reason="Authentication required.")
        return

    session = SessionManager.get(skey)
    if session is None:
        await ws.close(code=4004, reason="No active session for this OID.")
        return

    try:
        await WSHub.connect(ws, skey)
    except WSHubFull as exc:
        # 1013 = Try Again Later. Reason stays generic so a probing client
        # cannot use the close text to enumerate which sessions are at cap.
        logger.warning(
            "Refused WS connect for %s — at cap %d",
            redact_oid(skey), exc.cap,
        )
        await ws.close(code=1013, reason="Too many clients for this OID.")
        return
    try:
        state_data = GameService.get_state(session).model_dump()
        await ws.send_json({"type": "state_update", "data": state_data})

        while True:
            data = await ws.receive_text()
            WSHub.mark_active(ws)
            # Actions go through REST; WS is state-stream + ping/pong only.
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error for %s", redact_oid(skey))
    finally:
        WSHub.disconnect(ws, skey)
