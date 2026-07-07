"""Declarative base + shared column mixins.

A deterministic naming convention is attached to the metadata so Alembic
emits stable, named constraints — essential for SQLite ``batch`` migrations
(which recreate tables and need the constraint names to round-trip).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

# Stable constraint names for Alembic (batch mode on SQLite relies on these).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TZDateTime(TypeDecorator[datetime]):
    """A ``DateTime(timezone=True)`` that always round-trips UTC-aware values.

    SQLite has no timezone-aware column type: it stores the naive text and
    hands back naive datetimes, so any comparison against an aware
    ``datetime.now(UTC)`` raises ``TypeError``. Normalize both directions —
    aware values are converted to UTC on the way in (naive ones are assumed
    UTC), and naive values gain ``tzinfo=UTC`` on the way out. Postgres
    columns are unaffected (already aware).
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class TimestampMixin:
    """``created_at`` / ``updated_at`` columns, DB-populated on both backends."""

    created_at: Mapped[datetime] = mapped_column(
        TZDateTime(), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
