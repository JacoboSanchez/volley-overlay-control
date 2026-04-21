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
import os

import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from app.admin import admin_page_router, admin_router
from app.api import api_router
from app.overlay.routes import create_overlay_router
from app.overlay.state_store import OverlayStateStore

API_USER_PASSWORD = "user-secret"
ADMIN_PASSWORD = "admin-secret"
OVERLAY_SERVER_TOKEN = "overlay-server-secret"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch, tmp_path):
    monkeypatch.delenv("SCOREBOARD_USERS", raising=False)
    monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD", raising=False)
    monkeypatch.delenv("OVERLAY_SERVER_TOKEN", raising=False)
    monkeypatch.delenv("PREDEFINED_OVERLAYS", raising=False)
    yield


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


@pytest.fixture
def overlay_client_with_server_token(tmp_path, monkeypatch):
    """Overlay router with OVERLAY_SERVER_TOKEN set so F-3/F-5 gates engage."""
    monkeypatch.setenv("OVERLAY_SERVER_TOKEN", OVERLAY_SERVER_TOKEN)
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


def test_strict_oid_access_denies_user_without_control(monkeypatch):
    """With STRICT_OID_ACCESS=true, users lacking 'control' are rejected."""
    users = json.dumps({"alice": {"password": API_USER_PASSWORD}})
    monkeypatch.setenv("SCOREBOARD_USERS", users)
    monkeypatch.setenv("STRICT_OID_ACCESS", "true")

    app = FastAPI()
    app.include_router(api_router)
    client = TestClient(app)

    response = client.post(
        "/api/v1/session/init",
        json={"oid": "anything"},
        headers={"Authorization": f"Bearer {API_USER_PASSWORD}"},
    )
    assert response.status_code == 403


def test_strict_oid_access_off_preserves_open_default(monkeypatch):
    """Without STRICT_OID_ACCESS, users lacking 'control' still pass auth
    (they may still fail downstream for other reasons)."""
    users = json.dumps({"alice": {"password": API_USER_PASSWORD}})
    monkeypatch.setenv("SCOREBOARD_USERS", users)
    monkeypatch.delenv("STRICT_OID_ACCESS", raising=False)

    app = FastAPI()
    app.include_router(api_router)
    client = TestClient(app)

    response = client.get(
        "/api/v1/state?oid=anything",
        headers={"Authorization": f"Bearer {API_USER_PASSWORD}"},
    )
    # Auth must not be the reason for rejection; 404 (no session) is expected.
    assert response.status_code != 403


def test_strict_oid_access_allows_user_with_matching_control(monkeypatch):
    """Strict mode must still let a properly-scoped user through."""
    users = json.dumps({
        "alice": {"password": API_USER_PASSWORD, "control": "alice-oid"},
    })
    monkeypatch.setenv("SCOREBOARD_USERS", users)
    monkeypatch.setenv("STRICT_OID_ACCESS", "true")

    app = FastAPI()
    app.include_router(api_router)
    client = TestClient(app)

    response = client.get(
        "/api/v1/state?oid=alice-oid",
        headers={"Authorization": f"Bearer {API_USER_PASSWORD}"},
    )
    # Auth must pass; 404 (no session yet) is the expected downstream result.
    assert response.status_code != 403


# ---------------------------------------------------------------------------
# Admin API (/api/v1/admin/*) — require_admin
# ---------------------------------------------------------------------------


