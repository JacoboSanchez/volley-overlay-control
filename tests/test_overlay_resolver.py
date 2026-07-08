"""Tests for ``app.overlay_backends.utils.resolve_overlay_kind`` and helpers.

The resolver decides whether an OID points at a known local overlay or is
invalid. The legacy ``C-`` prefix is still accepted for backward compatibility
but never auto-creates a missing overlay.
"""

import pytest

from app.overlay_backends.utils import (
    OverlayKind,
    is_custom_overlay,
    resolve_overlay_kind,
    split_custom_oid,
    strip_legacy_prefix,
)


def make_store(*ids):
    known = set(ids)
    return lambda oid: oid in known


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


def test_resolve_kind_unknown_id_is_invalid():
    store = make_store()
    assert resolve_overlay_kind("nonexistent", store) == OverlayKind.INVALID


def test_resolve_kind_strips_surrounding_whitespace():
    store = make_store("foo")
    assert resolve_overlay_kind("  foo  ", store) == OverlayKind.CUSTOM
    assert resolve_overlay_kind("  bar  ", store) == OverlayKind.INVALID
