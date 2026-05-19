"""Audit log, match archive, and webhook hooks for game mutations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.api import action_log, match_archive
from app.api.schemas import GameStateResponse
from app.api.webhooks import webhook_dispatcher

if TYPE_CHECKING:
    from app.api.session_manager import GameSession

logger = logging.getLogger(__name__)


def archive_if_finished(
    session: GameSession,
    was_finished_before: bool,
    winning_team: int,
    state_response: GameStateResponse | None = None,
) -> str | None:
    """Archive the match when it transitions to finished."""
    if was_finished_before or not session.game_manager.match_finished(session.sets_limit):
        return None
    try:
        if state_response is None:
            from app.api.game_service import GameService

            state_response = GameService.get_state(session)
        final_state = state_response.model_dump()
        customization = session.customization.get_model()
        match_id = match_archive.archive_match(
            oid=session.oid,
            final_state=final_state,
            customization=customization,
            started_at=getattr(session, "match_started_at", None),
            winning_team=winning_team,
            points_limit=session.points_limit,
            points_limit_last_set=session.points_limit_last_set,
            sets_limit=session.sets_limit,
        )
        session.persist_meta()
        return match_id
    except Exception as exc:
        logger.warning("Match archive failed: %s", exc)
        return None


def audit(
    session: GameSession,
    action: str,
    params: dict,
    popped_forward: dict | None = None,
    target_set: int | None = None,
) -> dict | None:
    """Append an audit-log record and sync ``undoable_forward_count``."""
    try:
        state = session.game_manager.get_current_state()
        score_set = target_set if target_set is not None else session.current_set
        t1_score = state.get_game(1, score_set)
        t2_score = state.get_game(2, score_set)
        serve = state.get_current_serve()
        result = {
            "current_set": session.current_set,
            "score_set": score_set,
            "match_finished": session.game_manager.match_finished(session.sets_limit),
            "team_1": {
                "sets": state.get_sets(1),
                "score": t1_score,
                "timeouts": state.get_timeout(1),
            },
            "team_2": {
                "sets": state.get_sets(2),
                "score": t2_score,
                "timeouts": state.get_timeout(2),
            },
            "serve": serve.value if hasattr(serve, "value") else str(serve),
        }
        written = action_log.append(session.oid, action, params, result)
    except Exception as exc:
        logger.warning("Audit append failed: %s", exc)
        return None

    if written is None:
        return None

    if action in action_log.UNDOABLE_ACTIONS:
        if params.get("undo"):
            if popped_forward is not None:
                session.undoable_forward_count = max(
                    0, session.undoable_forward_count - 1,
                )
        else:
            session.undoable_forward_count += 1
    return written


def fire_webhook(
    session: GameSession,
    event: str,
    state_response: GameStateResponse,
    details: dict,
) -> None:
    """Fire a webhook event for the current session."""
    try:
        payload = {
            "state": state_response.model_dump(),
            "details": details,
        }
        webhook_dispatcher.dispatch(event, session.oid, payload)
    except Exception as exc:
        logger.warning("Webhook dispatch for %s failed: %s", event, exc)
