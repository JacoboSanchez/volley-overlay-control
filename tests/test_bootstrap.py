"""Tests for ``app.bootstrap.create_app`` graceful-missing-dir paths.

The factory must boot even when ``frontend/dist`` or
``overlay_templates`` are missing — that's the contract for
backend-only development and Docker builds where the frontend stage
hasn't run. These tests cover the warning paths and the resulting
route topology so a regression that crashes ``create_app`` would be
caught.

The existing ``conftest.isolate_security_bootstrap`` fixture is
auto-used so token persistence stays in a per-test temp dir.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import bootstrap as bootstrap_module
from app.bootstrap import create_app


@pytest.fixture
def missing_frontend(monkeypatch, tmp_path):
    """Point FRONTEND_DIR at a non-existent path."""
    monkeypatch.setattr(
        bootstrap_module, "FRONTEND_DIR", Path(tmp_path / "no-such-dist"),
    )


@pytest.fixture
def missing_overlay_templates(monkeypatch, tmp_path):
    """Point OVERLAY_TEMPLATES_DIR at a non-existent path."""
    monkeypatch.setattr(
        bootstrap_module,
        "OVERLAY_TEMPLATES_DIR",
        Path(tmp_path / "no-such-templates"),
    )


def test_create_app_succeeds_without_frontend_dist(missing_frontend, caplog):
    """No frontend/dist → app still builds; logs a warning; SPA mount skipped."""
    import logging

    with caplog.at_level(logging.WARNING, logger="app.bootstrap"):
        app = create_app()

    assert app is not None
    assert any(
        "Frontend build directory not found" in rec.getMessage()
        for rec in caplog.records
    )
    # The "/" mount should NOT be present when the dist directory is missing.
    mount_paths = [
        getattr(route, "path", None) for route in app.routes
    ]
    assert "/" not in mount_paths or all(
        getattr(route, "name", None) != "spa" for route in app.routes
    )


def test_create_app_succeeds_without_overlay_templates(missing_overlay_templates, caplog):
    """No overlay_templates/ → /overlay/* routes are skipped, app still builds."""
    import logging

    with caplog.at_level(logging.WARNING, logger="app.bootstrap"):
        app = create_app()

    assert app is not None
    assert any(
        "Overlay templates directory not found" in rec.getMessage()
        for rec in caplog.records
    )
    # A standard API endpoint should still be mounted. Introspect the
    # OpenAPI schema rather than ``app.routes``: newer FastAPI nests
    # ``include_router`` routes under an opaque router object instead of
    # flattening each ``/api/v1/*`` route into ``app.routes``, so the
    # generated schema paths are the version-stable place to assert the
    # API surface is present.
    api_paths = app.openapi().get("paths", {})
    assert any(p.startswith("/api/v1/") for p in api_paths)


def test_create_app_succeeds_without_either(
    missing_frontend, missing_overlay_templates,
):
    """Neither directory present (e.g. minimal test image) → app still builds."""
    app = create_app()
    assert app is not None
    # See the schema-introspection note in
    # ``test_create_app_succeeds_without_overlay_templates``.
    api_paths = app.openapi().get("paths", {})
    assert any(p.startswith("/api/v1/") for p in api_paths)


def test_split_csv_env_handles_empty_and_whitespace(monkeypatch):
    """The internal helper underpins TRUSTED_HOSTS / CORS env parsing."""
    from app.bootstrap import _split_csv_env

    monkeypatch.setenv("MY_LIST", "")
    assert _split_csv_env("MY_LIST") == []

    monkeypatch.setenv("MY_LIST", "  ,  , ")
    assert _split_csv_env("MY_LIST") == []

    monkeypatch.setenv("MY_LIST", "a, b ,,c")
    assert _split_csv_env("MY_LIST") == ["a", "b", "c"]

    monkeypatch.delenv("MY_LIST", raising=False)
    assert _split_csv_env("MY_LIST") == []
