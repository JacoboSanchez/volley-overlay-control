"""Tests for the public spectator (follow) page at /follow/{id}."""

import os

import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from app.overlay.broadcast import ObsBroadcastHub
from app.overlay.routes import create_overlay_router
from app.overlay.state_store import OverlayStateStore

# Path to the project's real overlay_templates so we don't need to
# reinvent _spectator.html and base.html inside each test.
_REAL_TEMPLATES = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "overlay_templates")
)


@pytest.fixture
def client(tmp_path):
    store = OverlayStateStore(
        data_dir=str(tmp_path / "data"),
        templates_dir=_REAL_TEMPLATES,
    )
    store.create_overlay("test-overlay")
    hub = ObsBroadcastHub()
    app = FastAPI()
    app.include_router(create_overlay_router(
        store, hub, Jinja2Templates(directory=_REAL_TEMPLATES),
    ))
    return TestClient(app), store


def test_follow_returns_404_for_unknown_overlay(client):
    cli, _ = client
    res = cli.get("/follow/does-not-exist")
    assert res.status_code == 404


def test_follow_serves_spectator_html(client):
    cli, _ = client
    res = cli.get("/follow/test-overlay")
    assert res.status_code == 200
    body = res.text
    # Spectator template includes the dependency-light layout markers
    # we expect — defensive checks that survive copy-edits.
    assert "spectator-scoreboard" in body
    assert "/static/js/spectator.js" in body
    assert "/static/css/spectator.css" in body
    # The output_key (SHA-derived hash) is the only public handle the
    # page exposes — the raw overlay id MUST stay out of the HTML
    # because it's the secret an operator would type into the control
    # UI to mutate the scoreboard.
    output_key = OverlayStateStore.get_output_key("test-overlay")
    assert output_key in body
    assert "test-overlay" not in body


# ---------------------------------------------------------------------------
# /overlay/{id} locale resolution
# ---------------------------------------------------------------------------


def test_overlay_picks_persisted_locale_over_env(client, monkeypatch):
    cli, store = client
    monkeypatch.setenv("OVERLAY_LOCALE", "de")
    store.set_raw_config("test-overlay", customization={"locale": "es"})
    res = cli.get(
        "/overlay/test-overlay",
        headers={"Accept-Language": "fr"},
    )
    assert res.status_code == 200
    assert 'window.OVERLAY_LOCALE = "es"' in res.text


def test_overlay_falls_back_to_env_when_no_persisted_locale(client, monkeypatch):
    cli, _ = client
    monkeypatch.setenv("OVERLAY_LOCALE", "pt")
    res = cli.get("/overlay/test-overlay")
    assert res.status_code == 200
    assert 'window.OVERLAY_LOCALE = "pt"' in res.text


def test_overlay_query_lang_overrides_persisted_locale(client):
    cli, store = client
    store.set_raw_config("test-overlay", customization={"locale": "es"})
    res = cli.get("/overlay/test-overlay?lang=fr")
    assert res.status_code == 200
    assert 'window.OVERLAY_LOCALE = "fr"' in res.text


def test_overlay_ignores_unsupported_persisted_locale(client, monkeypatch):
    cli, store = client
    monkeypatch.setenv("OVERLAY_LOCALE", "it")
    store.set_raw_config("test-overlay", customization={"locale": "xx"})
    res = cli.get("/overlay/test-overlay")
    assert res.status_code == 200
    assert 'window.OVERLAY_LOCALE = "it"' in res.text


def test_follow_resolves_by_output_key(client):
    cli, _ = client
    output_key = OverlayStateStore.get_output_key("test-overlay")
    res = cli.get(f"/follow/{output_key}")
    assert res.status_code == 200
    body = res.text
    assert output_key in body
    # Resolving by output_key must not expose the raw overlay id either.
    assert "test-overlay" not in body


def test_spectator_template_not_in_style_picker(tmp_path):
    """Underscore-prefixed templates must not show up as overlay styles."""
    store = OverlayStateStore(
        data_dir=str(tmp_path / "data"),
        templates_dir=_REAL_TEMPLATES,
    )
    styles = store.get_available_styles_list()
    assert "_spectator" not in styles
    # And the renderable set (which extends styles with meta-styles
    # like ``mosaic``) also rejects it.
    renderable = store.get_renderable_styles()
    assert "_spectator" not in renderable
