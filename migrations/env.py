"""Alembic environment.

Resolves the database URL from ``DATABASE_URL`` (defaulting to the SQLite
file under ``data/``) the same way the running app does, and points
autogenerate at ``app.db.Base.metadata``. ``render_as_batch=True`` so SQLite
— which can't ``ALTER`` most things — gets table-recreate migrations.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.db import Base
from app.db.engine import _enable_sqlite_fk, database_url

config = context.config

if config.config_file_name is not None:
    # ``disable_existing_loggers=False`` is essential: ``run_migrations()``
    # runs this env at app startup, and the default (True) would tear down
    # every logger the app already configured (and break caplog in tests).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Inject the resolved URL so both offline and online modes use it.
config.set_main_option("sqlalchemy.url", database_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _ensure_wide_version_table(connection) -> None:
    """Provision ``alembic_version`` with a column wide enough for this
    project's long, human-readable revision ids.

    Alembic defaults ``version_num`` to ``VARCHAR(32)``. SQLite ignores the
    declared length, but Postgres enforces it, so a revision id like
    ``0008_overlay_display_name_to_description`` (40 chars) overflows the
    ``UPDATE alembic_version`` and aborts the upgrade on Postgres. Pre-create
    the table wide when absent, and widen an already-narrow column on enforcing
    backends; both are idempotent, so existing SQLite/Postgres DBs are
    unaffected.
    """
    connection.execute(text(
        "CREATE TABLE IF NOT EXISTS alembic_version ("
        "version_num VARCHAR(255) NOT NULL, "
        "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
    ))
    if connection.dialect.name != "sqlite":
        connection.execute(text(
            "ALTER TABLE alembic_version "
            "ALTER COLUMN version_num TYPE VARCHAR(255)"
        ))


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # The app engine turns on ``PRAGMA foreign_keys`` per connection; this
    # standalone migration engine must too, or FK-reliant data migrations would
    # silently run with FK enforcement off on SQLite.
    if connectable.dialect.name == "sqlite":
        _enable_sqlite_fk(connectable)
    with connectable.connect() as connection:
        # Widen the version table before Alembic stamps it (committed in its own
        # transaction so the subsequent migration run sees the wider column).
        with connection.begin():
            _ensure_wide_version_table(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
