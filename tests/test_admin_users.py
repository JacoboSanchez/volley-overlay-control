"""Phase 5 — admin user management + registration toggle."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.bootstrap import create_app
from tests.conftest import login_client, make_user


def _admin(db_session):
    return login_client(TestClient(create_app()), db_session, "root", role="admin")


def test_user_management_requires_admin(db_session):
    user = login_client(TestClient(create_app()), db_session, "alice")
    assert user.get("/api/v1/admin/users").status_code == 403


def test_admin_lists_users(db_session):
    admin = _admin(db_session)
    make_user(db_session, "alice")
    names = {u["username"] for u in admin.get("/api/v1/admin/users").json()}
    assert {"root", "alice"} <= names


def test_admin_creates_user_with_temp_password(db_session):
    admin = _admin(db_session)
    r = admin.post("/api/v1/admin/users", json={"username": "newbie"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["must_change_password"] is True
    temp = body["temp_password"]
    assert temp

    # The new user can log in with the temp password and is forced to change.
    other = TestClient(create_app())
    login = other.post("/api/v1/auth/login", json={"username": "newbie", "password": temp})
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True
    assert other.patch("/api/v1/auth/me", json={"display_name": "x"}).status_code == 409


def test_admin_reset_password_forces_change_and_logs_out(db_session):
    admin = _admin(db_session)
    # Create + log in a normal user.
    target = make_user(db_session, "bob")
    bob = TestClient(create_app())
    bob.post("/api/v1/auth/login", json={"username": "bob", "password": "password123"})
    assert bob.get("/api/v1/auth/me").status_code == 200

    r = admin.post(f"/api/v1/admin/users/{target.id}/reset-password")
    assert r.status_code == 200
    temp = r.json()["temp_password"]
    assert temp

    # Bob's existing session is revoked, and the temp password forces a change.
    assert bob.get("/api/v1/auth/me").status_code == 401
    fresh = TestClient(create_app())
    assert fresh.post(
        "/api/v1/auth/login", json={"username": "bob", "password": temp},
    ).json()["must_change_password"] is True


def test_admin_cannot_delete_or_demote_last_admin(db_session):
    admin = _admin(db_session)
    me = admin.get("/api/v1/auth/me").json()
    assert admin.delete(f"/api/v1/admin/users/{me['id']}").status_code == 400
    assert admin.patch(
        f"/api/v1/admin/users/{me['id']}", json={"role": "user"},
    ).status_code == 400


def test_admin_toggles_registration(db_session):
    admin = _admin(db_session)
    assert admin.put(
        "/api/v1/admin/registration", json={"registration_open": False},
    ).status_code == 200
    assert admin.get("/api/v1/admin/registration").json()["registration_open"] is False

    # Registration is now closed for the public endpoint.
    pub = TestClient(create_app())
    assert pub.post(
        "/api/v1/auth/register", json={"username": "late", "password": "password123"},
    ).status_code == 403
