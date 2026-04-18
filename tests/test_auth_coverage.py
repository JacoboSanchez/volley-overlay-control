"""Tripwire tests pinning the authentication coverage documented in
``AUTHENTICATION.md``. Any change to the auth behavior of a route
below should update the expected status codes here and the companion
entry in ``AUTHENTICATION.md``.

The tests deliberately assert on *coarse* outcomes: either "auth
rejects" (``401``/``403``) or "auth is not consulted" (anything else).
They do not care about downstream business-logic responses, so
fixtures stay minimal and the matrix is easy to scan.
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.templating import Jinja2Templates

from app.admin import admin_page_router, admin_router
from app.admin.store import managed_overlays_store
from app.api import api_router
from app.overlay.routes import create_overlay_router
from app.overlay.state_store import OverlayStateStore


API_USER_PASSWORD = "user-secret"
ADMIN_PASSWORD = "admin-secret"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch, tmp_path):
    managed_overlays_store._reset_for_tests(str(tmp_path / "admin"))
    monkeypatch.delenv("SCOREBOARD_USERS", raising=False)
    monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD", raising=False)
    monkeypatch.delenv("PREDEFINED_OVERLAYS", raising=False)
    yield
    managed_overlays_store._reset_for_tests(str(tmp_path / "admin"))


@pytest.fixture
def api_client_with_users(monkeypatch):
    users = json.dumps({"alice": {"password": API_USER_PASSWORD}})
    monkeypatch.setenv("SCOREBOARD_USERS", users)
    app = FastAPI()
    app.include_router(api_router)
    return TestClient(app)


@pytest.fixture
def admin_client(monkeypatch):
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", ADMIN_PASSWORD)
    app = FastAPI()
    app.include_router(admin_page_router)
    app.include_router(admin_router)
    return TestClient(app)


def _make_overlay_app(tmp_path):
    store = OverlayStateStore(
        data_dir=str(tmp_path / "overlays"),
        templates_dir=str(tmp_path / "templates"),
    )

    class _FakeBroadcast:
        def get_client_count(self, _overlay_id):
            return 0

        async def cleanup_overlay(self, _overlay_id):
            return None

        def add_client(self, *_args, **_kwargs):
            return None

        def remove_client(self, *_args, **_kwargs):
            return None

    templates = Jinja2Templates(directory=str(tmp_path / "templates"))
    app = FastAPI()
    app.include_router(create_overlay_router(store, _FakeBroadcast(), templates))
    return app


@pytest.fixture
def overlay_client_no_admin(tmp_path):
    """Overlay router with no admin password configured."""
    return TestClient(_make_overlay_app(tmp_path))


@pytest.fixture
def overlay_client_with_admin(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", ADMIN_PASSWORD)
    return TestClient(_make_overlay_app(tmp_path))


# ---------------------------------------------------------------------------
# Scoreboard REST API (/api/v1/*) — verify_api_key
# ---------------------------------------------------------------------------


SCOREBOARD_SAMPLE_ROUTES = [
    ("GET", "/api/v1/state?oid=anything"),
    ("GET", "/api/v1/customization?oid=anything"),
    ("GET", "/api/v1/config?oid=anything"),
    ("GET", "/api/v1/teams"),
    ("GET", "/api/v1/themes"),
    ("GET", "/api/v1/overlays"),
    ("GET", "/api/v1/links?oid=anything"),
    ("GET", "/api/v1/styles?oid=anything"),
    ("POST", "/api/v1/session/init"),
    ("POST", "/api/v1/game/add-point?oid=anything"),
    ("POST", "/api/v1/game/add-set?oid=anything"),
    ("POST", "/api/v1/game/add-timeout?oid=anything"),
    ("POST", "/api/v1/game/change-serve?oid=anything"),
    ("POST", "/api/v1/game/set-score?oid=anything"),
    ("POST", "/api/v1/game/set-sets?oid=anything"),
    ("POST", "/api/v1/game/reset?oid=anything"),
    ("POST", "/api/v1/display/visibility?oid=anything"),
    ("POST", "/api/v1/display/simple-mode?oid=anything"),
    ("PUT", "/api/v1/customization?oid=anything"),
]


@pytest.mark.parametrize("method,path", SCOREBOARD_SAMPLE_ROUTES)
def test_scoreboard_api_rejects_missing_token(api_client_with_users, method, path):
    response = api_client_with_users.request(method, path, json={})
    assert response.status_code == 401, (
        f"{method} {path} should 401 without a Bearer token when "
        f"SCOREBOARD_USERS is set (got {response.status_code})"
    )


@pytest.mark.parametrize("method,path", SCOREBOARD_SAMPLE_ROUTES)
def test_scoreboard_api_rejects_invalid_token(api_client_with_users, method, path):
    response = api_client_with_users.request(
        method, path, json={}, headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 403, (
        f"{method} {path} should 403 with an invalid Bearer token "
        f"(got {response.status_code})"
    )


# ---------------------------------------------------------------------------
# Admin API (/api/v1/admin/*) — require_admin
# ---------------------------------------------------------------------------


ADMIN_PROTECTED_ROUTES = [
    ("POST", "/api/v1/admin/login"),
    ("GET", "/api/v1/admin/overlays"),
    ("POST", "/api/v1/admin/overlays"),
    ("PUT", "/api/v1/admin/overlays/anything"),
    ("DELETE", "/api/v1/admin/overlays/anything"),
]


@pytest.mark.parametrize("method,path", ADMIN_PROTECTED_ROUTES)
def test_admin_api_rejects_missing_token(admin_client, method, path):
    response = admin_client.request(method, path, json={})
    assert response.status_code == 401


@pytest.mark.parametrize("method,path", ADMIN_PROTECTED_ROUTES)
def test_admin_api_rejects_invalid_token(admin_client, method, path):
    response = admin_client.request(
        method, path, json={}, headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 403


def test_admin_status_is_public(admin_client):
    """`/api/v1/admin/status` intentionally exposes only a boolean."""
    response = admin_client.get("/api/v1/admin/status")
    assert response.status_code == 200
    assert response.json() == {"enabled": True}


# ---------------------------------------------------------------------------
# Overlay router — /list/overlay is gated; mutation routes are currently open
# ---------------------------------------------------------------------------


def test_list_overlay_requires_admin_when_configured(overlay_client_with_admin):
    """F-4: `/list/overlay` now requires OVERLAY_MANAGER_PASSWORD."""
    missing = overlay_client_with_admin.get("/list/overlay")
    assert missing.status_code == 401

    wrong = overlay_client_with_admin.get(
        "/list/overlay", headers={"Authorization": "Bearer wrong"},
    )
    assert wrong.status_code == 403

    ok = overlay_client_with_admin.get(
        "/list/overlay", headers={"Authorization": f"Bearer {ADMIN_PASSWORD}"},
    )
    assert ok.status_code == 200
    assert "overlays" in ok.json()


def test_list_overlay_disabled_when_admin_unset(overlay_client_no_admin):
    """When OVERLAY_MANAGER_PASSWORD is unset, `/list/overlay` returns 503
    instead of leaking overlay ids + output keys (was 200 pre-audit)."""
    response = overlay_client_no_admin.get("/list/overlay")
    assert response.status_code == 503


# The following routes are documented as *unauthenticated* (findings F-3
# and F-5). These tests pin the current behavior so that adding auth to
# any of them surfaces in this file instead of slipping through silently.
# When a follow-up PR fixes F-3 / F-5, update the expected assertions.


OVERLAY_OPEN_MUTATION_ROUTES = [
    ("POST", "/api/state/any-id", {}),
    ("GET", "/create/overlay/any-id", None),
    ("POST", "/create/overlay/any-id", None),
    ("GET", "/delete/overlay/any-id", None),
    ("POST", "/delete/overlay/any-id", None),
    ("DELETE", "/delete/overlay/any-id", None),
    ("POST", "/api/theme/any-id/dark", None),
]


@pytest.mark.parametrize("method,path,body", OVERLAY_OPEN_MUTATION_ROUTES)
def test_overlay_mutation_routes_are_currently_open(
    overlay_client_with_admin, method, path, body,
):
    """F-3: these routes accept writes with no auth header. Test pins the
    status quo so a future fix updates this file."""
    response = overlay_client_with_admin.request(method, path, json=body)
    assert response.status_code not in (401, 403), (
        f"{method} {path} unexpectedly rejected auth "
        f"({response.status_code}). If this is the intended behavior, "
        f"update AUTHENTICATION.md F-3 and flip this assertion."
    )


OVERLAY_OPEN_READ_ROUTES = [
    ("GET", "/api/config/any-id"),
    ("GET", "/api/themes"),
]


@pytest.mark.parametrize("method,path", OVERLAY_OPEN_READ_ROUTES)
def test_overlay_read_routes_are_currently_open(
    overlay_client_with_admin, method, path,
):
    """F-5: these routes return data without auth. `/api/themes` is
    intentionally public; `/api/config/{id}` is a known leak."""
    response = overlay_client_with_admin.request(method, path)
    assert response.status_code not in (401, 403)


def test_overlay_raw_config_get_is_currently_open(overlay_client_with_admin):
    """F-5: raw_config returns 404 on missing overlays — still reachable
    without auth, which is the leak we are documenting."""
    response = overlay_client_with_admin.get("/api/raw_config/any-id")
    assert response.status_code not in (401, 403)


def test_overlay_raw_config_post_is_currently_open(overlay_client_with_admin):
    """F-3: raw_config POST mutates state with no auth header."""
    response = overlay_client_with_admin.post(
        "/api/raw_config/any-id", json={"model": {}},
    )
    assert response.status_code not in (401, 403)
