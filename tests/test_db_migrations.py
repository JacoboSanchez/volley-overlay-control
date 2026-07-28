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


def _seed_users_and_teams(conn):
    """Two users and four teams (two global, one custom each), ids fixed."""
    conn.execute(text(
        "INSERT INTO users "
        "(id, username, password_hash, role, is_active, must_change_password) "
        "VALUES (1, 'alice', 'x', 'user', 1, 0), (2, 'bob', 'x', 'user', 1, 0)"
    ))
    # Names deliberately out of id order so ordering assertions mean something.
    conn.execute(text(
        "INSERT INTO teams (id, name, is_global, owner_user_id) VALUES "
        "(10, 'Zeta', 1, NULL), (11, 'Alfa', 1, NULL), "
        "(12, 'Alice Club', 0, 1), (13, 'Bob Club', 0, 2)"
    ))


def test_my_teams_group_name_matches_the_service(tmp_path):
    """The 0004 copy targets the same group ``seed_user_default_group`` creates.

    They are two independent literals — a migration must not import app code —
    so a rename on either side would silently strand every migrated roster in
    a group the app no longer treats as the default.
    """
    import importlib.util

    from app.teams_service import MY_TEAMS_NAME

    path = REPO_ROOT / "migrations" / "versions" / "0004_drop_user_team_list.py"
    spec = importlib.util.spec_from_file_location("migration_0004", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.MY_TEAMS_GROUP_NAME == MY_TEAMS_NAME


def test_upgrade_to_0004_copies_roster_globals_into_my_teams_group(tmp_path, monkeypatch):
    """A roster row for a global team is the only record that the user picked it.

    Nothing else in the schema implies it — unlike a custom team, which
    ``teams.owner_user_id`` covers — so the drop has to carry those
    memberships into the group model rather than discard them.
    """
    db_file = tmp_path / "carry.db"
    url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)
    command.upgrade(cfg, "0003_drop_overlay_session_meta")

    engine = create_engine(url)
    with engine.begin() as conn:
        _seed_users_and_teams(conn)
        # Alice already has a "My teams" group holding one of the two globals.
        conn.execute(text(
            "INSERT INTO team_groups (id, name, is_active, owner_user_id) "
            "VALUES (1, 'My teams', 1, 1)"
        ))
        conn.execute(text(
            "INSERT INTO user_group_teams (user_id, group_id, team_id, sort_order) "
            "VALUES (1, 1, 11, 0)"
        ))
        # Both users' rosters hold both globals plus their own custom team.
        # Bob has no group at all — an account predating the seeding feature.
        conn.execute(text(
            "INSERT INTO user_team_list (user_id, team_id, sort_order) VALUES "
            "(1, 11, 0), (1, 10, 1), (1, 12, 2), "
            "(2, 10, 0), (2, 13, 1)"
        ))

    command.upgrade(cfg, "head")

    with engine.begin() as conn:
        groups = conn.execute(text(
            "SELECT id, user_id FROM ("
            "  SELECT g.id AS id, g.owner_user_id AS user_id FROM team_groups g"
            "   WHERE g.name = 'My teams') ORDER BY user_id"
        )).fetchall()
        members = conn.execute(text(
            "SELECT user_id, team_id, sort_order FROM user_group_teams "
            "ORDER BY user_id, sort_order"
        )).fetchall()
    engine.dispose()

    # Bob had no group, so one was created for him.
    assert {g[1] for g in groups} == {1, 2}

    # Alice keeps her existing member at sort_order 0 and gains only the global
    # she was missing — appended, so her curated order survives. Her custom
    # team is not copied: ownership already implies it.
    assert [tuple(r) for r in members if r[0] == 1] == [(1, 11, 0), (1, 10, 1)]
    # Bob gains the one global his roster held, in his fresh group.
    assert [tuple(r) for r in members if r[0] == 2] == [(2, 10, 0)]


