"""Tests for OverlayStateStore._sanitize_id — the single choke point between
user-provided overlay ids and persisted ``runtime_overlay_state`` rows."""

import pytest
from sqlalchemy.orm import Session

from app.db.runtime import OverlayRuntimeState
from app.overlay.state_store import OverlayStateStore


@pytest.fixture
def store(tmp_path):
    return OverlayStateStore(
        data_dir=str(tmp_path / "data"),
        templates_dir=str(tmp_path / "tpl"),
    )


@pytest.mark.parametrize(
    "valid_id",
    [
        "a",
        "abc123",
        "f-2-capability-check",
        "C-8637cb0f-df01-45bb-9782-c6d705aeff46",
        "overlay.v1",
        "over_lay",
        "A" * 64,
    ],
)
def test_sanitize_accepts_allowlisted(valid_id):
    assert OverlayStateStore._sanitize_id(valid_id) == valid_id


@pytest.mark.parametrize(
    "bad_id",
    [
        "",                 # empty
        "A" * 65,           # too long
        ".",                # current dir
        "..",               # parent dir
        "../etc/passwd",    # classic traversal
        "/etc/passwd",      # absolute
        "foo/bar",          # separator
        "foo\\bar",         # windows-style separator (not in allow-list)
        "foo\x00bar",       # NUL
        "foo bar",          # whitespace
        "foo#bar",          # reserved char
        "héllo",            # non-ASCII
    ],
)
def test_sanitize_rejects_bad_inputs(bad_id):
    with pytest.raises(ValueError):
        OverlayStateStore._sanitize_id(bad_id)


def test_sanitize_rejects_non_string():
    with pytest.raises(ValueError):
        OverlayStateStore._sanitize_id(None)
    with pytest.raises(ValueError):
        OverlayStateStore._sanitize_id(b"bytes")


def test_overlay_exists_returns_false_for_invalid_id(store):
    """Public boolean contract must not leak ValueError."""
    assert store.overlay_exists("../../secret") is False
    assert store.overlay_exists("") is False


def test_create_overlay_rejects_invalid_id(store, runtime_db):
    """create_overlay returns False on invalid id instead of writing a row."""
    assert store.create_overlay("../escape") is False
    with Session(runtime_db) as db:
        assert db.get(OverlayRuntimeState, "../escape") is None


def test_delete_overlay_rejects_invalid_id(store):
    """delete_overlay returns False on invalid id without touching disk."""
    assert store.delete_overlay("../../secret") is False


def test_valid_id_round_trip(store):
    """A well-formed id still flows through create → exists → delete."""
    oid = "round-trip-1"
    assert store.create_overlay(oid) is True
    assert store.overlay_exists(oid) is True
    assert store.delete_overlay(oid) is True
    assert store.overlay_exists(oid) is False


def test_read_state_falls_back_to_default_on_non_object_row(store, runtime_db):
    """A stored value that is not a JSON object loads as default state."""
    oid = "corrupt-1"
    assert store.create_overlay(oid) is True
    with Session(runtime_db) as db, db.begin():
        db.get(OverlayRuntimeState, oid).state = ["not", "a", "dict"]

    loaded = store.load_persisted_state(oid)
    assert isinstance(loaded, dict)
    assert "team_home" in loaded

    # And a proper write still works after the recovery.
    loaded["_meta"] = {"overlay_id": oid, "smoke": True}
    store.save_persisted_state(oid, loaded)
    assert store.load_persisted_state(oid)["_meta"]["smoke"] is True


def test_read_error_propagates_instead_of_caching_defaults(store, monkeypatch, caplog):
    """A database error must not read as "no state".

    Answering with defaults would put them in the in-memory context, and the
    next mutation would persist them over the real row.
    """
    import logging

    from app.overlay import state_store as module

    oid = "db-down"
    assert store.create_overlay(oid) is True
    store.update_state_sync(oid, {"team_home": {"points": 9}})
    store._overlays.clear()  # force the next read to hit the database

    real_session = module.runtime_session

    def broken_session():
        raise RuntimeError("simulated outage")

    monkeypatch.setattr(module, "runtime_session", broken_session)
    with caplog.at_level(logging.WARNING, logger="app.overlay.state_store"), pytest.raises(RuntimeError):
        store.get_state(oid)
    assert oid not in store._overlays
    assert any("Failed to load state for" in r.getMessage() for r in caplog.records)

    monkeypatch.setattr(module, "runtime_session", real_session)
    assert store.get_state(oid)["team_home"]["points"] == 9


def test_create_never_overwrites_an_existing_row(store, monkeypatch):
    """Even when the existence probe wrongly answers "absent" (a transient
    error), creation is insert-only and leaves the real row alone."""
    oid = "keep-me"
    assert store.create_overlay(oid) is True
    store.update_state_sync(oid, {"team_home": {"points": 5}})
    store._existing.clear()
    store._overlays.clear()
    monkeypatch.setattr(store, "_row_exists", lambda _oid: False)

    assert store.create_overlay(oid) is False
    assert store.load_persisted_state(oid)["team_home"]["points"] == 5


def test_failed_scan_is_retried_not_cached_as_empty(store, monkeypatch):
    oid = "scan-me"
    assert store.create_overlay(oid) is True
    store._output_key_cache.clear()
    store._all_overlays_scanned = False

    def broken():
        raise RuntimeError("simulated outage")

    monkeypatch.setattr(store, "_iter_persisted_ids", broken)
    assert store.resolve_overlay_id(oid) is None
    assert store._all_overlays_scanned is False
    monkeypatch.undo()
    assert store.resolve_overlay_id(oid) == oid


def test_existence_probe_racing_a_delete_is_not_cached(store, monkeypatch):
    """A probe that saw the row before a concurrent delete must not put a
    stale "exists" back into the cache."""
    oid = "racy"
    assert store.create_overlay(oid) is True
    store._existing.clear()
    real_probe = store._row_exists

    def probe_then_delete(overlay_id):
        found = real_probe(overlay_id)
        store.delete_overlay(overlay_id)  # lands between probe and cache write
        return found

    monkeypatch.setattr(store, "_row_exists", probe_then_delete)
    assert store.overlay_exists(oid) is True  # the probe's (now stale) answer
    monkeypatch.undo()
    assert oid not in store._existing
    assert store.overlay_exists(oid) is False


def test_write_failure_keeps_in_memory_state(store, monkeypatch):
    """A failed save is logged, not raised, so a live match keeps going."""
    oid = "write-fail"
    assert store.create_overlay(oid) is True

    def broken_write(overlay_id, state):
        raise RuntimeError("disk full")

    monkeypatch.setattr(store, "_write_row", broken_write)
    store.update_state_sync(oid, {"team_home": {"points": 7}})
    assert store.get_state(oid)["team_home"]["points"] == 7
