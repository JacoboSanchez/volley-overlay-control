"""Router lifespan: background session cleanup and per-OID init locks."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from weakref import WeakValueDictionary

from fastapi import FastAPI

from app.api.session_manager import SessionManager
from app.api.webhooks import webhook_dispatcher
from app.api.ws_hub import WSHub
from app.constants import AUTH_SESSION_SWEEP_INTERVAL_SECONDS
from app.overlay_executor import shutdown_overlay_executor

logger = logging.getLogger(__name__)

# How often the in-memory ``GameSession`` eviction runs. The DB-backed
# ``auth_sessions`` sweep rides the same loop but on its own (longer) period,
# so the two knobs stay independent.
_GAME_SESSION_CLEANUP_INTERVAL_SECONDS = 3600

_cleanup_task: asyncio.Task[None] | None = None
_auth_sweep_task: asyncio.Task[None] | None = None
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


async def _session_cleanup_loop() -> None:
    """Periodically remove expired in-memory game sessions."""
    while True:
        await asyncio.sleep(_GAME_SESSION_CLEANUP_INTERVAL_SECONDS)
        try:
            removed = SessionManager.cleanup_expired()
            if removed:
                logger.info("Session cleanup removed %d expired sessions", removed)
        except Exception:
            logger.exception("Error during session cleanup")


def purge_expired_auth_sessions() -> int:
    """Delete expired ``auth_sessions`` rows. Returns the number removed.

    Runs in a worker thread (``to_thread`` below) because the DB driver is
    synchronous and the event loop must not block on it.
    """
    from app.auth import sessions as auth_sessions
    from app.db.engine import session_scope

    with session_scope() as db:
        return auth_sessions.purge_expired(db)


async def _auth_session_sweep_loop() -> None:
    """Periodically purge expired login sessions from the database.

    ``resolve_session`` only drops an expired row when its own token is
    presented again, so without this loop a row survives forever once the
    client stops presenting the cookie.

    The first sweep runs immediately, *before* the first sleep. Sleeping first
    would mean an instance redeployed more often than
    ``AUTH_SESSION_SWEEP_INTERVAL_SECONDS`` (6 h by default — shorter than many
    deploy cadences) is always cancelled before it ever purges, so the table
    would grow unbounded on exactly the deployments that restart most. The
    purge runs in a worker thread and the task is created after startup, so it
    never delays the app coming up.
    """
    while True:
        try:
            removed = await asyncio.to_thread(purge_expired_auth_sessions)
            if removed:
                logger.info("Purged %d expired login sessions", removed)
        except Exception:
            logger.exception("Error during expired login-session sweep")
        await asyncio.sleep(AUTH_SESSION_SWEEP_INTERVAL_SECONDS)


@asynccontextmanager
async def router_lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _cleanup_task, _auth_sweep_task
    _cleanup_task = asyncio.create_task(_session_cleanup_loop())
    # 0 disables the sweep entirely (operators running an external janitor).
    if AUTH_SESSION_SWEEP_INTERVAL_SECONDS > 0:
        _auth_sweep_task = asyncio.create_task(_auth_session_sweep_loop())
    # No-op when WSHUB_HEARTBEAT_INTERVAL_SECONDS == 0 (the default).
    WSHub.start_heartbeat()
    yield
    if _cleanup_task:
        _cleanup_task.cancel()
    if _auth_sweep_task:
        _auth_sweep_task.cancel()
        _auth_sweep_task = None
    WSHub.stop_heartbeat()
    SessionManager.clear()
    # Backends share one bounded pool. Individual session eviction must not
    # stop workers used by another overlay, so drain it exactly once here.
    shutdown_overlay_executor()
    # Drain in-flight deliveries with cancel_futures=True so a hung
    # outbound webhook can't keep the process alive past shutdown.
    webhook_dispatcher.shutdown()
