import logging
import time

from app.api import action_log, match_archive
from app.api.match_rules import (
    compute_match_point_info,
    compute_side_switch,
    defaults_for,
    is_valid_mode,
)
from app.api.schemas import (
    ALLOWED_CUSTOMIZATION_KEYS,
    LOGO_KEYS,
    MAX_CUSTOMIZATION_KEYS,
    MAX_STRING_VALUE_LENGTH,
    ActionResponse,
    BeachSideSwitch,
    GameStateResponse,
    MatchPointInfo,
    TeamState,
    is_safe_logo_url,
)
from app.api.webhooks import webhook_dispatcher
from app.api.ws_hub import WSHub
from app.env_vars_manager import EnvVarsManager
from app.state import State

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
RAPID_PAIR_WINDOW_S = 5.0

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

        team1_score = state.get_game(1, session.current_set)
        team2_score = state.get_game(2, session.current_set)
        side_switch_data = compute_side_switch(
            mode=session.mode,
            current_set=session.current_set,
            sets_limit=session.sets_limit,
            team1_score=team1_score,
            team2_score=team2_score,
            points_limit=session.points_limit,
            points_limit_last_set=session.points_limit_last_set,
        )
        side_switch = (
            BeachSideSwitch(**side_switch_data) if side_switch_data is not None
            else None
        )
        match_finished = session.game_manager.match_finished(session.sets_limit)
        match_point_info = MatchPointInfo(**compute_match_point_info(
            current_set=session.current_set,
            sets_limit=session.sets_limit,
            team1_sets=state.get_sets(1),
            team2_sets=state.get_sets(2),
            team1_score=team1_score,
            team2_score=team2_score,
            points_limit=session.points_limit,
            points_limit_last_set=session.points_limit_last_set,
            match_finished=match_finished,
        ))
        response = GameStateResponse(
            current_set=session.current_set,
            visible=session.visible,
            simple_mode=session.simple,
            match_finished=match_finished,
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
            match_point_info=match_point_info,
            can_undo=session.undoable_forward_count > 0,
            match_started_at=session.match_started_at,
            match_finished_at=session.match_finished_at,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        # Misconfigured env var must not turn every /state call into a 500;
        # silently fall back to the documented default.
        try:
            warn_threshold_ms = float(
                EnvVarsManager.get_env_var('PERF_GET_STATE_WARN_MS', '50')
            )
        except (TypeError, ValueError):
            warn_threshold_ms = 50.0
        if elapsed_ms > warn_threshold_ms:
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

        Concurrent callers for the same session coalesce on
        ``session.customization_fetch_lock``: only the first request hits
        the overlay server, the rest return the freshly populated cache
        as soon as the lock is released. Without this, a burst of UI
        opens (config panel, scoreboard mount, control bar refresh) can
        fire several simultaneous fetches before the first one populates
        the TTL window.
        """
        now = time.monotonic()
        last = getattr(session, "_last_customization_fetch", None)
        if last is not None and now - last < CUSTOMIZATION_CACHE_TTL_SECONDS:
            return session.customization.get_model()

        with session.customization_fetch_lock:
            # Re-check inside the lock: a sibling caller may have refreshed
            # while we were blocked, in which case the cache is now warm.
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
    def _match_finished_response(session) -> ActionResponse | None:
        """Return the early-exit ``ActionResponse`` when the match is already over.

        ``add_point`` / ``add_set`` / ``add_timeout`` all share the same
        guard for non-undo actions — keep its message and shape in one
        place so changes to the wording stay aligned.
        """
        if session.game_manager.match_finished(session.sets_limit):
            return ActionResponse(
                success=False,
                state=GameService.get_state(session),
                message="Match is already finished.",
            )
        return None

    @staticmethod
    def _ended_set_index(session) -> int:
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

    @staticmethod
    def _fire_serve_change_if_changed(
        session, serve_before, state_response: GameStateResponse
    ) -> None:
        """Fire a ``serve_change`` webhook when the current serve flipped."""
        serve_after = session.game_manager.get_current_state().get_current_serve()
        if serve_before != serve_after:
            GameService._fire(
                session, "serve_change", state_response,
                {"serve": str(getattr(serve_after, "value", serve_after))},
            )

    @staticmethod
    def _sync_match_finished_at(session, was_finished_before: bool) -> None:
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

    @staticmethod
    def _consume_rapid_pair(session, team: int, undo: bool) -> bool:
        """Return ``True`` when the incoming ``add_point`` collapses
        with the most recent opposite-kind action on the same team
        within :data:`RAPID_PAIR_WINDOW_S`.

        On a hit the cache is cleared, the audit log is rewritten so
        neither half of the pair surfaces (the original forward, if
        any, is restored from its tombstone), and the caller can
        assume the audit-log side of the action is already done — it
        only needs to apply the state-level mutation and skip the
        normal ``_audit`` append.

        On a miss returns ``False`` and leaves the cache untouched
        so the caller can update it after the normal flow completes.
        """
        cached = session.rapid_pair_cache.get(team)
        if not cached:
            return False
        if cached.get("kind") == ("undo" if undo else "forward"):
            # Same direction as the cached entry — not a pair. Treat
            # as a fresh action; the caller will overwrite the cache.
            return False
        now = time.time()
        ts = cached.get("ts")
        if not isinstance(ts, (int, float)) or now - ts > RAPID_PAIR_WINDOW_S:
            # Stale cache: drop it so the caller starts fresh.
            session.rapid_pair_cache.pop(team, None)
            return False

        audit_ts = cached.get("audit_ts")
        if undo:
            # Case A — tap, then double-tap-undo within the window.
            # The just-added forward is tombstoned and no undo is
            # appended. Net audit: nothing for the pair. The counter
            # only follows the on-disk state: a failed tombstone
            # write would leave the forward visible, so we hold off
            # decrementing until the tombstone landed.
            if audit_ts is not None and action_log.tombstone_ts(
                session.oid, audit_ts,
            ):
                session.undoable_forward_count = max(
                    0, session.undoable_forward_count - 1,
                )
        else:
            # Case B — double-tap-undo, then tap within the window.
            # Tombstone the undo we just wrote and resurrect the
            # forward the undo had originally hidden so the timeline
            # reads as if neither happened. Both writes must land or
            # neither side-effect should: if the undo tombstone fails
            # but the restore succeeds, ``_collapse_undos`` in the
            # report would pair the orphan undo with the restored
            # forward and hide both, defeating the recovery. So we
            # gate the restore (and the counter bump) on the
            # tombstone landing. Mirrors Case A: a missing
            # ``audit_ts`` means the seed never recorded a
            # writable reference, so we cannot tombstone the undo
            # — falling through to the restore in that case would
            # recreate the orphan-undo + restored-forward state
            # this fix is meant to prevent.
            tombstone_ok = audit_ts is not None and action_log.tombstone_ts(
                session.oid, audit_ts,
            )
            if tombstone_ok:
                popped_ref = cached.get("popped_ref_ts")
                if popped_ref is not None and action_log.restore_popped(
                    session.oid, popped_ref,
                ):
                    # The recovered forward is undoable again — increment
                    # the counter we decremented when the undo landed.
                    session.undoable_forward_count += 1

        session.rapid_pair_cache.pop(team, None)
        return True

    @staticmethod
    def _record_rapid_pair_seed(
        session,
        team: int,
        undo: bool,
        audit_record: dict | None,
        popped: dict | None,
    ) -> None:
        """Stash the action that just landed so a near-future
        opposite-kind action on the same team can collapse with it.

        Called after a *normal* ``add_point`` flow completes — i.e.
        when no rapid pair was consumed. The cache is per-team so a
        deliberate forward on team 1 doesn't accidentally pair with
        a stray double-tap on team 2.
        """
        if not isinstance(audit_record, dict):
            # The audit-append failed; nothing to refer back to.
            session.rapid_pair_cache.pop(team, None)
            return
        ts = audit_record.get("ts")
        if not isinstance(ts, (int, float)):
            session.rapid_pair_cache.pop(team, None)
            return
        entry: dict = {
            "kind": "undo" if undo else "forward",
            "ts": time.time(),
            "audit_ts": ts,
        }
        if undo and isinstance(popped, dict):
            popped_ts = popped.get("ts")
            if isinstance(popped_ts, (int, float)):
                entry["popped_ref_ts"] = popped_ts
        session.rapid_pair_cache[team] = entry

    @staticmethod
    def _invalidate_rapid_pair_cache(session) -> None:
        """Drop every per-team rapid-pair cache entry.

        Called from the non-``add_point`` mutation paths
        (``add_set``, ``add_timeout``, ``change_serve``,
        ``set_score``, ``set_sets_value``, ``reset``,
        ``set_rules``) so a tap that follows an unrelated action
        can never trigger a false-positive recovery.
        """
        if session.rapid_pair_cache:
            session.rapid_pair_cache.clear()

    @staticmethod
    def add_point(session, team: int, undo: bool = False) -> ActionResponse:
        if not undo:
            blocked = GameService._match_finished_response(session)
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
        rapid_pair = GameService._consume_rapid_pair(session, team, undo)

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
                session.oid, allowed_actions={"add_point"}, team=team,
            ) if undo and not rapid_pair else None
        )

        set_won = session.game_manager.add_game(
            team, session.current_set,
            session.points_limit, session.points_limit_last_set,
            session.sets_limit, undo,
        )

        if undo and session.undo:
            session.undo = False

        # ``_compute_current_set`` already handles the match-finished
        # case (returns t1+t2 without a +1 advance), so an extra
        # match_finished guard here is redundant.
        if set_won:
            session.current_set = session._compute_current_set()

        GameService._sync_match_finished_at(session, was_finished_before)

        # Audit before computing ``state_response`` so the cached
        # ``undoable_forward_count`` (and therefore ``can_undo``) the
        # state response carries is up to date for *this* action.
        # Otherwise the very first forward / last undo would broadcast
        # the pre-increment counter and the UI's undo button would lag
        # one action behind.
        if not rapid_pair:
            audit_record = GameService._audit(
                session, "add_point", {"team": team, "undo": undo},
                popped_forward=popped,
                target_set=target_set_before_advance,
            )
            GameService._record_rapid_pair_seed(
                session, team, undo, audit_record, popped,
            )

        # Compute the post-mutation state once and reuse it for the
        # broadcast, webhook fan-out, archive, and HTTP response.
        # ``get_state`` does non-trivial work (set-range iteration plus
        # side-switch / match-point computation), so collapsing four
        # call sites into one is a measurable per-action win.
        state_response = GameService.get_state(session)
        GameService._save_and_broadcast(session, state_response)

        # Fire after persistence so consumers always see the post-state.
        # Set-end / match-end webhooks fire whether or not a rapid pair
        # absorbed the audit half — the underlying state transition
        # really happened (operator saw the set close + reopen) and
        # downstream consumers should see the same effective edge.
        if not undo:
            if set_won:
                GameService._fire(session, "set_end", state_response, {
                    "team": team,
                    "set_number": GameService._ended_set_index(session),
                })
            if session.game_manager.match_finished(session.sets_limit) and not was_finished_before:
                GameService._archive_if_finished(
                    session, was_finished_before, team, state_response,
                )
                GameService._fire(session, "match_end", state_response, {
                    "winning_team": team,
                })
            GameService._fire_serve_change_if_changed(session, serve_before, state_response)

        return ActionResponse(success=True, state=state_response)

    @staticmethod
    def add_set(session, team: int, undo: bool = False) -> ActionResponse:
        if not undo:
            blocked = GameService._match_finished_response(session)
            if blocked is not None:
                return blocked

        # Any action other than ``add_point`` invalidates the rapid-
        # pair cache so a tap that follows can never trigger a false-
        # positive recovery against an unrelated prior action.
        GameService._invalidate_rapid_pair_cache(session)
        was_finished_before = session.game_manager.match_finished(session.sets_limit)
        # Same reasoning as add_point: capture before advance so the
        # audit log records the final score of the set that ended.
        target_set_before_advance = session.current_set

        popped = (
            action_log.pop_last_forward(
                session.oid, allowed_actions={"add_set"}, team=team,
            ) if undo else None
        )

        session.game_manager.add_set(team, undo, session.sets_limit)

        if undo and session.undo:
            session.undo = False

        session.current_set = session._compute_current_set()
        GameService._sync_match_finished_at(session, was_finished_before)
        # Audit before ``get_state`` so the ``can_undo`` flag the
        # broadcast carries reflects the just-bumped counter.
        GameService._audit(
            session, "add_set", {"team": team, "undo": undo},
            popped_forward=popped,
            target_set=target_set_before_advance,
        )
        state_response = GameService.get_state(session)
        GameService._save_and_broadcast(session, state_response)

        if not undo:
            GameService._fire(session, "set_end", state_response, {
                "team": team,
                "set_number": GameService._ended_set_index(session),
            })
            if session.game_manager.match_finished(session.sets_limit) and not was_finished_before:
                GameService._archive_if_finished(
                    session, was_finished_before, team, state_response,
                )
                GameService._fire(session, "match_end", state_response, {
                    "winning_team": team,
                })
        return ActionResponse(success=True, state=state_response)

    @staticmethod
    def add_timeout(session, team: int, undo: bool = False) -> ActionResponse:
        if not undo:
            blocked = GameService._match_finished_response(session)
            if blocked is not None:
                return blocked

        GameService._invalidate_rapid_pair_cache(session)
        popped = (
            action_log.pop_last_forward(
                session.oid, allowed_actions={"add_timeout"}, team=team,
            ) if undo else None
        )

        session.game_manager.add_timeout(team, undo)

        if undo and session.undo:
            session.undo = False

        # Audit before ``get_state`` so ``can_undo`` reflects the
        # post-action counter on the very first / last timeout.
        GameService._audit(
            session, "add_timeout", {"team": team, "undo": undo},
            popped_forward=popped,
        )
        state_response = GameService.get_state(session)
        GameService._save_and_broadcast(session, state_response)
        if not undo:
            GameService._fire(
                session, "timeout", state_response, {"team": team},
            )
        return ActionResponse(success=True, state=state_response)

    @staticmethod
    def change_serve(session, team: int) -> ActionResponse:
        GameService._invalidate_rapid_pair_cache(session)
        serve_before = session.game_manager.get_current_state().get_current_serve()
        session.game_manager.change_serve(team)
        state_response = GameService.get_state(session)
        GameService._save_and_broadcast(session, state_response)
        GameService._audit(session, "change_serve", {"team": team})
        GameService._fire_serve_change_if_changed(
            session, serve_before, state_response,
        )
        return ActionResponse(success=True, state=state_response)

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
        GameService._invalidate_rapid_pair_cache(session)
        was_finished_before = session.game_manager.match_finished(session.sets_limit)
        session.game_manager.set_game_value(team, value, set_number)
        set_won = session.game_manager.check_set_won(
            team, set_number,
            session.points_limit, session.points_limit_last_set,
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
        GameService._sync_match_finished_at(session, was_finished_before)
        state_response = GameService.get_state(session)
        GameService._save_and_broadcast(session, state_response)
        GameService._audit(session, "set_score", {
            "team": team, "set_number": set_number, "value": value,
        })
        return ActionResponse(success=True, state=state_response)

    @staticmethod
    def set_sets_value(session, team: int, value: int) -> ActionResponse:
        GameService._invalidate_rapid_pair_cache(session)
        was_finished_before = session.game_manager.match_finished(session.sets_limit)
        session.game_manager.set_sets_value(team, value)
        session.current_set = session._compute_current_set()
        # Same as ``set_score``: a direct sets-won edit can transition
        # the match in either direction; keep ``match_finished_at`` in
        # sync before the broadcast.
        GameService._sync_match_finished_at(session, was_finished_before)
        state_response = GameService.get_state(session)
        GameService._save_and_broadcast(session, state_response)
        GameService._audit(session, "set_sets_value", {"team": team, "value": value})
        return ActionResponse(success=True, state=state_response)

    @staticmethod
    def undo_last(session) -> ActionResponse:
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
            session.oid, allowed_actions=action_log.UNDOABLE_ACTIONS,
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
                    state=GameService.get_state(session),
                    message=f"Unknown mode: {mode!r}",
                )
            session.mode = mode

        GameService._invalidate_rapid_pair_cache(session)

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
        state_response = GameService.get_state(session)
        GameService._broadcast(session, state_response)
        GameService._audit(session, "set_rules", {
            "mode": session.mode,
            "points_limit": session.points_limit,
            "points_limit_last_set": session.points_limit_last_set,
            "sets_limit": session.sets_limit,
            "reset_to_defaults": reset_to_defaults,
        })
        return ActionResponse(success=True, state=state_response)

    @staticmethod
    def start_match(session) -> ActionResponse:
        """Arm the match-start clock without scoring a point.

        Idempotent: a second call after the match has already started
        is a no-op (the clock keeps the original anchor). The first
        ``add_point`` arms the clock implicitly, so this endpoint
        exists for the case where the operator wants the timer to
        reflect the actual whistle rather than the first rally.
        """
        if session.match_started_at is None:
            GameService._invalidate_rapid_pair_cache(session)
            session.match_started_at = time.time()
            # Belt-and-braces: a fresh arm should never carry a stale
            # finished-at from a prior match still hanging around in
            # the persisted meta.
            session.match_finished_at = None
            session.persist_meta()
            GameService._audit(session, "start_match", {})
            GameService._broadcast(session)
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def reset(session) -> ActionResponse:
        # Reset wipes the audit log; the rapid-pair cache that
        # references audit timestamps must vanish with it.
        GameService._invalidate_rapid_pair_cache(session)
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
        GameService._audit(session, "reset", {})
        state_response = GameService.get_state(session)
        GameService._save_and_broadcast(session, state_response)
        return ActionResponse(success=True, state=state_response)

    @staticmethod
    def set_visibility(session, visible: bool) -> ActionResponse:
        session.visible = visible
        session.backend.change_overlay_visibility(visible)
        state_response = GameService.get_state(session)
        GameService._broadcast(session, state_response)
        return ActionResponse(success=True, state=state_response)

    @staticmethod
    def set_simple_mode(session, enabled: bool) -> ActionResponse:
        session.simple = enabled
        if enabled:
            session.backend.reduce_games_to_one()
        state_response = GameService.get_state(session)
        GameService._save_and_broadcast(session, state_response)
        return ActionResponse(success=True, state=state_response)

    @staticmethod
    def update_customization(session, data: dict) -> ActionResponse:
        # Reject obviously malformed payloads before doing any work. The
        # cap on top-level keys keeps a malicious client from streaming
        # tens of thousands of unknown keys (the filter below drops them,
        # but allocating the dict iteration is still wasted work).
        if not isinstance(data, dict):
            return ActionResponse(
                success=False,
                state=GameService.get_state(session),
                message="Customization payload must be a JSON object.",
            )
        if len(data) > MAX_CUSTOMIZATION_KEYS:
            return ActionResponse(
                success=False,
                state=GameService.get_state(session),
                message=(
                    f"Customization payload exceeds {MAX_CUSTOMIZATION_KEYS} "
                    f"keys."
                ),
            )

        # Filter to allowed keys only
        filtered = {k: v for k, v in data.items() if k in ALLOWED_CUSTOMIZATION_KEYS}
        if not filtered:
            return ActionResponse(
                success=False,
                state=GameService.get_state(session),
                message="No valid customization keys provided.",
            )

        # Per-value validation: only scalar JSON types are allowed
        # (str / bool / int / float / None). Lists and nested objects
        # are rejected outright — the customization model is a flat
        # map of UI knobs, so an array or dict would either be ignored
        # downstream or balloon the broadcast payload via deep merge.
        # Strings are length-capped and logo URLs are scheme-checked.
        for key, value in filtered.items():
            if key in LOGO_KEYS:
                if value in (None, ""):
                    continue
                if not is_safe_logo_url(value):
                    return ActionResponse(
                        success=False,
                        state=GameService.get_state(session),
                        message=(
                            f"Logo URL for '{key}' must use http(s) or "
                            f"data:image scheme."
                        ),
                    )
            elif isinstance(value, str):
                if len(value) > MAX_STRING_VALUE_LENGTH:
                    return ActionResponse(
                        success=False,
                        state=GameService.get_state(session),
                        message=(
                            f"Value for '{key}' exceeds "
                            f"{MAX_STRING_VALUE_LENGTH} characters."
                        ),
                    )
            elif not isinstance(value, (bool, int, float, type(None))):
                # ``bool`` is a subclass of ``int`` so it would have
                # been accepted by the numeric branch anyway, but
                # listing it explicitly documents intent.
                return ActionResponse(
                    success=False,
                    state=GameService.get_state(session),
                    message=(
                        f"Value for '{key}' must be a string, "
                        f"boolean, number, or null."
                    ),
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
        state_response = GameService.get_state(session)
        GameService._broadcast(session, state_response)
        return ActionResponse(success=True, state=state_response)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _save_and_broadcast(session, state_response: GameStateResponse | None = None):
        """Persist state to the overlay backend and notify WS clients.

        Callers that already computed the post-mutation
        ``GameStateResponse`` should pass it via *state_response* —
        :func:`get_state` is non-trivial (iterates the set range,
        computes side-switch / match-point info), so reusing the
        same object across the broadcast and the API response avoids
        recomputing the payload twice on every action.
        """
        session.game_manager.save(session.simple, session.current_set)
        session.persist_meta()
        GameService._broadcast(session, state_response)

    @staticmethod
    def _broadcast(session, state_response: GameStateResponse | None = None):
        """Notify all WebSocket frontend clients about the new state.

        See :func:`_save_and_broadcast` for the *state_response* reuse
        contract. The payload is encoded directly via
        :meth:`pydantic.BaseModel.model_dump_json` so we skip the
        intermediate ``model_dump`` → dict → ``json.dumps`` round-trip
        that the previous code path went through on every action.
        """
        if state_response is None:
            state_response = GameService.get_state(session)
        payload_json = state_response.model_dump_json()
        WSHub.broadcast_payload_json_sync(session.oid, payload_json)

    @staticmethod
    def _archive_if_finished(
        session,
        was_finished_before: bool,
        winning_team: int,
        state_response: GameStateResponse | None = None,
    ) -> str | None:
        """Archive the match when it transitions to finished.

        Called from add_point and add_set after the mutation completes.
        Returns the new ``match_id`` (or ``None`` if no archive happened).
        ``match_started_at`` is intentionally left in place so the HUD
        timer and the spectator page can render the final elapsed
        duration (``match_finished_at - match_started_at``) until the
        operator hits Reset — which is the only path that clears both
        timestamps and returns the session to the pre-match idle state.

        Callers that have a fresh post-mutation ``GameStateResponse``
        should pass it via *state_response* to avoid the redundant
        ``get_state`` recompute the archive payload would otherwise
        trigger.
        """
        if was_finished_before or not session.game_manager.match_finished(session.sets_limit):
            return None
        try:
            if state_response is None:
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

    @staticmethod
    def _audit(
        session,
        action: str,
        params: dict,
        popped_forward: dict | None = None,
        target_set: int | None = None,
    ) -> dict | None:
        """Append an audit-log record for the action just performed
        and, atomically with the append, keep
        ``session.undoable_forward_count`` in sync.

        The counter is the cached source of truth for
        ``GameStateResponse.can_undo``. It must never disagree with
        what's on disk, so it is updated *only* after a successful
        ``action_log.append``. If the append fails (filesystem error,
        readonly mount, …) we leave the counter alone — a future
        restart's ``count_undoable_forwards`` rehydration will
        produce the same answer the in-memory counter does now.

        For undoable actions:
          * a forward call (``params.undo`` falsy) increments;
          * an undo call decrements iff *popped_forward* is not
            ``None`` (a forward was actually consumed).
        Non-undoable actions never touch the counter.

        *target_set* names the set that the action operated on.
        For most actions this is ``session.current_set``; for
        set-winning ``add_point``/``add_set`` calls the caller
        passes the *previous* set so the audit log records the
        final scores (e.g. 25-23) instead of the next set's empty
        0-0. The ``current_set`` field in the result still reports
        the post-action value so a reader can see the advance.

        Best-effort — file errors don't propagate. Returns the
        record that was written (so the caller can read its
        assigned ``ts``) or ``None`` when the append failed.
        """
        try:
            state = session.game_manager.get_current_state()
            score_set = (
                target_set if target_set is not None else session.current_set
            )
            t1_score = state.get_game(1, score_set)
            t2_score = state.get_game(2, score_set)
            serve = state.get_current_serve()
            result = {
                "current_set": session.current_set,
                # ``score_set`` tags which set the team scores below
                # correspond to. Usually identical to ``current_set``;
                # diverges for set-winning add_point/add_set calls
                # where ``current_set`` advances to the next set but
                # the meaningful scores belong to the one that just
                # ended.
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

        # ``action_log.append`` swallows internal write errors and
        # returns ``None`` instead of raising. The counter must only
        # follow the on-disk truth, so skip the bookkeeping in that
        # case — a future ``count_undoable_forwards`` rehydration
        # will reconcile the in-memory state with whatever actually
        # landed on disk.
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
