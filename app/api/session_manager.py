import asyncio
import logging
import threading
import time

from app.api.session_persistence import (
    delete_session_meta,
    load_session_meta,
    save_session_meta,
)
from app.backend import Backend
from app.conf import Conf
from app.customization import Customization
from app.game_manager import GameManager

logger = logging.getLogger(__name__)

# Sessions expire after 24 hours of inactivity
SESSION_TTL_SECONDS = 24 * 60 * 60


class GameSession:
    """Holds all state for one overlay/match session."""

    def __init__(self, oid, conf, backend,
                 points_limit=None, points_limit_last_set=None, sets_limit=None):
        self.oid = oid
        self.conf = conf
        self.backend = backend
        self.game_manager = GameManager(conf, backend)
        self.customization = Customization(
            backend.get_current_customization())
        self.visible = backend.is_visible()
        self.simple = False
        self.current_set = 1
        self.undo = False
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
        # Last access time for TTL-based cleanup
        self.last_accessed = time.monotonic()
        logger.info(
            "GameSession created for OID=%s (pts=%s, last=%s, sets=%s)",
            oid, self.points_limit, self.points_limit_last_set,
            self.sets_limit)

    def _compute_current_set(self):
        state = self.game_manager.get_current_state()
        t1sets = state.get_sets(1)
        t2sets = state.get_sets(2)
        current = t1sets + t2sets
        if not self.game_manager.match_finished():
            current += 1
        return max(1, min(current, self.sets_limit))

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
            "points_limit": int(self.points_limit),
            "points_limit_last_set": int(self.points_limit_last_set),
            "sets_limit": int(self.sets_limit),
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
    def remove(cls, oid):
        """Remove a session (e.g. on disconnect)."""
        with cls._lock:
            session = cls._sessions.pop(oid, None)
            if session:
                session.shutdown()

    @classmethod
    def clear(cls):
        """Remove all sessions (mainly for testing)."""
        with cls._lock:
            for session in cls._sessions.values():
                session.shutdown()
            cls._sessions.clear()

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
        return len(expired)
