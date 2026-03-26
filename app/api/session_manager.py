import asyncio
import logging
import threading
import time
from app.conf import Conf
from app.backend import Backend
from app.game_manager import GameManager
from app.customization import Customization

logger = logging.getLogger("SessionManager")

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
        """
        with cls._lock:
            if oid in cls._sessions:
                session = cls._sessions[oid]
                session.touch()
                # Update limits if explicitly provided
                if points_limit is not None:
                    session.points_limit = points_limit
                if points_limit_last_set is not None:
                    session.points_limit_last_set = points_limit_last_set
                if sets_limit is not None:
                    session.sets_limit = sets_limit
                return session

            if conf is None:
                conf = Conf()
                conf.oid = oid
            if backend is None:
                backend = Backend(conf)

            session = GameSession(
                oid, conf, backend,
                points_limit=points_limit,
                points_limit_last_set=points_limit_last_set,
                sets_limit=sets_limit,
            )
            cls._sessions[oid] = session
            return session

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
            cls._sessions.pop(oid, None)

    @classmethod
    def clear(cls):
        """Remove all sessions (mainly for testing)."""
        with cls._lock:
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
                del cls._sessions[oid]
                logger.info("Expired session for OID=%s", oid)
        return len(expired)
