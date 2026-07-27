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

import time
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
    # With no ``OVERLAY_PUBLIC_URL`` configured the only framed page is
    # this app's own /overlay/<token>, so ``frame-src`` must be exactly
    # ``'self'`` — the old bare ``https:`` wildcard allowed every site on
    # the internet to be framed by the control UI.
    frame_src_directive = next(
        (p.strip() for p in csp.split(";") if p.strip().startswith("frame-src")),
        "",
    )
    assert frame_src_directive.split() == ["frame-src", "'self'"]
    # ``script-src`` must not carry ``'unsafe-eval'``: nothing the app
    # ships evaluates strings, and granting it alongside
    # ``'unsafe-inline'`` leaves script-src with no mitigation at all.
    script_directive = next(
        (p.strip() for p in csp.split(";") if p.strip().startswith("script-src")),
        "",
    )
    assert "'unsafe-eval'" not in script_directive
    # ...while ``'unsafe-inline'`` stays — the match report and three
    # overlay templates ship inline <script> blocks.
    assert "'unsafe-inline'" in script_directive
    assert res.headers.get("x-frame-options") == "SAMEORIGIN"


def test_frame_src_names_configured_overlay_origin(monkeypatch):
    """A split-host deployment must still be able to frame its overlay.

    ``OVERLAY_PUBLIC_URL`` is what the OverlayPreview iframe's ``src`` is
    built from, so its origin — and only its origin — joins ``frame-src``.
    """
    monkeypatch.setenv("OVERLAY_PUBLIC_URL", "https://overlay.example.com/base/")
    client = TestClient(_build_headers_app())
    csp = client.get("/manage").headers.get("content-security-policy", "")
    frame_src_directive = next(
        (p.strip() for p in csp.split(";") if p.strip().startswith("frame-src")),
        "",
    )
    # Path components are dropped — CSP sources match scheme/host/port.
    assert frame_src_directive.split() == [
        "frame-src", "'self'", "https://overlay.example.com",
    ]
    # The bare wildcard must not come back with it.
    assert "https:" not in frame_src_directive.split()


def test_frame_src_reads_overlay_url_from_remote_config(monkeypatch):
    """``OVERLAY_PUBLIC_URL`` may arrive via ``REMOTE_CONFIG_URL``.

    Both builders of the framed URL (``app/api/routes/overlays.py`` and
    ``LocalOverlayBackend.fetch_output_token``) resolve it through
    ``EnvVarsManager``. If the CSP read ``os.environ`` directly it would
    emit ``frame-src 'self'`` while the SPA was handed a cross-origin
    overlay URL, blocking the preview iframe on exactly the split-host
    deployment the directive exists for.
    """
    from app.env_vars_manager import EnvVarsManager

    # Remote values live in the manager's cache, never in os.environ.
    monkeypatch.delenv("OVERLAY_PUBLIC_URL", raising=False)
    monkeypatch.setenv("REMOTE_CONFIG_URL", "https://config.example.com/app.json")
    monkeypatch.setattr(
        EnvVarsManager, "_remote_config_cache",
        {"OVERLAY_PUBLIC_URL": "https://remote-overlay.example.com"},
    )
    # Fresh timestamp keeps ``_load_remote_config_if_needed`` on its
    # no-op fast path, so the test never makes a network call.
    monkeypatch.setattr(EnvVarsManager, "_cache_timestamp", time.time())

    client = TestClient(_build_headers_app())
    csp = client.get("/manage").headers.get("content-security-policy", "")
    frame_src_directive = next(
        (p.strip() for p in csp.split(";") if p.strip().startswith("frame-src")),
        "",
    )
    assert frame_src_directive.split() == [
        "frame-src", "'self'", "https://remote-overlay.example.com",
    ]


@pytest.mark.parametrize("value", [
    "not a url",
    "javascript:alert(1)",
    "ftp://overlay.example.com",
    "   ",
])
def test_frame_src_ignores_unusable_overlay_url(monkeypatch, value):
    """A malformed / non-http(s) ``OVERLAY_PUBLIC_URL`` must not widen
    the policy (nor inject a junk token that invalidates the directive)."""
    monkeypatch.setenv("OVERLAY_PUBLIC_URL", value)
    client = TestClient(_build_headers_app())
    csp = client.get("/manage").headers.get("content-security-policy", "")
    frame_src_directive = next(
        (p.strip() for p in csp.split(";") if p.strip().startswith("frame-src")),
        "",
    )
    assert frame_src_directive.split() == ["frame-src", "'self'"]


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
# Rate limiter: capability-token surface, split keyspaces, live tunables
# ---------------------------------------------------------------------------


