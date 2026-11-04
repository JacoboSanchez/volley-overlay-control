"""Runtime-state database: live overlay state, session flags and audit log.

These three stores used to be per-overlay files under ``data/``
(``overlay_state_<hash>.json``, ``session_meta_<hash>.json`` and
``audit_<hash>.jsonl`` plus its rotations). They now live in three tables
owned by this module, keyed by the storage key (``skey``) exactly as the
files were.

Why a separate engine, not the request ``Session``
--------------------------------------------------
Runtime writes happen on the scoring hot path, often from the overlay
executor's worker threads and always outside any request transaction. They
are also issued *during* requests that hold an uncommitted write: board
init with the owner cookie flushes a freshly auto-created ``user_overlays``
row and then persists the new overlay's state before ``get_db`` commits.
On SQLite a database-wide write lock is held from that flush until commit,
so a second connection writing to the same file would block on its own
request thread until ``busy_timeout`` and fail.

The runtime engine therefore targets:

* the main database when it is a server database (PostgreSQL) — row-level
  locking means independent rows never wait on each other, and the whole
  deployment backs up with one ``pg_dump`` (plus ``data/media``);
* a sibling SQLite file (``runtime.db`` next to ``app.db``) when the main
  database is SQLite, in WAL mode, so the request transaction and runtime
  writes never contend for one lock.

Schema management
-----------------
The runtime tables are deliberately **not** part of the Alembic history:
on SQLite they live in a different file Alembic never sees. They have their
own :data:`RuntimeBase` metadata, are created idempotently by
:func:`init_runtime_schema`, and carry a version row in ``runtime_schema``.
A future change to these tables bumps :data:`RUNTIME_SCHEMA_VERSION` and adds
an explicit upgrade step there. ``migrations/env.py`` skips ``runtime_*``
tables so autogenerate against a PostgreSQL database never proposes dropping
them.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.db.base import NAMING_CONVENTION

logger = logging.getLogger(__name__)

#: Bump together with an upgrade step in :func:`init_runtime_schema`.
RUNTIME_SCHEMA_VERSION = 1

#: Storage keys are ``<user_id>:<oid>`` (oid ≤ 64 chars) or a bare legacy
#: overlay id (≤ 200 chars); 255 covers both with room to spare.
STORE_KEY_LENGTH = 255

RUNTIME_TABLE_PREFIX = "runtime_"


class RuntimeBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class RuntimeSchema(RuntimeBase):
    """Single-row table recording the runtime schema version."""

    __tablename__ = "runtime_schema"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class OverlayRuntimeState(RuntimeBase):
    """Merged overlay render state (what OBS browser sources receive)."""

    __tablename__ = "runtime_overlay_state"

    store_key: Mapped[str] = mapped_column(String(STORE_KEY_LENGTH), primary_key=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)


class RuntimeSessionMeta(RuntimeBase):
    """Session-level flags (rules, simple mode, …) that survive restarts."""

    __tablename__ = "runtime_session_meta"

    store_key: Mapped[str] = mapped_column(String(STORE_KEY_LENGTH), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)


class AuditEvent(RuntimeBase):
    """One record of the append-only per-overlay action audit log.

    ``id`` is the append order (the files' line order). ``record`` is the
    full record exactly as it was written to a JSONL line, ``ts`` included,
    so tombstones keep matching their targets by ``ts``. ``ts`` is also a
    column for range queries; ``size`` is the record's serialized length,
    used to enforce the ``AUDIT_LOG_MAX_BYTES`` retention cap.
    """

    __tablename__ = "runtime_audit_events"
    __table_args__ = (Index("ix_runtime_audit_events_key_id", "store_key", "id"),)

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    store_key: Mapped[str] = mapped_column(String(STORE_KEY_LENGTH), nullable=False)
    ts: Mapped[float] = mapped_column(Float, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    record: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def runtime_database_url(main_url: str | None = None) -> str:
    """Return the runtime database URL derived from the main one.

    A file-backed SQLite main database maps to ``runtime.db`` in the same
    directory; an in-memory SQLite URL stays in memory; anything else
    (PostgreSQL) is shared as-is.
    """
    if main_url is None:
        from app.db.engine import database_url

        main_url = database_url()
    url = make_url(main_url)
    if url.get_backend_name() != "sqlite":
        return main_url
    database = url.database or ""
    if database in ("", ":memory:") or database.startswith("file:"):
        return main_url
    import os

    runtime_path = os.path.join(os.path.dirname(database) or ".", "runtime.db")
    return url.set(database=runtime_path).render_as_string(hide_password=False)


def _configure_sqlite(engine: Engine) -> None:
    """WAL + a busy timeout so concurrent runtime writers queue, not fail."""

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn: Any, _record: Any) -> None:
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()


def configure_runtime_engine(
    url: str | None = None,
    *,
    engine: Engine | None = None,
) -> Engine:
    """(Re)create the runtime engine + session factory.

    Tests pass ``engine`` to bind an in-memory engine; production derives the
    URL from the main database via :func:`runtime_database_url`.
    """
    global _engine, _SessionLocal
    if engine is None:
        resolved = url or runtime_database_url()
        backend = make_url(resolved).get_backend_name()
        if backend == "sqlite":
            engine = create_engine(
                resolved,
                future=True,
                connect_args={"check_same_thread": False},
            )
            database = make_url(resolved).database or ""
            if database not in ("", ":memory:"):
                _configure_sqlite(engine)
        else:
            engine = create_engine(resolved, future=True, pool_pre_ping=True)
    _engine = engine
    _SessionLocal = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, future=True,
    )
    return engine


def get_runtime_engine() -> Engine:
    if _engine is None:
        configure_runtime_engine()
    assert _engine is not None
    return _engine


@contextmanager
def runtime_session() -> Iterator[Session]:
    """Short-lived session that commits on success and rolls back on error."""
    if _SessionLocal is None:
        configure_runtime_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def init_runtime_schema(engine: Engine | None = None) -> None:
    """Create the runtime tables if missing and stamp the schema version."""
    engine = engine or get_runtime_engine()
    RuntimeBase.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        row = session.get(RuntimeSchema, 1)
        if row is None:
            session.add(RuntimeSchema(id=1, version=RUNTIME_SCHEMA_VERSION))
        elif row.version > RUNTIME_SCHEMA_VERSION:
            logger.warning(
                "Runtime schema version %s is newer than this release (%s); "
                "continuing, but a downgrade may misread runtime state",
                row.version,
                RUNTIME_SCHEMA_VERSION,
            )
        # Future upgrade steps: ``elif row.version < N: ...; row.version = N``.


def is_runtime_table(name: str | None) -> bool:
    """True for tables owned by this module (used by ``migrations/env.py``)."""
    return bool(name) and str(name).startswith(RUNTIME_TABLE_PREFIX)
