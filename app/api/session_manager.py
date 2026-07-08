import asyncio
import logging
import threading
import time

from app.api import action_log
from app.api.match_rules import is_valid_mode
from app.api.session_persistence import (
    load_session_meta,
    save_session_meta,
)
from app.backend import Backend
from app.conf import Conf
from app.constants import SESSION_TTL_SECONDS  # re-exported
from app.customization import Customization
from app.game_manager import GameManager
from app.metrics import set_active_sessions

logger = logging.getLogger(__name__)


class GameSession:
    """Holds all state for one overlay/match session."""

    def __init__(self, oid, conf, backend,
                 points_limit=None, points_limit_last_set=None, sets_limit=None):
        # ``oid`` here is the *storage key* (``<user_id>:<oid>`` for a
        # logged-in user, or a bare id in standalone/legacy/test paths). It
        # is what every per-overlay persistence surface keys on — overlay
        # state, audit log, session meta, match archive, the SessionManager
        # registry, and the control WS hub — so two users with the same raw
        # oid stay isolated. ``raw_oid`` keeps the un-namespaced id for the
        # Backend (cloud/local resolution, uno API, control links).
        self.oid = oid
        self.skey = oid
        self.raw_oid = getattr(conf, "oid", None) or oid
        self.user_id = getattr(conf, "user_id", None)
        self.public_token = getattr(conf, "public_token", None)
        self.conf = conf
        self.backend = backend
        self.game_manager = GameManager(conf, backend)
        # Expose the session's current rules to the Backend's overlay
        # payload builder so the OBS broadcast (and the spectator page
        # that consumes it) sees the live mode + per-set limits, not
        # the env-default ``conf`` values. We go through the explicit
        # setter on Backend (rather than monkey-patching) so the
        # dependency is part of Backend's public surface.
        backend.set_rule_overrides_getter(self._build_rule_overrides)
        self.customization = Customization(
            backend.get_current_customization())
        self.visible = backend.is_visible()
        self.simple = False
        # Set summary overlay (off by default — feature is hidden in the
        # control UI unless the operator opts in via setSummaryEnabled).
        self.set_summary: bool = False
        self.set_summary_style: str = getattr(
            conf, "set_summary_default_style", "brand_ledger"
        )
        # Display-side swap (team 2 rendered on the left). Presentation
        # only — team identity in the audit log / API never changes.
        # ``sides_swapped_manual`` is the operator's base orientation;
        # when ``auto_swap_sides`` is on, the effective orientation is
        # ``manual XOR compute_sides_swapped_auto(...)`` so the manual
        # button stays usable as a correction. Both persisted.
        self.sides_swapped_manual: bool = False
        self.auto_swap_sides: bool = False
        self.current_set = 1
        self.undo = False
        # Wall-clock seconds at which the current match started, or
        # ``None`` when the match hasn't begun yet. The first
        # ``add_point`` auto-arms it (``GameService.add_point``); the
        # explicit ``POST /game/start_match`` lets the operator arm it
        # before the first point so the timer in the HUD reflects the
        # actual whistle. ``GameService.reset`` clears it back to
        # ``None``. Persisted via session_meta so it survives restarts.
        self.match_started_at: float | None = None
        # Wall-clock seconds at which the match transitioned from
        # in-progress to finished (the set-winning add_point/add_set
        # that closes the match), or ``None`` while the match is still
        # in progress. Used by the HUD timer and the spectator page to
        # freeze the elapsed counters at the actual end-of-match value
        # instead of letting them keep ticking after match end.
        # ``GameService.reset`` and ``GameService.start_match`` clear
        # it back to ``None``. Persisted via session_meta.
        self.match_finished_at: float | None = None
        # ``match_id`` of the report archived when this session's match
        # last finished (set by ``game_audit_hooks.archive_if_finished``).
        # Surfaced in ``GameStateResponse.last_match_id`` only while the
        # match is finished, so the control board can link straight to the
        # report. In-memory only — falls back to a DB lookup after a restart.
        self.last_match_id: str | None = None
        # Match-rule preset (``'indoor'`` or ``'beach'``). Persisted in
        # session_meta. Drives the beach side-switch indicator and the
        # "reset to defaults" affordance in the new MatchRulesSection.
        self.mode: str = "indoor"
        # Team (1 or 2) that serves first in game 1 of a table-tennis
        # match. The live server is derived from this, the score and the
        # game index (see ``match_rules.table_tennis_server``); it
        # alternates each game. Unused by volleyball modes (serve there
        # follows the rally winner). Persisted in session_meta.
        self.first_server: int = 1
        # The team group selected in the board's team picker (None = the "All"
        # group). Per-overlay; persisted in session_meta. Does not affect the
        # rendered overlay — only which teams the control selectors offer.
        self.selected_team_group_id: int | None = None
        # Cached count of undoable forward records in the audit log.
        # Updated by GameService._audit on every undoable mutation so
        # ``get_state`` can answer ``can_undo`` in O(1) without re-reading
        # the log. Rehydrated from disk here so a restart picks up
        # whatever forwards survived from a previous process.
        self.undoable_forward_count: int = action_log.count_undoable_forwards(oid)
        # Per-team trace of the most recent ``add_point`` action so the
        # rapid-pair flow can collapse a tap+double-tap (or vice-versa)
        # within ``RAPID_PAIR_WINDOW_S`` into a no-op. Each entry is
        # ``{kind, ts, audit_ts, popped_ref_ts}`` where
        # ``audit_ts`` is the timestamp of the audit record we wrote
        # for the action and ``popped_ref_ts`` is the ``ts`` of the
        # forward record we tombstoned (only set on undos). Cleared on
        # any non-add_point mutation (reset, add_set, add_timeout,
        # set_score, change_serve, set_sets_value) so a stale cache
        # can't trigger a false-positive recovery after the operator
        # moved on.
        self.rapid_pair_cache: dict[int, dict] = {}
        self.points_limit = points_limit if points_limit is not None else conf.points
        self.points_limit_last_set = (
            points_limit_last_set if points_limit_last_set is not None
            else conf.points_last_set
        )
        self.sets_limit = (
            sets_limit if sets_limit is not None else conf.sets
        )
        # Compute initial current set
        self.current_set = self._compute_current_set()
        # Async lock for protecting concurrent mutations
        self.lock = asyncio.Lock()
        # Coalesces concurrent customization refresh fetches so a burst
        # of UI requests collapses into a single overlay-server round-trip.
        self.customization_fetch_lock = threading.Lock()
        # Last access time for TTL-based cleanup
        self.last_accessed = time.monotonic()
        logger.debug(
            "GameSession created for OID=%s (pts=%s, last=%s, sets=%s)",
            oid, self.points_limit, self.points_limit_last_set,
            self.sets_limit)

    def _compute_current_set(self):
        state = self.game_manager.get_current_state()
        t1sets = state.get_sets(1)
        t2sets = state.get_sets(2)
        current = t1sets + t2sets
        if not self.game_manager.match_finished(self.sets_limit):
            current += 1
        return max(1, min(current, self.sets_limit))

    def _build_rule_overrides(self) -> dict:
        """Snapshot of the session's rule fields for the backend payload."""
        return {
            "mode": self.mode,
            "points_limit": self.points_limit,
            "points_limit_last_set": self.points_limit_last_set,
            "sets_limit": self.sets_limit,
            "match_finished": self.game_manager.match_finished(self.sets_limit),
            "match_started_at": (
                float(self.match_started_at)
                if self.match_started_at is not None else None
            ),
            "match_finished_at": (
                float(self.match_finished_at)
                if self.match_finished_at is not None else None
            ),
            "set_summary": bool(self.set_summary),
            "set_summary_style": str(self.set_summary_style),
            "sides_swapped_manual": bool(self.sides_swapped_manual),
            "auto_swap_sides": bool(self.auto_swap_sides),
        }

    def touch(self):
        """Update last access time."""
        self.last_accessed = time.monotonic()

    def to_meta_dict(self) -> dict:
        """Return the session-level fields that should survive restart.

        Match-state fields (scores, sets, current_set, serve, timeouts)
        are persisted via the overlay backend (raw_remote_model in the
        local store, the cloud for uno overlays) and are not included
        here.
        """
        return {
            "simple": bool(self.simple),
            "set_summary": bool(self.set_summary),
            "set_summary_style": str(self.set_summary_style),
            "sides_swapped_manual": bool(self.sides_swapped_manual),
            "auto_swap_sides": bool(self.auto_swap_sides),
            "points_limit": int(self.points_limit),
            "points_limit_last_set": int(self.points_limit_last_set),
            "sets_limit": int(self.sets_limit),
            "match_started_at": (
                float(self.match_started_at)
                if self.match_started_at is not None else None
            ),
            "match_finished_at": (
                float(self.match_finished_at)
                if self.match_finished_at is not None else None
            ),
            "mode": str(self.mode),
            "first_server": int(self.first_server),
            "selected_team_group_id": (
                int(self.selected_team_group_id)
                if self.selected_team_group_id is not None else None
            ),
        }

    def apply_meta(self, meta: dict) -> None:
        """Restore session-level fields from a previously persisted dict.

        Silently ignores missing or malformed keys so a stale meta file
        cannot break session creation.
        """
        if not isinstance(meta, dict):
            return
        if "simple" in meta:
            self.simple = bool(meta["simple"])
        if "set_summary" in meta:
            self.set_summary = bool(meta["set_summary"])
        if "set_summary_style" in meta:
            from app.api.schemas import SET_SUMMARY_STYLE_CHOICES
            candidate = meta["set_summary_style"]
            if isinstance(candidate, str) and candidate in SET_SUMMARY_STYLE_CHOICES:
                self.set_summary_style = candidate
        if "sides_swapped_manual" in meta:
            self.sides_swapped_manual = bool(meta["sides_swapped_manual"])
        if "auto_swap_sides" in meta:
            self.auto_swap_sides = bool(meta["auto_swap_sides"])
        for key in ("points_limit", "points_limit_last_set", "sets_limit"):
            value = meta.get(key)
            if value is None:
                continue
            try:
                setattr(self, key, int(value))
            except (TypeError, ValueError):
                logger.warning(
                    "Ignoring invalid %s=%r in persisted meta for OID=%s",
                    key, value, self.oid,
                )
        self._restore_optional_float(meta, "match_started_at")
        self._restore_optional_float(meta, "match_finished_at")
        if "mode" in meta and is_valid_mode(meta["mode"]):
            self.mode = meta["mode"]
        if meta.get("first_server") in (1, 2):
            self.first_server = int(meta["first_server"])
        if "selected_team_group_id" in meta:
            raw = meta["selected_team_group_id"]
            if raw is None:
                self.selected_team_group_id = None
            else:
                try:
                    self.selected_team_group_id = int(raw)
                except (TypeError, ValueError):
                    pass

    def _restore_optional_float(self, meta: dict, key: str) -> None:
        """Restore an optional ``float | None`` attribute from *meta*.

        Missing key → left untouched. Explicit ``None`` → cleared.
        Malformed value → ignored (keeps the constructor default).
        """
        if key not in meta:
            return
        raw = meta[key]
        if raw is None:
            setattr(self, key, None)
            return
        try:
            setattr(self, key, float(raw))
        except (TypeError, ValueError):
            pass

    def persist_meta(self) -> None:
        """Best-effort save of :meth:`to_meta_dict` to disk."""
        save_session_meta(self.oid, self.to_meta_dict())

    def shutdown(self):
        """Clean up background resources to prevent leaks."""
        if hasattr(self.backend, 'shutdown'):
            self.backend.shutdown()



