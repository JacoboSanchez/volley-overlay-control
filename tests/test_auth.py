"""Phase 2 — accounts, cookie sessions, and first-admin bootstrap."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def _claim_admin(client, db_session, username="root", password="adminpass1"):
    """Read the live bootstrap token and claim the first admin."""
    from app.auth import bootstrap

    token = bootstrap.get_bootstrap_token()
    assert token, "ensure_admin_bootstrap should have minted a token"
    resp = client.post(
        "/api/v1/auth/claim-admin",
        json={"token": token, "username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def test_context_reports_needs_bootstrap_when_no_admin(client):
    ctx = client.get("/api/v1/auth/context").json()
    assert ctx["needs_admin_bootstrap"] is True
    assert ctx["authenticated"] is False


def test_claim_admin_then_second_claim_is_gone(client, db_session):
    _claim_admin(client, db_session)
    # The session cookie is set; the new admin is authenticated.
    me = client.get("/api/v1/auth/me").json()
    assert me["role"] == "admin"
    assert me["username"] == "root"

    # A second claim must be rejected — the window is closed.
    from app.auth import bootstrap

    resp = client.post(
        "/api/v1/auth/claim-admin",
        json={"token": bootstrap.get_bootstrap_token() or "x",
              "username": "root2", "password": "adminpass1"},
    )
    assert resp.status_code == 410


def test_claim_admin_rejects_bad_token(client):
    resp = client.post(
        "/api/v1/auth/claim-admin",
        json={"token": "not-the-token", "username": "root", "password": "adminpass1"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Registration toggle + login lifecycle
# ---------------------------------------------------------------------------


def test_register_login_logout_cycle(client):
    reg = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "password123"},
    )
    assert reg.status_code == 200, reg.text
    assert client.get("/api/v1/auth/me").json()["username"] == "alice"

    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401

    bad = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "wrong"},
    )
    assert bad.status_code == 401
    ok = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "password123"},
    )
    assert ok.status_code == 200
    assert client.get("/api/v1/auth/me").json()["username"] == "alice"


def test_registration_can_be_closed(client, db_session):
    from app.settings_service import set_registration_open

    set_registration_open(db_session, False)
    db_session.commit()

    resp = client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "password": "password123"},
    )
    assert resp.status_code == 403


def test_duplicate_username_rejected(client):
    client.post("/api/v1/auth/register", json={"username": "dup", "password": "password123"})
    client.post("/api/v1/auth/logout")
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": "DUP", "password": "password123"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Force-change-on-first-login + admin reset
# ---------------------------------------------------------------------------


def test_force_password_change_flow(client, db_session):
    from app.auth import service

    # Create a user with a temp password requiring change.
    user = service.create_user(
        db_session, username="temp", password="temppass1",
        must_change_password=True,
    )
    db_session.commit()
    assert user.must_change_password is True

    login = client.post(
        "/api/v1/auth/login", json={"username": "temp", "password": "temppass1"},
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True

    # A guarded endpoint should 409 until the password is changed.
    blocked = client.patch("/api/v1/auth/me", json={"display_name": "Temp"})
    assert blocked.status_code == 409

    changed = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "temppass1", "new_password": "brandnew123"},
    )
    assert changed.status_code == 200
    assert changed.json()["must_change_password"] is False

    # Now the guarded endpoint works.
    assert client.patch("/api/v1/auth/me", json={"display_name": "Temp"}).status_code == 200


def test_change_password_revokes_other_sessions(client, db_session):
    client.post("/api/v1/auth/register", json={"username": "carol", "password": "password123"})

    # A second independent client = a second session for the same user.
    other = TestClient(client.app)
    assert other.post(
        "/api/v1/auth/login", json={"username": "carol", "password": "password123"},
    ).status_code == 200
    assert other.get("/api/v1/auth/me").status_code == 200

    # Changing the password on the first client logs the second one out.
    client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "password123", "new_password": "freshpass123"},
    )
    assert other.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 200  # current kept


def test_delete_own_account(client):
    client.post("/api/v1/auth/register", json={"username": "dave", "password": "password123"})
    assert client.delete("/api/v1/auth/me").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
