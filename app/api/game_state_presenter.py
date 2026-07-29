"""Presentation of live game state as API response models."""

import logging
import time

from app.api import game_rapid_pair as _rapid_pair
from app.api.match_rules import (
    compute_match_point_info,
    compute_serve_switch,
    compute_side_switch,
    table_tennis_server,
)
from app.api.schemas import (
    BeachSideSwitch,
    GameStateResponse,
    MatchPointInfo,
    ServeSwitch,
    TeamState,
)
from app.customization_cache_ttl import customization_cache_ttl_seconds
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
RAPID_PAIR_WINDOW_S = _rapid_pair.RAPID_PAIR_WINDOW_S

# Short TTL for the customization read-through cache. The overlay server is
# authoritative, but the React UI polls this endpoint on every config panel
# open; coalescing into a 5 s window avoids a burst of redundant round-trips
# without letting the UI show truly stale data.
CUSTOMIZATION_CACHE_TTL_SECONDS = customization_cache_ttl_seconds()


def _service(cls: type):
    """Return the composed facade class for cross-mixin calls."""
    return cls


class GameStatePresenter:
    """Build response models and presentation-only derived values."""

    @classmethod
    def _obs_client_count(cls, session) -> int:
        """Live output clients (OBS + spectator) on this overlay, 0 on error.

        Defensive: not every backend tracks this (e.g. bare/test backends),
        and a counting failure must never break the operator's state fetch.
        """
        try:
            return int(session.backend.obs_client_count)
        except Exception:  # pragma: no cover - defensive
            logger.debug(
                "Could not read obs_client_count for OID=%s",
                getattr(session, "oid", None),
                exc_info=True,
            )
            return 0

    @classmethod
    def _resolve_last_match_id(cls, session) -> str | None:
        """``match_id`` of the just-finished match for the report link.

        Prefers the id stashed on the session when the match was archived
        (free, in-memory); falls back to the archive index only when that is
        missing (e.g. the session was rebuilt after a restart).
        """
        cached = getattr(session, "last_match_id", None)
        if cached:
            return cached
        try:
            from app.api import match_archive

            summaries = match_archive.list_matches(oid=session.oid)
            return summaries[0]["match_id"] if summaries else None
        except Exception:  # pragma: no cover - defensive
            logger.warning(
                "Could not resolve last match id for OID=%s",
                getattr(session, "oid", None),
                exc_info=True,
            )
            return None

    @classmethod
    def _sync_table_tennis_serve(cls, session) -> None:
        """Recompute the live serve for a table-tennis session.

        Volleyball serve follows the rally winner (handled in
        ``GameManager.add_game``); table tennis rotates the serve on a
        fixed cadence that depends only on the score, the game index and
        the match's ``first_server``. We recompute it here — the single
        choke point every action runs through before broadcasting — so
        the API state *and* the OBS overlay (which reads serve straight
        off the persisted model) both track the rotation, and an undo
        rewinds it for free. No-op once the match is finished so the
        final server sticks.
        """
        if session.mode != "table_tennis":
            return
        if session.game_manager.match_finished(session.sets_limit):
            return
        state = session.game_manager.get_current_state()
        server = table_tennis_server(
            first_server=session.first_server,
            current_set=session.current_set,
            sets_limit=session.sets_limit,
            team1_score=state.get_game(1, session.current_set),
            team2_score=state.get_game(2, session.current_set),
            points_limit=session.points_limit,
            points_limit_last_set=session.points_limit_last_set,
        )
        desired = State.SERVE_1 if server == 1 else State.SERVE_2
        if state.get_current_serve() != desired:
            state.set_current_serve(desired)

    @classmethod
    def get_state(cls, session) -> GameStateResponse:
        """Build a ``GameStateResponse`` from the current session state."""
        t0 = time.perf_counter()
        _service(cls)._sync_table_tennis_serve(session)
        state = session.game_manager.get_current_state()
        serve = state.get_current_serve()

        def team_state(team):
            scores = {}
            timeouts_by_set = {}
            for i in range(1, session.sets_limit + 1):
                scores[f"set_{i}"] = state.get_game(team, i)
                timeouts_by_set[f"set_{i}"] = state.get_timeout(team, set_num=i)
            # Pin to ``session.current_set`` (not the implicit
            # ``state.current_set`` default) — the latter only updates in
            # ``GameManager.save`` after this response is built, so it
            # lags by one tick on a set-winning point and would report
            # the previous set's count.
            return TeamState(
                sets=state.get_sets(team),
                timeouts=state.get_timeout(team, set_num=session.current_set),
                timeouts_by_set=timeouts_by_set,
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
        side_switch = BeachSideSwitch(**side_switch_data) if side_switch_data is not None else None
        serve_switch_data = compute_serve_switch(
            mode=session.mode,
            current_set=session.current_set,
            sets_limit=session.sets_limit,
            first_server=session.first_server,
            team1_score=team1_score,
            team2_score=team2_score,
            points_limit=session.points_limit,
            points_limit_last_set=session.points_limit_last_set,
        )
        serve_switch = ServeSwitch(**serve_switch_data) if serve_switch_data is not None else None
        match_finished = session.game_manager.match_finished(session.sets_limit)
        match_point_info = MatchPointInfo(
            **compute_match_point_info(
                current_set=session.current_set,
                sets_limit=session.sets_limit,
                team1_sets=state.get_sets(1),
                team2_sets=state.get_sets(2),
                team1_score=team1_score,
                team2_score=team2_score,
                points_limit=session.points_limit,
                points_limit_last_set=session.points_limit_last_set,
                match_finished=match_finished,
            )
        )
        # Both ``_current_set_started_at`` and ``_resolve_summary_set``
        # need ``points_by_set``, so derive it once and pass it down
        # rather than letting each helper re-fetch. ``compute_live_stats``
        # is memoized against the audit-log version, so on this hot path
        # (fires on every action and broadcast) the call is a cache hit
        # whenever the log is unchanged, and the one real computation per
        # audit mutation is shared with the overlay push, which needs the
        # full stats payload anyway. ``None`` here is safe — the helpers
        # treat it as "no stats available" and fall back to defaults.
        points_by_set_cache: dict | None
        try:
            from app.api.live_stats import compute_live_stats

            stats = compute_live_stats(session.oid)
            points_by_set_cache = stats.get("points_by_set") or {}
        except Exception:  # pragma: no cover - defensive
            # Degrades several fields at once (current_set_started_at,
            # the summary-set resolution) and would otherwise be silent
            # and permanent, so this is logged loudly.
            logger.exception(
                "Live-stats computation failed for OID=%s; state response will fall back to defaults",
                getattr(session, "oid", None),
            )
            points_by_set_cache = None
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
            serve_switch=serve_switch,
            match_point_info=match_point_info,
            sides_swapped=_service(cls).effective_sides_swapped(session, state),
            auto_swap_sides=bool(session.auto_swap_sides),
            can_undo=session.undoable_forward_count > 0,
            match_started_at=session.match_started_at,
            match_finished_at=session.match_finished_at,
            current_set_started_at=_service(cls)._current_set_started_at(
                session,
                points_by_set=points_by_set_cache,
            ),
            set_summary=bool(getattr(session, "set_summary", False)),
            set_summary_set_num=(
                _service(cls)._resolve_summary_set(
                    session,
                    points_by_set=points_by_set_cache,
                )
                if getattr(session, "set_summary", False)
                else None
            ),
            set_summary_style=str(getattr(session, "set_summary_style", "brand_ledger")),
            server_time=time.time(),
            obs_clients=_service(cls)._obs_client_count(session),
            last_match_id=(_service(cls)._resolve_last_match_id(session) if match_finished else None),
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        # Misconfigured env var must not turn every /state call into a 500;
        # silently fall back to the documented default.
        try:
            warn_threshold_ms = float(EnvVarsManager.get_env_var("PERF_GET_STATE_WARN_MS", "50"))
        except (TypeError, ValueError):
            warn_threshold_ms = 50.0
        if elapsed_ms > warn_threshold_ms:
            logger.warning(
                "get_state slow: %.1fms sets_limit=%s",
                elapsed_ms,
                session.sets_limit,
            )
        else:
            logger.debug(
                "get_state took %.1fms sets_limit=%s",
                elapsed_ms,
                session.sets_limit,
            )
        return response

    @classmethod
    def _current_set_started_at(
        cls,
        session,
        points_by_set: dict | None = None,
    ) -> float | None:
        """Wall-clock timestamp of the first scoring event in the
        operator's current set.

        Used by the React control UI to detect abandoned sessions
        on page load (current-set elapsed > 1h → prompt the
        operator to reset). Returns ``None`` when:

        * The match has not started yet (no point recorded).
        * The current set has no scoring event yet (we're between
          sets after a forward set transition).
        * Computing the audit-derived stats failed for any reason
          — fail safe by returning ``None`` so the client doesn't
          surface a false positive prompt.

        ``set_score`` (manual edits) are intentionally honoured
        here: if the operator pulled a set forward by hand the
        edit's timestamp is the only signal we have, and treating
        the set as "just touched" is the right default.

        Pass ``points_by_set`` when the caller has already invoked
        ``compute_live_stats`` to avoid re-reading the audit log.
        """
        try:
            if points_by_set is None:
                from app.api.live_stats import compute_live_stats

                stats = compute_live_stats(session.oid)
                points_by_set = stats.get("points_by_set") or {}
            current = int(session.current_set)
            events = points_by_set.get(current) or points_by_set.get(str(current)) or []
            if not events:
                return None
            ts = events[0].get("ts")
            return float(ts) if isinstance(ts, (int, float)) else None
        except Exception:  # pragma: no cover - defensive
            logger.warning(
                "Could not resolve current-set start for OID=%s",
                getattr(session, "oid", None),
                exc_info=True,
            )
            return None

    @classmethod
    def _resolve_summary_set(
        cls,
        session,
        points_by_set: dict | None = None,
    ) -> int:
        """Return the set number the summary panel should show.

        Returns the current set if it has any recorded points yet, else
        the previous set so the operator can roll a recap between sets.
        Always clamped to at least 1.

        Pass ``points_by_set`` to avoid an extra ``compute_live_stats``
        call when the caller has the stats in hand already.

        Only ``add_point`` events count as "recorded points" — manual
        ``set_score`` edits to historical sets get tagged with the
        operator's current set via ``result.current_set`` and would
        otherwise make the resolver pick a set that has not actually
        been played.
        """
        try:
            from app.api.live_stats import compute_live_stats, resolve_summary_set_num

            if points_by_set is None:
                stats = compute_live_stats(session.oid)
                points_by_set = stats.get("points_by_set")
            return resolve_summary_set_num(points_by_set, session.current_set)
        except Exception:  # pragma: no cover - defensive
            logger.warning(
                "Could not resolve summary set for OID=%s; falling back to the previous set",
                getattr(session, "oid", None),
                exc_info=True,
            )
            return max(int(session.current_set) - 1, 1)
