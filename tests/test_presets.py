"""Tests for the preset system (Fase 2 replacement).

Covers three layers:

* ``app.api.preset_scopes`` — extract/apply contracts per scope.
* ``app.api.presets_store`` — disk CRUD + slug collisions + caps.
* The admin HTTP endpoints — auth gates, create-from-OID, apply,
  export round-trip, import-with-collision and apply-with-subset.
"""


import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin import admin_router
from app.api import api_router, preset_scopes, presets_store
from app.overlay import overlay_state_store

ADMIN_PASSWORD = "s3cret"


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Point the overlay store and preset store at an isolated tmp dir.

    Mirrors the pattern in ``test_admin.py``: overlay state files land
    directly under ``tmp_path`` (the directory already exists, the
    state store does not create it on demand), while the preset store
    gets a child directory it owns end-to-end since it always calls
    ``os.makedirs(..., exist_ok=True)`` before writing.
    """
    overlay_state_store._data_dir = str(tmp_path)
    overlay_state_store._overlays = {}
    overlay_state_store._output_key_cache = {}
    overlay_state_store._available_styles = None
    overlay_state_store._renderable_styles = None
    monkeypatch.setattr(
        presets_store, "_data_dir", lambda: str(tmp_path / "presets"),
    )
    monkeypatch.delenv("PREDEFINED_OVERLAYS", raising=False)
    monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD", raising=False)
    yield


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", ADMIN_PASSWORD)
    app = FastAPI()
    app.include_router(admin_router)
    app.include_router(api_router)
    return TestClient(app)


def _auth():
    return {"Authorization": f"Bearer {ADMIN_PASSWORD}"}


# ---------------------------------------------------------------------------
# preset_scopes
# ---------------------------------------------------------------------------


class TestPresetScopes:
    """The scope registry's contract is what the persistence builds on."""

    SAMPLE_STATE = {
        "team_home": {
            "name": "Real Madrid",
            "short_name": "RMA",
            "color_primary": "#FFFFFF",
            "color_secondary": "#FEC23E",
            "logo_url": "https://example.com/rm.png",
            # Live match keys — must NEVER leak into the snapshot:
            "points": 7,
            "sets_won": 2,
            "set_history": {"set_1": 25, "set_2": 23},
            "serving": True,
            "timeouts_taken": 1,
        },
        "team_away": {
            "name": "FC Barcelona",
            "color_primary": "#A50044",
        },
        "overlay_control": {
            "geometry": {"x": 10, "y": 20, "w": 1280, "h": 200},
            "colors": {"set_bg": "#000", "game_text": "#FFF"},
            "preferredStyle": "esports",
            # Visibility flags — explicitly NOT in any scope:
            "show_main_scoreboard": True,
            "show_bottom_ticker": False,
        },
        "match_info": {"current_set": 3, "best_of_sets": 5},
    }

    def test_known_scopes_are_the_documented_five(self):
        assert preset_scopes.SCOPES == (
            "team_home", "team_away", "overlay_layout",
            "overlay_colors", "overlay_style",
        )

    def test_team_home_excludes_match_state(self):
        snap = preset_scopes.extract(self.SAMPLE_STATE, "team_home")
        # Identity keys present:
        assert snap["name"] == "Real Madrid"
        assert snap["color_primary"] == "#FFFFFF"
        # Live-match keys absent — protecting against accidental rewinds:
        for forbidden in (
            "points", "sets_won", "set_history", "serving", "timeouts_taken",
        ):
            assert forbidden not in snap, (
                f"team_home snapshot leaked match key {forbidden!r}"
            )

    def test_team_away_extracts_only_present_keys(self):
        # away has only 'name' and 'color_primary' set — extractor
        # must drop the missing keys instead of writing None.
        snap = preset_scopes.extract(self.SAMPLE_STATE, "team_away")
        assert snap == {"name": "FC Barcelona", "color_primary": "#A50044"}

    def test_overlay_layout_round_trip(self):
        snap = preset_scopes.extract(self.SAMPLE_STATE, "overlay_layout")
        assert snap == {"geometry": {"x": 10, "y": 20, "w": 1280, "h": 200}}
        payload = preset_scopes.apply_payload(snap, "overlay_layout")
        assert payload == {"overlay_control": {
            "geometry": {"x": 10, "y": 20, "w": 1280, "h": 200},
        }}

    def test_overlay_colors_round_trip(self):
        snap = preset_scopes.extract(self.SAMPLE_STATE, "overlay_colors")
        payload = preset_scopes.apply_payload(snap, "overlay_colors")
        assert payload == {"overlay_control": {
            "colors": {"set_bg": "#000", "game_text": "#FFF"},
        }}

    def test_overlay_style_round_trip(self):
        snap = preset_scopes.extract(self.SAMPLE_STATE, "overlay_style")
        assert snap == {"preferredStyle": "esports"}
        payload = preset_scopes.apply_payload(snap, "overlay_style")
        assert payload == {"overlay_control": {"preferredStyle": "esports"}}

    def test_unknown_scope_returns_empty(self):
        assert preset_scopes.extract(self.SAMPLE_STATE, "ghost") == {}
        assert preset_scopes.apply_payload({"x": 1}, "ghost") == {}
        assert preset_scopes.is_known_scope("ghost") is False

    def test_empty_extract_means_skip_on_apply(self):
        # An overlay with no geometry set must produce an empty
        # snapshot and an empty apply payload — the endpoint relies
        # on this to drop scopes that would no-op.
        empty_state = {"overlay_control": {}}
        assert preset_scopes.extract(empty_state, "overlay_layout") == {}
        assert preset_scopes.apply_payload({}, "overlay_layout") == {}

    def test_merge_payloads_deep_merges(self):
        a = preset_scopes.apply_payload(
            preset_scopes.extract(self.SAMPLE_STATE, "overlay_colors"),
            "overlay_colors",
        )
        b = preset_scopes.apply_payload(
            preset_scopes.extract(self.SAMPLE_STATE, "overlay_style"),
            "overlay_style",
        )
        merged = preset_scopes.merge_payloads([a, b])
        # Both keys land under overlay_control without one wiping the
        # other — that's the whole point of the deep merge:
        assert merged["overlay_control"]["preferredStyle"] == "esports"
        assert merged["overlay_control"]["colors"]["set_bg"] == "#000"


