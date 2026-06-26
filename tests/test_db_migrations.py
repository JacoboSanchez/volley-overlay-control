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


def test_alembic_version_table_fits_long_revision_ids(tmp_path, monkeypatch):
    """Regression: Alembic's default ``version_num VARCHAR(32)`` is too narrow
    for this project's long, human-readable revision ids (e.g. the 40-char
    ``0008_overlay_display_name_to_description``). SQLite ignores the declared
    length, but Postgres enforces it, so the upgrade aborted on Postgres.
    ``env.py`` pre-provisions a wide column — assert it is at least as wide as
    the longest revision id in the tree.
    """
    import re

    rev_ids = []
    for f in (REPO_ROOT / "migrations" / "versions").glob("*.py"):
        m = re.search(r"^revision\b.*?['\"]([^'\"]+)['\"]", f.read_text(), re.M)
        if m:
            rev_ids.append(m.group(1))
    longest = max(len(r) for r in rev_ids)
    # Premise of the regression: at least one id must exceed Alembic's default
    # 32, otherwise this test would pass even with the bug present.
    assert longest > 32

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
    assert length is not None and length >= longest, (
        f"alembic_version.version_num is {length} wide but the longest "
        f"revision id is {longest} chars — Postgres would overflow"
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


def test_0007_migrates_flat_roster_into_private_my_teams_group(tmp_path, monkeypatch):
    """The 0007 data step copies each user's legacy ``user_team_list`` into a
    private "My teams" group, is idempotent, and leaves the source data intact."""
    db_file = tmp_path / "roster.db"
    url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)

    command.upgrade(cfg, "0006_drop_overlay_match_defaults")
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO users (id, username, password_hash, role, is_active, "
            "must_change_password) VALUES "
            "(1,'alice','x','user',1,0),(2,'bob','x','user',1,0)"
        ))
        c.execute(text(
            "INSERT INTO teams (id,name,is_global,owner_user_id) VALUES "
            "(10,'Breogan',1,NULL),(11,'Estudiantes',1,NULL),(12,'MyClub',0,1)"
        ))
        c.execute(text(
            "INSERT INTO user_team_list (user_id,team_id,sort_order) VALUES "
            "(1,10,0),(1,12,1),(2,11,0)"
        ))

    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # idempotent — must not duplicate groups

    with engine.connect() as c:
        groups = c.execute(text(
            "SELECT owner_user_id, name FROM team_groups WHERE owner_user_id IS NOT NULL"
        )).fetchall()
        assert {(g[0], g[1]) for g in groups} == {(1, "My teams"), (2, "My teams")}
        alice_teams = c.execute(text(
            "SELECT t.team_id FROM user_group_teams t "
            "JOIN team_groups g ON g.id = t.group_id WHERE t.user_id = 1"
        )).scalars().all()
        assert set(alice_teams) == {10, 12}
        # The legacy roster is preserved as a rollback safety net.
        assert c.execute(text("SELECT COUNT(*) FROM user_team_list")).scalar() == 3
    engine.dispose()
