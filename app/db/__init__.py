"""Database layer for the multi-user application.

Exposes the SQLAlchemy declarative ``Base``, the engine/session factory
(configured from ``DATABASE_URL``), and the ``run_migrations`` entrypoint
that Alembic-upgrades the schema on startup. Models live under
``app.db.models`` and are imported here so ``Base.metadata`` is fully
populated for both ``create_all`` (tests) and Alembic autogenerate.
"""

from __future__ import annotations

from app.db import models  # noqa: F401  (populate Base.metadata)
from app.db.base import Base
from app.db.engine import (
    configure_engine,
    database_url,
    get_db,
    get_engine,
    get_sessionmaker,
    session_scope,
)

__all__ = [
    "Base",
    "configure_engine",
    "database_url",
    "get_db",
    "get_engine",
    "get_sessionmaker",
    "session_scope",
]
