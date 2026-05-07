"""Coverage for the opt-in middlewares wired in PR 5 of the security plan.

Both ``TrustedHostMiddleware`` and ``CORSMiddleware`` are off by
default — operators that are happy with the bundled same-origin
deployment see no behavior change. When they're configured via env
vars, the helpers in :mod:`app.bootstrap` install them with a few
defensive defaults (no wildcard CORS on a credentialed API, etc.)
that are pinned here.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from importlib import reload

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(monkeypatch, *, trusted_hosts: Iterable[str] | None = None,
               cors_origins: Iterable[str] | None = None) -> FastAPI:
    """Re-create a FastAPI app with the given env-var configuration.

    ``app.bootstrap._maybe_register_*`` reads from ``os.environ`` at
    call time, so the test sets the env var, calls ``create_app``,
    and gets a fresh wiring per case. Other env vars are deliberately
    left to ``conftest`` defaults to keep the harness minimal.
    """
    monkeypatch.delenv("TRUSTED_HOSTS", raising=False)
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    if trusted_hosts is not None:
        monkeypatch.setenv("TRUSTED_HOSTS", ",".join(trusted_hosts))
    if cors_origins is not None:
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", ",".join(cors_origins))

    # Reload bootstrap so any cached env-var reads are dropped — the
    # helper functions read ``os.environ`` directly so this is mainly
    # cosmetic, but it documents the intent.
    from app import bootstrap as bootstrap_module
    reload(bootstrap_module)
    return bootstrap_module.create_app()


# ---------------------------------------------------------------------------
# TrustedHostMiddleware
# ---------------------------------------------------------------------------


def test_trusted_hosts_unset_does_not_enforce(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app)
    # Any Host header passes when the middleware isn't installed.
    res = client.get("/health", headers={"Host": "evil.example.com"})
    assert res.status_code == 200


def test_trusted_hosts_rejects_unlisted_host(monkeypatch):
    app = _build_app(monkeypatch, trusted_hosts=["scoreboard.example.com"])
    client = TestClient(app)
    res = client.get(
        "/health",
        headers={"Host": "evil.example.com"},
    )
    # Starlette returns 400 with body "Invalid host header".
    assert res.status_code == 400
    assert "host" in res.text.lower()


def test_trusted_hosts_accepts_listed_host(monkeypatch):
    app = _build_app(monkeypatch, trusted_hosts=["scoreboard.example.com"])
    client = TestClient(app)
    res = client.get(
        "/health",
        headers={"Host": "scoreboard.example.com"},
    )
    assert res.status_code == 200


def test_trusted_hosts_supports_wildcard_subdomain(monkeypatch):
    """Starlette's wildcard pattern is the cheapest way to allow many
    subdomains; pin the syntax so a future swap doesn't silently
    weaken host matching.
    """
    app = _build_app(monkeypatch, trusted_hosts=["*.example.com"])
    client = TestClient(app)
    ok = client.get("/health", headers={"Host": "a.example.com"})
    assert ok.status_code == 200
    rejected = client.get("/health", headers={"Host": "example.org"})
    assert rejected.status_code == 400


def test_trusted_hosts_csv_with_whitespace_is_split(monkeypatch):
    app = _build_app(
        monkeypatch,
        trusted_hosts=["a.example.com", " b.example.com "],
    )
    client = TestClient(app)
    assert client.get("/health", headers={"Host": "a.example.com"}).status_code == 200
    # Whitespace must be stripped — ``b.example.com `` (trailing space)
    # would never have matched a real Host header.
    assert client.get("/health", headers={"Host": "b.example.com"}).status_code == 200


# ---------------------------------------------------------------------------
# CORSMiddleware
# ---------------------------------------------------------------------------


def test_cors_unset_does_not_install_middleware(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app)
    res = client.get(
        "/health",
        headers={"Origin": "https://control.example.com"},
    )
    assert res.status_code == 200
    # Without CORS the response carries no ``Access-Control-Allow-Origin``.
    assert "access-control-allow-origin" not in res.headers


def test_cors_explicit_origin_is_echoed(monkeypatch):
    app = _build_app(
        monkeypatch, cors_origins=["https://control.example.com"],
    )
    client = TestClient(app)
    res = client.get(
        "/health",
        headers={"Origin": "https://control.example.com"},
    )
    assert res.status_code == 200
    assert (
        res.headers.get("access-control-allow-origin")
        == "https://control.example.com"
    )


def test_cors_unlisted_origin_does_not_get_header(monkeypatch):
    app = _build_app(
        monkeypatch, cors_origins=["https://control.example.com"],
    )
    client = TestClient(app)
    res = client.get(
        "/health",
        headers={"Origin": "https://evil.example.com"},
    )
    assert res.status_code == 200
    # Unlisted origin: no CORS header echoed → browser blocks the
    # response client-side.
    assert "access-control-allow-origin" not in res.headers


def test_cors_wildcard_is_rejected(monkeypatch, caplog):
    """A bare ``*`` must be refused — it would defeat the
    credentialed-API stance (Authorization header forwarding requires
    an explicit allow-list)."""
    with caplog.at_level(logging.ERROR, logger="app.bootstrap"):
        app = _build_app(monkeypatch, cors_origins=["*"])
    client = TestClient(app)
    res = client.get(
        "/health", headers={"Origin": "https://anything.example.com"},
    )
    # No CORS header — middleware was never installed.
    assert res.status_code == 200
    assert "access-control-allow-origin" not in res.headers
    assert any("CORS_ALLOWED_ORIGINS=*" in rec.message for rec in caplog.records)


def test_cors_preflight_passes_through(monkeypatch):
    """Preflight requests must short-circuit without consulting auth."""
    app = _build_app(
        monkeypatch, cors_origins=["https://control.example.com"],
    )
    client = TestClient(app)
    res = client.options(
        "/api/v1/state",
        headers={
            "Origin": "https://control.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    # 200 from the CORS middleware — the route's auth dependency is
    # never consulted on preflight.
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "https://control.example.com"
    assert "authorization" in res.headers.get(
        "access-control-allow-headers", "",
    ).lower()


@pytest.fixture(autouse=True)
def _restore_bootstrap():
    """Reload bootstrap once at teardown so other test modules see a
    clean module state (the fixture above reloads it per call but we
    don't want a half-mutated module surviving the test class).
    """
    yield
    from app import bootstrap as bootstrap_module
    reload(bootstrap_module)
