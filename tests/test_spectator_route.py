"""Tests for the public spectator (follow) page at /follow/{public_token}.

Post-cutover the public surface is addressed by the per-overlay
``public_token`` (resolved to the storage key via the DB), never by the
username/oid — so neither appears in the served HTML.
"""

import os

import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from app.overlay.broadcast import ObsBroadcastHub
from app.overlay.routes import create_overlay_router
from app.overlay.state_store import OverlayStateStore
from tests.conftest import make_user

# Path to the project's real overlay_templates so we don't need to
# reinvent _spectator.html and base.html inside each test.
_REAL_TEMPLATES = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "overlay_templates")
)


@pytest.fixture
def client(tmp_path, db_session):
    from app import overlays_service

    user = make_user(db_session, "tester")
    overlay = overlays_service.create_overlay(db_session, user.id, "testovl")
    db_session.commit()
    skey = overlays_service.skey_for(overlay)

    store = OverlayStateStore(
        data_dir=str(tmp_path / "data"),
        templates_dir=_REAL_TEMPLATES,
    )
    store.create_overlay(skey)
    hub = ObsBroadcastHub()
    app = FastAPI()
    app.include_router(create_overlay_router(
        store, hub, Jinja2Templates(directory=_REAL_TEMPLATES),
    ))
    return TestClient(app), store, overlay.public_token, skey


def test_follow_returns_404_for_unknown_overlay(client):
    cli, _, _, _ = client
    res = cli.get("/follow/does-not-exist")
    assert res.status_code == 404


def test_follow_serves_spectator_html(client):
    cli, _, token, skey = client
    res = cli.get(f"/follow/{token}")
    assert res.status_code == 200
    body = res.text
    assert "spectator-scoreboard" in body
    assert "/static/js/spectator.js" in body
    assert "/static/css/spectator.css" in body
    # The public token is the only public handle; the storage key
    # (user_id:oid) must never leak into the served page.
    assert token in body
    assert skey not in body


# ---------------------------------------------------------------------------
# /overlay/{public_token} locale resolution
# ---------------------------------------------------------------------------


def test_overlay_picks_persisted_locale_over_env(client, monkeypatch):
    cli, store, token, skey = client
    monkeypatch.setenv("OVERLAY_LOCALE", "de")
    store.set_raw_config(skey, customization={"locale": "es"})
    res = cli.get(f"/overlay/{token}", headers={"Accept-Language": "fr"})
    assert res.status_code == 200
    assert 'window.OVERLAY_LOCALE = "es"' in res.text


def test_overlay_falls_back_to_env_when_no_persisted_locale(client, monkeypatch):
    cli, _, token, _ = client
    monkeypatch.setenv("OVERLAY_LOCALE", "pt")
    res = cli.get(f"/overlay/{token}")
    assert res.status_code == 200
    assert 'window.OVERLAY_LOCALE = "pt"' in res.text


def test_overlay_query_lang_overrides_persisted_locale(client):
    cli, store, token, skey = client
    store.set_raw_config(skey, customization={"locale": "es"})
    res = cli.get(f"/overlay/{token}?lang=fr")
    assert res.status_code == 200
    assert 'window.OVERLAY_LOCALE = "fr"' in res.text


def test_overlay_ignores_unsupported_persisted_locale(client, monkeypatch):
    cli, store, token, skey = client
    monkeypatch.setenv("OVERLAY_LOCALE", "it")
    store.set_raw_config(skey, customization={"locale": "xx"})
    res = cli.get(f"/overlay/{token}")
    assert res.status_code == 200
    assert 'window.OVERLAY_LOCALE = "it"' in res.text


def test_spectator_template_not_in_style_picker(tmp_path):
    """Underscore-prefixed templates must not show up as overlay styles."""
    store = OverlayStateStore(
        data_dir=str(tmp_path / "data"),
        templates_dir=_REAL_TEMPLATES,
    )
    styles = store.get_available_styles_list()
    assert "_spectator" not in styles
    renderable = store.get_renderable_styles()
    assert "_spectator" not in renderable
