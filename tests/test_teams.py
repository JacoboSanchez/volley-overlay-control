"""Phase 4 — DB-backed teams: catalog, groups, per-user lists, admin JSON I/O."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.bootstrap import create_app
from tests.conftest import login_client


def _admin(db_session):
    return login_client(TestClient(create_app()), db_session, "root", role="admin")


def _user(db_session):
    return login_client(TestClient(create_app()), db_session, "alice", role="user")


# ---- admin import/export (config-provider migration path) ------------------

APP_TEAMS = {
    "Breogán": {"icon": "http://x/b.png", "color": "#ff0000", "text_color": "#ffffff"},
    "Estudiantes": {"icon": "http://x/e.png", "color": "#0000ff", "text_color": "#ffff00"},
}


def test_admin_import_then_export_roundtrips(db_session):
    admin = _admin(db_session)
    r = admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 2

    exported = admin.get("/api/v1/admin/teams/export").json()
    assert exported == APP_TEAMS


def test_admin_endpoints_require_admin(db_session):
    user = _user(db_session)
    assert user.post("/api/v1/admin/teams/import", json={"teams": {}}).status_code == 403
    assert user.get("/api/v1/admin/teams/export").status_code == 403


def test_import_replace_clears_previous(db_session):
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})
    admin.post(
        "/api/v1/admin/teams/import",
        json={"teams": {"Only": {"icon": "", "color": "#111", "text_color": "#fff"}},
              "replace": True},
    )
    exported = admin.get("/api/v1/admin/teams/export").json()
    assert set(exported) == {"Only"}


# ---- user catalog + personal list ------------------------------------------


def test_user_adds_catalog_team_to_their_list(db_session):
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})

    user = _user(db_session)
    catalog = user.get("/api/v1/teams/catalog").json()
    assert {t["name"] for t in catalog} == set(APP_TEAMS)

    ids = [catalog[0]["id"]]
    assert user.post("/api/v1/teams/mine", json={"team_ids": ids}).json()["added"] == 1
    # Idempotent re-add.
    assert user.post("/api/v1/teams/mine", json={"team_ids": ids}).json()["added"] == 0

    mine = user.get("/api/v1/teams").json()
    assert catalog[0]["name"] in mine

    assert user.delete(f"/api/v1/teams/mine/{ids[0]}").status_code == 200
    assert user.get("/api/v1/teams").json() == {}


def test_user_team_lists_are_isolated(db_session):
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})
    catalog = admin.get("/api/v1/teams/catalog").json()
    tid = catalog[0]["id"]

    alice = login_client(TestClient(create_app()), db_session, "alice")
    bob = login_client(TestClient(create_app()), db_session, "bob")
    alice.post("/api/v1/teams/mine", json={"team_ids": [tid]})

    assert catalog[0]["name"] in alice.get("/api/v1/teams").json()
    assert bob.get("/api/v1/teams").json() == {}


# ---- team groups (Liga Gallega) + copy-to-mine -----------------------------


def test_admin_group_published_then_user_copies_it(db_session):
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})
    catalog = admin.get("/api/v1/teams/catalog").json()

    gid = admin.post("/api/v1/admin/team-groups", json={"name": "Liga Gallega"}).json()["id"]
    for t in catalog:
        admin.post(f"/api/v1/admin/team-groups/{gid}/members", json={"team_id": t["id"]})

    user = _user(db_session)
    # Inactive group is not visible/copyable yet.
    assert user.get("/api/v1/team-groups").json() == []
    assert user.post(f"/api/v1/team-groups/{gid}/copy-to-mine").status_code == 404

    admin.patch(f"/api/v1/admin/team-groups/{gid}", json={"is_active": True})
    groups = user.get("/api/v1/team-groups").json()
    assert groups[0]["name"] == "Liga Gallega"
    assert {t["name"] for t in groups[0]["teams"]} == set(APP_TEAMS)

    assert user.post(f"/api/v1/team-groups/{gid}/copy-to-mine").json()["added"] == 2
    assert set(user.get("/api/v1/teams").json()) == set(APP_TEAMS)
    # Idempotent copy.
    assert user.post(f"/api/v1/team-groups/{gid}/copy-to-mine").json()["added"] == 0


def test_admin_can_create_and_edit_team_with_logo_and_colors(db_session):
    admin = _admin(db_session)
    created = admin.post(
        "/api/v1/admin/teams",
        json={"name": "Lugo", "icon": "http://x/l.png", "color": "#2e7d32", "text_color": "#ffffff"},
    )
    assert created.status_code == 201, created.text
    tid = created.json()["id"]
    assert created.json()["icon"] == "http://x/l.png"
    assert created.json()["color"] == "#2e7d32"

    edited = admin.patch(
        f"/api/v1/admin/teams/{tid}",
        json={"color": "#000000", "icon": "http://x/new.png"},
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["color"] == "#000000"
    assert body["icon"] == "http://x/new.png"
    assert body["text_color"] == "#ffffff"  # unchanged

    # The catalog the user sees carries the configured logo/colours.
    cat = {t["name"]: t for t in admin.get("/api/v1/teams/catalog").json()}
    assert cat["Lugo"]["color"] == "#000000"
    assert cat["Lugo"]["icon"] == "http://x/new.png"


def test_admin_update_missing_team_is_404(db_session):
    admin = _admin(db_session)
    assert admin.patch("/api/v1/admin/teams/999999", json={"color": "#fff"}).status_code == 404


def test_team_update_requires_admin(db_session):
    user = _user(db_session)
    assert user.patch("/api/v1/admin/teams/1", json={"color": "#fff"}).status_code == 403


def test_add_member_to_missing_group_is_404(db_session):
    """Regression: adding a member to a nonexistent group is 404, not a 500."""
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})
    tid = admin.get("/api/v1/teams/catalog").json()[0]["id"]
    r = admin.post("/api/v1/admin/team-groups/999999/members", json={"team_id": tid})
    assert r.status_code == 404


# ---- admin group manager (list-all / remove member / delete group) ---------


def test_admin_lists_all_groups_including_inactive(db_session):
    """The admin manager sees inactive groups (with members); users do not."""
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})
    catalog = admin.get("/api/v1/teams/catalog").json()
    gid = admin.post("/api/v1/admin/team-groups", json={"name": "Borrador"}).json()["id"]
    for t in catalog:
        admin.post(f"/api/v1/admin/team-groups/{gid}/members", json={"team_id": t["id"]})

    # Still inactive → invisible to users, visible to admin with its members.
    user = _user(db_session)
    assert user.get("/api/v1/team-groups").json() == []

    groups = admin.get("/api/v1/admin/team-groups").json()
    assert [g["name"] for g in groups] == ["Borrador"]
    assert groups[0]["is_active"] is False
    assert {t["name"] for t in groups[0]["teams"]} == set(APP_TEAMS)


def test_admin_group_list_requires_admin(db_session):
    user = _user(db_session)
    assert user.get("/api/v1/admin/team-groups").status_code == 403


def test_admin_removes_a_group_member(db_session):
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})
    catalog = admin.get("/api/v1/teams/catalog").json()
    gid = admin.post("/api/v1/admin/team-groups", json={"name": "Liga"}).json()["id"]
    for t in catalog:
        admin.post(f"/api/v1/admin/team-groups/{gid}/members", json={"team_id": t["id"]})
    drop = catalog[0]["id"]

    r = admin.delete(f"/api/v1/admin/team-groups/{gid}/members/{drop}")
    assert r.status_code == 200, r.text
    assert r.json()["removed"] is True

    groups = {g["id"]: g for g in admin.get("/api/v1/admin/team-groups").json()}
    assert drop not in {t["id"] for t in groups[gid]["teams"]}
    # Idempotent: removing it again still succeeds but reports nothing removed.
    assert admin.delete(f"/api/v1/admin/team-groups/{gid}/members/{drop}").json()["removed"] is False


def test_admin_remove_member_from_missing_group_is_404(db_session):
    admin = _admin(db_session)
    assert admin.delete("/api/v1/admin/team-groups/999999/members/1").status_code == 404


def test_admin_deletes_a_group_keeping_catalog_teams(db_session):
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})
    catalog = admin.get("/api/v1/teams/catalog").json()
    gid = admin.post("/api/v1/admin/team-groups", json={"name": "Temporal"}).json()["id"]
    for t in catalog:
        admin.post(f"/api/v1/admin/team-groups/{gid}/members", json={"team_id": t["id"]})

    assert admin.delete(f"/api/v1/admin/team-groups/{gid}").status_code == 200
    assert admin.get("/api/v1/admin/team-groups").json() == []
    # The member teams survive in the catalog.
    assert {t["name"] for t in admin.get("/api/v1/teams/catalog").json()} == set(APP_TEAMS)
    # Deleting again is a 404.
    assert admin.delete(f"/api/v1/admin/team-groups/{gid}").status_code == 404


def test_admin_group_delete_requires_admin(db_session):
    user = _user(db_session)
    assert user.delete("/api/v1/admin/team-groups/1").status_code == 403
    assert user.delete("/api/v1/admin/team-groups/1/members/1").status_code == 403


def test_admin_cannot_add_a_private_custom_team_to_a_group(db_session):
    """Data-isolation: a user's private custom team must never be linked to a
    group, or copy-to-mine would leak it into every other user's roster."""
    admin = _admin(db_session)
    alice = _user(db_session)
    secret = alice.post(
        "/api/v1/teams/mine/custom",
        json={"name": "Alice Secret", "color": "#abcdef"},
    ).json()
    assert secret["is_global"] is False

    gid = admin.post("/api/v1/admin/team-groups", json={"name": "Liga"}).json()["id"]
    # The private team id is rejected as if it did not exist.
    r = admin.post(f"/api/v1/admin/team-groups/{gid}/members", json={"team_id": secret["id"]})
    assert r.status_code == 404

    admin.patch(f"/api/v1/admin/team-groups/{gid}", json={"is_active": True})
    # Even after publishing, another user never sees or copies the private team.
    bob = login_client(TestClient(create_app()), db_session, "bob")
    groups = bob.get("/api/v1/team-groups").json()
    assert all("Alice Secret" not in {t["name"] for t in g["teams"]} for g in groups)