ADMIN_PROTECTED_ROUTES = [
    ("POST", "/api/v1/admin/login"),
    ("GET", "/api/v1/admin/custom-overlays"),
    ("POST", "/api/v1/admin/custom-overlays"),
    ("DELETE", "/api/v1/admin/custom-overlays/anything"),
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


# Overlay router mutation + leaky read endpoints are gated by
# ``require_overlay_server_token`` (F-3, F-5). These tests pin that
# gate in both postures: enforced when ``OVERLAY_SERVER_TOKEN`` is set,
# and backward-compatible no-op when the env var is unset.


OVERLAY_TOKEN_GATED_ROUTES = [
    ("POST", "/api/state/any-id", {}),
    ("GET", "/create/overlay/any-id", None),
    ("POST", "/create/overlay/any-id", None),
    ("GET", "/delete/overlay/any-id", None),
    ("POST", "/delete/overlay/any-id", None),
    ("DELETE", "/delete/overlay/any-id", None),
    ("POST", "/api/theme/any-id/dark", None),
    ("GET", "/api/raw_config/any-id", None),
    ("POST", "/api/raw_config/any-id", {"model": {}}),
    ("GET", "/api/config/any-id", None),
]


@pytest.mark.parametrize("method,path,body", OVERLAY_TOKEN_GATED_ROUTES)
def test_overlay_server_token_rejects_missing(
    overlay_client_with_server_token, method, path, body,
):
    """F-3/F-5: when OVERLAY_SERVER_TOKEN is set, the gated routes must
    reject requests that omit the Bearer header."""
    response = overlay_client_with_server_token.request(
        method, path, json=body,
    )
    assert response.status_code == 401, (
        f"{method} {path} should 401 without a Bearer token when "
        f"OVERLAY_SERVER_TOKEN is set (got {response.status_code})"
    )


@pytest.mark.parametrize("method,path,body", OVERLAY_TOKEN_GATED_ROUTES)
def test_overlay_server_token_rejects_invalid(
    overlay_client_with_server_token, method, path, body,
):
    response = overlay_client_with_server_token.request(
        method, path, json=body, headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 403, (
        f"{method} {path} should 403 with an invalid Bearer token "
        f"(got {response.status_code})"
    )


@pytest.mark.parametrize("method,path,body", OVERLAY_TOKEN_GATED_ROUTES)
def test_overlay_server_token_accepts_correct(
    overlay_client_with_server_token, method, path, body,
):
    """With the correct token the auth layer steps out of the way; downstream
    business-logic responses (200/404/etc.) are fine — the test only asserts
    the route is no longer rejecting on auth grounds."""
    response = overlay_client_with_server_token.request(
        method, path, json=body,
        headers={"Authorization": f"Bearer {OVERLAY_SERVER_TOKEN}"},
    )
    assert response.status_code not in (401, 403), (
        f"{method} {path} rejected a correct Bearer token "
        f"({response.status_code})"
    )


@pytest.mark.parametrize("method,path,body", OVERLAY_TOKEN_GATED_ROUTES)
def test_overlay_server_token_unset_is_noop(
    overlay_client_no_admin, method, path, body,
):
    """Backward-compat: when OVERLAY_SERVER_TOKEN is unset the dependency
    is a no-op and the gated routes respond without any auth header. The
    startup warning is logged elsewhere."""
    response = overlay_client_no_admin.request(method, path, json=body)
    assert response.status_code not in (401, 403), (
        f"{method} {path} unexpectedly rejected auth with no token "
        f"configured ({response.status_code}). The "
        f"OVERLAY_SERVER_TOKEN=unset path must stay backward-compatible."
    )


def test_overlay_themes_list_is_public(overlay_client_with_server_token):
    """`/api/themes` is intentionally public (see AUTHENTICATION.md §2.3) —
    listing preset theme names is not sensitive."""
    response = overlay_client_with_server_token.get("/api/themes")
    assert response.status_code == 200
    assert "themes" in response.json()


# ---------------------------------------------------------------------------
# Overlay routing: `/overlay/{…}` and `/ws/{…}` must accept both the
# SHA-256 output key and the raw overlay id so friendly URLs keep
# working alongside the capability-style hashed URLs.
# ---------------------------------------------------------------------------


def test_resolve_overlay_id_accepts_raw_id_and_output_key(tmp_path):
    """``resolve_overlay_id`` must resolve both the raw overlay id and
    the SHA-256 output key to the same overlay."""
    from app.overlay.state_store import OverlayStateStore

    raw_id = "f-2-capability-check"
    store = OverlayStateStore(
        data_dir=str(tmp_path / "overlays"),
        templates_dir=str(tmp_path / "templates"),
    )
    store.create_overlay(raw_id)

    assert store.resolve_overlay_id(raw_id) == raw_id, (
        "Raw overlay id must resolve — friendly URLs are a supported entrypoint."
    )

    output_key = OverlayStateStore.get_output_key(raw_id)
    assert store.resolve_overlay_id(output_key) == raw_id, (
        "Output key must still resolve back to the raw id."
    )

    assert store.resolve_overlay_id("does-not-exist") is None


def _make_overlay_app_with_real_templates(tmp_path):
    """Variant of ``_make_overlay_app`` that points Jinja at the real
    overlay templates directory so the rendered HTML reflects what
    production serves. Data directory stays under ``tmp_path`` so the
    test has no filesystem side effects."""
    templates_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "overlay_templates",
    )
    store = OverlayStateStore(
        data_dir=str(tmp_path / "overlays"),
        templates_dir=templates_dir,
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

    templates = Jinja2Templates(directory=templates_dir)
    app = FastAPI()
    app.include_router(create_overlay_router(store, _FakeBroadcast(), templates))
    return app, store


def test_served_overlay_page_uses_output_key_for_ws(tmp_path):
    """The overlay HTML embeds a WebSocket URL. When the page is served
    via /overlay/<output_key>, the template must build wsUrl from the
    output key so /ws/<output_key> resolves. Regression guard for the
    blank-overlay bug where the WS URL used the raw id while the URL
    was an output key."""
    from app.overlay.state_store import OverlayStateStore

    app, store = _make_overlay_app_with_real_templates(tmp_path)
    raw_id = "ws-url-capture"
    store.create_overlay(raw_id)

    output_key = OverlayStateStore.get_output_key(raw_id)
    response = TestClient(app).get(f"/overlay/{output_key}")
    assert response.status_code == 200
    body = response.text
    assert f'OUTPUT_KEY = "{output_key}"' in body, (
        "Rendered overlay must expose OUTPUT_KEY bound to the output key."
    )
    assert '/ws/${OUTPUT_KEY}' in body, (
        "WS URL must be built from OUTPUT_KEY so it resolves server-side."
    )


def test_overlay_page_accepts_raw_id(tmp_path):
    """/overlay/<raw_id> must render the overlay page, mirroring the
    behavior of /overlay/<output_key>."""
    app, store = _make_overlay_app_with_real_templates(tmp_path)
    raw_id = "raw-id-url"
    store.create_overlay(raw_id)

    response = TestClient(app).get(f"/overlay/{raw_id}")
    assert response.status_code == 200
    assert 'OUTPUT_KEY' in response.text


def test_mosaic_style_renders_but_is_not_selectable(tmp_path):
    """The `mosaic` meta-style must be renderable via ``?style=mosaic`` so
    users can preview every overlay side-by-side, but it must not appear
    in ``availableStyles`` (the style picker) — otherwise users could pick
    a meta-style as their broadcast layout.
    """
    app, store = _make_overlay_app_with_real_templates(tmp_path)
    raw_id = "mosaic-preview"
    store.create_overlay(raw_id)

    assert "mosaic" not in store.get_available_styles_list()
    assert "mosaic" in store.get_renderable_styles()

    response = TestClient(app).get(f"/overlay/{raw_id}?style=mosaic")
    assert response.status_code == 200, response.text
    # Server-rendered styles list (avoids a browser fetch to the
    # token-gated /api/config/ endpoint).
    assert "AVAILABLE_STYLES" in response.text
    assert "mosaic-grid" in response.text
