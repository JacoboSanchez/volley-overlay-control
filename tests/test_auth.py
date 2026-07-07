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


def test_claim_admin_auto_closes_registration(client, db_session):
    """With no explicit REGISTRATION_OPEN config, claiming the first admin
    closes public sign-ups (secure-by-default)."""
    from app import settings_service

    assert settings_service.registration_open(db_session) is True
    _claim_admin(client, db_session)

    db_session.expire_all()
    assert settings_service.registration_open(db_session) is False
    ctx = client.get("/api/v1/auth/context").json()
    assert ctx["registration_open"] is False

    anon = TestClient(client.app)
    resp = anon.post(
        "/api/v1/auth/register",
        json={"username": "walkin", "password": "password123"},
    )
    assert resp.status_code == 403


def test_claim_admin_respects_env_pinned_registration(client, db_session, monkeypatch):
    """An explicit REGISTRATION_OPEN=true is an operator choice — the
    first-admin claim must not override it."""
    from app import settings_service

    monkeypatch.setenv("REGISTRATION_OPEN", "true")
    _claim_admin(client, db_session)

    db_session.expire_all()
    assert settings_service.registration_open(db_session) is True


def test_claim_admin_respects_db_pinned_registration(client, db_session):
    """A pre-existing DB row (e.g. an operator opened registration via the
    admin API before re-claiming on a restored instance) is preserved."""
    from app import settings_service

    settings_service.set_registration_open(db_session, True)
    db_session.commit()
    _claim_admin(client, db_session)

    db_session.expire_all()
    assert settings_service.registration_open(db_session) is True


def test_empty_env_seed_counts_as_unset(client, db_session, monkeypatch):
    """docker-compose passes REGISTRATION_OPEN= (empty) when the operator
    left it unconfigured — that must behave exactly like unset."""
    from app import settings_service

    monkeypatch.setenv("REGISTRATION_OPEN", "")
    assert settings_service.registration_open(db_session) is True
    assert settings_service.registration_explicitly_configured(db_session) is False

    _claim_admin(client, db_session)
    db_session.expire_all()
    assert settings_service.registration_open(db_session) is False


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


# ---------------------------------------------------------------------------
# Session resolution: expiry, deactivation, cookie flags (review findings)
# ---------------------------------------------------------------------------


def test_resolve_session_rejects_and_deletes_expired(db_session):
    from datetime import timedelta

    from sqlalchemy import select

    from app.auth import sessions
    from app.db.models.user import AuthSession
    from tests.conftest import make_user

    user = make_user(db_session, "expu")
    raw = sessions.create_session(db_session, user)
    db_session.commit()

    row = db_session.execute(
        select(AuthSession).where(
            AuthSession.token_hash == sessions.hash_token(raw)
        )
    ).scalar_one()
    row.expires_at = sessions._now() - timedelta(hours=1)
    db_session.commit()

    assert sessions.resolve_session(db_session, raw) is None
    # Expired rows are dropped lazily.
    assert db_session.execute(select(AuthSession)).first() is None


def test_resolve_session_rejects_deactivated_user(db_session):
    from sqlalchemy import select

    from app.auth import sessions
    from app.db.models.user import AuthSession
    from tests.conftest import make_user

    user = make_user(db_session, "deactu")
    raw = sessions.create_session(db_session, user)
    db_session.commit()
    user.is_active = False
    db_session.commit()

    assert sessions.resolve_session(db_session, raw) is None
    # Deactivation is reversible, so the row is kept (not deleted) — it is
    # simply unusable while is_active is False.
    assert db_session.execute(select(AuthSession)).first() is not None


def test_deactivated_user_is_logged_out_on_next_request(client, db_session):
    from sqlalchemy import select

    from app.db.models.user import User
    from tests.conftest import make_user

    make_user(db_session, "normo", password="password123")
    assert client.post(
        "/api/v1/auth/login", json={"username": "normo", "password": "password123"}
    ).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200

    # Admin deactivates the account out-of-band; the existing cookie must stop working.
    u = db_session.execute(select(User).where(User.username == "normo")).scalar_one()
    u.is_active = False
    db_session.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_session_cookie_is_httponly_and_samesite_lax(client, db_session):
    resp = _claim_admin(client, db_session)
    set_cookie = resp.headers.get("set-cookie", "")
    assert "vsession=" in set_cookie
    low = set_cookie.lower()
    assert "httponly" in low
    assert "samesite=lax" in low


def test_cookie_secure_follows_env_then_scheme(monkeypatch):
    from app.auth import sessions

    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    assert sessions.cookie_secure("https") is True
    assert sessions.cookie_secure("http") is False
    # An explicit override wins over the request scheme either way.
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    assert sessions.cookie_secure("http") is True
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    assert sessions.cookie_secure("https") is False


def test_concurrent_claims_leave_exactly_one_admin(client, db_session):
    """Two simultaneous valid-token claims must produce a single admin —
    the claim lock serializes them and the loser gets 410."""
    import threading

    from app.auth import bootstrap

    token = bootstrap.get_bootstrap_token()
    assert token
    barrier = threading.Barrier(2)
    results: list[int] = []

    def claim(username: str) -> None:
        barrier.wait()
        resp = TestClient(client.app).post(
            "/api/v1/auth/claim-admin",
            json={"token": token, "username": username, "password": "adminpass1"},
        )
        results.append(resp.status_code)

    threads = [threading.Thread(target=claim, args=(f"root{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [200, 410], results
    from sqlalchemy import func, select

    from app.db.models.user import ROLE_ADMIN, User

    admins = db_session.execute(
        select(func.count()).select_from(User).where(User.role == ROLE_ADMIN)
    ).scalar_one()
    assert admins == 1


def test_registration_race_maps_integrity_error_to_400(client, db_session, monkeypatch):
    """When two registrations race past the duplicate pre-check, the loser
    must get the normal duplicate-username 400, not a 500."""
    from app.auth import service

    # Simulate the race: the pre-check sees no duplicate, but the row
    # already exists when the INSERT flushes.
    monkeypatch.setattr(service, "get_by_username", lambda db, u: None)
    client.post(
        "/api/v1/auth/register",
        json={"username": "dupe", "password": "password123"},
    )
    resp = TestClient(client.app).post(
        "/api/v1/auth/register",
        json={"username": "dupe", "password": "password123"},
    )
    assert resp.status_code == 400
    assert "already" in resp.json()["detail"].lower()
