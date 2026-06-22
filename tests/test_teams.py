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


def test_register_seeds_global_teams(db_session):
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})

    fresh = TestClient(create_app())
    r = fresh.post(
        "/api/v1/auth/register",
        json={"username": "newbie", "password": "password123"},
    )
    assert r.status_code == 200, r.text
    # The freshly-registered (and now logged-in) user starts with the catalog.
    assert set(fresh.get("/api/v1/teams").json()) == set(APP_TEAMS)


def test_admin_created_user_is_seeded(db_session):
    from app.db.models.team import UserTeamListItem

    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams/import", json={"teams": APP_TEAMS})
    res = admin.post("/api/v1/admin/users", json={"username": "staff"})
    assert res.status_code in (200, 201), res.text
    uid = res.json()["user"]["id"]

    seeded = db_session.query(UserTeamListItem).filter_by(user_id=uid).count()
    assert seeded == len(APP_TEAMS)
