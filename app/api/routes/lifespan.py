"""Router lifespan: background session cleanup and per-OID init locks."""

import asyncio
import logging
from contextlib import asynccontextmanager
from weakref import WeakValueDictionary

from app.api.session_manager import SessionManager

logger = logging.getLogger("APIRoutes")

_cleanup_task: asyncio.Task | None = None
# WeakValueDictionary auto-evicts entries once all strong refs to the lock are
# released — i.e. once every caller has exited its ``async with get_init_lock``
# block. This avoids a race where a manual cleanup could delete a lock between
# the time one request retrieved it and the time it acquired it, causing
# concurrent init_session calls for the same OID to serialize against
# different locks.
_init_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def get_init_lock(oid: str) -> asyncio.Lock:
    lock = _init_locks.get(oid)
    if lock is None:
        lock = asyncio.Lock()
        _init_locks[oid] = lock
    return lock


async def _session_cleanup_loop():
    """Periodically remove expired sessions."""
    while True:
        await asyncio.sleep(3600)  # Run every hour
        try:
            removed = SessionManager.cleanup_expired()
            if removed:
                logger.info("Session cleanup removed %d expired sessions", removed)
        except Exception:
            logger.exception("Error during session cleanup")


@asynccontextmanager
async def router_lifespan(app):
    global _cleanup_task
    _cleanup_task = asyncio.create_task(_session_cleanup_loop())
    yield
    if _cleanup_task:
        _cleanup_task.cancel()
    SessionManager.clear()