# ---- custom (user-owned) teams ---------------------------------------------


def test_user_creates_custom_team(db_session):
    user = _user(db_session)
    r = user.post(
        "/api/v1/teams/mine/custom",
        json={"name": "My Club", "color": "#123456", "text_color": "#ffffff"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "My Club" and body["is_global"] is False

    # Appears in both the rows endpoint and the APP_TEAMS map.
    rows = user.get("/api/v1/teams/mine").json()
    assert any(t["name"] == "My Club" and not t["is_global"] for t in rows)
    assert "My Club" in user.get("/api/v1/teams").json()


def test_user_edits_own_custom_team(db_session):
    user = _user(db_session)
    tid = user.post("/api/v1/teams/mine/custom", json={"name": "Tmp"}).json()["id"]
    r = user.patch(f"/api/v1/teams/mine/custom/{tid}", json={"name": "Renamed", "color": "#abcdef"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"
    assert r.json()["color"] == "#abcdef"


def test_cannot_edit_a_global_team_via_custom_endpoint(db_session):
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})
    gid = admin.get("/api/v1/teams/catalog").json()[0]["id"]
    user = _user(db_session)
    assert user.patch(f"/api/v1/teams/mine/custom/{gid}", json={"name": "Hijack"}).status_code == 404


def test_removing_custom_team_deletes_it(db_session):
    user = _user(db_session)
    tid = user.post("/api/v1/teams/mine/custom", json={"name": "Throwaway"}).json()["id"]
    assert user.delete(f"/api/v1/teams/mine/{tid}").status_code == 200
    # Gone from the list and from existence (no longer addable).
    assert "Throwaway" not in user.get("/api/v1/teams").json()
    assert user.post("/api/v1/teams/mine", json={"team_ids": [tid]}).status_code == 400


def test_removing_global_team_only_unlinks_it(db_session):
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})
    gid = admin.get("/api/v1/teams/catalog").json()[0]["id"]
    user = _user(db_session)
    user.post("/api/v1/teams/mine", json={"team_ids": [gid]})
    user.delete(f"/api/v1/teams/mine/{gid}")
    # Unlinked from the list but still in the global catalog (re-addable).
    assert gid in {t["id"] for t in user.get("/api/v1/teams/catalog").json()}
    assert user.post("/api/v1/teams/mine", json={"team_ids": [gid]}).json()["added"] == 1