def test_upgrade_then_downgrade_round_trips_a_roster_global(tmp_path, monkeypatch):
    """End to end: a roster-only global survives upgrade and comes back on rollback.

    This is the case a plain drop would lose — the team is global (so ownership
    says nothing about it) and was in no group before the upgrade.
    """
    db_file = tmp_path / "roundtrip.db"
    url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)
    command.upgrade(cfg, "0003_drop_overlay_session_meta")

    engine = create_engine(url)
    with engine.begin() as conn:
        _seed_users_and_teams(conn)
        conn.execute(text(
            "INSERT INTO user_team_list (user_id, team_id, sort_order) "
            "VALUES (2, 10, 0)"
        ))

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0003_drop_overlay_session_meta")

    with engine.begin() as conn:
        roster = conn.execute(text(
            "SELECT user_id, team_id, sort_order FROM user_team_list "
            "ORDER BY user_id, sort_order"
        )).fetchall()
    engine.dispose()

    # Bob's roster-only global round-tripped — the assertion this test exists
    # for. His custom team is rostered alongside it (the row the pre-0004
    # ``create_user_team`` wrote), ordered by name: 'Bob Club' then 'Zeta'.
    assert [tuple(r) for r in roster if r[0] == 2] == [(2, 13, 0), (2, 10, 1)]
    # Alice never had a roster row here, but owning a custom team is enough.
    assert [tuple(r) for r in roster if r[0] == 1] == [(1, 12, 0)]


def test_downgrade_from_0004_rebuilds_the_roster_from_groups(tmp_path, monkeypatch):
    """Rolling back the roster drop must not hand the old app an empty table.

    ``user_team_list`` is dropped by 0004 because nothing reads it any more,
    but the pre-0004 application serves ``GET /teams`` and ``/teams/mine``
    straight out of it. A downgrade that only re-created the table would leave
    every user with an empty roster, so it reconstructs one from the group
    memberships and owned custom teams the app has kept current.
    """
    db_file = tmp_path / "downgrade.db"
    url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users "
            "(id, username, password_hash, role, is_active, must_change_password) "
            "VALUES (1, 'alice', 'x', 'user', 1, 0), (2, 'bob', 'x', 'user', 1, 0)"
        ))
        # Two globals, plus one custom team each. Names are deliberately out of
        # id order so the sort_order assertion below means something.
        conn.execute(text(
            "INSERT INTO teams (id, name, is_global, owner_user_id) VALUES "
            "(10, 'Zeta', 1, NULL), (11, 'Alfa', 1, NULL), "
            "(12, 'Alice Club', 0, 1), (13, 'Bob Club', 0, 2)"
        ))
        conn.execute(text(
            "INSERT INTO team_groups (id, name, is_active, owner_user_id) "
            "VALUES (1, 'My teams', 1, 1)"
        ))
        # Alice picked both globals into her group; her custom team is in it
        # too, so the UNION has to collapse it to one roster row.
        conn.execute(text(
            "INSERT INTO user_group_teams (user_id, group_id, team_id, sort_order) "
            "VALUES (1, 1, 10, 0), (1, 1, 11, 1), (1, 1, 12, 2)"
        ))

    command.downgrade(cfg, "0003_drop_overlay_session_meta")

    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT user_id, team_id, sort_order FROM user_team_list "
            "ORDER BY user_id, sort_order"
        )).fetchall()
    engine.dispose()

    # Alice: her group's two globals + her custom team, ordered by name
    # (Alfa, Alice Club, Zeta) with contiguous sort_order and no duplicate.
    assert [tuple(r) for r in rows if r[0] == 1] == [(1, 11, 0), (1, 12, 1), (1, 10, 2)]
    # Bob is in no group, but owning a custom team is enough to be rostered —
    # that is the row the pre-0004 ``create_user_team`` would have written.
    assert [tuple(r) for r in rows if r[0] == 2] == [(2, 13, 0)]


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
