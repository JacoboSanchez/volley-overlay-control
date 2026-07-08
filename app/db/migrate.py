"""Programmatic Alembic upgrade — the schema-on-startup hook.

``run_migrations()`` runs ``alembic upgrade head`` in-process during
``create_app`` so a fresh or out-of-date database is brought to the current
schema before anything reads it. The Docker entrypoint also runs
``alembic upgrade head`` as a belt-and-suspenders; both are idempotent.

A cross-process file lock guards against several Uvicorn workers racing the
same upgrade on first boot.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.api._persistence_paths import data_dir
from app.db.engine import database_url

logger = logging.getLogger(__name__)

_ALEMBIC_INI = Path(__file__).resolve().parent.parent.parent / "alembic.ini"


def _alembic_config() -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    # env.py resolves DATABASE_URL itself, but set it here too so a Config
    # built outside the app context is consistent.
    cfg.set_main_option("sqlalchemy.url", database_url())
    return cfg


@contextmanager
def _migration_lock():
    """Best-effort cross-process lock so concurrent workers don't double-migrate.

    Uses an ``flock`` on a file in the data dir. If locking is unavailable
    (non-POSIX, odd filesystems) we proceed unlocked — Alembic's own
    transactional DDL still makes a duplicate run safe, the lock just avoids
    noisy "table already exists" races in the logs.
    """
    lock_path = Path(data_dir(".migrate.lock"))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    locked = False
    try:
        try:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
            locked = True
        except (ImportError, OSError):
            logger.debug("Migration file lock unavailable; proceeding unlocked")
        yield
    finally:
        if locked:
            try:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass
        os.close(fd)


def run_migrations() -> None:
    """Upgrade the database to ``head``. Safe to call repeatedly."""
    with _migration_lock():
        cfg = _alembic_config()
        logger.info("Running database migrations (alembic upgrade head)")
        command.upgrade(cfg, "head")
