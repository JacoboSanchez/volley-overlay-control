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
    insp = inspect(engine)
    actual = set(insp.get_table_names())
    expected = set(Base.metadata.tables.keys()) | {"alembic_version"}
    assert actual == expected

    # Column-level drift: every model table must have exactly the columns the
    # ORM declares. Catches a column added to a model but forgotten in a
    # migration (or vice versa) — which a table-name-only check would miss.
    # Column names (not types/defaults) are compared to avoid SQLite
    # reflection false-positives on type affinity and server defaults.
    for table_name, table in Base.metadata.tables.items():
        reflected = {c["name"] for c in insp.get_columns(table_name)}
        declared = set(table.columns.keys())
        assert reflected == declared, (
            f"{table_name} column drift vs model: "
            f"missing={declared - reflected}, extra={reflected - declared}"
        )
    engine.dispose()


def test_alembic_version_table_is_wide_for_long_revision_ids(tmp_path, monkeypatch):
    """``env.py`` provisions ``alembic_version.version_num`` wider than Alembic's
    default ``VARCHAR(32)``, so long, human-readable revision ids don't overflow
    on length-enforcing backends like Postgres (SQLite ignores the length, so it
    silently used to pass there). Assert the column is the wide ``VARCHAR(255)``
    rather than the 32-char default — guards the widening from regressing.
    """
    db_file = tmp_path / "wide.db"
    url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(_alembic_config(url), "head")

    engine = create_engine(url)
    col = next(
        c for c in inspect(engine).get_columns("alembic_version")
        if c["name"] == "version_num"
    )
    length = getattr(col["type"], "length", None)
    assert length is not None and length >= 255, (
        f"alembic_version.version_num is {length} wide; env.py should provision "
        "VARCHAR(255) so long revision ids don't overflow on Postgres"
    )
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


def test_tz_datetime_round_trips_aware_on_sqlite(db_session):
    """TZDateTime must hand back UTC-aware datetimes on SQLite so model
    timestamps can be compared against datetime.now(UTC) without TypeError."""
    from datetime import UTC, datetime, timedelta

    from app.auth import sessions
    from app.db.models.user import AuthSession
    from tests.conftest import make_user

    user = make_user(db_session, "tzuser")
    raw = sessions.create_session(db_session, user)
    db_session.commit()
    db_session.expire_all()

    row = db_session.query(AuthSession).one()
    assert row.expires_at.tzinfo is not None
    assert row.last_seen_at is None or row.last_seen_at.tzinfo is not None
    assert row.created_at.tzinfo is not None
    # Aware comparison — the exact failure mode this guards against.
    assert row.expires_at > datetime.now(UTC)

    # resolve_session still lazily drops expired rows.
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    assert sessions.resolve_session(db_session, raw) is None
    assert db_session.query(AuthSession).count() == 0
