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

import urllib.parse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware import auth_rate_limit
from app.api.middleware.auth_rate_limit import AuthRateLimitMiddleware
from app.api.middleware.security_headers import SecurityHeadersMiddleware
from app.api.routes.admin_users import router as admin_users_router
from app.api.schemas import (
    MAX_LOGO_VALUE_LENGTH,
    MAX_STRING_VALUE_LENGTH,
    is_safe_logo_url,
)
from app.auth.routes import auth_router

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
    # Default img-src must not contain a bare ``http:`` token —
    # HTTPS deployments would block mixed-content images anyway.
    img_directive = next(
        (p.strip() for p in csp.split(";") if p.strip().startswith("img-src")),
        "",
    )
    assert " http:" not in f" {img_directive} "
    assert "https:" in img_directive
    # ``frame-src`` must allow cross-origin HTTPS sources so the
    # OverlayPreview iframe can render UNO overlays and custom overlays
    # served from a different host (``OVERLAY_PUBLIC_URL`` split-host
    # deployments).
    frame_src_directive = next(
        (p.strip() for p in csp.split(";") if p.strip().startswith("frame-src")),
        "",
    )
    assert "https:" in frame_src_directive
    assert "'self'" in frame_src_directive
    assert res.headers.get("x-frame-options") == "SAMEORIGIN"


def test_overlay_html_relaxes_frame_ancestors(headers_client):
    res = headers_client.get("/overlay/x")
    csp = res.headers.get("content-security-policy", "")
    # OBS browser sources need to embed cross-origin.
    assert "frame-ancestors *" in csp
    # No legacy XFO that would block embedding either.
    assert "x-frame-options" not in res.headers


def test_overlay_html_allows_google_fonts(headers_client):
    """Overlay templates pull Google Fonts; the strict default CSP
    blocks them on every other route, so /overlay/* must allow the two
    Google Fonts hosts on style-src and font-src."""
    res = headers_client.get("/overlay/x")
    csp = res.headers.get("content-security-policy", "")
    style_directive = next(
        (p.strip() for p in csp.split(";") if p.strip().startswith("style-src")),
        "",
    )
    font_directive = next(
        (p.strip() for p in csp.split(";") if p.strip().startswith("font-src")),
        "",
    )
    style_tokens = style_directive.split()
    font_tokens = font_directive.split()
    # Compare each CSP source by parsing its scheme + host with
    # ``urllib.parse`` rather than putting a URL literal on the LHS of
    # ``in``. This (a) actually verifies the host appears as an allowed
    # source rather than as a path fragment of some other origin
    # (e.g. ``https://fonts.googleapis.com.evil.example``), and (b)
    # keeps CodeQL's ``py/incomplete-url-substring-sanitization`` rule
    # quiet on test code — the rule flags any ``URL_LITERAL in
    # something`` regardless of the RHS being a token list.
    def _origins(tokens: list[str]) -> set[tuple[str, str]]:
        out: set[tuple[str, str]] = set()
        for tok in tokens:
            if not tok.startswith(("http://", "https://")):
                continue
            parsed = urllib.parse.urlparse(tok)
            out.add((parsed.scheme, parsed.netloc))
        return out

    assert ("https", "fonts.googleapis.com") in _origins(style_tokens)
    assert ("https", "fonts.gstatic.com") in _origins(font_tokens)
    # Pre-existing tokens must be preserved.
    assert "'self'" in style_tokens
    assert "'unsafe-inline'" in style_tokens
    assert "'self'" in font_tokens


def test_non_overlay_html_does_not_allow_google_fonts(headers_client):
    """The control UI / manage page CSP stays strict — no third-party
    font hosts leak in from the overlay branch."""
    res = headers_client.get("/manage")
    csp = res.headers.get("content-security-policy", "")
    csp_tokens = {tok for part in csp.split(";") for tok in part.split()}
    # Stronger and CodeQL-clean: assert *no* http(s) origin appears
    # anywhere in the CSP for non-overlay pages (no need to spell
    # specific hosts, which CodeQL flags as
    # ``py/incomplete-url-substring-sanitization`` whenever a URL
    # literal sits on the LHS of an ``in`` / ``not in``).
    external_origins = {
        tok for tok in csp_tokens
        if tok.startswith(("http://", "https://"))
    }
    assert external_origins == set(), (
        f"unexpected external origins in /manage CSP: {external_origins}"
    )


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
    app = FastAPI()
    app.include_router(admin_users_router)
    app.include_router(auth_router)
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

    app = FastAPI()
    app.include_router(admin_users_router)
    app.include_router(auth_router)
    app.add_middleware(M)
    client = TestClient(app)

    bad = {"Authorization": "Bearer wrong"}
    # 3 failures fill the bucket, the 4th request must be blocked.
    for _ in range(3):
        assert client.get("/api/v1/admin/users", headers=bad).status_code == 401
    res = client.get("/api/v1/admin/users", headers=bad)
    assert res.status_code == 429
    assert res.headers.get("retry-after")
    # And subsequent attempts stay blocked, including with a *correct*
    # password — the bucket gates the IP, not the credential.
    good = {"Authorization": "Bearer correct-horse"}
    res = client.get("/api/v1/admin/users", headers=good)
    assert res.status_code == 429


