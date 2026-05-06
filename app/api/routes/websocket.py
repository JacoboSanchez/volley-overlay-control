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


# Subprotocol convention: the client opens the WebSocket with the
# subprotocols ``["bearer", "<token>"]``. The server picks
# ``bearer`` as the chosen subprotocol (echoed in the handshake) and
# uses the second list entry as the token. This is the RFC 6455
# pattern that browser ``new WebSocket(url, [...])`` clients can
# use without exposing the credential in the URL.
_BEARER_SUBPROTOCOL = "bearer"


def _resolve_ws_auth(ws: WebSocket) -> tuple[str, str | None]:
    """Return ``(authorization_header, selected_subprotocol)``.

    Resolution order:

    1. ``Sec-WebSocket-Protocol: bearer, <token>`` — preferred,
       no secret on the URL line.
    2. ``Authorization: Bearer <token>`` — for non-browser clients
       that can set headers on the upgrade request.
    3. ``?token=<value>`` — legacy fallback, kept for the existing
       CLI/script clients. Documented as deprecated.

    The selected subprotocol must be echoed back when calling
    ``ws.accept(subprotocol=...)``; otherwise a browser client drops
    the connection with a protocol-mismatch error.
    """
    raw_proto = ws.headers.get("sec-websocket-protocol", "")
    protocols = [p.strip() for p in raw_proto.split(",") if p.strip()]
    if (
        len(protocols) >= 2
        and protocols[0].lower() == _BEARER_SUBPROTOCOL
    ):
        token = protocols[1]
        return f"Bearer {token}", _BEARER_SUBPROTOCOL

    auth = ws.headers.get("authorization", "")
    if auth:
        return auth, None

    legacy_token = ws.query_params.get("token")
    if legacy_token:
        return f"Bearer {legacy_token}", None

    return "", None


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

    auth_header, selected_subprotocol = _resolve_ws_auth(ws)

    try:
        check_oid_access(auth_header, resolved)
    except HTTPException as e:
        await ws.close(code=4003, reason=e.detail)
        return

    session = SessionManager.get(resolved)
    if session is None:
        await ws.close(code=4004, reason="No active session for this OID.")
        return

    await WSHub.connect(ws, resolved, subprotocol=selected_subprotocol)
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
