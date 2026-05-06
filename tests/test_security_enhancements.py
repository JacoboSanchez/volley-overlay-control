"""Coverage for the security-hardening middlewares and validators.

Pins:

* :mod:`app.api.middleware.security_headers` — every response carries
  the always-on headers; HTML responses additionally carry CSP and
  ``X-Frame-Options``; ``/api/v1/`` JSON gains ``Cache-Control:
  no-store``.
* :mod:`app.api.middleware.auth_rate_limit` — repeated 401/403 from
  the same client IP eventually flips to 429 with ``Retry-After``.
* :mod:`app.api.schemas.is_safe_logo_url` and the customization
  payload caps in :mod:`app.api.game_service`.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin import admin_router
from app.api.middleware import auth_rate_limit
from app.api.middleware.auth_rate_limit import AuthRateLimitMiddleware
from app.api.middleware.security_headers import SecurityHeadersMiddleware
from app.api.schemas import (
    MAX_LOGO_VALUE_LENGTH,
    MAX_STRING_VALUE_LENGTH,
    is_safe_logo_url,
)

# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


def _build_headers_app() -> FastAPI:
    """Minimal app exercising all three response-shape branches."""
    app = FastAPI()

    @app.get("/api/v1/state")
    def api_json():
        return {"ok": True}

    @app.get("/manage", response_class=None)
    def manage_html():
        from fastapi.responses import HTMLResponse
        return HTMLResponse("<!doctype html><title>x</title>")

    @app.get("/overlay/x", response_class=None)
    def overlay_html():
        from fastapi.responses import HTMLResponse
        return HTMLResponse("<!doctype html><title>x</title>")

    app.add_middleware(SecurityHeadersMiddleware)
    return app


@pytest.fixture
def headers_client():
    return TestClient(_build_headers_app())


def test_always_on_headers_present_on_json(headers_client):
    res = headers_client.get("/api/v1/state")
    assert res.status_code == 200
    assert res.headers["x-content-type-options"] == "nosniff"
    assert "referrer-policy" in res.headers
    assert "permissions-policy" in res.headers
    # JSON responses should not get CSP / XFO (HTML-only headers).
    assert "content-security-policy" not in res.headers
    assert "x-frame-options" not in res.headers


def test_api_v1_response_disables_caching(headers_client):
    res = headers_client.get("/api/v1/state")
    assert res.headers.get("cache-control") == "no-store"


def test_html_response_carries_csp_and_xframe(headers_client):
    res = headers_client.get("/manage")
    assert res.status_code == 200
    csp = res.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'self'" in csp
    assert res.headers.get("x-frame-options") == "SAMEORIGIN"


def test_overlay_html_relaxes_frame_ancestors(headers_client):
    res = headers_client.get("/overlay/x")
    csp = res.headers.get("content-security-policy", "")
    # OBS browser sources need to embed cross-origin.
    assert "frame-ancestors *" in csp
    # No legacy XFO that would block embedding either.
    assert "x-frame-options" not in res.headers


def test_existing_cache_control_is_preserved(headers_client, monkeypatch):
    app = FastAPI()

    @app.get("/api/v1/cached")
    def cached():
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"ok": True}, headers={"Cache-Control": "public, max-age=60"},
        )

    app.add_middleware(SecurityHeadersMiddleware)
    client = TestClient(app)
    res = client.get("/api/v1/cached")
    assert res.headers["cache-control"] == "public, max-age=60"


def test_hsts_opt_in(monkeypatch):
    monkeypatch.setenv("SECURITY_HSTS_SECONDS", "86400")
    app = FastAPI()

    @app.get("/api/v1/state")
    def s():
        return {"ok": True}

    app.add_middleware(SecurityHeadersMiddleware)
    res = TestClient(app).get("/api/v1/state")
    assert "strict-transport-security" in res.headers
    assert "max-age=86400" in res.headers["strict-transport-security"]


# ---------------------------------------------------------------------------
# Auth rate limiting
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    auth_rate_limit._reset_for_tests()
    yield
    auth_rate_limit._reset_for_tests()


def _build_rate_limit_app(monkeypatch) -> FastAPI:
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "correct-horse")
    app = FastAPI()
    app.include_router(admin_router)
    app.add_middleware(AuthRateLimitMiddleware)
    return app


def test_rate_limit_blocks_after_repeated_failures(monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX_FAILURES", "3")
    monkeypatch.setenv("AUTH_RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("AUTH_RATE_LIMIT_BLOCK_SECONDS", "60")
    # Module reads its tunables at import time, so reload them.
    import importlib

    importlib.reload(auth_rate_limit)
    from app.api.middleware.auth_rate_limit import AuthRateLimitMiddleware as M

    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "correct-horse")
    app = FastAPI()
    app.include_router(admin_router)
    app.add_middleware(M)
    client = TestClient(app)

    bad = {"Authorization": "Bearer wrong"}
    # 3 failures fill the bucket, the 4th request must be blocked.
    for _ in range(3):
        assert client.post("/api/v1/admin/login", headers=bad).status_code == 403
    res = client.post("/api/v1/admin/login", headers=bad)
    assert res.status_code == 429
    assert res.headers.get("retry-after")
    # And subsequent attempts stay blocked, including with a *correct*
    # password — the bucket gates the IP, not the credential.
    good = {"Authorization": "Bearer correct-horse"}
    res = client.post("/api/v1/admin/login", headers=good)
    assert res.status_code == 429


def test_rate_limit_resets_on_success(monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX_FAILURES", "5")
    import importlib

    importlib.reload(auth_rate_limit)
    from app.api.middleware.auth_rate_limit import AuthRateLimitMiddleware as M

    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "correct-horse")
    app = FastAPI()
    app.include_router(admin_router)
    app.add_middleware(M)
    client = TestClient(app)

    bad = {"Authorization": "Bearer wrong"}
    good = {"Authorization": "Bearer correct-horse"}
    for _ in range(2):
        assert client.post("/api/v1/admin/login", headers=bad).status_code == 403
    # A success drops the bucket entirely.
    assert client.post("/api/v1/admin/login", headers=good).status_code == 200
    # Another four failures should still be allowed (fresh bucket).
    for _ in range(4):
        assert client.post("/api/v1/admin/login", headers=bad).status_code == 403


def test_rate_limit_ignores_unwatched_paths(monkeypatch):
    """A 401 from outside the watched prefix list should not poison the bucket."""
    import importlib

    importlib.reload(auth_rate_limit)
    from app.api.middleware.auth_rate_limit import AuthRateLimitMiddleware as M

    app = FastAPI()
    app.add_middleware(M)

    @app.get("/random")
    def r():
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="nope")

    client = TestClient(app)
    # 100 failures on /random must never trigger 429; the path isn't watched.
    for _ in range(100):
        assert client.get("/random").status_code == 401


# ---------------------------------------------------------------------------
# Logo URL allow-list
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "https://cdn.example.com/logo.png",
    "http://example.com/logo.svg",
    "//cdn.example.com/logo.png",
    "data:image/png;base64,iVBORw0KGgo=",
    "  https://example.com/logo.png  ",
])
def test_logo_url_accepts_safe_schemes(url):
    assert is_safe_logo_url(url) is True


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox",
    "file:///etc/passwd",
    "",
    "   ",
    None,
    123,
])
def test_logo_url_rejects_unsafe(url):
    assert is_safe_logo_url(url) is False


def test_logo_url_rejects_overlong():
    assert is_safe_logo_url("https://" + "a" * (MAX_LOGO_VALUE_LENGTH + 1)) is False


# ---------------------------------------------------------------------------
# Customization payload caps
# ---------------------------------------------------------------------------


def test_update_customization_rejects_unsafe_logo(api_session):
    from app.api.game_service import GameService

    res = GameService.update_customization(
        api_session, {"Team 1 Logo": "javascript:alert(1)"},
    )
    assert res.success is False
    assert "scheme" in (res.message or "").lower()


def test_update_customization_rejects_overlong_string(api_session):
    from app.api.game_service import GameService

    res = GameService.update_customization(
        api_session,
        {"Team 1 Name": "A" * (MAX_STRING_VALUE_LENGTH + 1)},
    )
    assert res.success is False
    assert "exceeds" in (res.message or "").lower()


def test_update_customization_rejects_too_many_keys(api_session):
    from app.api.game_service import GameService
    from app.api.schemas import MAX_CUSTOMIZATION_KEYS

    payload = {f"k{i}": "v" for i in range(MAX_CUSTOMIZATION_KEYS + 1)}
    res = GameService.update_customization(api_session, payload)
    assert res.success is False
    assert "keys" in (res.message or "").lower()


def test_update_customization_accepts_safe_payload(api_session):
    from app.api.game_service import GameService

    res = GameService.update_customization(
        api_session,
        {
            "Team 1 Name": "Wolves",
            "Team 1 Logo": "https://example.com/wolves.png",
            "Team 2 Logo": "data:image/svg+xml;base64,PHN2Zy8+",
        },
    )
    assert res.success is True


def test_update_customization_rejects_non_dict(api_session):
    from app.api.game_service import GameService

    res = GameService.update_customization(api_session, "not a dict")
    assert res.success is False
