"""DB-layer scaling guards for #433.

Four things must stay true as the data grows:

* group listings cost a **constant** number of queries, not O(groups);
* the hot filter/order columns are indexed;
* expired ``auth_sessions`` rows are swept, not left to accumulate;
* no list endpoint can be made to return an unbounded page.

Each test below pins one of those. They are behavioural, not micro-benchmarks:
a regression shows up as a query count or a row count, never as a timing.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect

from app import teams_service
from app.bootstrap import create_app
from tests.conftest import login_client, make_user


@contextmanager
def count_selects(db_session):
    """Collect every SELECT issued on the test engine inside the block."""
    engine = db_session.get_bind()
    statements: list[str] = []

    def on_execute(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", on_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", on_execute)


def _admin(db_session):
    return login_client(TestClient(create_app()), db_session, "root", role="admin")


def _user(db_session, name="alice"):
    return login_client(TestClient(create_app()), db_session, name, role="user")


def _seed_groups(db_session, user_id: int, *, shared: int, private: int) -> None:
    """A catalog plus *shared* published admin groups and *private* own groups,
    each holding two teams, so a per-group query pattern is unmistakable."""
    teams = [teams_service.upsert_global(db_session, f"Club {i}") for i in range(6)]
    for i in range(shared):
        group = teams_service.create_group(db_session, f"Shared {i}")
        teams_service.set_group_active(db_session, group.id, True)
        teams_service.add_group_member(db_session, group.id, teams[i % 6].id)
        teams_service.add_group_member(db_session, group.id, teams[(i + 1) % 6].id)
    for i in range(private):
        group = teams_service.create_private_group(db_session, user_id, f"Mine {i}")
        teams_service.add_user_group_teams(
            db_session, user_id, group.id,
            [teams[i % 6].id, teams[(i + 2) % 6].id],
        )
    db_session.commit()


# ---- 1. N+1 on group listings ----------------------------------------------


@pytest.mark.parametrize(
    ("path", "as_admin"),
    [
        ("/api/v1/my/groups", False),
        ("/api/v1/team-groups", False),
        ("/api/v1/admin/team-groups", True),
    ],
)
def test_group_listings_do_not_scale_queries_with_group_count(
    db_session, path, as_admin,
):
    """The listing must cost the same number of SELECTs for 2 groups as for 10.

    Previously each group cost 1-4 extra queries (``group_member_teams`` /
    ``group_effective_teams`` / ``user_group_team_ids`` called in a loop).
    """
    client = _admin(db_session) if as_admin else _user(db_session)
    user_id = client.test_user_id

    _seed_groups(db_session, user_id, shared=1, private=1)
    with count_selects(db_session) as small:
        assert client.get(path).status_code == 200
    baseline = len(small)

    _seed_groups(db_session, user_id, shared=4, private=4)
    with count_selects(db_session) as large:
        response = client.get(path)
    assert response.status_code == 200
    assert len(large) == baseline, (
        f"{path}: {baseline} SELECTs for 2 groups but {len(large)} for 10 — "
        "the listing is still issuing per-group queries"
    )


def test_board_picker_counts_without_loading_teams(db_session):
    """``/board/team-groups`` returns only counts, so it must never SELECT the
    ``teams`` rows themselves — this runs on every single board load."""
    client = _user(db_session)
    _seed_groups(db_session, client.test_user_id, shared=3, private=3)
    overlay = client.post("/api/v1/overlays", json={"oid": "match"})
    assert overlay.status_code == 201, overlay.text

    with count_selects(db_session) as queries:
        response = client.get("/api/v1/board/team-groups?oid=match")
    assert response.status_code == 200

    selected_columns = [
        q for q in queries
        if "teams.name" in q.replace("\n", " ") and "count(" not in q.lower()
    ]
    assert not selected_columns, (
        "board picker materialised Team rows just to count them:\n"
        + "\n".join(selected_columns)
    )


def test_board_picker_counts_match_the_effective_team_lists(db_session):
    """The cheap COUNT path must agree with the list path it replaced —
    including de-duplication when a user re-adds a team a shared group
    already contains."""
    client = _user(db_session)
    user_id = client.test_user_id
    teams = [teams_service.upsert_global(db_session, f"C{i}") for i in range(4)]
    shared = teams_service.create_group(db_session, "Liga")
    teams_service.set_group_active(db_session, shared.id, True)
    teams_service.add_group_member(db_session, shared.id, teams[0].id)
    teams_service.add_group_member(db_session, shared.id, teams[1].id)
    # Overlapping addition (already an admin member) + a genuinely new one.
    teams_service.add_user_group_teams(
        db_session, user_id, shared.id, [teams[1].id, teams[2].id],
    )
    private = teams_service.create_private_group(db_session, user_id, "Mine")
    teams_service.add_user_group_teams(db_session, user_id, private.id, [teams[3].id])
    db_session.commit()

    client.post("/api/v1/overlays", json={"oid": "b1"})
    payload = client.get("/api/v1/board/team-groups?oid=b1").json()
    by_id = {g["id"]: g["count"] for g in payload["groups"]}

    assert by_id[shared.id] == 3  # {C0, C1, C2} — C1 counted once, not twice
    assert by_id[private.id] == 1
    assert by_id[None] == len(teams_service.all_group_teams(db_session, user_id))
    for group_id, count in by_id.items():
        assert count == len(
            teams_service.group_effective_teams(db_session, user_id, group_id)
        ), f"count for group {group_id} disagrees with the effective list"


def test_group_effective_counts_ignores_other_users_additions(db_session):
    """A second user's ``UserGroupTeam`` rows must not inflate the count."""
    alice = make_user(db_session, "counter_a")
    bob = make_user(db_session, "counter_b")
    team = teams_service.upsert_global(db_session, "Shared Club")
    other = teams_service.upsert_global(db_session, "Bob Only")
    group = teams_service.create_group(db_session, "Open")
    teams_service.set_group_active(db_session, group.id, True)
    teams_service.add_group_member(db_session, group.id, team.id)
    teams_service.add_user_group_teams(db_session, bob.id, group.id, [other.id])
    db_session.commit()

    counts = teams_service.group_effective_counts(db_session, alice.id, [group])
    assert counts[group.id] == 1
    assert counts[group.id] == len(
        teams_service.group_effective_teams(db_session, alice.id, group.id)
    )


