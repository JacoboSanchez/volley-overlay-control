import copy
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.customization_cache import CustomizationCache
from app.customization_cache_ttl import (
    BACKEND_DEFAULT_TTL_SECONDS,
    customization_cache_ttl_seconds,
)
from app.overlay_backends import (
    LocalOverlayBackend,
    OverlayKind,
    resolve_overlay_kind,
)
from app.state import State

_CUSTOMIZATION_CACHE_TTL_SECONDS = customization_cache_ttl_seconds(
    default=BACKEND_DEFAULT_TTL_SECONDS,
)

# Warn when a single remote overlay call exceeds this duration. Conservative so
# it only fires on real slowdowns, not on a cold-start connection setup.
_REMOTE_CALL_WARN_MS = 500.0


@contextmanager
def _timed(label: str, logger: logging.Logger):
    """Log perf_counter-based duration at DEBUG, or WARNING above the threshold."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms > _REMOTE_CALL_WARN_MS:
            logger.warning('%s slow: %.1fms', label, elapsed_ms)
        else:
            logger.debug('%s took %.1fms', label, elapsed_ms)


class Backend:
    """Coordinator that forwards overlay operations to the in-process backend.

    Every overlay is served in-process by :class:`LocalOverlayBackend`; this
    class keeps the same public surface the rest of the app calls.
    """

    logger = logging.getLogger(__name__)

    def __init__(self, config):
        self.conf = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.conf.rest_user_agent,
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*'
        })
        # Pool sized for ThreadPoolExecutor (max_workers=5) plus the foreground
        # request thread, with headroom. Retry covers transient 5xx/connection
        # hiccups from the overlay server without masking real failures — the
        # short per-call timeouts (2-5 s) keep the worst case bounded.
        _adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=Retry(
                total=2,
                backoff_factor=0.3,
                status_forcelist=(502, 503, 504),
                allowed_methods=frozenset(["GET", "PUT", "POST"]),
                raise_on_status=False,
            ),
        )
        self.session.mount("http://", _adapter)
        self.session.mount("https://", _adapter)
        self.executor = ThreadPoolExecutor(max_workers=5)
        self._customization_cache = CustomizationCache(
            _CUSTOMIZATION_CACHE_TTL_SECONDS
        )
        # Hook for the per-session rule overrides (mode + per-set
        # point/sets limits + match_started_at). Wired explicitly by
        # ``GameSession`` via :meth:`set_rule_overrides_getter` so the
        # dependency is part of the public surface rather than a
        # monkey-patched attribute. ``None`` means "fall back to the
        # env-default ``conf`` values" — the legacy standalone path
        # that doesn't use the session manager.
        self._rule_overrides_getter: Callable[[], dict] | None = None
        self._overlay = self._create_overlay_backend()

    def set_rule_overrides_getter(self, getter: Callable[[], dict] | None) -> None:
        """Register the per-session rule-overrides callable.

        Called by :meth:`GameSession.__init__` so
        :meth:`_build_overlay_payload` can pull the live mode +
        per-set limits + ``match_started_at`` on every broadcast.
        Passing ``None`` reverts to env-default conf values; useful
        for tests that build a bare Backend without a session.
        """
        self._rule_overrides_getter = getter

    def _remember_customization(self, data):
        """Store a copy of *data* in the cache so callers can't mutate it."""
        self._customization_cache.remember(data)

    def _fresh_customization_cache(self):
        """Return a fresh copy of the cached customization, or None if stale."""
        return self._customization_cache.fresh()

    def _local_overlay_exists(self, overlay_id: str) -> bool:
        # Local overlay state is keyed by the per-user storage key when one
        # is bound to the session (``conf.skey``); fall back to the raw id
        # for bare/standalone backends (tests, legacy paths).
        from app.overlay import overlay_state_store
        key = self.conf.skey or overlay_id
        return bool(key) and overlay_state_store.overlay_exists(key)

    def _oid_or_default(self, oid):
        return oid if oid is not None else self.conf.oid

    def _resolve_kind(self, oid=None) -> OverlayKind:
        return resolve_overlay_kind(self._oid_or_default(oid), self._local_overlay_exists)

    def _create_overlay_backend(self, oid=None):
        """Instantiate the in-process overlay backend.

        Every overlay is served by ``LocalOverlayBackend``; ``validate_oid``
        later reports INVALID for an OID with no local overlay (overlays are
        created up-front via the "My overlays" page — no auto-creation here).
        """
        backend = LocalOverlayBackend(self.conf)
        backend._build_payload = self._build_overlay_payload
        return backend

    def _ensure_overlay_backend(self, oid=None):
        """No-op: there is a single in-process backend (kept for call-site compat)."""

    # -- Public interface (used by GameManager, GameSession, routes, GUI) ----

    def is_custom_overlay(self, oid=None):
        return self._resolve_kind(oid) == OverlayKind.CUSTOM

    def get_custom_overlay_id(self, oid=None):
        check_oid = self._oid_or_default(oid)
        if self._resolve_kind(check_oid) == OverlayKind.CUSTOM:
            return LocalOverlayBackend.get_overlay_id(check_oid)
        return check_oid, None

    # -- WebSocket lifecycle (delegated) ------------------------------------

    def init_ws_client(self, oid=None):
        # In-process backend has no external WS connection (no-op).
        self._overlay.init_ws_client(self._oid_or_default(oid))

    def close_ws_client(self):
        self._overlay.close_ws_client()

    def shutdown(self):
        # Close the WebSocket first so no new tasks are submitted that would
        # race with the executor drain below.
        self._overlay.shutdown()
        executor = getattr(self, 'executor', None)
        if executor is None:
            return
        # wait=True so in-flight overlay saves aren't abandoned mid-request.
        # cancel_futures=False preserves the queued tasks (queued saves will
        # run before the executor finally exits).
        executor.shutdown(wait=True, cancel_futures=False)

    @property
    def ws_connected(self):
        return self._overlay.ws_connected

    @property
    def obs_client_count(self):
        return self._overlay.obs_client_count

    # -- Overlay payload builder -------------------------------------------

    def _build_overlay_payload(
        self, current_model,
        force_visibility=None,
        customization_state=None,
        show_only_current_set=None,
    ):
        """Build the standardized overlay state JSON payload."""
        from app.customization import Customization

        if customization_state is None:
            cached = self._fresh_customization_cache()
            customization_state = (
                cached if cached is not None
                else (self.get_current_customization() or {})
            )
        cust = Customization(customization_state)

        def get_set_history(team):
            return {
                f"set_{i}": int(
                    current_model.get(
                        f'Team {team} Game {i} Score', 0
                    )
                )
                for i in range(1, 8)
            }

        current_set = int(
            current_model.get(State.CURRENT_SET_INT, 1)
        )

        # Pull the active session's rules (set in
        # ``GameSession.__init__``) so the broadcast carries the live
        # mode + per-set limits. Falls back to env-default ``conf``
        # values when no session has bound the hook — e.g. legacy
        # standalone backends still drive an overlay correctly.
        mode = "indoor"
        points_limit = int(self.conf.points)
        points_limit_last_set = int(self.conf.points_last_set)
        sets_limit = int(self.conf.sets)
        match_finished_flag = False
        match_started_at: float | None = None
        match_finished_at: float | None = None
        set_summary_flag = False
        set_summary_style = "brand_ledger"
        sides_swapped_manual = False
        auto_swap_sides = False
        getter = self._rule_overrides_getter
        if callable(getter):
            try:
                overrides = getter() or {}
            except Exception:  # pragma: no cover - defensive
                # Defensive only: the session-bound callable shouldn't
                # raise. ``logger.exception`` captures the full
                # traceback so a real bug isn't silently masked.
                Backend.logger.exception("Rule overrides getter raised")
                overrides = {}
            mode = str(overrides.get("mode", mode))
            points_limit = int(overrides.get("points_limit", points_limit))
            points_limit_last_set = int(
                overrides.get("points_limit_last_set", points_limit_last_set)
            )
            sets_limit = int(overrides.get("sets_limit", sets_limit))
            match_finished_flag = bool(overrides.get("match_finished", False))
            raw_started = overrides.get("match_started_at")
            if isinstance(raw_started, (int, float)):
                match_started_at = float(raw_started)
            raw_finished = overrides.get("match_finished_at")
            if isinstance(raw_finished, (int, float)):
                match_finished_at = float(raw_finished)
            set_summary_flag = bool(overrides.get("set_summary", False))
            raw_style = overrides.get("set_summary_style")
            if isinstance(raw_style, str) and raw_style:
                set_summary_style = raw_style
            sides_swapped_manual = bool(
                overrides.get("sides_swapped_manual", False)
            )
            auto_swap_sides = bool(overrides.get("auto_swap_sides", False))

        payload = {
            "match_info": {
                "tournament": "Superliga Masculina",
                "phase": "Playoffs",
                "best_of_sets": sets_limit,
                "current_set": current_set,
                # New: surface the live match rules to the spectator
                # page so it can render a quick-reference badge and
                # drive the per-set targets in its UI.
                "mode": mode,
                "points_limit": points_limit,
                "points_limit_last_set": points_limit_last_set,
                # Wall-clock seconds at which the operator armed the
                # match (or ``None`` if pending). The spectator uses
                # this to tick a live match-elapsed counter; the OBS
                # templates ignore it.
                "match_started_at": match_started_at,
                # Wall-clock seconds at which the match transitioned
                # to finished (or ``None`` while it's still in
                # progress). Lets the spectator freeze its match
                # timer at the actual end-of-match value instead of
                # ticking forward indefinitely after match end.
                "match_finished_at": match_finished_at,
                # Server wall-clock at the moment this payload was
                # composed. Clients use the delta between
                # ``server_time`` and their own ``Date.now()`` on
                # arrival to derive a clock-skew offset, then apply
                # the offset to every live-tick computation (set
                # duration, match elapsed, stale-set check) — so
                # the displayed durations track the server even
                # when the client's system clock is wrong.
                "server_time": time.time(),
                # Mirror of ``match_finished_flag`` so the spectator
                # can render a "match finished" indicator without
                # having to re-derive it from the per-team set counts.
                "match_finished": match_finished_flag,
                # Set summary overlay (operator-toggled panel that
                # replaces the scoreboard between sets). ``show_set_summary``
                # is the on/off flag; ``set_summary_style`` is the
                # visual variant ('brand_ledger', 'bento', …). The
                # actual set number is resolved further down once the
                # live stats are available.
                "show_set_summary": set_summary_flag,
                "set_summary_style": set_summary_style,
                # Display-side swap (True = team 2 rendered on the
                # left). Starts at the operator's manual base and is
                # XOR-ed with the auto-derived component below once
                # the live scores are available.
                "sides_swapped": sides_swapped_manual,
            },
            "team_home": {
                "name": cust.get_team_name(1),
                "short_name": (
                    cust.get_team_name(1)[:3].upper()
                    if cust.get_team_name(1) else "HOM"
                ),
                "color_primary": cust.get_team_color(1),
                "color_secondary": cust.get_team_text_color(1),
                "logo_url": cust.get_team_logo(1),
                "sets_won": int(
                    current_model.get(State.T1SETS_INT, 0)
                ),
                "points": int(
                    current_model.get(
                        f'Team 1 Game {current_set} Score', 0
                    )
                ),
                "serving": (
                    current_model.get(State.SERVE) == State.SERVE_1
                ),
                "timeouts_taken": int(
                    current_model.get(State.T1TIMEOUTS_INT, 0)
                ),
                "set_history": get_set_history(1),
            },
            "team_away": {
                "name": cust.get_team_name(2),
                "short_name": (
                    cust.get_team_name(2)[:3].upper()
                    if cust.get_team_name(2) else "AWA"
                ),
                "color_primary": cust.get_team_color(2),
                "color_secondary": cust.get_team_text_color(2),
                "logo_url": cust.get_team_logo(2),
                "sets_won": int(
                    current_model.get(State.T2SETS_INT, 0)
                ),
                "points": int(
                    current_model.get(
                        f'Team 2 Game {current_set} Score', 0
                    )
                ),
                "serving": (
                    current_model.get(State.SERVE) == State.SERVE_2
                ),
                "timeouts_taken": int(
                    current_model.get(State.T2TIMEOUTS_INT, 0)
                ),
                "set_history": get_set_history(2),
            },
            "overlay_control": {
                "show_bottom_ticker": False,
                "ticker_message": "",
                "show_player_stats": False,
                "player_stats_data": None,
                "geometry": {
                    "width": cust.get_width(),
                    "height": cust.get_height(),
                    "xpos": cust.get_hpos(),
                    "ypos": cust.get_vpos(),
                    "scale": cust.get_scale(),
                    "margin": cust.get_margin(),
                },
                "colors": {
                    "set_bg": cust.get_set_color(),
                    "set_text": cust.get_set_text_color(),
                    "game_bg": cust.get_game_color(),
                    "game_text": cust.get_game_text_color(),
                },
                "preferredStyle": cust.get_preferred_style(),
                "show_logos": cust.is_show_logos() not in (False, "false", "False"),
                "show_stats": cust.is_show_stats(),
                "show_points_history": cust.is_show_points_history(),
            },
        }

        # Live stats and points history are derived from the per-OID
        # audit log so the overlay viewer + the public spectator page
        # see the same trajectory as the final printed match report.
        #
        # The data is included in *every* broadcast (not gated by the
        # operator toggles) so the /follow/{id} page and any external
        # consumer can read it without the operator having to enable
        # display on the OBS overlay. The toggles
        # (``overlay_control.show_stats`` / ``show_points_history``)
        # control whether app.js *renders* the panels on the OBS-side
        # overlay — they are pure display flags. Computing the stats
        # is a fast audit-log walk; the cost is bounded by audit size
        # (capped + rotated by the action_log module).
        # Match-point + beach side-switch indicators. These are pure
        # functions of the current scores plus the rule overrides we
        # already pulled above, so we include them unconditionally on
        # every broadcast — the spectator page and the React control
        # UI both read them.
        try:
            from app.api.match_rules import (
                compute_match_point_info,
                compute_side_switch,
                compute_sides_swapped_auto,
            )
            team1_score = int(
                current_model.get(f'Team 1 Game {current_set} Score', 0)
            )
            team2_score = int(
                current_model.get(f'Team 2 Game {current_set} Score', 0)
            )
            team1_sets = int(current_model.get(State.T1SETS_INT, 0))
            team2_sets = int(current_model.get(State.T2SETS_INT, 0))
            payload["overlay_control"]["match_point_info"] = (
                compute_match_point_info(
                    current_set=current_set,
                    sets_limit=sets_limit,
                    team1_sets=team1_sets,
                    team2_sets=team2_sets,
                    team1_score=team1_score,
                    team2_score=team2_score,
                    points_limit=points_limit,
                    points_limit_last_set=points_limit_last_set,
                    match_finished=match_finished_flag,
                )
            )
            beach_side_switch = compute_side_switch(
                mode=mode,
                current_set=current_set,
                sets_limit=sets_limit,
                team1_score=team1_score,
                team2_score=team2_score,
                points_limit=points_limit,
                points_limit_last_set=points_limit_last_set,
            )
            if beach_side_switch is not None:
                payload["overlay_control"]["beach_side_switch"] = (
                    beach_side_switch
                )
            if auto_swap_sides:
                completed = [
                    (
                        int(current_model.get(f'Team 1 Game {i} Score', 0)),
                        int(current_model.get(f'Team 2 Game {i} Score', 0)),
                    )
                    for i in range(1, current_set)
                ]
                payload["match_info"]["sides_swapped"] = (
                    sides_swapped_manual ^ compute_sides_swapped_auto(
                        mode=mode,
                        current_set=current_set,
                        sets_limit=sets_limit,
                        team1_score=team1_score,
                        team2_score=team2_score,
                        points_limit=points_limit,
                        points_limit_last_set=points_limit_last_set,
                        completed_set_scores=completed,
                    )
                )
        except Exception:  # pragma: no cover - defensive
            Backend.logger.exception(
                "Failed to compute match-point / side-switch info",
            )

        try:
            from app.api.live_stats import compute_live_stats
            # The audit log is keyed by the per-user storage key (``skey``);
            # ``conf.oid`` is the bare oid and would read the wrong (empty)
            # file. Fall back to the raw id for bare/standalone backends.
            stats = compute_live_stats(
                self.conf.skey or self.conf.oid, history_limit=30,
            )
            payload["overlay_control"]["stats"] = {
                "current_streak": stats["current_streak"],
                "longest_streak": stats["longest_streak"],
                "partial_comeback": stats["partial_comeback"],
                "set_win_comeback": stats["set_win_comeback"],
                "total_points": stats["total_points"],
                # Per-set duration in seconds, derived from the audit
                # log's first/last event timestamps. The spectator
                # uses ``set_durations[viewed_set]`` for the set-time
                # display; stringified keys so JSON round-trip is
                # stable.
                "set_durations": {
                    str(k): v for k, v in stats["set_durations"].items()
                },
                # Services-won / total per team. Sent as string keys
                # for JSON round-trip; the spectator stats panel
                # renders them as a "Services" row.
                "services": {
                    str(team): counts
                    for team, counts in stats["services"].items()
                },
                # Per-set variants of streak + services so the set-
                # summary recap can show stats scoped to the displayed
                # set instead of match-wide totals.
                "longest_streak_by_set": {
                    str(set_num): {str(t): v for t, v in by_team.items()}
                    for set_num, by_team in stats["longest_streak_by_set"].items()
                },
                "services_by_set": {
                    str(set_num): {
                        str(t): counts for t, counts in by_team.items()
                    }
                    for set_num, by_team in stats["services_by_set"].items()
                },
                # Per-point classification (opt-in scouting tags). Sent
                # with string team keys for a stable JSON round-trip;
                # the spectator stats panel renders a per-type row and
                # the last-point indicator. ``error_types`` is a subset
                # of each team's ``opp_error`` total.
                "point_types": {
                    str(team): counts
                    for team, counts in stats["point_types"].items()
                },
                "error_types": {
                    str(team): counts
                    for team, counts in stats["error_types"].items()
                },
                # Per-set point types so the set-summary recap (the
                # overlay's stats view) can show a breakdown scoped to
                # the displayed set. Nested string keys for JSON round-
                # trip stability.
                "point_types_by_set": {
                    str(set_num): {
                        str(t): counts for t, counts in by_team.items()
                    }
                    for set_num, by_team in stats["point_types_by_set"].items()
                },
                "last_point": stats.get("last_point"),
            }
            payload["overlay_control"]["points_history"] = stats[
                "points_history"
            ]
            # Per-set bucketed events, stringified keys so the JSON
            # broadcast survives round-trip without key-type churn.
            # Consumed by the spectator (/follow) page to render past
            # sets via prev/next navigation.
            payload["overlay_control"]["points_by_set"] = {
                str(k): v for k, v in stats["points_by_set"].items()
            }
            # Timeout markers per set so the chart can draw them on
            # the same time axis as the running score lines.
            payload["overlay_control"]["timeouts_by_set"] = {
                str(k): v for k, v in stats["timeouts_by_set"].items()
            }
        except Exception:  # pragma: no cover - defensive
            Backend.logger.exception(
                "Failed to compute live stats for overlay payload",
            )

        if show_only_current_set is not None:
            payload["match_info"][
                "show_only_current_set"
            ] = show_only_current_set

        # Resolve summary_set_num — current_set when it has any
        # recorded points, else the previous set so the recap panel
        # has something to show right after a set transition. The
        # rule lives in :func:`live_stats.resolve_summary_set_num`
        # so :class:`GameService` and this broadcaster can't drift.
        try:
            from app.api.live_stats import resolve_summary_set_num
            payload["match_info"]["summary_set_num"] = resolve_summary_set_num(
                payload["overlay_control"].get("points_by_set"),
                current_set,
            )
        except Exception:  # pragma: no cover - defensive
            payload["match_info"]["summary_set_num"] = max(int(current_set) - 1, 1)

        if force_visibility is not None:
            payload["overlay_control"][
                "show_main_scoreboard"
            ] = force_visibility

        return payload

    # -- Model persistence --------------------------------------------------

    def save_model(self, current_model, simple):
        Backend.logger.debug('saving model...')
        self._ensure_overlay_backend()
        with _timed('save_model.model', Backend.logger):
            self._overlay.save_model(current_model)

        to_save = copy.copy(current_model)
        if simple:
            to_save = State.simplify_model(to_save)

        if self.conf.id == State.CHAMPIONSHIP_LAYOUT_ID:
            to_save["Sets Display"] = str(to_save.get(State.CURRENT_SET_INT, "1"))

        # Wrap the push inside the callable so the timing span runs where the
        # call actually executes — either inline (sync) or on the executor
        # thread (multithread). Otherwise the multithread branch would only
        # measure `executor.submit` (microseconds) and the WARNING threshold
        # would never fire even on a genuinely slow remote save.
        def _push():
            with _timed('save_model.push', Backend.logger):
                self._overlay.push_model_update(
                    current_model, to_save, show_only_current_set=simple,
                )

        if self.conf.multithread:
            self.executor.submit(_push)
        else:
            _push()

    def reduce_games_to_one(self):
        self._ensure_overlay_backend()
        self._overlay.reduce_games_to_one()

    def save_json_model(self, to_save):
        Backend.logger.debug('saving JSON model...')
        self._ensure_overlay_backend()
        self._overlay.send_json_model(to_save)

    def save_json_customization(self, to_save):
        Backend.logger.debug('saving JSON customization...')
        self._ensure_overlay_backend()
        self._remember_customization(to_save)

        self._overlay.save_customization(to_save)

        def get_model():
            return self.get_current_model(self.conf.oid)

        if self.conf.multithread:
            self.executor.submit(
                self._overlay.on_customization_saved, get_model, to_save,
            )
        else:
            self._overlay.on_customization_saved(get_model, to_save)

    def change_overlay_visibility(self, show):
        Backend.logger.debug('changing overlay visibility, show: %s', show)
        self._ensure_overlay_backend()
        self._overlay.change_visibility_with_fallback(
            show, lambda: self.get_current_model(self.conf.oid),
        )

    # -- Model/customization retrieval --------------------------------------

    def get_current_model(self, customOid=None, saveResult=False):
        oid = customOid if customOid is not None else self.conf.oid
        Backend.logger.debug('getting state for oid %s', oid)
        with _timed('get_current_model', Backend.logger):
            self._ensure_overlay_backend(oid)
            return self._overlay.get_model(oid=oid, save_result=saveResult)

    def get_current_customization(self, customOid=None):
        Backend.logger.debug('getting customization')
        with _timed('get_current_customization', Backend.logger):
            oid = customOid if customOid is not None else self.conf.oid
            self._ensure_overlay_backend(oid)
            data = self._overlay.get_customization(oid=oid)
            if data is not None:
                self._remember_customization(data)
            return data

    def is_visible(self):
        self._ensure_overlay_backend()
        return self._overlay.is_visible()

    def get_available_styles(self, oid: str = None) -> list:
        check_oid = self._oid_or_default(oid)
        self._ensure_overlay_backend(check_oid)
        return self._overlay.get_available_styles(check_oid)

    def get_style_capabilities(self, oid: str = None) -> dict:
        check_oid = self._oid_or_default(oid)
        self._ensure_overlay_backend(check_oid)
        return self._overlay.get_style_capabilities(check_oid)

    # -- OID validation / output token -------------------------------------

    def validate_and_store_model_for_oid(self, oid: str):
        if not oid or not oid.strip():
            return State.OIDStatus.EMPTY
        self._ensure_overlay_backend(oid)
        return self._overlay.validate_oid(oid)

    def fetch_and_update_overlay_id(self, oid: str):
        self._ensure_overlay_backend(oid)
        self._overlay.fetch_and_update_overlay_id(oid)

    def fetch_output_token(self, oid):
        self._ensure_overlay_backend(oid)
        return self._overlay.fetch_output_token(oid)

    # -- High-level helpers ------------------------------------------------

    def reset(self, state):
        current = state.get_current_model()
        reset_model = state.get_reset_model()
        new_state = copy.copy(current)
        new_state.update(reset_model)
        self.save_model(new_state, False)

    def save(self, state, simple):
        self.save_model(state.get_current_model(), simple)

    def process_response(self, response):
        if response.status_code >= 400:
            logging.warning("response %s: '%s'", response.status_code, response.text)
        else:
            # Routine 2xx broadcasts — DEBUG so the steady-state push
            # stream doesn't drown INFO. Errors above stay at WARNING.
            logging.debug("response status: %s", response.status_code)
            logging.debug("response message: '%s'", response.text)
        return response

    def update_local_overlay(self, current_model, force_visibility=None,
                             customization_state=None, show_only_current_set=None):
        try:
            payload = self._build_overlay_payload(
                current_model,
                force_visibility=force_visibility,
                customization_state=customization_state,
                show_only_current_set=show_only_current_set,
            )
            self._overlay.send_overlay_state(payload)
        except Exception:
            Backend.logger.exception("Error updating local overlay")

