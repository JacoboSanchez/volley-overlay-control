"""Tests for the overlay management admin module."""

import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin import admin_page_router, admin_router
from app.admin.store import OverlaysStore, managed_overlays_store
from app.api import api_router


ADMIN_PASSWORD = "s3cret"


@pytest.fixture(autouse=True)
def _reset_store(tmp_path, monkeypatch):
    """Point the shared store at an isolated temp dir for every test."""
    managed_overlays_store._reset_for_tests(str(tmp_path))
    monkeypatch.delenv("PREDEFINED_OVERLAYS", raising=False)
    monkeypatch.delenv("SCOREBOARD_USERS", raising=False)
    monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD", raising=False)
    yield
    managed_overlays_store._reset_for_tests(str(tmp_path))


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
# OverlaysStore
# ---------------------------------------------------------------------------


def test_store_persists_overlays(tmp_path):
    store = OverlaysStore(str(tmp_path))
    store.create("Court A", {"control": "TOKEN1", "output": "OUT1"})

    # Re-open from disk.
    other = OverlaysStore(str(tmp_path))
    entries = other.list()
    assert len(entries) == 1
    assert entries[0]["name"] == "Court A"
    assert entries[0]["control"] == "TOKEN1"
    assert entries[0]["output"] == "OUT1"


def test_store_rejects_duplicates(tmp_path):
    store = OverlaysStore(str(tmp_path))
    store.create("Main", {"control": "T"})
    with pytest.raises(KeyError):
        store.create("Main", {"control": "T"})


def test_store_requires_control(tmp_path):
    store = OverlaysStore(str(tmp_path))
    with pytest.raises(ValueError):
        store.create("Main", {"control": "   "})


def test_store_update_and_rename(tmp_path):
    store = OverlaysStore(str(tmp_path))
    store.create("Main", {"control": "T1"})
    store.update(
        "Main",
        {"control": "T2", "allowed_users": ["user1"]},
        new_name="Primary",
    )
    assert store.get("Main") is None
    updated = store.get("Primary")
    assert updated["control"] == "T2"
    assert updated["allowed_users"] == ["user1"]


def test_store_update_rename_conflict(tmp_path):
    store = OverlaysStore(str(tmp_path))
    store.create("A", {"control": "T1"})
    store.create("B", {"control": "T2"})
    with pytest.raises(KeyError):
        store.update("A", {"control": "T1"}, new_name="B")


def test_store_delete(tmp_path):
    store = OverlaysStore(str(tmp_path))
    store.create("Gone", {"control": "T"})
    store.delete("Gone")
    assert store.get("Gone") is None
    with pytest.raises(KeyError):
        store.delete("Gone")


def test_store_returns_defensive_copies(tmp_path):
    """Mutating the dicts/lists returned by list()/get()/as_dict() must not
    affect the store's internal state."""
    store = OverlaysStore(str(tmp_path))
    store.create("Main", {"control": "T", "allowed_users": ["u1"]})

    snapshot = store.get("Main")
    snapshot["control"] = "HIJACKED"
    snapshot["allowed_users"].append("intruder")

    fresh = store.get("Main")
    assert fresh["control"] == "T"
    assert fresh["allowed_users"] == ["u1"]

    # list() and as_dict() must also yield independent copies.
    listed = store.list()
    listed[0]["allowed_users"].append("intruder2")
    assert store.get("Main")["allowed_users"] == ["u1"]

    as_dict = store.as_dict()
    as_dict["Main"]["allowed_users"].append("intruder3")
    assert store.get("Main")["allowed_users"] == ["u1"]


def test_store_ignores_malformed_file(tmp_path):
    path = tmp_path / OverlaysStore.FILENAME
    path.write_text("not valid json", encoding="utf-8")
    store = OverlaysStore(str(tmp_path))
    assert store.list() == []


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_admin_status_reports_enabled(client):
    res = client.get("/api/v1/admin/status")
    assert res.status_code == 200
    assert res.json() == {"enabled": True}


def test_admin_status_when_disabled(monkeypatch):
    # No password configured.
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
    res = client.get("/api/v1/admin/overlays", headers=_auth("anything"))
    assert res.status_code == 503


def test_login_rejects_bad_password(client):
    res = client.post("/api/v1/admin/login", headers=_auth("wrong"))
    assert res.status_code == 403


def test_login_accepts_correct_password(client):
    res = client.post("/api/v1/admin/login", headers=_auth())
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_list_requires_auth(client):
    res = client.get("/api/v1/admin/overlays")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


def test_create_list_update_delete(client):
    # Create
    res = client.post(
        "/api/v1/admin/overlays",
        json={"name": "Court 1", "control": "TOKEN1", "output": "OUT1"},
        headers=_auth(),
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Court 1"

    # List
    res = client.get("/api/v1/admin/overlays", headers=_auth())
    assert res.status_code == 200
    entries = res.json()
    assert len(entries) == 1
    assert entries[0]["control"] == "TOKEN1"

    # Update + rename
    res = client.put(
        "/api/v1/admin/overlays/Court 1",
        json={
            "name": "Court 1",
            "new_name": "Court A",
            "control": "TOKEN2",
            "allowed_users": ["u1"],
        },
        headers=_auth(),
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Court A"

    # Delete
    res = client.delete("/api/v1/admin/overlays/Court A", headers=_auth())
    assert res.status_code == 200
    assert res.json() == {"ok": True}

    res = client.get("/api/v1/admin/overlays", headers=_auth())
    assert res.json() == []


def test_create_conflict(client):
    client.post(
        "/api/v1/admin/overlays",
        json={"name": "Dup", "control": "T"},
        headers=_auth(),
    )
    res = client.post(
        "/api/v1/admin/overlays",
        json={"name": "Dup", "control": "T"},
        headers=_auth(),
    )
    assert res.status_code == 409


def test_update_missing(client):
    res = client.put(
        "/api/v1/admin/overlays/ghost",
        json={"name": "ghost", "control": "T"},
        headers=_auth(),
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Public overlays endpoint merges managed + env
# ---------------------------------------------------------------------------


def test_public_overlays_merges_managed_and_env(client, monkeypatch):
    monkeypatch.setenv(
        "PREDEFINED_OVERLAYS",
        json.dumps({"Env overlay": {"control": "ENV-TOKEN"}}),
    )
    client.post(
        "/api/v1/admin/overlays",
        json={"name": "Managed overlay", "control": "MAN-TOKEN"},
        headers=_auth(),
    )

    res = client.get("/api/v1/overlays")
    assert res.status_code == 200
    names = {o["name"] for o in res.json()}
    assert names == {"Env overlay", "Managed overlay"}


def test_public_overlays_managed_overrides_env(client, monkeypatch):
    monkeypatch.setenv(
        "PREDEFINED_OVERLAYS",
        json.dumps({"Same": {"control": "ENV-TOKEN"}}),
    )
    client.post(
        "/api/v1/admin/overlays",
        json={"name": "Same", "control": "MAN-TOKEN"},
        headers=_auth(),
    )

    res = client.get("/api/v1/overlays")
    overlays = res.json()
    assert len(overlays) == 1
    assert overlays[0]["oid"] == "MAN-TOKEN"


# ---------------------------------------------------------------------------
# Static HTML page
# ---------------------------------------------------------------------------


def test_manage_page_served(client):
    res = client.get("/manage")
    assert res.status_code == 200
    assert "Overlay Manager" in res.text
    # The admin password must not be persisted client-side — the page keeps
    # it in a JS closure variable only.
    assert "sessionStorage.setItem" not in res.text
    assert "localStorage.setItem" not in res.text