def test_batch_remove(db_session):
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})
    user = _user(db_session)
    ids = [t["id"] for t in user.get("/api/v1/teams/catalog").json()]
    user.post("/api/v1/teams/mine", json={"team_ids": ids})
    assert len(user.get("/api/v1/teams/mine").json()) == len(ids)

    r = user.post("/api/v1/teams/mine/remove", json={"team_ids": ids})
    assert r.status_code == 200
    assert r.json()["removed"] == len(ids)
    assert user.get("/api/v1/teams/mine").json() == []


# ---- seed-on-creation ------------------------------------------------------


def test_register_seeds_my_teams_group(db_session):
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})

    fresh = TestClient(create_app())
    r = fresh.post(
        "/api/v1/auth/register",
        json={"username": "newbie", "password": "password123"},
    )
    assert r.status_code == 200, r.text
    # The freshly-registered user starts with a private "My teams" group holding
    # the full catalog, and the "All" group also surfaces the catalog.
    groups = {g["name"]: g for g in fresh.get("/api/v1/my/groups").json()}
    assert {t["name"] for t in groups["My teams"]["teams"]} == set(APP_TEAMS)
    assert groups["My teams"]["kind"] == "private"
    assert {t["name"] for t in groups["All teams"]["teams"]} == set(APP_TEAMS)


