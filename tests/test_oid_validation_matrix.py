"""Cross-layer OID / overlay-id validation matrix.

Ensures API OIDs, overlay-store ids, and admin names stay aligned via
:mod:`app.id_validation`.
"""

import pytest

from app.id_validation import (
    api_oid_compatible_with_overlay_store,
    api_oid_overlay_base,
    is_uno_oid,
    is_valid_api_oid,
    is_valid_overlay_id,
    validate_api_oid,
    validate_overlay_id,
)


@pytest.mark.parametrize(
    "oid",
    [
        "mybroadcast",
        "C-mybroadcast",
        "mybroadcast/line",
        "f-2-capability-check",
        "a" * 64,
    ],
)
def test_api_and_overlay_accept_common_bare_ids(oid: str) -> None:
    assert is_valid_api_oid(oid)
    if "/" not in oid:
        assert is_valid_overlay_id(oid.replace("C-", "", 1) if oid.startswith("C-") else oid)
    assert api_oid_compatible_with_overlay_store(oid)


@pytest.mark.parametrize(
    "oid",
    [
        "a" * 201,
        "..",
        "foo..bar",
        "",
    ],
)
def test_api_rejects_invalid_oids(oid: str) -> None:
    assert not is_valid_api_oid(oid)


@pytest.mark.parametrize(
    "overlay_id",
    [
        "foo/bar",
        "a" * 65,
        ".",
        "..",
        "../x",
    ],
)
def test_overlay_store_rejects_unsafe_ids(overlay_id: str) -> None:
    assert not is_valid_overlay_id(overlay_id)
    with pytest.raises(ValueError):
        validate_overlay_id(overlay_id)


def test_api_oid_with_style_suffix_maps_to_overlay_base() -> None:
    assert api_oid_overlay_base("mybroadcast/line") == "mybroadcast"
    assert api_oid_overlay_base("C-legacy/style") == "legacy"


def test_api_oid_with_multiple_slashes_fails_overlay_compat() -> None:
    # API allows slashes, but only a single style suffix maps to overlay store.
    assert is_valid_api_oid("mybroadcast/line/extra")
    assert api_oid_overlay_base("mybroadcast/line/extra") is None


def test_uno_oid_format() -> None:
    assert is_uno_oid("2cIXk2IjHvMuva6Wwele8j")
    assert not is_uno_oid("mybroadcast")
    assert not is_uno_oid("2cIXk2IjHvMuva6Wwele8")  # too short


def test_validate_api_oid_returns_input() -> None:
    assert validate_api_oid("demo-1") == "demo-1"