class SessionManager:
    """Thread-safe singleton managing GameSession instances by OID."""

    _sessions: dict = {}
    _lock = threading.Lock()

    @classmethod
    def get_or_create(cls, oid, conf=None, backend=None,
                      points_limit=None, points_limit_last_set=None,
                      sets_limit=None):
        """Get an existing session or create a new one.

        If *conf* or *backend* are ``None`` and the session doesn't exist yet,
        sensible defaults are constructed from environment variables.

        Backend and GameSession construction happen inside the global lock
        only after a session-exists re-check: two racing callers on the
        same OID cannot both allocate a ``Backend`` (``ThreadPoolExecutor``
        + ``requests.Session``). Lock contention is bounded because the
        fast path (existing session) never enters the construction block.
        """
        def _apply_limits(session):
            changed = False
            if points_limit is not None and session.points_limit != points_limit:
                session.points_limit = points_limit
                changed = True
            if (points_limit_last_set is not None
                    and session.points_limit_last_set != points_limit_last_set):
                session.points_limit_last_set = points_limit_last_set
                changed = True
            if sets_limit is not None and session.sets_limit != sets_limit:
                session.sets_limit = sets_limit
                changed = True
            if changed:
                session.persist_meta()

        with cls._lock:
            session = cls._sessions.get(oid)
            if session is not None:
                session.touch()
                _apply_limits(session)
                return session

            if conf is None:
                conf = Conf()
                conf.oid = oid
            if backend is None:
                backend = Backend(conf)
            new_session = GameSession(
                oid, conf, backend,
                points_limit=points_limit,
                points_limit_last_set=points_limit_last_set,
                sets_limit=sets_limit,
            )
            # Restore persisted session metadata before any explicit
            # caller overrides take effect — the kwargs above already
            # won at construction time, so apply_meta only fills in
            # fields the caller did not specify.
            persisted = load_session_meta(oid)
            if persisted is not None:
                fields_to_restore = {
                    k: v for k, v in persisted.items()
                    if not (k == "points_limit" and points_limit is not None)
                    and not (k == "points_limit_last_set" and points_limit_last_set is not None)
                    and not (k == "sets_limit" and sets_limit is not None)
                }
                new_session.apply_meta(fields_to_restore)
                # current_set is derived from the (already-restored)
                # match state and the freshly-restored sets_limit.
                new_session.current_set = new_session._compute_current_set()
            # Persist the resulting meta so a future restart can
            # rehydrate without requiring any mutation in between.
            new_session.persist_meta()
            cls._sessions[oid] = new_session
            set_active_sessions(len(cls._sessions))
            return new_session

    @classmethod
    def get(cls, oid):
        """Return an existing session or ``None``."""
        with cls._lock:
            session = cls._sessions.get(oid)
            if session is not None:
                session.touch()
            return session

    @classmethod
    def peek(cls, oid):
        """Return an existing session without bumping ``last_accessed``.

        Used by inspect-only paths (admin usage endpoint) that need to
        report liveness without resetting the eviction TTL.
        """
        with cls._lock:
            return cls._sessions.get(oid)

    @classmethod
    def remove(cls, oid):
        """Remove a session (e.g. on disconnect)."""
        with cls._lock:
            session = cls._sessions.pop(oid, None)
            if session:
                session.shutdown()
            set_active_sessions(len(cls._sessions))

    @classmethod
    def clear(cls):
        """Remove all sessions (mainly for testing)."""
        with cls._lock:
            for session in cls._sessions.values():
                session.shutdown()
            cls._sessions.clear()
            set_active_sessions(0)

    @classmethod
    def cleanup_expired(cls):
        """Remove sessions that have not been accessed within the TTL."""
        now = time.monotonic()
        with cls._lock:
            expired = [
                oid for oid, session in cls._sessions.items()
                if (now - session.last_accessed) > SESSION_TTL_SECONDS
            ]
            for oid in expired:
                session = cls._sessions.pop(oid)
                session.shutdown()
                logger.info("Expired session for OID=%s", oid)
            if expired:
                set_active_sessions(len(cls._sessions))
        return len(expired)