def test_admin_created_user_is_seeded(db_session):
    from app.db.models.team import TeamGroup, UserGroupTeam

    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})
    res = admin.post("/api/v1/admin/users", json={"username": "staff"})
    assert res.status_code in (200, 201), res.text
    uid = res.json()["user"]["id"]

    group = db_session.query(TeamGroup).filter_by(owner_user_id=uid, name="My teams").one()
    seeded = db_session.query(UserGroupTeam).filter_by(user_id=uid, group_id=group.id).count()
    assert seeded == len(APP_TEAMS)


# ---- groups as the primary unit: private groups, extensions, board picker --


def _catalog_ids(client) -> dict[str, int]:
    return {t["name"]: t["id"] for t in client.get("/api/v1/teams/catalog").json()}


def _seed_catalog(admin) -> dict[str, int]:
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})
    return _catalog_ids(admin)


def test_create_private_group_with_global_and_custom(db_session):
    admin = _admin(db_session)
    cat = _seed_catalog(admin)
    custom = admin.post("/api/v1/teams/mine/custom", json={"name": "My Club"}).json()

    gid = admin.post("/api/v1/my/groups", json={"name": "My league"}).json()["id"]
    r = admin.post(
        f"/api/v1/my/groups/{gid}/teams",
        json={"team_ids": [cat["Breogán"], custom["id"]]},
    )
    assert r.status_code == 200 and r.json()["added"] == 2

    groups = {g["name"]: g for g in admin.get("/api/v1/my/groups").json()}
    assert groups["My league"]["kind"] == "private"
    assert groups["My league"]["is_private"] is True
    assert {t["name"] for t in groups["My league"]["teams"]} == {"Breogán", "My Club"}


def test_all_group_is_catalog_union_customs(db_session):
    admin = _admin(db_session)
    _seed_catalog(admin)
    admin.post("/api/v1/teams/mine/custom", json={"name": "My Club"})
    groups = {g["name"]: g for g in admin.get("/api/v1/my/groups").json()}
    assert groups["All teams"]["kind"] == "all"
    assert {t["name"] for t in groups["All teams"]["teams"]} == set(APP_TEAMS) | {"My Club"}


def test_private_group_invisible_to_other_user(db_session):
    admin = _admin(db_session)
    _seed_catalog(admin)
    gid = admin.post("/api/v1/my/groups", json={"name": "Secret"}).json()["id"]

    bob = login_client(TestClient(create_app()), db_session, "bob")
    assert "Secret" not in {g["name"] for g in bob.get("/api/v1/my/groups").json()}
    # bob cannot read, rename, delete, or add to alice's private group.
    assert bob.post(f"/api/v1/my/groups/{gid}/teams", json={"team_ids": []}).status_code == 404
    assert bob.patch(f"/api/v1/my/groups/{gid}", json={"name": "x"}).status_code == 404
    assert bob.delete(f"/api/v1/my/groups/{gid}").status_code == 404


