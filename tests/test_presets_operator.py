"""Tests for the operator-curated preset CRUD.

Covers three layers:

* ``app.api.preset_categories`` — the six-bucket partition of
  ``ALLOWED_CUSTOMIZATION_KEYS``.
* ``app.api.presets_store`` — disk CRUD with the flat ``values`` /
  derived-``categories`` shape.
* ``GET / POST / DELETE /api/v1/customization/presets`` — the
  operator-facing HTTP surface (API-key gating, validation, error
  mapping).
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api import preset_categories, presets_store
from app.api.schemas import ALLOWED_CUSTOMIZATION_KEYS
from app.bootstrap import create_app
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
    yield


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
        # Init a session so every later request resolves through
        # ``get_session`` without 404. The route under test doesn't
        # require a session but the rest of the suite expects one.
        r = c.post("/api/v1/session/init", json={"oid": "op-1"})
        assert r.status_code == 200, r.text
        yield c


# ---------------------------------------------------------------------------
# Categories partition
# ---------------------------------------------------------------------------


class TestPresetCategoriesPartition:
    def test_categories_partition_allowed_keys_exactly(self):
        # Module-level ``_validate_partition`` already runs at import
        # time. This test re-asserts the property explicitly so a
        # future refactor that defers validation can't regress
        # silently — and so the test names tell the operator why a
        # mis-categorised allow-list key is broken.
        covered: set[str] = set()
        for cat in preset_categories.CATEGORY_ORDER:
            covered.update(preset_categories.keys_for_category(cat))
        assert covered == set(ALLOWED_CUSTOMIZATION_KEYS), (
            "Each ``ALLOWED_CUSTOMIZATION_KEYS`` member must belong to "
            "exactly one preset category."
        )

    def test_categories_for_keys_returns_canonical_order(self):
        # Mixed inputs across multiple categories collapse to the
        # canonical order so the React side can render chips
        # deterministically.
        cats = preset_categories.categories_for_keys(
            ["preferredStyle", "Team 1 Color", "Height", "Team 2 Name"],
        )
        assert cats == ["team1_color", "team2_name", "position", "style"]

    def test_filter_to_known_drops_unknown_and_keeps_value_types(self):
        cleaned = preset_categories.filter_to_known({
            "Team 1 Color": "#fff",
            "Height": 12,
            "Up-Down": -41.1,
            "Logos": "true",
            # Unknown key — must be dropped silently rather than
            # planted into the on-disk record.
            "raw_remote_customization": {"hidden": "value"},
        })
        assert cleaned == {
            "Team 1 Color": "#fff",
            "Height": 12,
            "Up-Down": -41.1,
            "Logos": "true",
        }


# ---------------------------------------------------------------------------
# presets_store
# ---------------------------------------------------------------------------


class TestPresetsStore:
    def test_create_persists_record_and_derives_categories(self):
        record = presets_store.create(
            name="Cancha A",
            values={"Height": 12, "Width": 35, "Up-Down": -40, "Left-Right": -30},
        )
        assert record["_meta"]["name"] == "Cancha A"
        assert record["_meta"]["slug"] == "cancha-a"
        assert record["categories"] == ["position"]
        assert record["values"] == {
            "Height": 12, "Width": 35, "Up-Down": -40, "Left-Right": -30,
        }

    def test_create_drops_unknown_keys_before_persistence(self):
        record = presets_store.create(
            name="Mixed",
            values={"Team 1 Color": "#fff", "raw_remote_model": {"x": 1}},
        )
        # The unknown ``raw_remote_model`` is filtered out — the
        # operator picker only ever ships allow-listed keys, but
        # this is the defence against a hand-crafted POST.
        assert record["values"] == {"Team 1 Color": "#fff"}
        assert record["categories"] == ["team1_color"]

    def test_create_rejects_empty_values(self):
        with pytest.raises(ValueError):
            presets_store.create(name="Empty", values={})
        # Same outcome when the only keys are unknown — ``filter_to_known``
        # collapses them to an empty dict, which the create path
        # rejects.
        with pytest.raises(ValueError):
            presets_store.create(name="OnlyUnknown", values={"foo": "bar"})

    def test_create_rejects_duplicate_slug(self):
        presets_store.create(name="Dup", values={"Height": 8})
        with pytest.raises(presets_store.PresetExists):
            presets_store.create(name="Dup", values={"Height": 9})

    def test_list_orders_by_name_case_insensitive(self):
        presets_store.create(name="zoo", values={"Height": 1})
        presets_store.create(name="Alpha", values={"Height": 2})
        presets_store.create(name="bravo", values={"Height": 3})
        names = [r["_meta"]["name"] for r in presets_store.list_all()]
        assert names == ["Alpha", "bravo", "zoo"]

    def test_delete_returns_true_on_success_and_false_on_missing(self):
        presets_store.create(name="Removable", values={"Height": 8})
        assert presets_store.delete("removable") is True
        assert presets_store.delete("removable") is False
        assert presets_store.delete("never-existed") is False
        assert presets_store.delete("INVALID SLUG WITH SPACES") is False


# ---------------------------------------------------------------------------
# /api/v1/customization/presets
# ---------------------------------------------------------------------------


class TestPresetCRUDEndpoints:
    def test_list_returns_empty_when_no_presets(self, client):
        body = client.get("/api/v1/customization/presets").json()
        assert body == {"items": []}

    def test_create_then_list_round_trip(self, client):
        r = client.post(
            "/api/v1/customization/presets",
            json={
                "name": "Default Position",
                "values": {"Height": 12, "Width": 35},
            },
        )
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["slug"] == "default-position"
        assert created["name"] == "Default Position"
        assert created["categories"] == ["position"]
        assert created["values"] == {"Height": 12, "Width": 35}
        assert created["created_at"] > 0

        body = client.get("/api/v1/customization/presets").json()
        assert len(body["items"]) == 1
        assert body["items"][0]["slug"] == "default-position"
        assert body["items"][0]["values"] == {"Height": 12, "Width": 35}

    def test_create_filters_unknown_keys(self, client):
        r = client.post(
            "/api/v1/customization/presets",
            json={
                "name": "Mixed",
                "values": {
                    "Team 1 Color": "#0F0",
                    "Height": 8,
                    # Unknown — filtered out at persistence time.
                    "raw_remote_model": {"hidden": True},
                },
            },
        )
        body = r.json()
        assert "raw_remote_model" not in body["values"]
        assert body["values"] == {"Team 1 Color": "#0F0", "Height": 8}
        assert sorted(body["categories"]) == ["position", "team1_color"]

    def test_create_with_only_unknown_keys_is_400(self, client):
        r = client.post(
            "/api/v1/customization/presets",
            json={"name": "Junk", "values": {"foo": "bar"}},
        )
        assert r.status_code == 400, r.text
        assert "supported" in r.json()["detail"].lower()

    def test_create_with_duplicate_name_is_409(self, client):
        first = client.post(
            "/api/v1/customization/presets",
            json={"name": "Dup", "values": {"Height": 1}},
        )
        assert first.status_code == 200, first.text
        second = client.post(
            "/api/v1/customization/presets",
            json={"name": "Dup", "values": {"Height": 2}},
        )
        assert second.status_code == 409, second.text

    def test_create_with_invalid_name_is_400(self, client):
        r = client.post(
            "/api/v1/customization/presets",
            json={"name": "   ", "values": {"Height": 1}},
        )
        # Empty after trim — pydantic min_length catches the strict
        # empty case (422) and the slugify path catches whitespace-
        # only (400). Either is acceptable here; we just want
        # ``not 200`` and the preset to never land on disk.
        assert r.status_code in (400, 422), r.text
        assert presets_store.list_all() == []

    def test_delete_removes_preset_and_returns_204(self, client):
        client.post(
            "/api/v1/customization/presets",
            json={"name": "Delete Me", "values": {"Height": 8}},
        )
        r = client.delete("/api/v1/customization/presets/delete-me")
        assert r.status_code == 204
        assert client.get("/api/v1/customization/presets").json()["items"] == []

    def test_delete_unknown_slug_is_404(self, client):
        r = client.delete("/api/v1/customization/presets/never-existed")
        assert r.status_code == 404

    def test_categories_round_trip_on_disk(self, client, tmp_path):
        client.post(
            "/api/v1/customization/presets",
            json={
                "name": "All In",
                "values": {
                    "Team 1 Name": "Home",
                    "Team 1 Color": "#fff",
                    "Team 2 Name": "Away",
                    "Team 2 Color": "#000",
                    "Height": 10,
                    "preferredStyle": "esports",
                },
            },
        )
        # Read the on-disk record straight back to lock the schema:
        # ``_meta`` + derived ``categories`` + flat ``values``. No
        # admin-side fields like ``snapshots`` / ``scopes`` — that
        # was the previous model and is gone.
        files = list((tmp_path / "presets").iterdir())
        assert len(files) == 1
        record = json.loads(files[0].read_text())
        assert set(record.keys()) == {"_meta", "categories", "values"}
        assert set(record["_meta"].keys()) == {"name", "slug", "created_at"}
        assert sorted(record["categories"]) == [
            "position", "style", "team1_color", "team1_name",
            "team2_color", "team2_name",
        ]