def test_group_effective_counts_of_no_groups_is_empty(db_session):
    user = make_user(db_session, "emptycounts")
    db_session.commit()
    assert teams_service.group_effective_counts(db_session, user.id, []) == {}


# ---- 2. indexes -------------------------------------------------------------


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("teams", "is_global"),
        ("teams", "name"),
        ("team_groups", "is_active"),
        ("icons", "is_global"),
        ("presets", "scope"),
        ("presets", "is_active"),
        ("auth_sessions", "expires_at"),
    ],
)
def test_hot_filter_columns_are_indexed(db_session, table, column):
    """Every column a listing filters or orders by carries an index.

    ``tests/test_db_migrations.py`` proves the migration matches the models;
    this pins the specific set from #433 so dropping one is a deliberate act.
    """
    indexed = {
        tuple(ix["column_names"])
        for ix in inspect(db_session.get_bind()).get_indexes(table)
    }
    assert (column,) in indexed, f"{table}.{column} is not indexed (have {indexed})"


# ---- 3. expired auth_sessions sweeper --------------------------------------


def test_purge_expired_removes_only_expired_rows(db_session):
    from app.auth import sessions
    from app.db.models.user import AuthSession

    user = make_user(db_session, "sweeper")
    live = sessions.create_session(db_session, user)
    stale = sessions.create_session(db_session, user)
    db_session.commit()

    row = db_session.query(AuthSession).filter_by(
        token_hash=sessions.hash_token(stale),
    ).one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    assert sessions.purge_expired(db_session) == 1
    assert db_session.query(AuthSession).count() == 1
    # The surviving session still authenticates; the swept one is gone.
    assert sessions.resolve_session(db_session, live) is not None
    assert sessions.resolve_session(db_session, stale) is None


