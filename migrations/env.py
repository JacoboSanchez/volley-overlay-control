"""Alembic environment.

Resolves the database URL from ``DATABASE_URL`` (defaulting to the SQLite
file under ``data/``) the same way the running app does, and points
autogenerate at ``app.db.Base.metadata``. ``render_as_batch=True`` so SQLite
— which can't ``ALTER`` most things — gets table-recreate migrations.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db import Base
from app.db.engine import database_url

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


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
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
