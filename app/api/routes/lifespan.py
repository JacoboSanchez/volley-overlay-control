"""Router lifespan: background session cleanup and per-OID init locks."""

import asyncio
import logging
from contextlib import asynccontextmanager

from app.api.session_manager import SessionManager

logger = logging.getLogger("APIRoutes")

_cleanup_task: asyncio.Task | None = None
_init_locks: dict[str, asyncio.Lock] = {}


def get_init_lock(oid: str) -> asyncio.Lock:
    if oid not in _init_locks:
        _init_locks[oid] = asyncio.Lock()
    return _init_locks[oid]


async def _session_cleanup_loop():
    """Periodically remove expired sessions."""
    while True:
        await asyncio.sleep(3600)  # Run every hour
        try:
            removed = SessionManager.cleanup_expired()
            if removed:
                logger.info("Session cleanup removed %d expired sessions", removed)

            # Clean up un-needed locks to prevent memory leaks
            to_remove = [oid for oid, lock in _init_locks.items() if not lock.locked()]
            for oid in to_remove:
                del _init_locks[oid]
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