def test_user_extension_of_shared_group_is_private_to_them(db_session):
    admin = _admin(db_session)
    cat = _seed_catalog(admin)
    gid = admin.post("/api/v1/admin/team-groups", json={"name": "Liga"}).json()["id"]
    admin.post(f"/api/v1/admin/team-groups/{gid}/members", json={"team_id": cat["Breogán"]})
    admin.patch(f"/api/v1/admin/team-groups/{gid}", json={"is_active": True})

    alice = login_client(TestClient(create_app()), db_session, "alice")
    mine = alice.post("/api/v1/teams/mine/custom", json={"name": "Alice FC"}).json()
    alice.post(f"/api/v1/my/groups/{gid}/teams", json={"team_ids": [mine["id"]]})

    a_groups = {g["name"]: g for g in alice.get("/api/v1/my/groups").json()}
    assert {t["name"] for t in a_groups["Liga"]["teams"]} == {"Breogán", "Alice FC"}

    bob = login_client(TestClient(create_app()), db_session, "bob")
    b_groups = {g["name"]: g for g in bob.get("/api/v1/my/groups").json()}
    assert {t["name"] for t in b_groups["Liga"]["teams"]} == {"Breogán"}  # no Alice FC


def test_cannot_add_other_users_custom_team_to_group(db_session):
    admin = _admin(db_session)
    _seed_catalog(admin)
    alice = login_client(TestClient(create_app()), db_session, "alice")
    secret = alice.post("/api/v1/teams/mine/custom", json={"name": "Alice Secret"}).json()

    bob = login_client(TestClient(create_app()), db_session, "bob")
    gid = bob.post("/api/v1/my/groups", json={"name": "Bob group"}).json()["id"]
    r = bob.post(f"/api/v1/my/groups/{gid}/teams", json={"team_ids": [secret["id"]]})
    # alice's private team is rejected as if it did not exist — no leak.
    assert r.status_code == 404
    grp = next(g for g in bob.get("/api/v1/my/groups").json() if g["id"] == gid)
    assert grp["teams"] == []


def test_remove_group_team_keeps_the_team(db_session):
    admin = _admin(db_session)
    cat = _seed_catalog(admin)
    gid = admin.post("/api/v1/my/groups", json={"name": "G"}).json()["id"]
    admin.post(f"/api/v1/my/groups/{gid}/teams", json={"team_ids": [cat["Breogán"]]})
    r = admin.delete(f"/api/v1/my/groups/{gid}/teams/{cat['Breogán']}")
    assert r.status_code == 200 and r.json()["removed"] is True
    # The team is gone from the group but still in the catalog.
    grp = next(g for g in admin.get("/api/v1/my/groups").json() if g["id"] == gid)
    assert grp["teams"] == []
    assert "Breogán" in _catalog_ids(admin)


def test_board_picker_via_control_token(db_session):
    """The board picker resolves the OWNER's groups for an operator holding the
    control token (the old GET /teams left operators with an empty picker)."""
    owner = _admin(db_session)
    cat = _seed_catalog(owner)
    gid = owner.post("/api/v1/admin/team-groups", json={"name": "Liga"}).json()["id"]
    owner.post(f"/api/v1/admin/team-groups/{gid}/members", json={"team_id": cat["Breogán"]})
    owner.patch(f"/api/v1/admin/team-groups/{gid}", json={"is_active": True})
    priv = owner.post("/api/v1/my/groups", json={"name": "My league"}).json()["id"]
    owner.post(f"/api/v1/my/groups/{priv}/teams", json={"team_ids": [cat["Estudiantes"]]})

    ctrl = owner.post("/api/v1/overlays", json={"oid": "liga"}).json()["control_token"]
    op = TestClient(create_app())  # operator: no cookie
    bg = op.get(f"/api/v1/board/team-groups?c={ctrl}").json()
    names = {g["name"] for g in bg["groups"]}
    assert {"All teams", "Liga", "My league"} <= names  # incl. owner's private group

    liga_teams = op.get(f"/api/v1/board/team-groups/{gid}/teams?c={ctrl}").json()
    assert set(liga_teams) == {"Breogán"}
    all_teams = op.get(f"/api/v1/board/team-groups/all/teams?c={ctrl}").json()
    assert set(all_teams) == set(APP_TEAMS)


def test_board_picker_via_public_bookmark(db_session):
    owner = _admin(db_session)
    _seed_catalog(owner)
    owner.post("/api/v1/overlays", json={"oid": "liga"})
    owner.patch("/api/v1/overlays/liga", json={"public_control": True})

    op = TestClient(create_app())
    bg = op.get("/api/v1/board/team-groups?u=root&oid=liga")
    assert bg.status_code == 200, bg.text
    assert "All teams" in {g["name"] for g in bg.json()["groups"]}