def test_purge_expired_is_idempotent_when_nothing_expired(db_session):
    from app.auth import sessions

    user = make_user(db_session, "sweeper2")
    sessions.create_session(db_session, user)
    db_session.commit()
    assert sessions.purge_expired(db_session) == 0
    assert sessions.purge_expired(db_session) == 0


def test_lifespan_sweep_helper_purges_through_its_own_session(db_session):
    """The background loop's helper opens its own ``session_scope`` — prove it
    reaches the same database the request path uses."""
    from app.api.routes.lifespan import purge_expired_auth_sessions
    from app.auth import sessions
    from app.db.models.user import AuthSession

    user = make_user(db_session, "sweeper3")
    raw = sessions.create_session(db_session, user)
    db_session.commit()
    db_session.query(AuthSession).filter_by(
        token_hash=sessions.hash_token(raw),
    ).one().expires_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()

    assert purge_expired_auth_sessions() == 1
    assert db_session.query(AuthSession).count() == 0


# ---- 4. pagination ----------------------------------------------------------


def _seed_catalog(db_session, count: int) -> None:
    for i in range(count):
        teams_service.upsert_global(db_session, f"Team {i:03d}")
    db_session.commit()


def test_catalog_pages_and_reports_the_total(db_session):
    client = _user(db_session)
    _seed_catalog(db_session, 7)

    first = client.get("/api/v1/teams/catalog?limit=3")
    assert first.status_code == 200
    assert first.headers["X-Total-Count"] == "7"
    names = [t["name"] for t in first.json()]
    assert names == ["Team 000", "Team 001", "Team 002"]

    second = client.get("/api/v1/teams/catalog?limit=3&offset=3")
    assert [t["name"] for t in second.json()] == ["Team 003", "Team 004", "Team 005"]

    # Paging the whole listing reproduces the unpaginated result exactly.
    walked: list[str] = []
    offset = 0
    while True:
        page = client.get(f"/api/v1/teams/catalog?limit=2&offset={offset}").json()
        if not page:
            break
        walked.extend(t["name"] for t in page)
        offset += 2
    assert walked == [f"Team {i:03d}" for i in range(7)]


def test_paging_is_stable_when_names_collide(db_session):
    """Every paged ``ORDER BY`` ends in a unique key.

    ``teams.name`` has no uniqueness constraint (``get_global_by_name``
    documents why), so ordering by name alone lets the database return tied
    rows in a different order per query — and a client walking pages would
    then duplicate some rows and miss others. Same for ``icons.name`` and
    ``presets.name``.
    """
    from app.db.models.team import Team

    client = _user(db_session)
    for _ in range(6):
        db_session.add(Team(name="Same Name", is_global=True))
    db_session.commit()

    walked: list[int] = []
    for offset in range(0, 6, 2):
        page = client.get(f"/api/v1/teams/catalog?limit=2&offset={offset}").json()
        walked.extend(t["id"] for t in page)

    assert len(walked) == 6
    assert len(set(walked)) == 6, f"paging duplicated/dropped tied rows: {walked}"
    assert walked == sorted(walked)


