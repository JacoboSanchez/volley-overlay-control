"""Engine + session factory, configured from ``DATABASE_URL``.

Defaults to a SQLite file under the app's ``data/`` directory (the same
directory every other persistence module anchors to) so a plain
``docker compose up`` works with no configuration. Postgres is supported
by setting ``DATABASE_URL=postgresql+psycopg://...`` — no code change.

The engine and ``sessionmaker`` are process-global singletons created
lazily on first use. ``configure_engine`` lets tests swap in an in-memory
SQLite engine (``StaticPool``) before the app touches the DB.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def database_url() -> str:
    """Resolve the configured database URL.

    Order: ``DATABASE_URL`` env var, else a SQLite file at
    ``<data_dir>/app.db``. ``data_dir`` already creates an absolute,
    normalized path anchored at the repo root.
    """
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if url:
        return url
    # Lazy import: keeps app.db.engine free of the app.api package at module
    # load time, which would otherwise create an import cycle
    # (api -> auth.dependencies -> db.engine).
    from app.api._persistence_paths import data_dir

    return f"sqlite:///{data_dir('app.db')}"


def _engine_kwargs(url: str) -> dict[str, Any]:
    """Per-backend engine kwargs.

    SQLite needs ``check_same_thread=False`` because the app touches the
    DB from request handlers and background threads; Postgres benefits
    from ``pool_pre_ping`` to recycle dropped connections.
    """
    backend = make_url(url).get_backend_name()
    if backend == "sqlite":
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


def configure_engine(
    url: str | None = None,
    *,
    engine: Engine | None = None,
    **engine_kwargs: Any,
) -> Engine:
    """(Re)create the global engine + session factory.

    Pass ``engine`` to bind a caller-built engine directly (tests use this
    to inject an in-memory ``StaticPool`` engine). Otherwise an engine is
    built from ``url`` (defaulting to :func:`database_url`).
    """
    global _engine, _SessionLocal
    if engine is None:
        resolved = url or database_url()
        kwargs = {**_engine_kwargs(resolved), **engine_kwargs}
        engine = create_engine(resolved, future=True, **kwargs)
    if engine.dialect.name == "sqlite":
        _enable_sqlite_fk(engine)
    _engine = engine
    _SessionLocal = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, future=True,
    )
    return engine


def _enable_sqlite_fk(engine: Engine) -> None:
    """Turn on ``PRAGMA foreign_keys`` for every SQLite connection.

    SQLite ships with FK enforcement OFF; without this the ``ON DELETE
    CASCADE`` rules (user-account deletion wiping overlays/teams/presets/
    reports/sessions) silently no-op. Registered once per engine.
    """

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_engine() -> Engine:
    """Return the global engine, creating it on first use."""
    if _engine is None:
        configure_engine()
    assert _engine is not None  # configure_engine sets it
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    """Return the global ``sessionmaker``, creating the engine if needed."""
    if _SessionLocal is None:
        configure_engine()
    assert _SessionLocal is not None
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session for non-request code (bootstrap, importer, jobs).

    Commits on clean exit, rolls back on exception, always closes.
    """
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session.

    Commit/rollback is the handler's responsibility for writes; the
    session is always closed when the request ends.
    """
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
