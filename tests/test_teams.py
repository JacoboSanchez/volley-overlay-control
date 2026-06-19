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
