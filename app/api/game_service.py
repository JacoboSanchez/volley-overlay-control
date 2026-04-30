import logging
import time
from typing import Optional

from app.api import action_log, match_archive
from app.api.match_rules import compute_side_switch, defaults_for, is_valid_mode
from app.api.schemas import (
    ALLOWED_CUSTOMIZATION_KEYS,
    ActionResponse,
    BeachSideSwitch,
    GameStateResponse,
    TeamState,
)
from app.api.webhooks import webhook_dispatcher
from app.api.ws_hub import WSHub
from app.state import State

logger = logging.getLogger(__name__)

# Short TTL for the customization read-through cache. The overlay server is
# authoritative, but the React UI polls this endpoint on every config panel
# open; coalescing into a 5 s window avoids a burst of redundant round-trips
# without letting the UI show truly stale data.
CUSTOMIZATION_CACHE_TTL_SECONDS = 5.0


class MatchFinishedError(Exception):
    """Raised when an action is blocked because the match is already over."""
    pass


class GameService:
    """Stateless service that operates on GameSession instances."""

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    @staticmethod
    def get_state(session) -> GameStateResponse:
        """Build a ``GameStateResponse`` from the current session state."""
        t0 = time.perf_counter()
        state = session.game_manager.get_current_state()
        serve = state.get_current_serve()

        def team_state(team):
            scores = {}
            for i in range(1, session.sets_limit + 1):
                scores[f"set_{i}"] = state.get_game(team, i)
            return TeamState(
                sets=state.get_sets(team),
                timeouts=state.get_timeout(team),
                scores=scores,
                serving=(serve == State.SERVE_1 if team == 1 else serve == State.SERVE_2),
            )

        side_switch_data = compute_side_switch(
            mode=session.mode,
            current_set=session.current_set,
            sets_limit=session.sets_limit,
            team1_score=state.get_game(1, session.current_set),
            team2_score=state.get_game(2, session.current_set),
        )
        side_switch = (
            BeachSideSwitch(**side_switch_data) if side_switch_data is not None
            else None
        )
        response = GameStateResponse(
            current_set=session.current_set,
            visible=session.visible,
            simple_mode=session.simple,
            match_finished=session.game_manager.match_finished(),
            team_1=team_state(1),
            team_2=team_state(2),
            serve=serve,
            config={
                "mode": session.mode,
                "points_limit": session.points_limit,
                "points_limit_last_set": session.points_limit_last_set,
                "sets_limit": session.sets_limit,
            },
            beach_side_switch=side_switch,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms > 50:
            logger.warning(
                'get_state slow: %.1fms sets_limit=%s', elapsed_ms, session.sets_limit,
            )
        else:
            logger.debug(
                'get_state took %.1fms sets_limit=%s', elapsed_ms, session.sets_limit,
            )
        return response

    @staticmethod
    def get_customization(session) -> dict:
        return session.customization.get_model()

    @staticmethod
    def refresh_customization(session) -> dict:
        """Re-fetch customization from the overlay server and update the session cache.

        For custom overlays this performs an HTTP round-trip to the overlay server
        so the React UI always sees the latest team names, colors, logos, etc.
        For Uno overlays the backend fetches from the Uno API.

        A short TTL (``CUSTOMIZATION_CACHE_TTL_SECONDS``) short-circuits the
        network call when the last successful refresh happened recently —
        callers still receive the current session model, just without a
        redundant HTTP round-trip. ``update_customization`` primes the
        timestamp, so a write is immediately visible on the next read.
        """
        now = time.monotonic()
        last = getattr(session, "_last_customization_fetch", None)
        if last is not None and now - last < CUSTOMIZATION_CACHE_TTL_SECONDS:
            return session.customization.get_model()

        fresh = session.backend.get_current_customization()
        if fresh is not None:
            session.customization.set_model(fresh)
        session._last_customization_fetch = now
        return session.customization.get_model()

    # ------------------------------------------------------------------
    # State mutations
    # ------------------------------------------------------------------

    @staticmethod
    def add_point(session, team: int, undo: bool = False) -> ActionResponse:
        if not undo and session.game_manager.match_finished():
            return ActionResponse(
                success=False,
                state=GameService.get_state(session),
                message="Match is already finished.",
            )

        was_finished_before = session.game_manager.match_finished()
        serve_before = session.game_manager.get_current_state().get_current_serve()

        set_won = session.game_manager.add_game(
            team, session.current_set,
            session.points_limit, session.points_limit_last_set,
            session.sets_limit, undo,
        )

        if undo and session.undo:
            session.undo = False

        if set_won and not session.game_manager.match_finished():
            session.current_set = session._compute_current_set()

        GameService._save_and_broadcast(session)
        GameService._audit(session, "add_point", {"team": team, "undo": undo})

        # Fire after persistence so consumers always see the post-state.
        if not undo:
            state_response = GameService.get_state(session)
            if set_won:
                GameService._fire(session, "set_end", state_response, {
                    "team": team,
                    "set_number": session.current_set if not session.game_manager.match_finished() else session.current_set,
                })
            if session.game_manager.match_finished() and not was_finished_before:
                GameService._archive_if_finished(session, was_finished_before, team)
                GameService._fire(session, "match_end", state_response, {
                    "winning_team": team,
                })
            serve_after = session.game_manager.get_current_state().get_current_serve()
            if serve_before != serve_after:
                GameService._fire(session, "serve_change", state_response, {
                    "serve": str(serve_after.value if hasattr(serve_after, "value") else serve_after),
                })

        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def add_set(session, team: int, undo: bool = False) -> ActionResponse:
        if not undo and session.game_manager.match_finished():
            return ActionResponse(
                success=False,
                state=GameService.get_state(session),
                message="Match is already finished.",
            )

        was_finished_before = session.game_manager.match_finished()

        session.game_manager.add_set(team, undo)

        if undo and session.undo:
            session.undo = False

        session.current_set = session._compute_current_set()
        GameService._save_and_broadcast(session)
        GameService._audit(session, "add_set", {"team": team, "undo": undo})

        if not undo:
            state_response = GameService.get_state(session)
            GameService._fire(session, "set_end", state_response, {
                "team": team,
                "set_number": session.current_set,
            })
            if session.game_manager.match_finished() and not was_finished_before:
                GameService._archive_if_finished(session, was_finished_before, team)
                GameService._fire(session, "match_end", state_response, {
                    "winning_team": team,
                })
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def add_timeout(session, team: int, undo: bool = False) -> ActionResponse:
        if not undo and session.game_manager.match_finished():
            return ActionResponse(
                success=False,
                state=GameService.get_state(session),
                message="Match is already finished.",
            )

        session.game_manager.add_timeout(team, undo)

        if undo and session.undo:
            session.undo = False

        GameService._save_and_broadcast(session)
        GameService._audit(session, "add_timeout", {"team": team, "undo": undo})
        if not undo:
            GameService._fire(
                session, "timeout", GameService.get_state(session),
                {"team": team},
            )
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def change_serve(session, team: int) -> ActionResponse:
        serve_before = session.game_manager.get_current_state().get_current_serve()
        session.game_manager.change_serve(team)
        GameService._save_and_broadcast(session)
        GameService._audit(session, "change_serve", {"team": team})
        serve_after = session.game_manager.get_current_state().get_current_serve()
        if serve_before != serve_after:
            GameService._fire(
                session, "serve_change", GameService.get_state(session),
                {"serve": str(serve_after.value if hasattr(serve_after, "value") else serve_after)},
            )
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def set_score(session, team: int, set_number: int, value: int) -> ActionResponse:
        if not (1 <= set_number <= session.sets_limit):
            return ActionResponse(
                success=False,
                state=GameService.get_state(session),
                message=(
                    f"set_number {set_number} is out of range "
                    f"(1-{session.sets_limit})."
                ),
            )
        session.game_manager.set_game_value(team, value, set_number)
        set_won = session.game_manager.check_set_won(
            team, set_number,
            session.points_limit, session.points_limit_last_set,
            session.sets_limit,
        )
        if set_won and not session.game_manager.match_finished():
            session.current_set = session._compute_current_set()
        GameService._save_and_broadcast(session)
        GameService._audit(session, "set_score", {
            "team": team, "set_number": set_number, "value": value,
        })
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def set_sets_value(session, team: int, value: int) -> ActionResponse:
        session.game_manager.set_sets_value(team, value)
        session.current_set = session._compute_current_set()
        GameService._save_and_broadcast(session)
        GameService._audit(session, "set_sets_value", {"team": team, "value": value})
        return ActionResponse(success=True, state=GameService.get_state(session))

    # Actions that the server-side undo stack will reverse. Other
    # entries (set_score, set_sets_value, change_serve, reset, …) are
    # left in the log untouched and skipped over by undo_last.
    _UNDOABLE_ACTIONS = {"add_point", "add_set", "add_timeout"}

    @staticmethod
    def undo_last(session) -> ActionResponse:
        """Pop the most-recent undoable forward action and reverse it.

        The audit log is the source of truth: the most recent record
        whose ``action`` is in ``_UNDOABLE_ACTIONS`` and whose
        ``params.undo`` is falsy is removed from the log, then the
        corresponding inverse mutation is applied via the existing
        per-type ``add_*(undo=True)`` flag.

        Non-undoable forward actions stay in the log so the timeline
        is preserved. The reverse mutation itself writes a fresh
        ``undo=True`` audit entry, so re-running undo_last walks
        further back rather than oscillating.
        """
        record = action_log.pop_last_forward(
            session.oid, allowed_actions=GameService._UNDOABLE_ACTIONS,
        )
        if record is None:
            return ActionResponse(
                success=False,
                state=GameService.get_state(session),
                message="Nothing to undo.",
            )
        action = record.get("action")
        params = record.get("params") or {}
        team = params.get("team")
        if not isinstance(team, int) or team not in (1, 2):
            return ActionResponse(
                success=False,
                state=GameService.get_state(session),
                message=f"Refusing to undo malformed audit record: {record!r}",
            )
        if action == "add_point":
            return GameService.add_point(session, team=team, undo=True)
        if action == "add_set":
            return GameService.add_set(session, team=team, undo=True)
        if action == "add_timeout":
            return GameService.add_timeout(session, team=team, undo=True)
        # Should be unreachable given the allow-list filter above.
        return ActionResponse(
            success=False,
            state=GameService.get_state(session),
            message=f"Unsupported undo action: {action!r}",
        )

    @staticmethod
    def set_rules(
        session,
        mode: Optional[str] = None,
        points_limit: Optional[int] = None,
        points_limit_last_set: Optional[int] = None,
        sets_limit: Optional[int] = None,
        reset_to_defaults: bool = False,
    ) -> ActionResponse:
        """Update the match-rule preset for *session*.

        Behaviour:

        * When *mode* is provided, it is stored on the session.
        * When *reset_to_defaults* is true, every limit is replaced
          with the canonical preset for the resulting mode (the
          new *mode* if provided, else the existing one). Any
          per-field overrides in the same call still win — so the
          UI can ask "switch to beach but keep my custom 25 pts/set"
          by passing ``mode='beach', points_limit=25,
          reset_to_defaults=True``.
        * Otherwise only the fields the caller passed are updated;
          the rest stay as they are.

        After the update, ``current_set`` is recomputed because a
        smaller ``sets_limit`` may need to clamp it. Audit log gets
        a ``set_rules`` entry, and the meta file is re-persisted so
        the change survives restart.
        """
        if mode is not None:
            if not is_valid_mode(mode):
                return ActionResponse(
                    success=False,
                    state=GameService.get_state(session),
                    message=f"Unknown mode: {mode!r}",
                )
            session.mode = mode

        if reset_to_defaults:
            preset = defaults_for(session.mode)
            session.points_limit = preset.points_limit
            session.points_limit_last_set = preset.points_limit_last_set
            session.sets_limit = preset.sets_limit

        # Per-field overrides win over the reset block above.
        if points_limit is not None:
            session.points_limit = max(1, int(points_limit))
        if points_limit_last_set is not None:
            session.points_limit_last_set = max(1, int(points_limit_last_set))
        if sets_limit is not None:
            cleaned = max(1, int(sets_limit))
            # Whilst the rules allow odd numbers in general, the rest of
            # the codebase (State, get_game) hard-codes 1..5. Clamp.
            session.sets_limit = min(cleaned, 5)

        # A smaller sets_limit may invalidate the current set.
        session.current_set = session._compute_current_set()
        session.persist_meta()
        GameService._broadcast(session)
        GameService._audit(session, "set_rules", {
            "mode": session.mode,
            "points_limit": session.points_limit,
            "points_limit_last_set": session.points_limit_last_set,
            "sets_limit": session.sets_limit,
            "reset_to_defaults": reset_to_defaults,
        })
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def reset(session) -> ActionResponse:
        session.game_manager.reset()
        session.current_set = session._compute_current_set()
        # Reset starts a new match — bump the start clock so duration_s
        # in the next archived snapshot is correct.
        session.match_started_at = time.time()
        GameService._save_and_broadcast(session)
        # Reset wipes the match — start the audit log fresh too so the
        # archive boundaries align with operator intent.
        action_log.clear(session.oid)
        GameService._audit(session, "reset", {})
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def set_visibility(session, visible: bool) -> ActionResponse:
        session.visible = visible
        session.backend.change_overlay_visibility(visible)
        GameService._broadcast(session)
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def set_simple_mode(session, enabled: bool) -> ActionResponse:
        session.simple = enabled
        if enabled:
            session.backend.reduce_games_to_one()
        GameService._save_and_broadcast(session)
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def update_customization(session, data: dict) -> ActionResponse:
        # Filter to allowed keys only
        filtered = {k: v for k, v in data.items() if k in ALLOWED_CUSTOMIZATION_KEYS}
        if not filtered:
            return ActionResponse(
                success=False,
                state=GameService.get_state(session),
                message="No valid customization keys provided.",
            )
        # Merge into existing model to preserve keys not in the allowed set
        # (e.g. Team 1 Logo Fit, Color 3, Text Color 3)
        current = session.customization.get_model()
        merged = {**current, **filtered}
        session.customization.set_model(merged)
        session.backend.save_json_customization(merged)
        # A write just made the session's view authoritative — prime the
        # cache so the next refresh short-circuits instead of fetching
        # the same data we just pushed.
        session._last_customization_fetch = time.monotonic()
        GameService._broadcast(session)
        return ActionResponse(success=True, state=GameService.get_state(session))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _save_and_broadcast(session):
        """Persist state to the overlay backend and notify WS clients."""
        session.game_manager.save(session.simple, session.current_set)
        session.persist_meta()
        GameService._broadcast(session)

    @staticmethod
    def _broadcast(session):
        """Notify all WebSocket frontend clients about the new state."""
        state_data = GameService.get_state(session).model_dump()
        WSHub.broadcast_sync(session.oid, state_data)

    @staticmethod
    def _archive_if_finished(session, was_finished_before: bool,
                             winning_team: int) -> Optional[str]:
        """Archive the match when it transitions to finished.

        Called from add_point and add_set after the mutation completes.
        Returns the new ``match_id`` (or ``None`` if no archive happened).
        After a successful archive the session's ``match_started_at`` is
        bumped to ``now`` so a follow-up ``reset`` does not retroactively
        backdate the next match.
        """
        if was_finished_before or not session.game_manager.match_finished():
            return None
        try:
            final_state = GameService.get_state(session).model_dump()
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
            session.match_started_at = time.time()
            session.persist_meta()
            return match_id
        except Exception as exc:
            logger.warning("Match archive failed: %s", exc)
            return None

    @staticmethod
    def _audit(session, action: str, params: dict) -> None:
        """Append an audit-log record for the action just performed.

        Captures a compact post-state snapshot (the same shape used by
        the match-history archive) so the log alone is enough to render
        a recent-actions feed and to drive the server-side undo stack.
        Best-effort: failures are swallowed.
        """
        try:
            state = session.game_manager.get_current_state()
            t1_score = state.get_game(1, session.current_set)
            t2_score = state.get_game(2, session.current_set)
            serve = state.get_current_serve()
            result = {
                "current_set": session.current_set,
                "match_finished": session.game_manager.match_finished(),
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
            action_log.append(session.oid, action, params, result)
        except Exception as exc:
            logger.warning("Audit append failed: %s", exc)

    @staticmethod
    def _fire(session, event: str, state_response, details: dict) -> None:
        """Fire a webhook event for the current session.

        Caller is responsible for choosing when to fire (e.g. only on
        non-undo mutations). The dispatcher handles env-var
        configuration, target filtering, and async delivery.
        """
        try:
            payload = {
                "state": state_response.model_dump(),
                "details": details,
            }
            webhook_dispatcher.dispatch(event, session.oid, payload)
        except Exception as exc:
            logger.warning("Webhook dispatch for %s failed: %s", event, exc)
