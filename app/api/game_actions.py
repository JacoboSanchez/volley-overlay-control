"""Score, rules, lifecycle, audit, and webhook game actions."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, cast

from app.api import action_log
from app.api import game_audit_hooks as _audit_hooks
from app.api import game_broadcast as _broadcast
from app.api import game_rapid_pair as _rapid_pair
from app.api.match_rules import (
    defaults_for,
    is_valid_mode,
    table_tennis_first_server_for,
)
from app.api.schemas import (
    ActionResponse,
    GameStateResponse,
)
from app.customization_cache_ttl import customization_cache_ttl_seconds

if TYPE_CHECKING:
    from app.api.game_service import GameService
    from app.api.session_manager import GameSession

logger = logging.getLogger(__name__)

# Window for the rapid-pair "undo correction" flow. Two opposite
# ``add_point`` actions on the same team that land within this many
# seconds of each other collapse into a no-op:
#
#   * tap → double-tap-undo within 5 s ⇒ neither lands in the audit
#     log (the just-added forward is tombstoned, no undo is appended).
#   * double-tap-undo → tap within 5 s ⇒ the original forward (which
#     the undo had hidden) is restored and the undo is tombstoned.
#
# Outside the window the actions stay separate. Tuned to match the
# operator's "wait, that wasn't right" reflex without being so wide
# that a deliberate next-rally tap could be mistaken for a recovery.
RAPID_PAIR_WINDOW_S = _rapid_pair.RAPID_PAIR_WINDOW_S

# Short TTL for the customization read-through cache. The overlay server is
# authoritative, but the React UI polls this endpoint on every config panel
# open; coalescing into a 5 s window avoids a burst of redundant round-trips
# without letting the UI show truly stale data.
CUSTOMIZATION_CACHE_TTL_SECONDS = customization_cache_ttl_seconds()


def _service(cls: type) -> type[GameService]:
    """Return the composed facade class for cross-mixin calls."""
    return cast("type[GameService]", cls)


class GameActions:
    """Mutate match state through GameManager and fan out side effects."""

    @classmethod
    def _match_finished_response(cls, session: GameSession) -> ActionResponse | None:
        """Return the early-exit ``ActionResponse`` when the match is already over.

        ``add_point`` / ``add_set`` / ``add_timeout`` all share the same
        guard for non-undo actions — keep its message and shape in one
        place so changes to the wording stay aligned.
        """
        if session.game_manager.match_finished(session.sets_limit):
            return ActionResponse(
                success=False,
                state=_service(cls).get_state(session),
                message="Match is already finished.",
            )
        return None

    @classmethod
    def _ended_set_index(cls, session: GameSession) -> int:
        """Set number that just ended (1-indexed).

        ``current_set`` is advanced on a set win unless the match
        finishes, so the just-ended set is ``current_set`` when the
        match is over and ``current_set - 1`` otherwise. Shared by
        ``add_point`` and ``add_set`` to keep the two ``set_end``
        webhook payloads aligned.
        """
        if session.game_manager.match_finished(session.sets_limit):
            return session.current_set
        return session.current_set - 1

    @classmethod
    def _fire_serve_change_if_changed(
        cls,
        session: GameSession,
        serve_before: object,
        state_response: GameStateResponse,
    ) -> None:
        """Fire a ``serve_change`` webhook when the current serve flipped."""
        serve_after = session.game_manager.get_current_state().get_current_serve()
        if serve_before != serve_after:
            _service(cls)._fire(
                session,
                "serve_change",
                state_response,
                {"serve": str(getattr(serve_after, "value", serve_after))},
            )

    @classmethod
    def _sync_match_finished_at(cls, session: GameSession, was_finished_before: bool) -> None:
        """Stamp / clear ``session.match_finished_at`` to match the
        current match-finished state.

        Called before every broadcast that follows a mutation that
        could transition the match-finished flag (``add_point``,
        ``add_set``, ``set_score``, ``set_sets_value``). Both
        directions matter:

        * forward transition into finished ⇒ stamp the wall clock so
          consumers freeze their elapsed counters at the actual end-
          of-match value.
        * reverse transition out of finished (undo of a match-winning
          action, or a manual ``set_score`` / ``set_sets_value`` edit
          that re-opens the match) ⇒ clear the stamp so the React
          ``MatchTimer`` (which freezes purely on ``finishedAt !=
          null``) resumes ticking.

        No-op when the finished state didn't change.
        """
        is_finished_now = session.game_manager.match_finished(
            session.sets_limit,
        )
        if not was_finished_before and is_finished_now:
            if session.match_finished_at is None:
                session.match_finished_at = time.time()
        elif was_finished_before and not is_finished_now:
            session.match_finished_at = None

    @classmethod
    def _consume_rapid_pair(
        cls,
        session: GameSession,
        team: int,
        undo: bool,
        point_type: str | None = None,
        error_type: str | None = None,
    ) -> bool:
        return _rapid_pair.consume_rapid_pair(
            session,
            team,
            undo,
            point_type,
            error_type,
        )

    @classmethod
    def _record_rapid_pair_seed(
        cls,
        session: GameSession,
        team: int,
        undo: bool,
        audit_record: dict[str, Any] | None,
        popped: dict[str, Any] | None,
    ) -> None:
        _rapid_pair.record_rapid_pair_seed(session, team, undo, audit_record, popped)

    @classmethod
    def _invalidate_rapid_pair_cache(cls, session: GameSession) -> None:
        _rapid_pair.invalidate_rapid_pair_cache(session)

    @classmethod
    def add_point(
        cls,
        session: GameSession,
        team: int,
        undo: bool = False,
        point_type: str | None = None,
        error_type: str | None = None,
    ) -> ActionResponse:
        if not undo:
            blocked = _service(cls)._match_finished_response(session)
            if blocked is not None:
                return blocked

        # Implicit match-start: scoring before the operator hit
        # ``Start match`` arms the timer here so the HUD timer and the
        # match-report duration agree on when the match really began.
        # Undo paths skip this — undoing the very first point shouldn't
        # ghost-arm a match that never explicitly started.
        if not undo and session.match_started_at is None:
            session.match_started_at = time.time()

        was_finished_before = session.game_manager.match_finished(session.sets_limit)
        serve_before = session.game_manager.get_current_state().get_current_serve()
        # Capture the set the action operates on *before* a potential
        # set-win advances ``current_set`` — needed so the audit log
        # records the final score (e.g. 25-23) of the set that just
        # ended rather than the next set's empty 0-0.
        target_set_before_advance = session.current_set

        # Rapid-pair recovery: if the operator just performed the
        # opposite action on the same team within
        # ``RAPID_PAIR_WINDOW_S``, fold the pair into a no-op at the
        # audit-log level. The state still mutates normally (set-end
        # / match-end / serve-change side effects re-fire) so a
        # set-winning recovery is honoured the same as any forward.
        rapid_pair = _service(cls)._consume_rapid_pair(
            session,
            team,
            undo,
            point_type,
            error_type,
        )

        # When the audit-log half is handled by the rapid-pair path
        # we skip the normal ``pop_last_forward`` (the forward was
        # already tombstoned via the cache). Otherwise — for fresh
        # undos — the pop tombstones the matching forward so a
        # follow-up generic undo cannot double-revert the same
        # action. State-undo runs regardless of pop result so
        # callers manipulating state without a corresponding audit
        # record (e.g. via ``set_score``) keep their backward-
        # compatible no-op-on-zero semantics.
        popped = (
            action_log.pop_last_forward(
                session.oid,
                allowed_actions={"add_point"},
                team=team,
            )
            if undo and not rapid_pair
            else None
        )

        set_won = session.game_manager.add_game(
            team,
            session.current_set,
            session.points_limit,
            session.points_limit_last_set,
            session.sets_limit,
            undo,
        )

        if undo and session.undo:
            session.undo = False

        # ``_compute_current_set`` already handles the match-finished
        # case (returns t1+t2 without a +1 advance), so an extra
        # match_finished guard here is redundant.
        if set_won:
            session.current_set = session._compute_current_set()

        _service(cls)._sync_match_finished_at(session, was_finished_before)

        # Audit before computing ``state_response`` so the cached
        # ``undoable_forward_count`` (and therefore ``can_undo``) the
        # state response carries is up to date for *this* action.
        # Otherwise the very first forward / last undo would broadcast
        # the pre-increment counter and the UI's undo button would lag
        # one action behind.
        if not rapid_pair:
            params: dict[str, object] = {"team": team, "undo": undo}
            # Scouting tags only attach to forward points; an undo
            # reverses a point and carries no classification of its own.
            if not undo:
                if point_type:
                    params["point_type"] = point_type
                if error_type:
                    params["error_type"] = error_type
            audit_record = _service(cls)._audit(
                session,
                "add_point",
                params,
                popped_forward=popped,
                target_set=target_set_before_advance,
            )
            _service(cls)._record_rapid_pair_seed(
                session,
                team,
                undo,
                audit_record,
                popped,
            )

        # Compute the post-mutation state once and reuse it for the
        # broadcast, webhook fan-out, archive, and HTTP response.
        # ``get_state`` does non-trivial work (set-range iteration plus
        # side-switch / match-point computation), so collapsing four
        # call sites into one is a measurable per-action win.
        state_response = _service(cls).get_state(session)
        _service(cls)._save_and_broadcast(session, state_response)

        # Fire after persistence so consumers always see the post-state.
        # Set-end / match-end webhooks fire whether or not a rapid pair
        # absorbed the audit half — the underlying state transition
        # really happened (operator saw the set close + reopen) and
        # downstream consumers should see the same effective edge.
        if not undo:
            if set_won:
                _service(cls)._fire(
                    session,
                    "set_end",
                    state_response,
                    {
                        "team": team,
                        "set_number": _service(cls)._ended_set_index(session),
                    },
                )
            if session.game_manager.match_finished(session.sets_limit) and not was_finished_before:
                _service(cls)._archive_if_finished(
                    session,
                    was_finished_before,
                    team,
                    state_response,
                )
                _service(cls)._fire(
                    session,
                    "match_end",
                    state_response,
                    {
                        "winning_team": team,
                    },
                )
            _service(cls)._fire_serve_change_if_changed(session, serve_before, state_response)

        return ActionResponse(success=True, state=state_response)

    @classmethod
    def add_set(cls, session: GameSession, team: int, undo: bool = False) -> ActionResponse:
        if not undo:
            blocked = _service(cls)._match_finished_response(session)
            if blocked is not None:
                return blocked

        # Any action other than ``add_point`` invalidates the rapid-
        # pair cache so a tap that follows can never trigger a false-
        # positive recovery against an unrelated prior action.
        _service(cls)._invalidate_rapid_pair_cache(session)
        was_finished_before = session.game_manager.match_finished(session.sets_limit)
        # Same reasoning as add_point: capture before advance so the
        # audit log records the final score of the set that ended.
        target_set_before_advance = session.current_set

        popped = (
            action_log.pop_last_forward(
                session.oid,
                allowed_actions={"add_set"},
                team=team,
            )
            if undo
            else None
        )

        session.game_manager.add_set(team, undo, session.sets_limit)

        if undo and session.undo:
            session.undo = False

        session.current_set = session._compute_current_set()
        _service(cls)._sync_match_finished_at(session, was_finished_before)
        # Audit before ``get_state`` so the ``can_undo`` flag the
        # broadcast carries reflects the just-bumped counter.
        _service(cls)._audit(
            session,
            "add_set",
            {"team": team, "undo": undo},
            popped_forward=popped,
            target_set=target_set_before_advance,
        )
        state_response = _service(cls).get_state(session)
        _service(cls)._save_and_broadcast(session, state_response)

        if not undo:
            _service(cls)._fire(
                session,
                "set_end",
                state_response,
                {
                    "team": team,
                    "set_number": _service(cls)._ended_set_index(session),
                },
            )
            if session.game_manager.match_finished(session.sets_limit) and not was_finished_before:
                _service(cls)._archive_if_finished(
                    session,
                    was_finished_before,
                    team,
                    state_response,
                )
                _service(cls)._fire(
                    session,
                    "match_end",
                    state_response,
                    {
                        "winning_team": team,
                    },
                )
        return ActionResponse(success=True, state=state_response)

    @classmethod
    def add_timeout(cls, session: GameSession, team: int, undo: bool = False) -> ActionResponse:
        if not undo:
            blocked = _service(cls)._match_finished_response(session)
            if blocked is not None:
                return blocked

        # Table tennis allows a single timeout per team for the *whole*
        # match (volleyball is 2 per set, enforced in GameManager). Since
        # timeouts are stored per-set, sum across sets to enforce the
        # per-match cap before the forward add lands.
        if not undo and session.mode == "table_tennis":
            state = session.game_manager.get_current_state()
            taken = sum(state.get_timeouts_by_set(team).values())
            if taken >= 1:
                return ActionResponse(
                    success=False,
                    state=_service(cls).get_state(session),
                    message="Timeout limit reached for this match.",
                )

        _service(cls)._invalidate_rapid_pair_cache(session)
        popped = (
            action_log.pop_last_forward(
                session.oid,
                allowed_actions={"add_timeout"},
                team=team,
            )
            if undo
            else None
        )

        session.game_manager.add_timeout(team, undo)

        if undo and session.undo:
            session.undo = False

        # Audit before ``get_state`` so ``can_undo`` reflects the
        # post-action counter on the very first / last timeout.
        _service(cls)._audit(
            session,
            "add_timeout",
            {"team": team, "undo": undo},
            popped_forward=popped,
        )
        state_response = _service(cls).get_state(session)
        _service(cls)._save_and_broadcast(session, state_response)
        if not undo:
            _service(cls)._fire(
                session,
                "timeout",
                state_response,
                {"team": team},
            )
        return ActionResponse(success=True, state=state_response)

    @classmethod
    def change_serve(cls, session: GameSession, team: int) -> ActionResponse:
        _service(cls)._invalidate_rapid_pair_cache(session)
        serve_before = session.game_manager.get_current_state().get_current_serve()
        if session.mode == "table_tennis":
            # Serve is automatic in table tennis — the toggle instead
            # re-bases who serves first so the clicked team is on serve
            # *now* and the rotation stays consistent from here. ``get_state``
            # then derives and writes the live serve via _sync.
            state = session.game_manager.get_current_state()
            session.first_server = table_tennis_first_server_for(
                desired_server=team,
                current_set=session.current_set,
                sets_limit=session.sets_limit,
                team1_score=state.get_game(1, session.current_set),
                team2_score=state.get_game(2, session.current_set),
                points_limit=session.points_limit,
                points_limit_last_set=session.points_limit_last_set,
            )
            session.persist_meta()
        else:
            session.game_manager.change_serve(team)
        state_response = _service(cls).get_state(session)
        _service(cls)._save_and_broadcast(session, state_response)
        _service(cls)._audit(session, "change_serve", {"team": team})
        _service(cls)._fire_serve_change_if_changed(
            session,
            serve_before,
            state_response,
        )
        return ActionResponse(success=True, state=state_response)

    @classmethod
    def set_score(cls, session: GameSession, team: int, set_number: int, value: int) -> ActionResponse:
        if not (1 <= set_number <= session.sets_limit):
            return ActionResponse(
                success=False,
                state=_service(cls).get_state(session),
                message=(f"set_number {set_number} is out of range (1-{session.sets_limit})."),
            )
        _service(cls)._invalidate_rapid_pair_cache(session)
        was_finished_before = session.game_manager.match_finished(session.sets_limit)
        session.game_manager.set_game_value(team, value, set_number)
        set_won = session.game_manager.check_set_won(
            team,
            set_number,
            session.points_limit,
            session.points_limit_last_set,
            session.sets_limit,
        )
        # ``_compute_current_set`` already handles the match-finished
        # case (returns t1+t2 without a +1 advance), so an extra
        # match_finished guard here is redundant.
        if set_won:
            session.current_set = session._compute_current_set()
        # A manual ``set_score`` edit can push the match in either
        # direction (e.g. setting the winning team's score to 25 in
        # the deciding set finishes the match; setting it back to 23
        # re-opens it), so keep ``match_finished_at`` in sync with
        # the current finished state before the broadcast.
        _service(cls)._sync_match_finished_at(session, was_finished_before)
        state_response = _service(cls).get_state(session)
        _service(cls)._save_and_broadcast(session, state_response)
        _service(cls)._audit(
            session,
            "set_score",
            {
                "team": team,
                "set_number": set_number,
                "value": value,
            },
        )
        return ActionResponse(success=True, state=state_response)

    @classmethod
    def set_sets_value(cls, session: GameSession, team: int, value: int) -> ActionResponse:
        _service(cls)._invalidate_rapid_pair_cache(session)
        was_finished_before = session.game_manager.match_finished(session.sets_limit)
        session.game_manager.set_sets_value(team, value)
        session.current_set = session._compute_current_set()
        # Same as ``set_score``: a direct sets-won edit can transition
        # the match in either direction; keep ``match_finished_at`` in
        # sync before the broadcast.
        _service(cls)._sync_match_finished_at(session, was_finished_before)
        state_response = _service(cls).get_state(session)
        _service(cls)._save_and_broadcast(session, state_response)
        _service(cls)._audit(session, "set_sets_value", {"team": team, "value": value})
        return ActionResponse(success=True, state=state_response)

    @classmethod
    def undo_last(cls, session: GameSession) -> ActionResponse:
        """Reverse the most-recent undoable forward action.

        The audit log is the single source of truth for the undo
        stack. ``undo_last`` peeks the most recent record whose
        ``action`` is in ``_UNDOABLE_ACTIONS`` and dispatches to the
        matching per-type API with ``undo=True`` — that path then
        pops the same forward, applies the state-level inverse, and
        appends an undo audit entry. The two undo entry points (this
        one and ``add_*(undo=True)``) therefore share one stack and
        cannot drift out of sync.

        Non-undoable forward actions (``change_serve``, ``set_score``,
        ``reset``, …) stay in the log; ``peek_last_forward`` skips
        them so undo walks past them rather than touching them.
        """
        record = action_log.peek_last_forward(
            session.oid,
            allowed_actions=action_log.UNDOABLE_ACTIONS,
        )
        if record is None:
            return ActionResponse(
                success=False,
                state=_service(cls).get_state(session),
                message="Nothing to undo.",
            )
        action = record.get("action")
        params = record.get("params") or {}
        team = params.get("team")
        if not isinstance(team, int) or team not in (1, 2):
            return ActionResponse(
                success=False,
                state=_service(cls).get_state(session),
                message=f"Refusing to undo malformed audit record: {record!r}",
            )
        if action == "add_point":
            return _service(cls).add_point(session, team=team, undo=True)
        if action == "add_set":
            return _service(cls).add_set(session, team=team, undo=True)
        if action == "add_timeout":
            return _service(cls).add_timeout(session, team=team, undo=True)
        # Should be unreachable given the allow-list filter above.
        return ActionResponse(
            success=False,
            state=_service(cls).get_state(session),
            message=f"Unsupported undo action: {action!r}",
        )

    @classmethod
    def set_rules(
        cls,
        session: GameSession,
        mode: str | None = None,
        points_limit: int | None = None,
        points_limit_last_set: int | None = None,
        sets_limit: int | None = None,
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
                    state=_service(cls).get_state(session),
                    message=f"Unknown mode: {mode!r}",
                )
            session.mode = mode

        _service(cls)._invalidate_rapid_pair_cache(session)

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
            # The per-set arrays in State are 1-indexed up to MAX_SETS (7),
            # so a best-of-7 table-tennis match is the upper bound. Clamp.
            session.sets_limit = min(cleaned, 7)

        # A smaller sets_limit may invalidate the current set.
        session.current_set = session._compute_current_set()
        session.persist_meta()
        # ``get_state`` re-derives the table-tennis server into the match state;
        # persist (not just WS-broadcast) so the OBS overlay's stored state
        # reflects the new server immediately instead of only after the next
        # scoring action.
        state_response = _service(cls).get_state(session)
        _service(cls)._save_and_broadcast(session, state_response)
        _service(cls)._audit(
            session,
            "set_rules",
            {
                "mode": session.mode,
                "points_limit": session.points_limit,
                "points_limit_last_set": session.points_limit_last_set,
                "sets_limit": session.sets_limit,
                "reset_to_defaults": reset_to_defaults,
            },
        )
        return ActionResponse(success=True, state=state_response)

    @classmethod
    def start_match(cls, session: GameSession) -> ActionResponse:
        """Arm the match-start clock without scoring a point.

        Idempotent: a second call after the match has already started
        is a no-op (the clock keeps the original anchor). The first
        ``add_point`` arms the clock implicitly, so this endpoint
        exists for the case where the operator wants the timer to
        reflect the actual whistle rather than the first rally.
        """
        if session.match_started_at is None:
            _service(cls)._invalidate_rapid_pair_cache(session)
            session.match_started_at = time.time()
            # Belt-and-braces: a fresh arm should never carry a stale
            # finished-at from a prior match still hanging around in
            # the persisted meta.
            session.match_finished_at = None
            session.persist_meta()
            _service(cls)._audit(session, "start_match", {})
            _service(cls)._broadcast(session)
        return ActionResponse(success=True, state=_service(cls).get_state(session))

    @classmethod
    def reset(cls, session: GameSession) -> ActionResponse:
        # Reset wipes the audit log; the rapid-pair cache that
        # references audit timestamps must vanish with it.
        _service(cls)._invalidate_rapid_pair_cache(session)
        session.game_manager.reset()
        session.current_set = session._compute_current_set()
        # Reset wipes the match — clear the start clock so the next
        # match begins unarmed (operator hits ``Start match`` or scores
        # the first point to arm it again). Also clear the end-of-match
        # timestamp so the HUD timer / spectator page exit the frozen
        # post-match display and return to the pre-match idle state.
        session.match_started_at = None
        session.match_finished_at = None
        # Reset wipes the match — start the audit log fresh too so the
        # archive boundaries align with operator intent. Counter goes
        # to zero alongside the log so ``can_undo`` is correct. Run
        # before ``get_state`` so the broadcast that follows carries
        # ``can_undo=False`` instead of the stale pre-reset counter.
        action_log.clear(session.oid)
        session.undoable_forward_count = 0
        _service(cls)._audit(session, "reset", {})
        state_response = _service(cls).get_state(session)
        _service(cls)._save_and_broadcast(session, state_response)
        return ActionResponse(success=True, state=state_response)

    @classmethod
    def _save_and_broadcast(cls, session: GameSession, state_response: GameStateResponse | None = None) -> None:
        _broadcast.save_and_broadcast(session, state_response)

    @classmethod
    def _broadcast(cls, session: GameSession, state_response: GameStateResponse | None = None) -> None:
        _broadcast.broadcast(session, state_response)

    @classmethod
    def _archive_if_finished(
        cls,
        session: GameSession,
        was_finished_before: bool,
        winning_team: int,
        state_response: GameStateResponse | None = None,
    ) -> str | None:
        return _audit_hooks.archive_if_finished(
            session,
            was_finished_before,
            winning_team,
            state_response,
        )

    @classmethod
    def _audit(
        cls,
        session: GameSession,
        action: str,
        params: dict[str, Any],
        popped_forward: dict[str, Any] | None = None,
        target_set: int | None = None,
    ) -> dict[str, Any] | None:
        return _audit_hooks.audit(
            session,
            action,
            params,
            popped_forward,
            target_set,
        )

    @classmethod
    def _fire(
        cls,
        session: GameSession,
        event: str,
        state_response: GameStateResponse,
        details: dict[str, Any],
    ) -> None:
        _audit_hooks.fire_webhook(session, event, state_response, details)
