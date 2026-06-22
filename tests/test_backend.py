# tests/test_backend.py
"""Backend coordinator tests.

Every overlay is served in-process by ``LocalOverlayBackend`` (there is no
cloud/external backend). The conftest ``isolate_overlay_store`` fixture seeds a
local overlay named ``test_overlay`` so the resolver classifies it as CUSTOM.
"""
import pytest

from app.backend import Backend
from app.conf import Conf
from app.overlay_backends import LocalOverlayBackend
from app.state import State

SEEDED_OID = "test_overlay"  # created by the conftest overlay-store fixture


@pytest.fixture
def conf():
    c = Conf()
    c.oid = SEEDED_OID
    c.multithread = False
    return c


@pytest.fixture
def backend(conf):
    return Backend(conf)


def test_initialization_uses_local_backend(backend):
    assert isinstance(backend._overlay, LocalOverlayBackend)
    assert backend._overlay.is_custom is True


def test_is_custom_overlay_for_existing_local_overlay(backend):
    assert backend.is_custom_overlay(SEEDED_OID) is True


def test_is_custom_overlay_false_for_unknown_oid(backend):
    assert backend.is_custom_overlay("does-not-exist") is False


def test_validate_existing_overlay_is_valid(backend):
    assert backend.validate_and_store_model_for_oid(SEEDED_OID) == State.OIDStatus.VALID


def test_validate_existing_overlay_with_style_suffix_is_valid(backend):
    assert (
        backend.validate_and_store_model_for_oid(f"{SEEDED_OID}/line")
        == State.OIDStatus.VALID
    )


def test_validate_legacy_prefix_existing_overlay_is_valid(backend):
    assert (
        backend.validate_and_store_model_for_oid(f"C-{SEEDED_OID}")
        == State.OIDStatus.VALID
    )


def test_validate_unknown_overlay_is_invalid(backend):
    assert backend.validate_and_store_model_for_oid("nope") == State.OIDStatus.INVALID


def test_validate_legacy_prefix_missing_overlay_is_invalid(backend):
    # The legacy ``C-`` syntax never auto-creates a missing overlay.
    assert backend.validate_and_store_model_for_oid("C-missing") == State.OIDStatus.INVALID


def test_validate_empty_is_empty(backend):
    assert backend.validate_and_store_model_for_oid("") == State.OIDStatus.EMPTY


def test_save_and_get_model_roundtrip(backend):
    model = State().get_reset_model()
    model["Team 1 Game 1 Score"] = 7
    backend.save_model(model, False)
    got = backend.get_current_model(SEEDED_OID)
    assert int(got["Team 1 Game 1 Score"]) == 7


def test_save_model_single_threaded_pushes_inline(backend, conf):
    conf.multithread = False
    model = State().get_reset_model()
    # Should not raise and should persist without an executor.
    backend.save_model(model, False)
    assert backend.get_current_model(SEEDED_OID) is not None


def test_get_customization_returns_a_dict(backend):
    data = backend.get_current_customization(SEEDED_OID)
    assert isinstance(data, dict)


def test_save_customization_roundtrip(backend):
    data = backend.get_current_customization(SEEDED_OID)  # full default model
    data["Team 1 Name"] = "Home"
    backend.save_json_customization(data)
    assert backend.get_current_customization(SEEDED_OID).get("Team 1 Name") == "Home"


def test_is_visible_defaults_true(backend):
    assert backend.is_visible() is True


def test_change_visibility(backend):
    backend.change_overlay_visibility(False)
    assert backend.is_visible() is False
    backend.change_overlay_visibility(True)
    assert backend.is_visible() is True


def test_fetch_output_token_is_local_overlay_url(backend):
    url = backend.fetch_output_token(SEEDED_OID)
    assert "/overlay/" in url


def test_available_styles_is_a_list(backend):
    assert isinstance(backend.get_available_styles(SEEDED_OID), list)


def test_reset_zeroes_current_set_score(backend):
    state = State()
    state.set_game(1, 1, 9)
    backend.save_model(state.get_current_model(), False)
    backend.reset(state)
    got = backend.get_current_model(SEEDED_OID)
    assert int(got.get("Team 1 Game 1 Score", 0)) == 0
