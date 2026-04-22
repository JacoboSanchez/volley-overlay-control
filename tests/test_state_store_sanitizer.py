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
        OverlayStateStore._sanitize_id(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        OverlayStateStore._sanitize_id(b"bytes")  # type: ignore[arg-type]


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