def test_preset_paging_is_stable_when_names_collide(db_session):
    """A user preset and a global preset may share a display name; the page
    boundary must still not duplicate or drop one."""
    from app.db.models.preset import SCOPE_GLOBAL, SCOPE_USER, Preset

    client = _user(db_session, "tiedpresets")
    for i in range(4):
        db_session.add(Preset(
            slug=f"g{i}", name="Tie", scope=SCOPE_GLOBAL, owner_user_id=None,
            is_active=True, categories=[], values={"Team 1 Color": "#111111"},
        ))
        db_session.add(Preset(
            slug=f"u{i}", name="Tie", scope=SCOPE_USER,
            owner_user_id=client.test_user_id, is_active=True,
            categories=[], values={"Team 2 Color": "#222222"},
        ))
    db_session.commit()

    walked: list[str] = []
    for offset in range(0, 8, 3):
        page = client.get(
            f"/api/v1/customization/presets?limit=3&offset={offset}",
        ).json()["items"]
        walked.extend(p["slug"] for p in page)
    assert len(walked) == 8
    assert len(set(walked)) == 8, f"paging duplicated/dropped tied presets: {walked}"
    # Globals still come first even though every name is identical.
    assert all(s.startswith("g") for s in walked[:4])


def test_default_page_is_unchanged_for_existing_clients(db_session):
    """A caller that sends no paging parameters still gets everything, so the
    bundled SPA and any existing integration are unaffected."""
    client = _user(db_session)
    _seed_catalog(db_session, 25)
    body = client.get("/api/v1/teams/catalog").json()
    assert len(body) == 25


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/teams",
        "/api/v1/teams/mine",
        "/api/v1/teams/catalog",
        "/api/v1/team-groups",
        "/api/v1/my/groups",
        "/api/v1/overlays",
        "/api/v1/icons",
        "/api/v1/customization/presets",
    ],
)
def test_list_endpoints_reject_an_unbounded_page(db_session, path):
    """``limit`` is capped server-side: no caller can ask for the whole table."""
    from app.constants import LIST_MAX_LIMIT

    client = _user(db_session)
    assert client.get(f"{path}?limit={LIST_MAX_LIMIT + 1}").status_code == 422
    assert client.get(f"{path}?limit=0").status_code == 422
    assert client.get(f"{path}?offset=-1").status_code == 422
    ok = client.get(f"{path}?limit={LIST_MAX_LIMIT}")
    assert ok.status_code == 200
    assert "X-Total-Count" in ok.headers


def test_admin_preset_and_group_listings_page(db_session):
    admin = _admin(db_session)
    for i in range(4):
        group = teams_service.create_group(db_session, f"G{i}")
        teams_service.set_group_active(db_session, group.id, True)
    db_session.commit()

    page = admin.get("/api/v1/admin/team-groups?limit=2")
    assert page.headers["X-Total-Count"] == "4"
    assert len(page.json()) == 2

    for i in range(3):
        assert admin.post(
            "/api/v1/admin/presets",
            json={"name": f"Theme {i}", "values": {"Team 1 Color": "#112233"}},
        ).status_code == 201
    presets = admin.get("/api/v1/admin/presets?limit=2")
    assert presets.headers["X-Total-Count"] == "3"
    assert len(presets.json()["items"]) == 2


def test_my_groups_pages_with_the_all_group_first(db_session):
    """"All" is row 0 of the paged sequence, so the total counts it and a
    non-zero offset walks past it into the real groups."""
    client = _user(db_session)
    _seed_groups(db_session, client.test_user_id, shared=1, private=2)

    full = client.get("/api/v1/my/groups")
    assert full.headers["X-Total-Count"] == "4"  # All + 1 shared + 2 private
    assert len(full.json()) == 4
    assert full.json()[0]["kind"] == "all"

    first = client.get("/api/v1/my/groups?limit=1").json()
    assert [g["kind"] for g in first] == ["all"]

    rest = client.get("/api/v1/my/groups?limit=10&offset=1").json()
    assert [g["kind"] for g in rest] == ["shared", "private", "private"]
    assert [g["name"] for g in rest] == [g["name"] for g in full.json()[1:]]