def test_board_selected_group_persists_per_overlay(db_session):
    owner = _admin(db_session)
    _seed_catalog(owner)
    gid = owner.post("/api/v1/admin/team-groups", json={"name": "Liga"}).json()["id"]
    owner.patch(f"/api/v1/admin/team-groups/{gid}", json={"is_active": True})
    ctrl = owner.post("/api/v1/overlays", json={"oid": "liga"}).json()["control_token"]

    op = TestClient(create_app())
    op.post(f"/api/v1/session/init?c={ctrl}", json={"oid": "liga"})
    r = op.put(f"/api/v1/board/selected-group?c={ctrl}", json={"group_id": gid})
    assert r.status_code == 200 and r.json()["selected_id"] == gid
    assert op.get(f"/api/v1/board/team-groups?c={ctrl}").json()["selected_id"] == gid

    # Selecting "All" clears it; an unknown group id is rejected.
    op.put(f"/api/v1/board/selected-group?c={ctrl}", json={"group_id": None})
    assert op.get(f"/api/v1/board/team-groups?c={ctrl}").json()["selected_id"] is None
    assert op.put(
        f"/api/v1/board/selected-group?c={ctrl}", json={"group_id": 999999},
    ).status_code == 404


# ---- bulk-add batching ------------------------------------------------------


def _count_queries(db_session):
    """Context manager counting SELECT statements executed on the test engine."""
    from contextlib import contextmanager

    from sqlalchemy import event

    engine = db_session.get_bind()

    @contextmanager
    def counter(box):
        def on_execute(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                box.append(statement)

        event.listen(engine, "before_cursor_execute", on_execute)
        try:
            yield box
        finally:
            event.remove(engine, "before_cursor_execute", on_execute)

    return counter([])


def test_bulk_add_teams_uses_constant_queries(db_session):
    """Adding N teams must not issue O(N) queries (was 3 per team)."""
    from app import teams_service
    from tests.conftest import make_user

    ids = [
        teams_service.upsert_global(db_session, f"Club {i}").id
        for i in range(12)
    ]
    user = make_user(db_session, "bulkuser")
    db_session.commit()

    # Pre-link a couple so the batch mixes new / already-linked / duplicates.
    teams_service.add_teams_to_user(db_session, user.id, ids[:2])
    with _count_queries(db_session) as queries:
        added = teams_service.add_teams_to_user(
            db_session, user.id, ids + ids[:3],  # duplicates in the input too
        )
    assert added == 10
    # Inserts are per-row by nature; the SELECT count must stay constant
    # (validate ids + existing links + max sort_order — was 2 per team).
    assert len(queries) <= 3, f"{len(queries)} SELECTs for a 12-team batch"

    rows = teams_service.list_user_team_rows(db_session, user.id)
    assert [t.id for t in rows[:12]] == ids  # input order, contiguous sort


def test_bulk_add_teams_missing_id_raises_and_adds_nothing(db_session):
    from app import teams_service
    from tests.conftest import make_user

    tid = teams_service.upsert_global(db_session, "Solo").id
    user = make_user(db_session, "bulkuser2")
    db_session.commit()

    import pytest as _pytest

    with _pytest.raises(teams_service.TeamError, match="not found"):
        teams_service.add_teams_to_user(db_session, user.id, [tid, 99999])
    assert teams_service.list_user_team_rows(db_session, user.id) == []


def test_bulk_group_add_validates_scope_in_batch(db_session):
    """Group bulk add: one query validates visibility; another user's custom
    team in the batch fails the whole call."""
    from app import teams_service
    from tests.conftest import make_user

    alice = make_user(db_session, "galice")
    bob = make_user(db_session, "gbob")
    mine = teams_service.create_user_team(db_session, alice.id, "Mine").id
    theirs = teams_service.create_user_team(db_session, bob.id, "Theirs").id
    group = teams_service.create_private_group(db_session, alice.id, "Grp")
    db_session.commit()

    import pytest as _pytest

    with _pytest.raises(teams_service.TeamError, match="not found"):
        teams_service.add_user_group_teams(
            db_session, alice.id, group.id, [mine, theirs],
        )
    added = teams_service.add_user_group_teams(db_session, alice.id, group.id, [mine])
    assert added == 1
    # Idempotent re-add.
    assert teams_service.add_user_group_teams(db_session, alice.id, group.id, [mine]) == 0