# ---------------------------------------------------------------------------
# presets_store
# ---------------------------------------------------------------------------


class TestPresetsStore:
    def test_slugify_normalises_input(self):
        assert presets_store.slugify("Real Madrid as Home") == "real-madrid-as-home"
        assert presets_store.slugify("  ACB  Final  ") == "acb-final"
        assert presets_store.slugify("name_with-dashes/slashes") == "name-with-dashes-slashes"

    def test_slugify_rejects_invalid(self):
        for bad in ("", "   ", "---", "!!!"):
            with pytest.raises(ValueError):
                presets_store.slugify(bad)

    def test_slugify_strips_trailing_dash_after_truncation(self, monkeypatch):
        # Cut-point lands inside a run of non-alphanumerics that the
        # initial sub() already collapsed to ``-``. Without the
        # post-truncation ``rstrip("-")`` the slug would end in ``-``
        # and the validator would reject it with a misleading
        # "cannot derive" error instead of the silent-trim that the
        # operator expects when their name is over the cap.
        monkeypatch.setattr(presets_store, "PRESETS_MAX_NAME_LEN", 9)
        # "Real Madrid" → "real-madrid"; truncated to 9 → "real-madr"
        # (cleanly cut). Pick a name whose 9-char prefix ends in a
        # collapsed dash to exercise the strip:
        name = "Real M  drid"  # double-space → "-" → "real-m--drid"
        # Actually re.sub collapses any run of non-alnum to a single
        # "-", so "Real M  drid" → "real-m-drid". Truncate to 7 →
        # "real-m-" (trailing dash). ``[:7].strip("-")`` → "real-m".
        monkeypatch.setattr(presets_store, "PRESETS_MAX_NAME_LEN", 7)
        slug = presets_store.slugify(name)
        assert slug == "real-m", slug
        assert presets_store._SLUG_PATTERN.match(slug)

    def test_slugify_respects_configured_max_above_default(self, monkeypatch):
        # The legacy regex hardcoded a 64-char ceiling. After the
        # decoupling fix, raising PRESETS_MAX_NAME_LEN to 100 must
        # let a 90-char slug through without the regex rejecting it.
        monkeypatch.setattr(presets_store, "PRESETS_MAX_NAME_LEN", 100)
        name = "a" * 90
        slug = presets_store.slugify(name)
        assert len(slug) == 90
        assert presets_store._SLUG_PATTERN.match(slug)

    def test_create_persists_and_round_trips(self):
        rec = presets_store.create(
            name="Real Madrid as home",
            scopes=["team_home"],
            snapshots={"team_home": {"name": "Real Madrid"}},
        )
        assert rec["_meta"]["slug"] == "real-madrid-as-home"
        assert rec["_meta"]["name"] == "Real Madrid as home"
        # Round-trip:
        read = presets_store.read("real-madrid-as-home")
        assert read["snapshots"]["team_home"]["name"] == "Real Madrid"

    def test_duplicate_slug_raises(self):
        presets_store.create("Dup", ["team_home"], {"team_home": {"name": "x"}})
        with pytest.raises(presets_store.PresetExists):
            presets_store.create(
                "Dup", ["team_home"], {"team_home": {"name": "y"}},
            )

    def test_delete_idempotent(self):
        presets_store.create("Tmp", ["team_home"], {"team_home": {"name": "x"}})
        assert presets_store.delete("tmp") is True
        assert presets_store.delete("tmp") is False

    def test_list_sorted_case_insensitive(self):
        for n in ("Bravo", "alpha", "Charlie"):
            presets_store.create(n, ["team_home"], {"team_home": {"name": n}})
        names = [r["_meta"]["name"] for r in presets_store.list_all()]
        assert names == ["alpha", "Bravo", "Charlie"]

    def test_import_collision_appends_suffix(self):
        original = presets_store.create(
            "Same", ["team_home"], {"team_home": {"name": "x"}},
        )
        imported = presets_store.import_payload(original)
        assert imported["_meta"]["slug"] == "same-2"
        # Both are independently readable:
        assert presets_store.read("same")["_meta"]["slug"] == "same"
        assert presets_store.read("same-2")["_meta"]["slug"] == "same-2"

    def test_import_with_override_name(self):
        original = presets_store.create(
            "Original", ["team_home"], {"team_home": {"name": "x"}},
        )
        imported = presets_store.import_payload(
            original, override_name="Renamed copy",
        )
        assert imported["_meta"]["name"] == "Renamed copy"
        assert imported["_meta"]["slug"] == "renamed-copy"

    def test_catalogue_cap_rejects_overflow(self, monkeypatch):
        monkeypatch.setattr(presets_store, "PRESETS_MAX_RECORDS", 2)
        for n in ("a", "b"):
            presets_store.create(n, ["team_home"], {"team_home": {"name": n}})
        with pytest.raises(presets_store.PresetCatalogueFull):
            presets_store.create(
                "c", ["team_home"], {"team_home": {"name": "c"}},
            )


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


