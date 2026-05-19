"""Persist overlay state and push WebSocket updates to control clients."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.api.schemas import GameStateResponse
from app.api.ws_hub import WSHub

if TYPE_CHECKING:
    from app.api.session_manager import GameSession


def save_and_broadcast(
    session: GameSession,
    state_response: GameStateResponse | None = None,
) -> None:
    """Persist state to the overlay backend and notify WS clients."""
    session.game_manager.save(session.simple, session.current_set)
    session.persist_meta()
    broadcast(session, state_response)


def broadcast(
    session: GameSession,
    state_response: GameStateResponse | None = None,
) -> None:
    """Notify all WebSocket frontend clients about the new state."""
    if state_response is None:
        from app.api.game_service import GameService

        state_response = GameService.get_state(session)
    payload_json = state_response.model_dump_json()
    WSHub.broadcast_payload_json_sync(session.oid, payload_json)
