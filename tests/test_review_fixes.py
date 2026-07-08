"""Regression tests for the branch code-review fixes.

Covers the confirmed findings that were straightforward to pin with a test:
the last-admin self-delete guard, admin group routes refusing to touch a
user's *private* group, the audit endpoint presenting the raw oid (not the
internal skey), and the degenerate table-tennis serve-switch flag.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.match_rules import compute_serve_switch
from app.bootstrap import create_app
from tests.conftest import login_client, make_user


def _client(db_session, username, *, role="user"):
    return login_client(TestClient(create_app()), db_session, username, role=role)


# --- last-admin self-delete guard (app/auth/routes.py:delete_me) ------------

def test_last_admin_cannot_self_delete(db_session):
    admin = _client(db_session, "root", role="admin")
    assert admin.delete("/api/v1/auth/me").status_code == 400


def test_self_delete_allowed_when_another_admin_exists(db_session):
    admin = _client(db_session, "root", role="admin")
    make_user(db_session, "admin2", role="admin")  # commits
    assert admin.delete("/api/v1/auth/me").status_code == 200


def test_regular_user_can_self_delete(db_session):
    user = _client(db_session, "alice", role="user")
    assert user.delete("/api/v1/auth/me").status_code == 200


# --- admin group routes never reach a user's PRIVATE group ------------------

def test_admin_group_routes_cannot_touch_private_groups(db_session):
    user = _client(db_session, "alice", role="user")
    gid = user.post("/api/v1/my/groups", json={"name": "My league"}).json()["id"]

    admin = _client(db_session, "root", role="admin")
    # Delete / set-active / add-member by id must all 404 for a private group.
    assert admin.delete(f"/api/v1/admin/team-groups/{gid}").status_code == 404
    assert admin.patch(
        f"/api/v1/admin/team-groups/{gid}", json={"is_active": False},
    ).status_code == 404
    assert admin.post(
        f"/api/v1/admin/team-groups/{gid}/members", json={"team_id": 1},
    ).status_code == 404

    # The private group still exists for its owner.
    names = {g["name"] for g in user.get("/api/v1/my/groups").json()}
    assert "My league" in names


# --- audit endpoint presents the raw oid, not the "<uid>:<oid>" skey --------

def test_audit_response_uses_raw_oid_not_skey(db_session):
    user = _client(db_session, "alice", role="user")
    assert user.post("/api/v1/session/init", json={"oid": "liga"}).status_code == 200
    r = user.get("/api/v1/audit?oid=liga")
    assert r.status_code == 200
    assert r.json()["oid"] == "liga"  # not "<user_id>:liga"


# --- table-tennis serve-switch must not flash at 0-0 with points_limit=1 ----

def test_serve_switch_not_pending_at_zero_zero_when_points_limit_one():
    res = compute_serve_switch(
        mode="table_tennis", current_set=1, sets_limit=1, first_server=1,
        team1_score=0, team2_score=0, points_limit=1, points_limit_last_set=1,
    )
    assert res is not None
    assert res["is_change_pending"] is False


def test_serve_switch_pending_after_a_point():
    res = compute_serve_switch(
        mode="table_tennis", current_set=1, sets_limit=3, first_server=1,
        team1_score=1, team2_score=1, points_limit=11, points_limit_last_set=11,
    )
    assert res is not None
    assert res["is_change_pending"] is True
