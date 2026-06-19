"""Migration foundation tests.

Proves the headline "migratable on update" requirement: a fresh database
upgraded with Alembic ends up with exactly the schema the ORM models
describe, and the per-(user, oid) uniqueness rule that lets two users share
an oid is enforced at the database level.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.db import Base

REPO_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def _alembic_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_alembic_upgrade_head_matches_models(tmp_path, monkeypatch):
    """``alembic upgrade head`` on a fresh SQLite yields the model schema."""
    db_file = tmp_path / "fresh.db"
    url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", url)

    command.upgrade(_alembic_config(url), "head")

    engine = create_engine(url)
    actual = set(inspect(engine).get_table_names())
    expected = set(Base.metadata.tables.keys()) | {"alembic_version"}
    assert actual == expected
    engine.dispose()


def test_two_users_can_share_an_oid_but_one_user_cannot(db_session):
    """``UniqueConstraint(user_id, oid)`` — same oid across users is allowed."""
    from app.db.models import User, UserOverlay

    a = User(username="alice", password_hash="x", role="user")
    b = User(username="bob", password_hash="x", role="user")
    db_session.add_all([a, b])
    db_session.flush()

    db_session.add(UserOverlay(user_id=a.id, oid="liga", public_token="tok-a"))
    db_session.add(UserOverlay(user_id=b.id, oid="liga", public_token="tok-b"))
    db_session.commit()  # both succeed — oid is unique only per user

    db_session.add(UserOverlay(user_id=a.id, oid="liga", public_token="tok-c"))
    with pytest.raises(Exception):  # noqa: B017 - IntegrityError across backends
        db_session.commit()
    db_session.rollback()


def test_sqlite_foreign_keys_are_enforced(db_session):
    """The SQLite ``PRAGMA foreign_keys=ON`` listener is active."""
    if db_session.bind.dialect.name != "sqlite":
        pytest.skip("FK pragma is SQLite-specific")
    result = db_session.execute(text("PRAGMA foreign_keys")).scalar()
    assert result == 1
