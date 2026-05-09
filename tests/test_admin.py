"""Tests for the custom overlay admin module."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin import admin_page_router, admin_router
from app.api import api_router
from app.overlay import overlay_state_store

ADMIN_PASSWORD = "s3cret"


@pytest.fixture(autouse=True)
def _reset_store(tmp_path, monkeypatch):
    """Point the overlay state store at an isolated temp dir for every test."""
    overlay_state_store._data_dir = str(tmp_path)
    overlay_state_store._overlays = {}
    overlay_state_store._output_key_cache = {}
    overlay_state_store._available_styles = None
    overlay_state_store._renderable_styles = None
    monkeypatch.delenv("PREDEFINED_OVERLAYS", raising=False)
    monkeypatch.delenv("SCOREBOARD_USERS", raising=False)
    monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD", raising=False)
    yield


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", ADMIN_PASSWORD)
    app = FastAPI()
    app.include_router(admin_page_router)
    app.include_router(admin_router)
    app.include_router(api_router)
    return TestClient(app)


def _auth(password=ADMIN_PASSWORD):
    return {"Authorization": f"Bearer {password}"}


# ---------------------------------------------------------------------------
# Status / auth
# ---------------------------------------------------------------------------


def test_admin_status_reports_enabled(client):
    res = client.get("/api/v1/admin/status")
    assert res.status_code == 200
    assert res.json() == {"enabled": True}


def test_admin_status_when_disabled(monkeypatch):
    monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD", raising=False)
    app = FastAPI()
    app.include_router(admin_router)
    client = TestClient(app)
    res = client.get("/api/v1/admin/status")
    assert res.status_code == 200
    assert res.json() == {"enabled": False}


def test_admin_requires_password_when_disabled(monkeypatch):
    monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD", raising=False)
    app = FastAPI()
    app.include_router(admin_router)
    client = TestClient(app)
    res = client.get("/api/v1/admin/custom-overlays", headers=_auth("anything"))
    assert res.status_code == 503


def test_login_rejects_bad_password(client):
    res = client.post("/api/v1/admin/login", headers=_auth("wrong"))
    assert res.status_code == 403


def test_login_accepts_correct_password(client):
    res = client.post("/api/v1/admin/login", headers=_auth())
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_list_requires_auth(client):
    res = client.get("/api/v1/admin/custom-overlays")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Custom overlay CRUD
# ---------------------------------------------------------------------------


def test_list_empty(client):
    res = client.get("/api/v1/admin/custom-overlays", headers=_auth())
    assert res.status_code == 200
    assert res.json() == []


def test_create_custom_overlay(client):
    res = client.post(
        "/api/v1/admin/custom-overlays",
        json={"name": "mybroadcast"},
        headers=_auth(),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == "mybroadcast"
    assert body["oid"] == "mybroadcast"
    assert body["output_key"]

    res = client.get("/api/v1/admin/custom-overlays", headers=_auth())
    entries = res.json()
    assert len(entries) == 1
    assert entries[0]["id"] == "mybroadcast"


def test_create_rejects_duplicate(client):
    client.post(
        "/api/v1/admin/custom-overlays",
        json={"name": "dup"}, headers=_auth(),
    )
    res = client.post(
        "/api/v1/admin/custom-overlays",
        json={"name": "dup"}, headers=_auth(),
    )
    assert res.status_code == 409


def test_create_rejects_invalid_name(client):
    res = client.post(
        "/api/v1/admin/custom-overlays",
        json={"name": "bad/name"}, headers=_auth(),
    )
    assert res.status_code == 400


def test_create_rejects_empty_name(client):
    res = client.post(
        "/api/v1/admin/custom-overlays",
        json={"name": "   "}, headers=_auth(),
    )
    # Pydantic rejects empty string at min_length, returns 422.
    assert res.status_code in (400, 422)


def test_create_copy_inherits_configuration(client):
    # Seed a source overlay with a custom raw_config we can later compare.
    client.post(
        "/api/v1/admin/custom-overlays",
        json={"name": "source"}, headers=_auth(),
    )
    overlay_state_store.set_raw_config(
        "source",
        customization={"preferredStyle": "esports", "team_home_color": "#abcdef"},
    )

    res = client.post(
        "/api/v1/admin/custom-overlays",
        json={"name": "clone", "copy_from": "source"},
        headers=_auth(),
    )
    assert res.status_code == 200

    source_raw = overlay_state_store.get_raw_config("source")
    clone_raw = overlay_state_store.get_raw_config("clone")
    assert clone_raw["customization"] == source_raw["customization"]


def test_create_copy_missing_source(client):
    res = client.post(
        "/api/v1/admin/custom-overlays",
        json={"name": "clone", "copy_from": "ghost"},
        headers=_auth(),
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /custom-overlays/{name}  (M4 — Fase 1)
# ---------------------------------------------------------------------------


@pytest.fixture
def overlay_named(client):
    """Create a fresh custom overlay and yield its id."""
    name = "patchme"
    res = client.post(
        "/api/v1/admin/custom-overlays",
        json={"name": name}, headers=_auth(),
    )
    assert res.status_code == 200
    yield name


class TestPatchCustomOverlay:
    def test_requires_auth(self, client, overlay_named):
        res = client.patch(
            f"/api/v1/admin/custom-overlays/{overlay_named}",
            json={"theme": "dark"},
        )
        assert res.status_code == 401

    def test_unknown_overlay_returns_404(self, client):
        res = client.patch(
            "/api/v1/admin/custom-overlays/ghost",
            json={"theme": "dark"}, headers=_auth(),
        )
        assert res.status_code == 404

    def test_empty_patch_rejected(self, client, overlay_named):
        res = client.patch(
            f"/api/v1/admin/custom-overlays/{overlay_named}",
            json={}, headers=_auth(),
        )
        assert res.status_code == 400
        assert "at least one of" in res.json()["detail"]

    def test_invalid_id_rejected(self, client):
        res = client.patch(
            "/api/v1/admin/custom-overlays/bad..name",
            json={"theme": "dark"}, headers=_auth(),
        )
        # ``..`` is filtered by _validate_overlay_id (rejects ".." stem).
        # The pattern actually allows dots, so ``bad..name`` matches the
        # admin-side allow-list — the failure comes from "not found".
        assert res.status_code in (400, 404)

    def test_unknown_theme_returns_404(self, client, overlay_named):
        res = client.patch(
            f"/api/v1/admin/custom-overlays/{overlay_named}",
            json={"theme": "no-such-theme"}, headers=_auth(),
        )
        assert res.status_code == 404
        assert "no-such-theme" in res.json()["detail"]

    def test_apply_theme_persists_colors(self, client, overlay_named):
        res = client.patch(
            f"/api/v1/admin/custom-overlays/{overlay_named}",
            json={"theme": "dark"}, headers=_auth(),
        )
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == overlay_named
        state = overlay_state_store.get_state(overlay_named)
        # ``dark`` theme sets specific bg/text colors — verify a couple.
        colors = state["overlay_control"]["colors"]
        assert colors["set_bg"] == "#222222"
        assert colors["game_text"] == "#FFFFFF"

    def test_apply_theme_with_preferred_style(self, client, overlay_named):
        # ``esports`` includes preferredStyle on top of colors.
        res = client.patch(
            f"/api/v1/admin/custom-overlays/{overlay_named}",
            json={"theme": "esports"}, headers=_auth(),
        )
        assert res.status_code == 200
        state = overlay_state_store.get_state(overlay_named)
        assert state["overlay_control"]["preferredStyle"] == "esports"
        assert state["overlay_control"]["colors"]["set_text"] == "#00FFFF"

    def test_colors_only_merge(self, client, overlay_named):
        res = client.patch(
            f"/api/v1/admin/custom-overlays/{overlay_named}",
            json={"colors": {"set_bg": "#123456", "team_home": "#abcdef"}},
            headers=_auth(),
        )
        assert res.status_code == 200
        state = overlay_state_store.get_state(overlay_named)
        assert state["overlay_control"]["colors"]["set_bg"] == "#123456"
        assert state["overlay_control"]["colors"]["team_home"] == "#abcdef"

    def test_explicit_colors_override_theme(self, client, overlay_named):
        # Theme baseline + override on top: the operator's explicit color
        # must win, not the theme's.
        res = client.patch(
            f"/api/v1/admin/custom-overlays/{overlay_named}",
            json={"theme": "dark", "colors": {"set_bg": "#FF00FF"}},
            headers=_auth(),
        )
        assert res.status_code == 200
        state = overlay_state_store.get_state(overlay_named)
        assert state["overlay_control"]["colors"]["set_bg"] == "#FF00FF"
        # The other theme colors survive (deep-merge, not replace).
        assert state["overlay_control"]["colors"]["game_text"] == "#FFFFFF"

    def test_invalid_preferred_style_rejected(self, client, overlay_named):
        res = client.patch(
            f"/api/v1/admin/custom-overlays/{overlay_named}",
            json={"preferred_style": "non-existent-template"},
            headers=_auth(),
        )
        assert res.status_code == 400
        assert "preferred_style" in res.json()["detail"]

    def test_combined_patch_writes_state_once(self, client, overlay_named):
        """Theme + overrides must collapse into a single ``update_state``.

        Two ``update_state`` calls would mean two disk writes plus two
        WebSocket broadcasts for one logical edit. Mock the store call
        directly to prove the call count.
        """
        from unittest.mock import AsyncMock

        from app.overlay import overlay_state_store

        original = overlay_state_store.update_state
        mock = AsyncMock(side_effect=original)
        overlay_state_store.update_state = mock
        try:
            res = client.patch(
                f"/api/v1/admin/custom-overlays/{overlay_named}",
                json={
                    "theme": "dark",
                    "colors": {"set_bg": "#FF00FF"},
                    "preferred_style": "default",
                },
                headers=_auth(),
            )
        finally:
            overlay_state_store.update_state = original
        assert res.status_code == 200
        # Single coalesced write — used to be two (theme then overrides).
        assert mock.call_count == 1
        merged = mock.call_args.args[1]
        # Theme baseline survived (game_text from "dark"); explicit
        # set_bg won; preferred_style folded into the same payload.
        oc = merged["overlay_control"]
        assert oc["colors"]["set_bg"] == "#FF00FF"
        assert oc["colors"]["game_text"] == "#FFFFFF"
        assert oc["preferredStyle"] == "default"

    def test_default_preferred_style_accepted(self, client, overlay_named):
        # ``default`` is the implicit fallback (index.html) and not in
        # get_available_styles_list — the handler must accept it explicitly.
        res = client.patch(
            f"/api/v1/admin/custom-overlays/{overlay_named}",
            json={"preferred_style": "default"}, headers=_auth(),
        )
        assert res.status_code == 200
        state = overlay_state_store.get_state(overlay_named)
        assert state["overlay_control"]["preferredStyle"] == "default"


# ---------------------------------------------------------------------------
# GET /custom-overlays/{name}/usage  (M7 — Fase 1)
# ---------------------------------------------------------------------------


class TestCustomOverlayUsage:
    def test_requires_auth(self, client, overlay_named):
        res = client.get(
            f"/api/v1/admin/custom-overlays/{overlay_named}/usage",
        )
        assert res.status_code == 401

    def test_unknown_overlay_returns_404(self, client):
        res = client.get(
            "/api/v1/admin/custom-overlays/ghost/usage",
            headers=_auth(),
        )
        assert res.status_code == 404

    def test_idle_overlay_reports_zero(self, client, overlay_named):
        res = client.get(
            f"/api/v1/admin/custom-overlays/{overlay_named}/usage",
            headers=_auth(),
        )
        assert res.status_code == 200
        body = res.json()
        assert body == {
            "obs_clients": 0,
            "frontend_ws_clients": 0,
            "has_active_session": False,
            "seconds_since_last_activity": None,
        }

    def test_reports_active_session(self, client, overlay_named):
        # Materialise a GameSession for the overlay — ``SessionManager.get``
        # is the same path the WS / API routes take, so this exercises the
        # real registry rather than a mock.
        from app.api.session_manager import SessionManager
        SessionManager.get_or_create(overlay_named)
        try:
            res = client.get(
                f"/api/v1/admin/custom-overlays/{overlay_named}/usage",
                headers=_auth(),
            )
            assert res.status_code == 200
            body = res.json()
            assert body["has_active_session"] is True
            assert isinstance(body["seconds_since_last_activity"], int)
            assert body["seconds_since_last_activity"] >= 0
        finally:
            SessionManager.remove(overlay_named)

    def test_reports_obs_client_count(self, client, overlay_named):
        # The hub treats ``add_client`` as the canonical way to register
        # an OBS source — fake one with a sentinel object since we only
        # care about the count, not real WebSocket I/O.
        from app.overlay import obs_broadcast_hub
        sentinel = object()
        obs_broadcast_hub._clients.setdefault(overlay_named, []).append(sentinel)
        try:
            res = client.get(
                f"/api/v1/admin/custom-overlays/{overlay_named}/usage",
                headers=_auth(),
            )
            assert res.status_code == 200
            assert res.json()["obs_clients"] == 1
        finally:
            obs_broadcast_hub._clients.pop(overlay_named, None)


def test_delete_custom_overlay(client):
    client.post(
        "/api/v1/admin/custom-overlays",
        json={"name": "temp"}, headers=_auth(),
    )
    res = client.delete("/api/v1/admin/custom-overlays/temp", headers=_auth())
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    assert overlay_state_store.overlay_exists("temp") is False


def test_delete_missing(client):
    res = client.delete("/api/v1/admin/custom-overlays/ghost", headers=_auth())
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# POST /webhooks/replay  (M16 — Fase 4)
# ---------------------------------------------------------------------------


class TestWebhookReplayEndpoint:
    """Operator-triggered redelivery of dead-lettered webhooks."""

    @pytest.fixture
    def replay_env(self, monkeypatch, tmp_path):
        """Isolate the dead-letter file and shrink retry timing."""
        from app.api import webhook_dead_letter, webhooks

        monkeypatch.setattr(webhooks, "WEBHOOK_RETRY_ATTEMPTS", 0)
        monkeypatch.setattr(webhooks, "WEBHOOK_RETRY_BASE_SECONDS", 0)
        monkeypatch.setattr(webhooks, "WEBHOOK_RETRY_MAX_SECONDS", 0)
        monkeypatch.setattr(webhook_dead_letter, "_data_dir", lambda: str(tmp_path))
        monkeypatch.setenv("WEBHOOKS_ALLOW_PRIVATE_IPS", "true")
        monkeypatch.setenv("WEBHOOKS_URL", "https://hooks.example.com/x")
        webhooks.webhook_dispatcher.reload()
        yield

    def test_requires_auth(self, client, replay_env):
        res = client.post("/api/v1/admin/webhooks/replay")
        assert res.status_code == 401

    def test_empty_dead_letter_is_a_clean_no_op(self, client, replay_env):
        res = client.post(
            "/api/v1/admin/webhooks/replay", headers=_auth(),
        )
        assert res.status_code == 200
        body = res.json()
        assert body == {
            "considered": 0,
            "succeeded": 0,
            "still_failing": 0,
            "skipped_unknown_url": 0,
            "remaining_in_dl": 0,
        }

    def test_redelivers_and_prunes_successes(self, client, replay_env):
        from unittest.mock import MagicMock, patch

        from app.api import webhook_dead_letter
        webhook_dead_letter.append({
            "url": "https://hooks.example.com/x",
            "event": "set_end", "oid": "o", "body": "{}",
            "last_error": "HTTP 503", "attempts": 4,
        })
        with patch(
            "app.api.webhooks.requests.post",
            return_value=MagicMock(status_code=200),
        ):
            res = client.post(
                "/api/v1/admin/webhooks/replay", headers=_auth(),
            )
        assert res.status_code == 200
        body = res.json()
        assert body["considered"] == 1
        assert body["succeeded"] == 1
        assert body["still_failing"] == 0
        # The DL file is now empty.
        assert webhook_dead_letter.read_all() == []

    def test_max_records_caps_per_call_and_reports_remaining(
        self, client, replay_env,
    ):
        from unittest.mock import MagicMock, patch

        from app.api import webhook_dead_letter

        # Seed 5 records — all targeting the same configured URL.
        for i in range(5):
            webhook_dead_letter.append({
                "url": "https://hooks.example.com/x",
                "event": "set_end", "oid": f"o{i}", "body": "{}",
            })
        with patch(
            "app.api.webhooks.requests.post",
            return_value=MagicMock(status_code=200),
        ) as post:
            res = client.post(
                "/api/v1/admin/webhooks/replay",
                params={"max_records": 2},
                headers=_auth(),
            )
        assert res.status_code == 200
        body = res.json()
        assert body["considered"] == 2
        assert body["succeeded"] == 2
        # 3 remaining records (5 seeded - 2 redelivered) stayed in
        # the file, untouched by this call.
        assert body["remaining_in_dl"] == 3
        # Two redeliveries hit the network.
        assert post.call_count == 2
        # File content matches: 3 oldest-eligible records were
        # consumed by replay, so the 3 newest remain.
        remaining = webhook_dead_letter.read_all()
        assert len(remaining) == 3
        assert [r["oid"] for r in remaining] == ["o2", "o3", "o4"]

    def test_since_filter_keeps_older_records_untouched(self, client, replay_env):
        import time as _time
        from unittest.mock import MagicMock, patch

        from app.api import webhook_dead_letter

        old_ts = _time.time() - 3600
        recent_ts = _time.time()
        webhook_dead_letter.append({
            "ts": old_ts,
            "url": "https://hooks.example.com/x",
            "event": "set_end", "oid": "old", "body": "{}",
        })
        webhook_dead_letter.append({
            "ts": recent_ts,
            "url": "https://hooks.example.com/x",
            "event": "set_end", "oid": "new", "body": "{}",
        })
        with patch(
            "app.api.webhooks.requests.post",
            return_value=MagicMock(status_code=200),
        ):
            # Replay only the recent one.
            res = client.post(
                "/api/v1/admin/webhooks/replay",
                params={"since": recent_ts - 1},
                headers=_auth(),
            )
        assert res.status_code == 200
        body = res.json()
        assert body["considered"] == 1
        assert body["succeeded"] == 1
        # The old record is still on disk.
        remaining = webhook_dead_letter.read_all()
        assert len(remaining) == 1
        assert remaining[0]["oid"] == "old"


# ---------------------------------------------------------------------------
# Public overlays endpoint no longer merges managed overlays
# ---------------------------------------------------------------------------


def test_public_overlays_only_from_env(client, monkeypatch):
    monkeypatch.setenv(
        "PREDEFINED_OVERLAYS",
        json.dumps({"Env overlay": {"control": "ENV-TOKEN"}}),
    )
    # Creating a custom overlay through the admin API must NOT add it to
    # the public predefined-overlay list — those come from env only now.
    client.post(
        "/api/v1/admin/custom-overlays",
        json={"name": "mybroadcast"}, headers=_auth(),
    )

    res = client.get("/api/v1/overlays")
    assert res.status_code == 200
    names = {o["name"] for o in res.json()}
    assert names == {"Env overlay"}


# ---------------------------------------------------------------------------
# Static HTML page
# ---------------------------------------------------------------------------


def test_manage_page_served(client):
    res = client.get("/manage")
    assert res.status_code == 200
    assert "Custom Overlay Manager" in res.text
    # The admin password must not be persisted client-side — the page keeps
    # it in a JS closure variable only. We allow other localStorage writes
    # for opaque per-overlay UI state (e.g. the "last applied preset" hint
    # introduced in Phase 2), so the password-leak guard is now expressed
    # by name rather than as a blanket setItem ban.
    assert "sessionStorage.setItem" not in res.text
    assert "localStorage.setItem('password'" not in res.text
    assert "localStorage.setItem(\"password\"" not in res.text
    assert "localStorage.setItem(`password`" not in res.text
    # Defensive — also reject obvious aliases. ``password`` flows
    # through a single closure variable named ``password`` in the
    # script, so any setItem call referencing that token would be a
    # regression.
    for forbidden in ("setItem(password",
                      "sessionStorage.password",
                      "localStorage.password"):
        assert forbidden not in res.text
