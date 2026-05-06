"""Integration coverage for hashed-credential support across the three
auth surfaces extended in PR 4 of the security plan:

* ``SCOREBOARD_USERS`` user entries — ``password_hash`` field accepted
  alongside legacy ``password``.
* ``OVERLAY_MANAGER_PASSWORD_HASH`` — admin Bearer credential.
* ``OVERLAY_SERVER_TOKEN_HASH`` — overlay-server mutation gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import password_hash, security_bootstrap
from app.admin import admin_router
from app.api.middleware import auth_rate_limit
from app.api.session_manager import SessionManager
from app.api.ws_hub import WSHub
from app.authentication import PasswordAuthenticator
from app.overlay.routes import _get_overlay_server_credential


# Use light scrypt parameters so the test suite stays under a second.
@pytest.fixture
def fast_hash(monkeypatch):
    """Return a callable that produces hashes with light scrypt params.

    Default ``n=16384`` would add ~50 ms × 30 tests = ~1.5 s; the
    light params (``n=1024``) keep verification well under 5 ms.
    """
    def _hash(pw: str) -> str:
        return password_hash.hash_password(pw, n=1024, r=4, p=1)
    return _hash


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("SCOREBOARD_USERS", raising=False)
    monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD", raising=False)
    monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("OVERLAY_SERVER_TOKEN", raising=False)
    monkeypatch.delenv("OVERLAY_SERVER_TOKEN_HASH", raising=False)
    monkeypatch.delenv("OVERLAY_SERVER_TOKEN_DISABLED", raising=False)
    PasswordAuthenticator._cached_users = None
    PasswordAuthenticator._cached_users_raw = None
    PasswordAuthenticator._verify_cache.clear()
    SessionManager.clear()
    WSHub.clear()
    auth_rate_limit._reset_for_tests()
    yield
    PasswordAuthenticator._cached_users = None
    PasswordAuthenticator._cached_users_raw = None
    PasswordAuthenticator._verify_cache.clear()
    SessionManager.clear()
    WSHub.clear()
    auth_rate_limit._reset_for_tests()


# ---------------------------------------------------------------------------
# SCOREBOARD_USERS — password_hash field
# ---------------------------------------------------------------------------


def test_scoreboard_users_accepts_password_hash(monkeypatch, fast_hash):
    monkeypatch.setenv(
        "SCOREBOARD_USERS",
        json.dumps({
            "alice": {"password_hash": fast_hash("alice-pw")},
        }),
    )
    assert PasswordAuthenticator.check_api_key("alice-pw") is True
    assert PasswordAuthenticator.check_api_key("wrong") is False
    assert PasswordAuthenticator.get_username_for_api_key("alice-pw") == "alice"


def test_scoreboard_users_legacy_plaintext_still_works(monkeypatch):
    monkeypatch.setenv(
        "SCOREBOARD_USERS",
        json.dumps({"bob": {"password": "bob-pw"}}),
    )
    assert PasswordAuthenticator.check_api_key("bob-pw") is True


def test_scoreboard_users_hash_takes_precedence_over_plaintext(
    monkeypatch, fast_hash,
):
    """An entry with both fields uses the hash; the plaintext is ignored.

    Operators in the middle of a migration shouldn't have to delete
    the plaintext value to switch over.
    """
    monkeypatch.setenv(
        "SCOREBOARD_USERS",
        json.dumps({
            "carol": {
                "password": "old-plaintext",
                "password_hash": fast_hash("new-hashed"),
            },
        }),
    )
    assert PasswordAuthenticator.check_api_key("new-hashed") is True
    # The plaintext field is ignored when a hash is also configured —
    # otherwise the migration would leave both credentials valid
    # forever, which defeats the rotation story.
    assert PasswordAuthenticator.check_api_key("old-plaintext") is False


def test_scoreboard_users_mixed_entries(monkeypatch, fast_hash):
    """One user on plaintext, another on hash — both authenticate."""
    monkeypatch.setenv(
        "SCOREBOARD_USERS",
        json.dumps({
            "legacy": {"password": "legacy-pw"},
            "modern": {"password_hash": fast_hash("modern-pw")},
        }),
    )
    assert PasswordAuthenticator.get_username_for_api_key("legacy-pw") == "legacy"
    assert PasswordAuthenticator.get_username_for_api_key("modern-pw") == "modern"


def test_verify_cache_short_circuits_repeat_lookups(monkeypatch, fast_hash):
    """Cached verifications skip the expensive scrypt path."""
    monkeypatch.setenv(
        "SCOREBOARD_USERS",
        json.dumps({"dave": {"password_hash": fast_hash("dave-pw")}}),
    )
    # First call populates the cache.
    assert PasswordAuthenticator.get_username_for_api_key("dave-pw") == "dave"
    # Pin a different verifier to detect cache use: if the cache is
    # working, the second call must return the cached "dave" without
    # invoking ``verify_password`` at all.
    calls = {"n": 0}

    def counting_verify(provided, stored):
        calls["n"] += 1
        return password_hash.verify_password(provided, stored)

    monkeypatch.setattr(
        "app.authentication.verify_password", counting_verify,
    )
    # Within the TTL, the cache returns the username immediately.
    assert PasswordAuthenticator.get_username_for_api_key("dave-pw") == "dave"
    assert calls["n"] == 0


def test_verify_cache_invalidated_on_user_rotation(monkeypatch, fast_hash):
    """Removing a user from SCOREBOARD_USERS must invalidate cached entries."""
    monkeypatch.setenv(
        "SCOREBOARD_USERS",
        json.dumps({"erin": {"password_hash": fast_hash("erin-pw")}}),
    )
    assert PasswordAuthenticator.check_api_key("erin-pw") is True
    # Rotate the env var: erin is gone.
    monkeypatch.setenv(
        "SCOREBOARD_USERS",
        json.dumps({"frank": {"password_hash": fast_hash("frank-pw")}}),
    )
    assert PasswordAuthenticator.check_api_key("erin-pw") is False
    assert PasswordAuthenticator.check_api_key("frank-pw") is True


def test_has_hashed_credentials_reports_correctly(monkeypatch, fast_hash):
    monkeypatch.setenv(
        "SCOREBOARD_USERS",
        json.dumps({"u": {"password": "p"}}),
    )
    assert PasswordAuthenticator.has_hashed_credentials() is False
    monkeypatch.setenv(
        "SCOREBOARD_USERS",
        json.dumps({"u": {"password_hash": fast_hash("p")}}),
    )
    assert PasswordAuthenticator.has_hashed_credentials() is True


# ---------------------------------------------------------------------------
# OVERLAY_MANAGER_PASSWORD_HASH — admin Bearer
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_app(monkeypatch):
    app = FastAPI()
    app.include_router(admin_router)
    return app


def test_admin_login_accepts_hashed_credential(monkeypatch, fast_hash, admin_app):
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD_HASH", fast_hash("admin-pw"))
    client = TestClient(admin_app)
    res = client.post(
        "/api/v1/admin/login",
        headers={"Authorization": "Bearer admin-pw"},
    )
    assert res.status_code == 200
    bad = client.post(
        "/api/v1/admin/login",
        headers={"Authorization": "Bearer wrong"},
    )
    assert bad.status_code == 403


def test_admin_login_legacy_plaintext_still_works(monkeypatch, admin_app):
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "admin-pw")
    client = TestClient(admin_app)
    res = client.post(
        "/api/v1/admin/login",
        headers={"Authorization": "Bearer admin-pw"},
    )
    assert res.status_code == 200


def test_admin_hash_takes_precedence_over_plaintext(
    monkeypatch, fast_hash, admin_app,
):
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "old-plaintext")
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD_HASH", fast_hash("new-hashed"))
    client = TestClient(admin_app)
    # The hash wins — the plaintext value no longer authenticates.
    res = client.post(
        "/api/v1/admin/login",
        headers={"Authorization": "Bearer old-plaintext"},
    )
    assert res.status_code == 403
    res = client.post(
        "/api/v1/admin/login",
        headers={"Authorization": "Bearer new-hashed"},
    )
    assert res.status_code == 200


def test_admin_status_503_when_neither_credential_set(monkeypatch, admin_app):
    client = TestClient(admin_app)
    res = client.get("/api/v1/admin/custom-overlays",
                     headers={"Authorization": "Bearer x"})
    assert res.status_code == 503


# ---------------------------------------------------------------------------
# OVERLAY_SERVER_TOKEN_HASH — overlay router gate
# ---------------------------------------------------------------------------


def _build_overlay_app(tmp_path: Path):
    """Mount the overlay router with isolated state for the auth tests."""
    from fastapi.templating import Jinja2Templates

    from app.overlay.broadcast import ObsBroadcastHub
    from app.overlay.routes import create_overlay_router
    from app.overlay.state_store import OverlayStateStore

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "index.html").write_text("ok")
    store = OverlayStateStore(
        data_dir=str(tmp_path / "overlays"),
        templates_dir=str(templates_dir),
    )
    store.create_overlay("ovl-1")
    hub = ObsBroadcastHub()
    app = FastAPI()
    app.include_router(create_overlay_router(store, hub, Jinja2Templates(directory=str(templates_dir))))
    return app


def test_overlay_token_hash_gates_mutation_endpoint(
    monkeypatch, fast_hash, tmp_path,
):
    monkeypatch.setenv("OVERLAY_SERVER_TOKEN_HASH", fast_hash("server-pw"))
    client = TestClient(_build_overlay_app(tmp_path))

    # Missing header → 401.
    res = client.post("/api/state/ovl-1", json={})
    assert res.status_code == 401
    # Wrong token → 403.
    res = client.post(
        "/api/state/ovl-1", json={},
        headers={"Authorization": "Bearer wrong"},
    )
    assert res.status_code == 403
    # Correct token → 200.
    res = client.post(
        "/api/state/ovl-1", json={},
        headers={"Authorization": "Bearer server-pw"},
    )
    assert res.status_code == 200


def test_overlay_token_legacy_plaintext_still_works(monkeypatch, tmp_path):
    monkeypatch.setenv("OVERLAY_SERVER_TOKEN", "server-pw")
    client = TestClient(_build_overlay_app(tmp_path))
    res = client.post(
        "/api/state/ovl-1", json={},
        headers={"Authorization": "Bearer server-pw"},
    )
    assert res.status_code == 200


def test_overlay_token_hash_takes_precedence(monkeypatch, fast_hash, tmp_path):
    monkeypatch.setenv("OVERLAY_SERVER_TOKEN", "old-plaintext")
    monkeypatch.setenv("OVERLAY_SERVER_TOKEN_HASH", fast_hash("new-hashed"))
    client = TestClient(_build_overlay_app(tmp_path))
    bad = client.post(
        "/api/state/ovl-1", json={},
        headers={"Authorization": "Bearer old-plaintext"},
    )
    assert bad.status_code == 403
    good = client.post(
        "/api/state/ovl-1", json={},
        headers={"Authorization": "Bearer new-hashed"},
    )
    assert good.status_code == 200


def test_get_overlay_server_credential_prefers_hash(monkeypatch, fast_hash):
    monkeypatch.setenv("OVERLAY_SERVER_TOKEN", "old-plaintext")
    monkeypatch.setenv("OVERLAY_SERVER_TOKEN_HASH", fast_hash("new-hashed"))
    cred = _get_overlay_server_credential()
    assert cred is not None
    assert cred.startswith("scrypt$")


# ---------------------------------------------------------------------------
# security_bootstrap — hash-only configuration skips auto-generation
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(security_bootstrap, "_data_dir", lambda: str(tmp_path))
    return tmp_path


def test_bootstrap_skips_auto_gen_when_hash_set(
    isolated_data_dir, monkeypatch, fast_hash,
):
    monkeypatch.setenv("OVERLAY_SERVER_TOKEN_HASH", fast_hash("server-pw"))
    result = security_bootstrap.ensure_overlay_server_token()
    # Hash-only deployments deliberately keep no plaintext on this
    # server: bootstrap returns None and never writes the persisted
    # token file.
    assert result is None
    assert "OVERLAY_SERVER_TOKEN" not in __import__("os").environ
    assert not (isolated_data_dir / ".overlay_server_token").exists()


def test_bootstrap_auto_gen_when_hash_unset(isolated_data_dir, monkeypatch):
    """Without a hash, auto-generation still runs (regression check)."""
    monkeypatch.delenv("OVERLAY_SERVER_TOKEN_HASH", raising=False)
    monkeypatch.delenv("OVERLAY_SERVER_TOKEN", raising=False)
    result = security_bootstrap.ensure_overlay_server_token()
    assert result is not None
    assert (isolated_data_dir / ".overlay_server_token").exists()