def test_rate_limit_does_not_reset_on_intervening_success(monkeypatch):
    """A successful response on a public endpoint must not launder failures.

    Earlier revisions cleared the bucket on any non-401/403 outcome,
    which let an attacker interleave login attempts with hits to
    ``/api/v1/admin/status`` (a 200, no auth) to keep the failure
    count below the threshold. The current implementation only ever
    appends to the bucket — old failures fall out of the sliding
    window on their own.
    """
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX_FAILURES", "3")
    import importlib

    importlib.reload(auth_rate_limit)
    from app.api.middleware.auth_rate_limit import AuthRateLimitMiddleware as M

    app = FastAPI()
    app.include_router(admin_users_router)
    app.include_router(auth_router)
    app.add_middleware(M)
    client = TestClient(app)

    bad = {"Authorization": "Bearer wrong"}
    # Two failures, then a public 200 (status check), then a third
    # failure must still trip the limit on the next attempt.
    for _ in range(2):
        assert client.get("/api/v1/admin/users", headers=bad).status_code == 401
    assert client.get("/api/v1/auth/context").status_code == 200
    assert client.get("/api/v1/admin/users", headers=bad).status_code == 401
    # 3 failures in the window; the 4th request must be blocked even
    # though a 200 happened in the middle.
    res = client.get("/api/v1/admin/users", headers=bad)
    assert res.status_code == 429


def test_rate_limit_uses_socket_peer_not_xff(monkeypatch):
    """The limiter must ignore client-supplied ``X-Forwarded-For``.

    Trusting the leftmost XFF would let an attacker mint a fresh
    bucket per request by varying the header. The middleware now
    relies on ``scope["client"]`` only, which the ASGI server
    populates from the socket peer (or from a trusted proxy hop
    when ``--proxy-headers`` is configured).
    """
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX_FAILURES", "3")
    import importlib

    importlib.reload(auth_rate_limit)
    from app.api.middleware.auth_rate_limit import AuthRateLimitMiddleware as M

    app = FastAPI()
    app.include_router(admin_users_router)
    app.include_router(auth_router)
    app.add_middleware(M)
    client = TestClient(app)

    bad = {"Authorization": "Bearer wrong"}
    # Vary X-Forwarded-For across requests; if it were trusted, each
    # request would hit a fresh bucket and never trip the limit.
    for i in range(3):
        spoof = {**bad, "X-Forwarded-For": f"10.0.0.{i}"}
        assert client.get(
            "/api/v1/admin/users", headers=spoof,
        ).status_code == 401
    res = client.get(
        "/api/v1/admin/users",
        headers={**bad, "X-Forwarded-For": "10.0.0.99"},
    )
    assert res.status_code == 429


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


@pytest.mark.parametrize("url", [
    "/media/icons/abc123-ff00.webp",
    "/static/images/default_volleyball.svg",
])
def test_logo_url_accepts_same_origin_paths(url):
    """Hosted icons are stored as origin-relative paths — they must pass."""
    assert is_safe_logo_url(url) is True


@pytest.mark.parametrize("url", [
    # ``/\`` would leave the origin under WHATWG backslash normalization.
    "/\\evil.com/x.png",
])
def test_logo_url_rejects_backslash_path(url):
    assert is_safe_logo_url(url) is False


def test_update_customization_accepts_hosted_icon_path(api_session):
    """Picking a team whose catalog icon is a hosted /media URL must work —
    this is the exact path the board copy travels (6b in the icon plan)."""
    from app.api.game_service import GameService

    res = GameService.update_customization(
        api_session, {"Team 1 Logo": "/media/icons/abc123-ff00.webp"},
    )
    assert res.success is True


def test_update_customization_still_rejects_backslash_path(api_session):
    from app.api.game_service import GameService

    res = GameService.update_customization(
        api_session, {"Team 1 Logo": "/\\evil.com/x.png"},
    )
    assert res.success is False


# ---------------------------------------------------------------------------
# Catalog icon gate (permissive variant used by the team CRUD/import)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [
    "https://cdn.example.com/logo.png",
    "//cdn.example.com/logo.png",
    "data:image/png;base64,iVBORw0KGgo=",
    "/media/icons/abc123-ff00.webp",
    "foo.png",              # legacy scheme-less values keep round-tripping
    "images/logo.jpg",
    "",
])
def test_catalog_icon_accepts_harmless_values(value):
    from app.api.schemas import is_acceptable_catalog_icon

    assert is_acceptable_catalog_icon(value) is True


@pytest.mark.parametrize("value", [
    "javascript:alert(1)",
    "vbscript:msgbox",
    "data:text/html,<script>alert(1)</script>",
    "file:///etc/passwd",
    "/\\evil.com/x.png",
    "\\\\evil.com\\share\\x.png",
    None,
    123,
])
def test_catalog_icon_rejects_dangerous_values(value):
    from app.api.schemas import is_acceptable_catalog_icon

    assert is_acceptable_catalog_icon(value) is False


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


@pytest.mark.parametrize("bad_value", [
    {"nested": "object"},
    ["array", "of", "strings"],
    [],
    {},
])
def test_update_customization_rejects_nested_types(api_session, bad_value):
    """Only scalar JSON types may be stored — arrays / objects bypass
    the per-string length cap and would balloon the broadcast payload
    via deep merge.
    """
    from app.api.game_service import GameService

    res = GameService.update_customization(
        api_session, {"Team 1 Name": bad_value},
    )
    assert res.success is False
    assert "string" in (res.message or "").lower() or "type" in (res.message or "").lower()


@pytest.mark.parametrize("scalar_value", [
    True,
    False,
    None,
    42,
    1.5,
    "short string",
])
def test_update_customization_accepts_scalar_types(api_session, scalar_value):
    """Booleans, numbers, None, and short strings are all valid."""
    from app.api.game_service import GameService

    res = GameService.update_customization(
        api_session, {"Team 1 Name": scalar_value},
    )
    assert res.success is True
