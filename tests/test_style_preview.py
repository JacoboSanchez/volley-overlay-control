"""Style previews must use demo data without resolving any live overlay."""
import json
import re
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from app.api.schemas import SET_SUMMARY_STYLE_CHOICES
from app.overlay.broadcast import ObsBroadcastHub
from app.overlay.routes import create_overlay_router
from app.overlay.state_store import OverlayStateStore


@pytest.fixture
def preview_client(tmp_path):
    templates_dir = str(Path(__file__).parents[1] / "overlay_templates")
    store = OverlayStateStore(data_dir=str(tmp_path), templates_dir=templates_dir)
    store.get_state = Mock(side_effect=AssertionError("must not read live state"))
    app = FastAPI()
    app.include_router(create_overlay_router(
        store, ObsBroadcastHub(), Jinja2Templates(directory=templates_dir),
    ))
    return TestClient(app), store


def _preview_state(response):
    match = re.search(r"window.OVERLAY_PREVIEW_STATE = (.*);", response.text)
    assert match
    return json.loads(match.group(1))


def test_every_selectable_style_has_an_isolated_preview(preview_client):
    client, store = preview_client
    for style in store.get_available_styles_list():
        response = client.get(f"/overlay-preview/{style}")
        assert response.status_code == 200
        state = _preview_state(response)
        assert state["team_home"]["name"] == "CV Pontevedra"
        assert state["overlay_control"]["preferredStyle"] == style
        assert not state["match_info"]["show_set_summary"]
        assert response.headers["cache-control"] == "no-store"
    store.get_state.assert_not_called()


@pytest.mark.parametrize("summary", SET_SUMMARY_STYLE_CHOICES)
def test_summary_preview_has_complete_rally_data_and_native_palette(preview_client, summary):
    client, _ = preview_client
    response = client.get(f"/overlay-preview/broadcast?summary={summary}&lang=es")
    assert response.status_code == 200
    assert 'window.OVERLAY_NATIVE_THEME = "light"' in response.text
    assert 'window.OVERLAY_LOCALE = "es"' in response.text
    state = _preview_state(response)
    assert state["match_info"]["set_summary_style"] == summary
    assert state["match_info"]["show_set_summary"]
    rallies = state["overlay_control"]["points_by_set"]["3"]
    assert len(rallies) == 46
    assert rallies[-1]["score"] == [25, 21]


@pytest.mark.parametrize("path", [
    "/overlay-preview/nope", "/overlay-preview/base", "/overlay-preview/mosaic",
    "/overlay-preview/_spectator", "/overlay-preview/default?summary=nope",
    "/overlay-preview/%2e%2e%2fbase",
])
def test_preview_rejects_unknown_or_private_templates(preview_client, path):
    client, _ = preview_client
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_preview_accepts_explicit_palettes(preview_client, theme):
    client, _ = preview_client
    response = client.get(f"/overlay-preview/broadcast?theme={theme}")
    assert response.status_code == 200
    assert _preview_state(response)["raw_remote_customization"]["overlayTheme"] == theme


def test_preview_rejects_unknown_palettes(preview_client):
    client, _ = preview_client
    assert client.get("/overlay-preview/broadcast?theme=unknown").status_code == 422
