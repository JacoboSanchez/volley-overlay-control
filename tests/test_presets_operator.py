"""Operator-facing preset surface — translation + ``GET preset-options``.

Admin presets continue to live under ``/api/v1/admin/presets/*`` (see
``test_presets.py``). This file covers the read-only counterpart
exposed at ``/api/v1/customization/preset-options``: the React control
panel consumes it to show env-var ``APP_THEMES`` and admin-curated
user presets in a single picker, with snapshots translated from the
nested admin shape (``team_home.color_primary``, ``geometry.h``, …) to
the flat ``ALLOWED_CUSTOMIZATION_KEYS`` layer the operator's session
actually edits.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api import preset_translation, presets_store
from app.bootstrap import create_app
from app.customization import Customization
from app.overlay import overlay_state_store
from app.state import State
from tests.conftest import load_fixture

pytestmark = pytest.mark.usefixtures("clean_sessions")


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    overlay_state_store._data_dir = str(tmp_path)
    overlay_state_store._overlays = {}
    overlay_state_store._output_key_cache = {}
    overlay_state_store._available_styles = None
    overlay_state_store._renderable_styles = None
    monkeypatch.setattr(
        presets_store, "_data_dir", lambda: str(tmp_path / "presets"),
    )
    monkeypatch.delenv("APP_THEMES", raising=False)
    monkeypatch.delenv("PREDEFINED_OVERLAYS", raising=False)
    Customization.refresh()
    yield
    Customization.refresh()


@pytest.fixture
def client():
    fake = MagicMock()
    fake.validate_and_store_model_for_oid.return_value = State.OIDStatus.VALID
    fake.init_ws_client.return_value = None
    fake.fetch_output_token.return_value = None
    fake.get_current_model.return_value = load_fixture("base_model")
    fake.get_current_customization.return_value = load_fixture("base_customization")
    fake.is_visible.return_value = True
    fake.is_custom_overlay.return_value = False
    with (
        patch("app.api.routes.session.Backend", return_value=fake),
        TestClient(create_app()) as c,
    ):
            # Initialise a session so ``get_session`` resolves; use a
            # plain OID so we don't have to wrestle with auth header
            # plumbing — ``verify_api_key`` is a no-op when
            # ``SCOREBOARD_USERS`` is absent (default).
            r = c.post("/api/v1/session/init", json={"oid": "op-1"})
            assert r.status_code == 200, r.text
            yield c


# ---------------------------------------------------------------------------
# Translation helper
# ---------------------------------------------------------------------------


class TestTranslateSnapshot:
    def test_team_home_to_flat_keys(self):
        patch = preset_translation.translate_snapshot(
            {
                "name": "Real Madrid",
                "color_primary": "#FFFFFF",
                "color_secondary": "#FEC23E",
                "logo_url": "https://example.com/rm.png",
                # No flat counterpart — must be silently dropped
                # rather than crash or land under an unknown key.
                "short_name": "RMA",
            },
            "team_home",
        )
        assert patch == {
            "Team 1 Name": "Real Madrid",
            "Team 1 Color": "#FFFFFF",
            "Team 1 Text Color": "#FEC23E",
            "Team 1 Logo": "https://example.com/rm.png",
        }

    def test_team_away_uses_team2_flat_keys(self):
        patch = preset_translation.translate_snapshot(
            {"name": "FC Barcelona", "color_primary": "#A50044"},
            "team_away",
        )
        assert patch == {
            "Team 2 Name": "FC Barcelona",
            "Team 2 Color": "#A50044",
        }

    def test_layout_geometry_dotted_lookup(self):
        patch = preset_translation.translate_snapshot(
            {"geometry": {"x": 10, "y": 20, "w": 30, "h": 12}},
            "overlay_layout",
        )
        assert patch == {
            "Left-Right": 10, "Up-Down": 20, "Width": 30, "Height": 12,
        }

    def test_layout_with_partial_geometry(self):
        patch = preset_translation.translate_snapshot(
            {"geometry": {"h": 12}}, "overlay_layout",
        )
        assert patch == {"Height": 12}

    def test_overlay_colors_dotted_lookup(self):
        patch = preset_translation.translate_snapshot(
            {
                "colors": {
                    "set_bg": "#000",
                    "set_text": "#FFF",
                    "game_bg": "#DDD",
                    "game_text": "#222",
                },
            },
            "overlay_colors",
        )
        assert patch == {
            "Color 1": "#000", "Text Color 1": "#FFF",
            "Color 2": "#DDD", "Text Color 2": "#222",
        }

    def test_overlay_style_passes_through(self):
        assert preset_translation.translate_snapshot(
            {"preferredStyle": "esports"}, "overlay_style",
        ) == {"preferredStyle": "esports"}

    def test_unknown_scope_returns_empty(self):
        assert preset_translation.translate_snapshot(
            {"any": "thing"}, "no_such_scope",
        ) == {}

    def test_empty_snapshot_returns_empty(self):
        assert preset_translation.translate_snapshot({}, "team_home") == {}


class TestTranslateRecord:
    def _record(self) -> dict:
        return {
            "_meta": {"name": "Default Court", "slug": "default-court"},
            "scopes": ["overlay_layout", "team_home"],
            "snapshots": {
                "overlay_layout": {"geometry": {"h": 12, "w": 35}},
                "team_home": {"name": "Home", "color_primary": "#0F0"},
            },
        }

    def test_merges_all_scopes_by_default(self):
        patch, applied = preset_translation.translate_record(self._record())
        assert patch == {
            "Height": 12, "Width": 35,
            "Team 1 Name": "Home", "Team 1 Color": "#0F0",
        }
        assert sorted(applied) == ["overlay_layout", "team_home"]

    def test_subset_scopes(self):
        patch, applied = preset_translation.translate_record(
            self._record(), scopes=["overlay_layout"],
        )
        assert patch == {"Height": 12, "Width": 35}
        assert applied == ["overlay_layout"]

    def test_unknown_requested_scope_is_filtered_silently(self):
        # Records can be created with whatever scopes the admin had at
        # the time. Asking for one the record never carried just yields
        # an empty contribution, not a crash.
        patch, applied = preset_translation.translate_record(
            self._record(), scopes=["overlay_colors"],
        )
        assert patch == {}
        assert applied == []


# ---------------------------------------------------------------------------
# GET /api/v1/customization/preset-options
# ---------------------------------------------------------------------------


def _seed_user_preset(slug: str, name: str, scopes_payload: dict) -> None:
    presets_store.create(
        name=name,
        snapshots=scopes_payload,
        scopes=list(scopes_payload.keys()),
    )


class TestPresetOptionsList:
    def test_includes_env_var_themes_marked_read_only(self, client, monkeypatch):
        monkeypatch.setenv(
            "APP_THEMES",
            '{"dark": {"Color 1": "#000", "Text Color 1": "#FFF"}}',
        )
        Customization.refresh()
        r = client.get("/api/v1/customization/preset-options?oid=op-1")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        env_items = [i for i in items if i["source"] == "env"]
        assert env_items, items
        dark = env_items[0]
        assert dark["id"] == "theme:dark"
        assert dark["name"] == "dark"
        assert dark["read_only"] is True
        assert dark["scopes"] == ["overlay_colors"]
        assert dark["patch"] == {"Color 1": "#000", "Text Color 1": "#FFF"}

    def test_skips_empty_env_themes(self, client, monkeypatch):
        # Malformed entries shouldn't crash the listing.
        monkeypatch.setenv("APP_THEMES", '{"empty": {}, "valid": {"Height": 8}}')
        Customization.refresh()
        r = client.get("/api/v1/customization/preset-options?oid=op-1")
        ids = {i["id"] for i in r.json()["items"]}
        assert "theme:valid" in ids
        assert "theme:empty" not in ids

    def test_user_preset_translates_to_flat_patch(self, client):
        _seed_user_preset(
            slug="default-position",
            name="Default Position",
            scopes_payload={
                "overlay_layout": {
                    "geometry": {"h": 12, "w": 35, "x": -30, "y": -40},
                },
            },
        )
        r = client.get("/api/v1/customization/preset-options?oid=op-1")
        items = [i for i in r.json()["items"] if i["source"] == "user"]
        assert len(items) == 1
        item = items[0]
        assert item["id"] == "preset:default-position"
        assert item["name"] == "Default Position"
        assert item["read_only"] is False
        assert item["scopes"] == ["overlay_layout"]
        assert item["patch"] == {
            "Height": 12, "Width": 35, "Left-Right": -30, "Up-Down": -40,
        }

    def test_drops_user_preset_with_no_translatable_keys(self, client):
        # ``short_name`` has no flat counterpart — translating the
        # whole record yields ``{}``, so the operator-facing list
        # should hide the entry rather than show a no-op apply.
        _seed_user_preset(
            slug="short-only",
            name="Short only",
            scopes_payload={"team_home": {"short_name": "RMA"}},
        )
        r = client.get("/api/v1/customization/preset-options?oid=op-1")
        ids = {i["id"] for i in r.json()["items"]}
        assert "preset:short-only" not in ids

    def test_response_omits_raw_snapshots(self, client):
        # Snapshots are admin-only; the operator endpoint must not
        # leak them in any form. The response shape is locked to
        # the flat patch + scope list.
        _seed_user_preset(
            slug="rm-home",
            name="Real Madrid home",
            scopes_payload={
                "team_home": {
                    "name": "Real Madrid", "color_primary": "#FFF",
                },
            },
        )
        body = client.get("/api/v1/customization/preset-options?oid=op-1").json()
        for item in body["items"]:
            # No ``snapshots`` field, no ``_meta`` leak, no nested
            # admin-shape keys (``team_home``) — the operator only
            # needs the flat patch.
            assert "snapshots" not in item
            assert "_meta" not in item
            for k in item["patch"]:
                assert k not in {"team_home", "team_away", "overlay_control"}

    def test_mixed_feed_combines_env_and_user(self, client, monkeypatch):
        monkeypatch.setenv("APP_THEMES", '{"dark": {"Color 1": "#000"}}')
        Customization.refresh()
        _seed_user_preset(
            slug="court-a",
            name="Court A position",
            scopes_payload={"overlay_layout": {"geometry": {"h": 8}}},
        )
        body = client.get("/api/v1/customization/preset-options?oid=op-1").json()
        sources = {i["source"] for i in body["items"]}
        assert sources == {"env", "user"}

    def test_response_is_oid_independent(self, client):
        # The picker payload describes the global preset catalogue
        # plus env-var themes — neither is per-OID — so the route
        # legitimately answers without ``?oid=``. Locking the test in
        # documents the contract: a future refactor that adds a
        # per-OID filter would have to update both ends.
        r = client.get("/api/v1/customization/preset-options")
        assert r.status_code == 200
