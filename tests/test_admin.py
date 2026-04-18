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
    # it in a JS closure variable only.
    assert "sessionStorage.setItem" not in res.text
    assert "localStorage.setItem" not in res.text