def _limiter_app(routes: dict[str, int]) -> TestClient:
    """App whose *routes* map a path to the status it always returns."""
    app = FastAPI()
    app.add_middleware(AuthRateLimitMiddleware)
    for path, status in routes.items():
        def _make(status_code: int):
            def _handler():
                from fastapi import HTTPException
                raise HTTPException(status_code=status_code, detail="nope")
            return _handler
        app.get(path)(_make(status))
    return TestClient(app)


def test_tunables_are_read_without_reimporting_the_module(monkeypatch):
    """Env overrides must apply to an already-imported limiter.

    The tunables used to be evaluated at import time, so a limit set after
    first import silently did nothing — which is why the older tests above
    have to ``importlib.reload``. No reload here on purpose: that is the
    behaviour under test.
    """
    auth_rate_limit._reset_for_tests()
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX_FAILURES", "2")
    monkeypatch.setenv("AUTH_RATE_LIMIT_BLOCK_SECONDS", "45")

    client = _limiter_app({"/api/v1/thing": 401})
    assert client.get("/api/v1/thing").status_code == 401
    assert client.get("/api/v1/thing").status_code == 401
    res = client.get("/api/v1/thing")
    assert res.status_code == 429
    # Retry-After also comes from the live value, not an import-time copy.
    assert res.headers["retry-after"] == "45"


def test_capability_surface_counts_404_token_misses(monkeypatch):
    """An unknown overlay token is a 404, and must now be throttled.

    ``/overlay/<token>`` reports an unknown capability token as 404
    (app/overlay/routes.py), and the limiter previously watched only
    ``/api/v1/`` and counted only 401/403 — so token guessing incremented
    nothing whatsoever.
    """
    auth_rate_limit._reset_for_tests()
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX_FAILURES", "3")

    client = _limiter_app({"/overlay/{token}": 404})
    for _ in range(3):
        assert client.get("/overlay/guess").status_code == 404
    assert client.get("/overlay/guess").status_code == 429


def test_api_surface_still_ignores_404(monkeypatch):
    """404 must stay harmless on /api/v1/ — there it is a missing resource,
    not a credential probe, so counting it would lock operators out for
    ordinary navigation."""
    auth_rate_limit._reset_for_tests()
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX_FAILURES", "3")

    client = _limiter_app({"/api/v1/missing": 404})
    for _ in range(20):
        assert client.get("/api/v1/missing").status_code == 404


def test_surfaces_have_separate_keyspaces(monkeypatch):
    """Exhausting one surface must not throttle the other.

    This is what makes widening the watched set safe: a shared per-IP bucket
    would let 403s from somebody's SPA take an on-air /overlay/ browser
    source down with it.
    """
    auth_rate_limit._reset_for_tests()
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX_FAILURES", "3")

    client = _limiter_app({"/api/v1/thing": 401, "/overlay/{token}": 404})

    for _ in range(3):
        client.get("/api/v1/thing")
    assert client.get("/api/v1/thing").status_code == 429
    # Same IP, different surface — must still be served.
    assert client.get("/overlay/tok").status_code == 404


def test_blocks_are_counted_per_surface(monkeypatch):
    """A 429 increments voc_rate_limit_blocks_total{surface}.

    Without it a brute-force attempt and a shared-NAT lockout of real
    operators are indistinguishable in /metrics.
    """
    pytest.importorskip("prometheus_client")
    auth_rate_limit._reset_for_tests()
    monkeypatch.setenv("AUTH_RATE_LIMIT_MAX_FAILURES", "2")

    from app.metrics import rate_limit_blocks_total

    def _count() -> float:
        return rate_limit_blocks_total.labels(surface="capability")._value.get()

    before = _count()
    client = _limiter_app({"/follow/{token}": 404})
    for _ in range(2):
        client.get("/follow/tok")
    assert client.get("/follow/tok").status_code == 429
    assert _count() == before + 1


def test_websocket_scope_is_passed_through(monkeypatch):
    """The limiter must not attempt to gate a WebSocket handshake.

    A handshake arrives as ASGI scope type "websocket", which this
    middleware deliberately ignores — the docstring says so rather than
    implying /ws/ is covered.
    """
    auth_rate_limit._reset_for_tests()
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    mw = AuthRateLimitMiddleware(inner)
    import asyncio as _asyncio

    _asyncio.run(mw({"type": "websocket", "path": "/ws/tok"}, None, None))
    assert seen == ["websocket"]


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