def test_icons_listing_pages_the_uncapped_global_library(db_session):
    """``mine`` is already capped by ICONS_MAX_PER_USER; ``globals`` is not, so
    that is the half the page window applies to."""
    from app.db.models.icon import Icon

    client = _user(db_session)
    for i in range(5):
        db_session.add(Icon(
            name=f"icon{i}", filename=f"f{i}.webp", width=8, height=8,
            size_bytes=32, is_global=True,
        ))
    db_session.commit()

    body = client.get("/api/v1/icons?limit=2")
    assert body.headers["X-Total-Count"] == "5"
    assert len(body.json()["globals"]) == 2
    assert body.json()["quota"]["used"] == 0


def test_presets_listing_orders_globals_first_across_pages(db_session):
    """``list_for_user`` sorts in SQL now — the page boundary must not scramble
    the globals-then-mine ordering the picker relies on."""
    admin = _admin(db_session)
    for name in ("Zeta", "Alpha"):
        assert admin.post(
            "/api/v1/admin/presets",
            json={"name": name, "values": {"Team 1 Color": "#010203"}},
        ).status_code == 201

    user = _user(db_session, "presetuser")
    for name in ("Beta", "Yankee"):
        assert user.post(
            "/api/v1/customization/presets",
            json={"name": name, "values": {"Team 2 Color": "#040506"}},
        ).status_code == 200

    everything = user.get("/api/v1/customization/presets").json()["items"]
    assert [p["name"] for p in everything] == ["Alpha", "Zeta", "Beta", "Yankee"]

    walked: list[str] = []
    for offset in range(0, 4, 2):
        page = user.get(
            f"/api/v1/customization/presets?limit=2&offset={offset}",
        ).json()["items"]
        walked.extend(p["name"] for p in page)
    assert walked == [p["name"] for p in everything]


def test_exports_stay_complete_and_unpaginated(db_session):
    """Backup surfaces deliberately do not page — a truncated export would
    silently lose data on the next import."""
    admin = _admin(db_session)
    _seed_catalog(db_session, 12)
    exported = admin.get("/api/v1/admin/teams/export")
    assert exported.status_code == 200
    assert len(exported.json()) == 12
    assert "limit" not in exported.request.url.query.decode()


# ---- 5. ownership checks that do not load the payload -----------------------


def _archive_one(db_session, user_id: int) -> str:
    from app.api import match_archive
    from app.overlay_key import make_skey

    match_id = match_archive.archive_match(
        make_skey(user_id, "cup"),
        {"team_1": {"sets": 3}, "team_2": {"sets": 1}},
        {"Team 1 Name": "A", "Team 2 Name": "B"},
        winning_team=1,
    )
    assert match_id is not None
    return match_id


def test_owner_user_id_reads_only_the_owner_column(db_session):
    from app.api import match_archive

    user = make_user(db_session, "owner")
    db_session.commit()
    match_id = _archive_one(db_session, user.id)

    with count_selects(db_session) as queries:
        assert match_archive.owner_user_id(match_id) == user.id
    joined = " ".join(q.replace("\n", " ") for q in queries)
    assert "match_reports.audit_log" not in joined
    assert "match_reports.final_state" not in joined

    assert match_archive.owner_user_id("match_" + "0" * 20 + "_20260101T000000_000000Z") is None
    assert match_archive.owner_user_id("not-a-match-id") is None


def test_delete_and_sign_url_still_enforce_ownership(db_session):
    owner = _user(db_session, "matchowner")
    match_id = _archive_one(db_session, owner.test_user_id)

    stranger = _user(db_session, "stranger")
    assert stranger.delete(f"/api/v1/matches/{match_id}").status_code == 404
    assert stranger.post(f"/api/v1/matches/{match_id}/sign-url").status_code == 404

    assert owner.post(f"/api/v1/matches/{match_id}/sign-url").status_code == 200
    assert owner.delete(f"/api/v1/matches/{match_id}").status_code == 204
    assert owner.delete(f"/api/v1/matches/{match_id}").status_code == 404
