"""Tests for ``app.overlay_backends.utils.resolve_overlay_kind`` and helpers.

The resolver is the new single source of truth that decides whether an OID
points at a custom (local) overlay, an overlays.uno cloud overlay, or is
invalid. The legacy ``C-`` prefix is still accepted for backward compatibility
but never auto-creates a missing overlay.
"""

import pytest

from app.overlay_backends.utils import (
    OverlayKind,
    UNO_OID_LENGTH,
    is_custom_overlay,
    matches_uno_format,
    resolve_overlay_kind,
    split_custom_oid,
    strip_legacy_prefix,
)


# A representative UNO OID — mixed-case alphanumeric, exactly 22 chars.
UNO_OID = "2cIXk2IjHvMuva6Wwele8j"


@pytest.fixture
def store_with(tmp_overlay_ids=None):
    """Return a callable simulating a local overlay store."""
    ids = set(tmp_overlay_ids or [])

    def _exists(overlay_id: str) -> bool:
        return overlay_id in ids

    return _exists


def make_store(*ids):
    known = set(ids)
    return lambda oid: oid in known


# ---------------------------------------------------------------------------
# matches_uno_format
# ---------------------------------------------------------------------------


def test_uno_oid_constant_matches_real_world_example():
    assert UNO_OID_LENGTH == 22
    assert len(UNO_OID) == 22
    assert matches_uno_format(UNO_OID)


@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        "short",
        "x" * 21,                     # one char too few
        "x" * 23,                     # one char too many
        "abcdefghij-lmnopqrstuvw",    # 22 but contains '-'
        "abcdefghij/lmnopqrstuvw",    # 22 but contains '/'
        "C-mybroadcast",              # legacy prefix is not UNO
    ],
)
def test_matches_uno_format_rejects_non_uno_inputs(value):
    assert not matches_uno_format(value)


# ---------------------------------------------------------------------------
# is_custom_overlay (legacy helper) and strip_legacy_prefix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        ("C-foo", True),
        ("c-foo", True),                 # case-insensitive
        ("C-foo/style", True),
        ("foo", False),
        ("", False),
        (None, False),
        (UNO_OID, False),
    ],
)
def test_is_custom_overlay(value, expected):
    assert is_custom_overlay(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("C-foo", "foo"),
        ("c-foo/style", "foo/style"),
        ("foo", "foo"),
        ("", ""),
        (None, ""),
    ],
)
def test_strip_legacy_prefix(value, expected):
    assert strip_legacy_prefix(value) == expected


def test_split_custom_oid_handles_legacy_and_bare_forms():
    assert split_custom_oid("C-foo") == ("foo", None)
    assert split_custom_oid("C-foo/line") == ("foo", "line")
    assert split_custom_oid("foo") == ("foo", None)
    assert split_custom_oid("foo/line") == ("foo", "line")


# ---------------------------------------------------------------------------
# resolve_overlay_kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   "])
def test_resolve_kind_empty(value):
    assert resolve_overlay_kind(value, make_store()) == OverlayKind.EMPTY


def test_resolve_kind_bare_existing_overlay_is_custom():
    store = make_store("mybroadcast")
    assert resolve_overlay_kind("mybroadcast", store) == OverlayKind.CUSTOM


def test_resolve_kind_bare_existing_overlay_with_style_is_custom():
    store = make_store("mybroadcast")
    assert (
        resolve_overlay_kind("mybroadcast/line", store) == OverlayKind.CUSTOM
    )


def test_resolve_kind_legacy_prefix_existing_overlay_is_custom():
    store = make_store("mybroadcast")
    assert resolve_overlay_kind("C-mybroadcast", store) == OverlayKind.CUSTOM
    assert (
        resolve_overlay_kind("c-mybroadcast/line", store) == OverlayKind.CUSTOM
    )


def test_resolve_kind_legacy_prefix_missing_overlay_is_invalid():
    """Legacy syntax must not auto-create — missing overlay -> INVALID."""
    store = make_store()  # nothing exists
    assert resolve_overlay_kind("C-missing", store) == OverlayKind.INVALID
    # Even when the OID would otherwise look like a UNO OID, the explicit
    # legacy prefix forces the custom path and disables UNO fallback.
    legacy_uno_shaped = "C-" + ("a" * UNO_OID_LENGTH)
    assert (
        resolve_overlay_kind(legacy_uno_shaped, store) == OverlayKind.INVALID
    )


def test_resolve_kind_bare_uno_format_falls_back_to_uno():
    store = make_store()  # not a known custom overlay
    assert resolve_overlay_kind(UNO_OID, store) == OverlayKind.UNO


def test_resolve_kind_local_overlay_wins_over_uno_format():
    """A 22-char alphanumeric id that also exists locally is CUSTOM."""
    store = make_store(UNO_OID)
    assert resolve_overlay_kind(UNO_OID, store) == OverlayKind.CUSTOM


def test_resolve_kind_unknown_short_id_is_invalid():
    store = make_store()
    assert resolve_overlay_kind("nonexistent", store) == OverlayKind.INVALID


def test_resolve_kind_strips_surrounding_whitespace():
    store = make_store("foo")
    assert resolve_overlay_kind("  foo  ", store) == OverlayKind.CUSTOM
    assert resolve_overlay_kind(f"  {UNO_OID}  ", store) == OverlayKind.UNO