def _seed_overlay(client, name: str = "src", **state) -> str:
    """Create a custom overlay and apply *state* via PATCH-equivalent."""
    res = client.post(
        "/api/v1/admin/custom-overlays",
        json={"name": name}, headers=_auth(),
    )
    assert res.status_code == 200, res.text
    if state:
        # Use the state store directly — exercising a minimum dependency
        # surface; the PATCH endpoint is tested elsewhere.
        overlay_state_store.update_state_sync(name, state)
    return name


class TestPresetEndpointsAuth:
    def test_list_requires_auth(self, client):
        assert client.get("/api/v1/admin/presets").status_code == 401

    def test_create_requires_auth(self, client):
        res = client.post(
            "/api/v1/admin/presets",
            json={"name": "x", "source_oid": "y", "scopes": ["team_home"]},
        )
        assert res.status_code == 401

    def test_apply_requires_auth(self, client):
        res = client.post(
            "/api/v1/admin/presets/anything/apply",
            json={"target_oid": "x"},
        )
        assert res.status_code == 401


class TestPresetCreate:
    def test_create_from_overlay_state(self, client):
        _seed_overlay(client, "src", team_home={
            "name": "Real Madrid", "color_primary": "#FFF",
        })
        res = client.post(
            "/api/v1/admin/presets",
            json={
                "name": "RM home",
                "source_oid": "src",
                "scopes": ["team_home"],
            },
            headers=_auth(),
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["slug"] == "rm-home"
        assert body["scopes"] == ["team_home"]

        detail = client.get(
            "/api/v1/admin/presets/rm-home", headers=_auth(),
        ).json()
        assert detail["snapshots"]["team_home"]["name"] == "Real Madrid"
        # color_primary was set on the source — must be in the snapshot:
        assert detail["snapshots"]["team_home"]["color_primary"] == "#FFF"

    def test_create_drops_empty_scopes(self, client):
        # Source OID has no overlay_layout (geometry never set), so
        # the saved record must drop overlay_layout from its scopes
        # rather than persisting an empty snapshot.
        _seed_overlay(client, "src", team_home={"name": "RM"})
        res = client.post(
            "/api/v1/admin/presets",
            json={
                "name": "RM with empty scope",
                "source_oid": "src",
                "scopes": ["team_home", "overlay_layout"],
            },
            headers=_auth(),
        )
        assert res.status_code == 200
        assert res.json()["scopes"] == ["team_home"]

    def test_create_with_only_empty_scopes_400(self, client):
        _seed_overlay(client, "src")
        res = client.post(
            "/api/v1/admin/presets",
            json={
                "name": "Empty everything",
                "source_oid": "src",
                "scopes": ["overlay_layout"],
            },
            headers=_auth(),
        )
        assert res.status_code == 400
        assert "nothing to save" in res.json()["detail"]

    def test_unknown_scope_400(self, client):
        _seed_overlay(client, "src")
        res = client.post(
            "/api/v1/admin/presets",
            json={
                "name": "Bad",
                "source_oid": "src",
                "scopes": ["team_home", "bogus"],
            },
            headers=_auth(),
        )
        assert res.status_code == 400

    def test_unknown_source_oid_404(self, client):
        res = client.post(
            "/api/v1/admin/presets",
            json={"name": "x", "source_oid": "ghost", "scopes": ["team_home"]},
            headers=_auth(),
        )
        assert res.status_code == 404

    def test_duplicate_slug_409(self, client):
        _seed_overlay(client, "src", team_home={"name": "RM"})
        client.post(
            "/api/v1/admin/presets",
            json={"name": "RM", "source_oid": "src", "scopes": ["team_home"]},
            headers=_auth(),
        )
        res = client.post(
            "/api/v1/admin/presets",
            json={"name": "RM", "source_oid": "src", "scopes": ["team_home"]},
            headers=_auth(),
        )
        assert res.status_code == 409


class TestPresetApply:
    def test_apply_full_preset(self, client):
        _seed_overlay(client, "src", team_home={
            "name": "Real Madrid", "color_primary": "#FFF",
        }, overlay_control={"preferredStyle": "esports"})
        client.post(
            "/api/v1/admin/presets",
            json={
                "name": "RM full",
                "source_oid": "src",
                "scopes": ["team_home", "overlay_style"],
            },
            headers=_auth(),
        )
        # Brand new target overlay:
        _seed_overlay(client, "dst")
        res = client.post(
            "/api/v1/admin/presets/rm-full/apply",
            json={"target_oid": "dst"},
            headers=_auth(),
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert set(body["applied_scopes"]) == {"team_home", "overlay_style"}
        # State was actually merged into the target:
        target_state = overlay_state_store.get_state("dst")
        assert target_state["team_home"]["name"] == "Real Madrid"
        assert target_state["overlay_control"]["preferredStyle"] == "esports"

    def test_apply_subset_of_scopes(self, client):
        _seed_overlay(client, "src", team_home={
            "name": "Real Madrid",
        }, overlay_control={"preferredStyle": "esports"})
        client.post(
            "/api/v1/admin/presets",
            json={
                "name": "RM full",
                "source_oid": "src",
                "scopes": ["team_home", "overlay_style"],
            },
            headers=_auth(),
        )
        _seed_overlay(client, "dst")
        # Apply only team_home — overlay_style must NOT change on dst.
        original_style = (
            overlay_state_store.get_state("dst")
            .get("overlay_control", {}).get("preferredStyle")
        )
        res = client.post(
            "/api/v1/admin/presets/rm-full/apply",
            json={"target_oid": "dst", "scopes": ["team_home"]},
            headers=_auth(),
        )
        assert res.status_code == 200
        assert res.json()["applied_scopes"] == ["team_home"]
        target_state = overlay_state_store.get_state("dst")
        assert target_state["team_home"]["name"] == "Real Madrid"
        # The other scope did not flow through:
        assert (
            target_state.get("overlay_control", {}).get("preferredStyle")
            == original_style
        )

    def test_apply_unknown_target_404(self, client):
        _seed_overlay(client, "src", team_home={"name": "RM"})
        client.post(
            "/api/v1/admin/presets",
            json={"name": "x", "source_oid": "src", "scopes": ["team_home"]},
            headers=_auth(),
        )
        res = client.post(
            "/api/v1/admin/presets/x/apply",
            json={"target_oid": "ghost"},
            headers=_auth(),
        )
        assert res.status_code == 404

    def test_apply_unknown_preset_404(self, client):
        _seed_overlay(client, "dst")
        res = client.post(
            "/api/v1/admin/presets/no-such/apply",
            json={"target_oid": "dst"},
            headers=_auth(),
        )
        assert res.status_code == 404

    def test_apply_scope_not_in_preset_400(self, client):
        _seed_overlay(client, "src", team_home={"name": "RM"})
        client.post(
            "/api/v1/admin/presets",
            json={"name": "small", "source_oid": "src", "scopes": ["team_home"]},
            headers=_auth(),
        )
        _seed_overlay(client, "dst")
        res = client.post(
            "/api/v1/admin/presets/small/apply",
            json={"target_oid": "dst", "scopes": ["overlay_style"]},
            headers=_auth(),
        )
        assert res.status_code == 400
        assert "does not cover" in res.json()["detail"]


class TestPresetExportImport:
    def test_export_then_import_round_trip(self, client):
        _seed_overlay(client, "src", team_home={"name": "RM"})
        client.post(
            "/api/v1/admin/presets",
            json={"name": "RM", "source_oid": "src", "scopes": ["team_home"]},
            headers=_auth(),
        )
        export = client.get(
            "/api/v1/admin/presets/rm/export", headers=_auth(),
        )
        assert export.status_code == 200
        payload = export.json()
        # Round-trip through import — collision suffix bumps the slug.
        imported = client.post(
            "/api/v1/admin/presets/import",
            json={"payload": payload},
            headers=_auth(),
        )
        assert imported.status_code == 200
        assert imported.json()["slug"] == "rm-2"

    def test_import_strips_unknown_scopes(self, client):
        # Future-compat: a payload from a newer build that names a
        # scope this build doesn't know about must import cleanly,
        # dropping the unknown scope, instead of 400ing.
        body = {
            "_meta": {"name": "Future", "slug": "future"},
            "scopes": ["team_home", "future_scope"],
            "snapshots": {
                "team_home": {"name": "RM"},
                "future_scope": {"x": 1},
            },
        }
        imported = client.post(
            "/api/v1/admin/presets/import",
            json={"payload": body},
            headers=_auth(),
        )
        assert imported.status_code == 200
        assert imported.json()["scopes"] == ["team_home"]

    def test_import_with_only_unknown_scopes_400(self, client):
        body = {
            "_meta": {"name": "Future"},
            "scopes": ["future_scope"],
            "snapshots": {"future_scope": {"x": 1}},
        }
        res = client.post(
            "/api/v1/admin/presets/import",
            json={"payload": body},
            headers=_auth(),
        )
        assert res.status_code == 400


class TestPresetList:
    def test_list_returns_summaries_without_snapshots(self, client):
        _seed_overlay(client, "src", team_home={"name": "RM"})
        client.post(
            "/api/v1/admin/presets",
            json={"name": "Alpha", "source_oid": "src", "scopes": ["team_home"]},
            headers=_auth(),
        )
        res = client.get("/api/v1/admin/presets", headers=_auth())
        assert res.status_code == 200
        body = res.json()
        assert len(body) == 1
        # ``snapshots`` must not bloat the catalogue listing:
        assert "snapshots" not in body[0]
        assert body[0]["slug"] == "alpha"

    def test_delete_removes_from_listing(self, client):
        _seed_overlay(client, "src", team_home={"name": "RM"})
        client.post(
            "/api/v1/admin/presets",
            json={"name": "Doomed", "source_oid": "src", "scopes": ["team_home"]},
            headers=_auth(),
        )
        res = client.delete("/api/v1/admin/presets/doomed", headers=_auth())
        assert res.status_code == 200
        listing = client.get("/api/v1/admin/presets", headers=_auth()).json()
        assert listing == []

    def test_delete_unknown_404(self, client):
        res = client.delete("/api/v1/admin/presets/ghost", headers=_auth())
        assert res.status_code == 404
