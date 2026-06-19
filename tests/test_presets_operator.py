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
def client(db_session):
    from tests.conftest import login_client

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
        login_client(c, db_session)
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
        # Non-preset keys (per-operator/per-session knobs that don't
        # belong to a saved preset) are opted out via
        # ``_NON_PRESET_KEYS`` and are intentionally excluded from the
        # partition.
        assert covered == (
            set(ALLOWED_CUSTOMIZATION_KEYS) - preset_categories._NON_PRESET_KEYS
        ), (
            "Each ``ALLOWED_CUSTOMIZATION_KEYS`` member must belong to "
            "exactly one preset category (or be opted out via "
            "``_NON_PRESET_KEYS``)."
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

    def test_slugify_rejects_reserved_system_prefix(self):
        # Names that resolve to ``system-…`` would shadow the
        # read-only entries surfaced from ``APP_THEMES``. The store
        # rejects them at slug derivation so a hand-crafted POST
        # can't ever land such a record on disk.
        with pytest.raises(ValueError):
            presets_store.slugify("system-bright")
        with pytest.raises(ValueError):
            presets_store.slugify("System Bright")

    def test_slugify_check_reserved_false_allows_system_prefix(self):
        # The system-preset loader prepends ``system-`` unconditionally,
        # so it needs to slugify env theme names without the reservation
        # check or a theme literally named "System Dark" would be
        # silently dropped instead of addressing as
        # ``system-system-dark``.
        assert (
            presets_store.slugify("System Dark", check_reserved=False)
            == "system-dark"
        )
        assert (
            presets_store.slugify("system-bright", check_reserved=False)
            == "system-bright"
        )

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
    """The /customization/presets surface is now DB-backed and cookie-scoped.

    ``client`` is an authenticated normal user; admin-only global authoring
    is exercised through a separate admin client.
    """

    def _admin(self, db_session):
        from fastapi.testclient import TestClient

        from app.bootstrap import create_app
        from tests.conftest import login_client
        return login_client(TestClient(create_app()), db_session, "root", role="admin")

    def test_list_returns_empty_when_no_presets(self, client):
        assert client.get("/api/v1/customization/presets").json() == {"items": []}

    def test_create_then_list_round_trip(self, client):
        r = client.post(
            "/api/v1/customization/presets",
            json={"name": "Default Position", "values": {"Height": 12, "Width": 35}},
        )
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["slug"] == "default-position"
        assert created["source"] == "user"
        assert created["categories"] == ["position"]
        assert created["values"] == {"Height": 12, "Width": 35}

        items = client.get("/api/v1/customization/presets").json()["items"]
        assert len(items) == 1
        assert items[0]["slug"] == "default-position"

    def test_create_filters_unknown_keys(self, client):
        r = client.post(
            "/api/v1/customization/presets",
            json={"name": "Mixed", "values": {
                "Team 1 Color": "#0F0", "Height": 8, "raw_remote_model": {"x": 1},
            }},
        )
        body = r.json()
        assert body["values"] == {"Team 1 Color": "#0F0", "Height": 8}
        assert sorted(body["categories"]) == ["position", "team1_color"]

    def test_create_with_only_unknown_keys_is_400(self, client):
        r = client.post(
            "/api/v1/customization/presets",
            json={"name": "Junk", "values": {"foo": "bar"}},
        )
        assert r.status_code == 400, r.text

    def test_create_with_duplicate_name_is_409(self, client):
        assert client.post(
            "/api/v1/customization/presets",
            json={"name": "Dup", "values": {"Height": 1}},
        ).status_code == 200
        assert client.post(
            "/api/v1/customization/presets",
            json={"name": "Dup", "values": {"Height": 2}},
        ).status_code == 409

    def test_create_with_invalid_name_is_400(self, client):
        r = client.post(
            "/api/v1/customization/presets",
            json={"name": "   ", "values": {"Height": 1}},
        )
        assert r.status_code in (400, 422), r.text

    def test_delete_removes_preset_and_returns_204(self, client):
        client.post(
            "/api/v1/customization/presets",
            json={"name": "Delete Me", "values": {"Height": 8}},
        )
        assert client.delete("/api/v1/customization/presets/delete-me").status_code == 204
        assert client.get("/api/v1/customization/presets").json()["items"] == []

    def test_delete_unknown_slug_is_404(self, client):
        assert client.delete(
            "/api/v1/customization/presets/never-existed"
        ).status_code == 404

    def test_user_cannot_delete_global_preset(self, client, db_session):
        admin = self._admin(db_session)
        admin.post(
            "/api/v1/admin/presets",
            json={"name": "Brand", "values": {"Height": 5}},
        )
        # The global preset is visible to the normal user...
        slugs = {p["slug"] for p in client.get(
            "/api/v1/customization/presets").json()["items"]}
        assert "brand" in slugs
        # ...but they cannot delete it.
        assert client.delete("/api/v1/customization/presets/brand").status_code == 403

    def test_global_preset_visible_only_when_active(self, client, db_session):
        admin = self._admin(db_session)
        admin.post(
            "/api/v1/admin/presets",
            json={"name": "Hidden", "values": {"Width": 9}, "is_active": False},
        )

        def user_slugs():
            return {p["slug"] for p in client.get(
                "/api/v1/customization/presets").json()["items"]}

        assert "hidden" not in user_slugs()
        admin.patch("/api/v1/admin/presets/hidden", json={"is_active": True})
        assert "hidden" in user_slugs()

    def test_admin_import_export_roundtrip(self, db_session):
        admin = self._admin(db_session)
        themes = {
            "Center": {"Height": 50, "Width": 50},
            "Corner": {"Height": 12, "Up-Down": -45.6},
        }
        r = admin.post("/api/v1/admin/presets/import", json={"themes": themes})
        assert r.status_code == 200 and r.json()["imported"] == 2
        assert admin.get("/api/v1/admin/presets/export").json() == themes

    def test_admin_list_includes_inactive_globals(self, client, db_session):
        """The admin list shows inactive globals (the user list hides them)."""
        admin = self._admin(db_session)
        admin.post("/api/v1/admin/presets",
                   json={"name": "Hidden", "values": {"Width": 9}, "is_active": False})
        # User-facing list excludes the inactive global.
        user_slugs = {p["slug"] for p in client.get(
            "/api/v1/customization/presets").json()["items"]}
        assert "hidden" not in user_slugs
        # Admin management list includes it, with is_active False.
        items = admin.get("/api/v1/admin/presets").json()["items"]
        hidden = next(p for p in items if p["slug"] == "hidden")
        assert hidden["is_active"] is False
        assert client.get("/api/v1/admin/presets").status_code == 403  # non-admin

    def test_admin_presets_require_admin(self, client):
        assert client.post(
            "/api/v1/admin/presets", json={"name": "X", "values": {"Height": 1}},
        ).status_code == 403
        assert client.get("/api/v1/admin/presets/export").status_code == 403

    def test_user_can_delete_own_preset_despite_global_same_slug(self, client, db_session):
        """Regression: a global preset sharing a user's slug must not block the
        user from deleting their own (distinct) preset."""
        client.post(
            "/api/v1/customization/presets",
            json={"name": "Corner", "values": {"Height": 3}},
        )
        self._admin(db_session).post(
            "/api/v1/admin/presets", json={"name": "Corner", "values": {"Width": 9}},
        )
        assert client.delete("/api/v1/customization/presets/corner").status_code == 204
        slugs = {p["slug"]: p["source"]
                 for p in client.get("/api/v1/customization/presets").json()["items"]}
        assert slugs.get("corner") == "global"

    def test_user_presets_are_isolated(self, client, db_session):
        from fastapi.testclient import TestClient

        from app.bootstrap import create_app
        from tests.conftest import login_client

        client.post(
            "/api/v1/customization/presets",
            json={"name": "Mine", "values": {"Height": 1}},
        )
        other = login_client(TestClient(create_app()), db_session, "bob")
        assert other.get("/api/v1/customization/presets").json()["items"] == []
