"""Tests for OverlayStateStore._sanitize_id — the single choke point between
user-provided overlay ids and on-disk ``overlay_state_<id>.json`` paths."""

import os

import pytest

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


def test_create_overlay_rejects_invalid_id(store):
    """create_overlay returns False on invalid id instead of writing a file."""
    data_dir = store._data_dir
    assert store.create_overlay("../escape") is False
    # No file should have been written anywhere under or near data_dir.
    assert not any(f.startswith("overlay_state_") for f in os.listdir(data_dir))


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


def test_read_state_falls_back_to_default_on_corrupt_json(store, caplog):
    """A corrupt JSON file must not raise; we log a warning and fall
    back to the default state. Previously a bare ``except Exception``
    masked everything and made debugging hard — the narrow
    ``OSError | json.JSONDecodeError`` handler keeps the recovery path
    while letting unexpected errors surface."""
    import json
    import logging

    oid = "corrupt-1"
    # Create the overlay so the on-disk path exists, then overwrite with garbage.
    assert store.create_overlay(oid) is True
    path = store.get_state_file_path(oid)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not valid json")

    with caplog.at_level(logging.WARNING, logger="app.overlay.state_store"):
        loaded = store.load_persisted_state(oid)

    # Falls back to a fresh default rather than raising.
    assert isinstance(loaded, dict)
    assert any(
        "Failed to load state from" in rec.getMessage()
        for rec in caplog.records
    ), "expected a warning log for the corrupt-JSON file"

    # And a proper write still works after the recovery.
    loaded["_meta"] = {"overlay_id": oid, "smoke": True}
    store.save_persisted_state(oid, loaded)
    with open(path, encoding="utf-8") as f:
        roundtripped = json.load(f)
    assert roundtripped["_meta"]["smoke"] is True


def test_read_state_falls_back_when_file_unreadable(store, tmp_path, monkeypatch):
    """Permission / OS errors during read should log and fall back to
    defaults instead of crashing the caller."""
    oid = "perm-denied"
    assert store.create_overlay(oid) is True
    path = store.get_state_file_path(oid)

    # Simulate an OSError without actually chmoding (test runner often
    # runs as root and chmod 000 is a no-op).
    real_open = open

    def fake_open(p, *args, **kwargs):
        if p == path:
            raise OSError("simulated EACCES")
        return real_open(p, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    loaded = store.load_persisted_state(oid)
    assert isinstance(loaded, dict)
