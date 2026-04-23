# tests/test_backend.py
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add the project's root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.app_storage import AppStorage
from app.backend import Backend
from app.conf import Conf
from app.state import State

# The autouse fixture that was here has been moved to conftest.py
# to be applied globally to all tests, ensuring UI tests are also isolated.

@pytest.fixture
def mock_requests_session():
    """Fixture to mock the requests.Session object and top level requests."""
    with patch('app.backend.requests.Session') as mock_session_class, \
         patch('app.backend.requests.post') as mock_post:
        mock_session_instance = mock_session_class.return_value
        # Default successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'payload': {}}
        mock_session_instance.put.return_value = mock_response
        mock_session_instance.get.return_value = mock_response
        mock_session_instance.post.return_value = mock_response

        mock_post.return_value = mock_response

        yield mock_session_instance

@pytest.fixture
def conf():
    """Provides a default Conf instance for tests."""
    return Conf()

@pytest.fixture
def backend(conf, mock_requests_session):
    """Provides a Backend instance with a mocked session."""
    return Backend(conf)


# --- Test Cases ---

def test_initialization(conf):
    """Tests that the Backend initializes correctly and sets up session headers."""
    with patch('app.backend.requests.Session') as mock_session_class:
        mock_session_instance = mock_session_class.return_value
        Backend(conf)

        mock_session_class.assert_called_once()

        expected_headers = {
            'User-Agent': conf.rest_user_agent,
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*'
        }
        mock_session_instance.headers.update.assert_called_once_with(expected_headers)

def test_save_json_model(backend, mock_requests_session, conf):
    """Tests that a model is sent to the correct API endpoint with the correct payload."""
    model_to_save = {'Team 1 Game 1 Score': '10'}
    backend.save_json_model(model_to_save)

    expected_url = f'https://app.overlays.uno/apiv2/controlapps/{conf.oid}/api'
    expected_payload = {
        "command": "SetOverlayContent",
        "id": conf.id,
        "content": model_to_save
    }

    mock_requests_session.put.assert_called_once_with(expected_url, json=expected_payload, timeout=5.0)

def test_change_overlay_visibility(backend, mock_requests_session, conf):
    """Tests sending commands to show and hide the overlay."""
    # Test showing the overlay
    backend.change_overlay_visibility(True)
    expected_payload_show = {"command": "ShowOverlay", "id": conf.id, "content": ""}
    mock_requests_session.put.assert_called_with(mock_requests_session.put.call_args[0][0], json=expected_payload_show, timeout=5.0)

    # Test hiding the overlay
    backend.change_overlay_visibility(False)
    expected_payload_hide = {"command": "HideOverlay", "id": conf.id, "content": ""}
    mock_requests_session.put.assert_called_with(mock_requests_session.put.call_args[0][0], json=expected_payload_hide, timeout=5.0)

def test_get_current_model_success(backend, mock_requests_session):
    """Tests successfully retrieving the current model from the API."""
    expected_model = {'Team 1 Sets': '1'}
    mock_requests_session.put.return_value.json.return_value = {'payload': expected_model}

    retrieved_model = backend.get_current_model()

    assert retrieved_model == expected_model

@patch('app.overlay_backends.AppStorage.load')
def test_get_current_model_from_storage(mock_appstorage_load, backend, mock_requests_session):
    """Tests that the model is loaded from AppStorage if available, skipping the API call."""
    stored_model = {'Team 1 Sets': '2'}
    mock_appstorage_load.return_value = stored_model

    retrieved_model = backend.get_current_model()

    assert retrieved_model == stored_model
    mock_requests_session.put.assert_not_called()

def test_get_current_model_failure(backend, mock_requests_session):
    """Tests handling of a failed API call when retrieving the model."""
    mock_requests_session.put.return_value.status_code = 404

    retrieved_model = backend.get_current_model()

    assert retrieved_model is None

@patch('app.overlay_backends.AppStorage.save')
def test_validate_and_store_model_for_oid_valid(mock_appstorage_save, backend, mock_requests_session):
    """Tests the validation logic for a valid OID."""
    mock_requests_session.put.return_value.json.return_value = {'payload': {'Team 1 Sets': '0'}}

    result = backend.validate_and_store_model_for_oid("valid_oid")

    assert result == State.OIDStatus.VALID
    mock_appstorage_save.assert_called_once()

def test_validate_and_store_model_for_oid_invalid(backend, mock_requests_session):
    """Tests the validation logic for an invalid OID that causes an API failure."""
    mock_requests_session.put.return_value.status_code = 403 # Forbidden

    result = backend.validate_and_store_model_for_oid("invalid_oid")

    assert result == State.OIDStatus.INVALID

def test_validate_and_store_model_for_oid_deprecated(backend, mock_requests_session):
    """Tests the validation logic for a deprecated model format."""
    mock_requests_session.put.return_value.json.return_value = {'payload': {'game1State': 'some_value'}}

    result = backend.validate_and_store_model_for_oid("deprecated_oid")

    assert result == State.OIDStatus.DEPRECATED

def test_validate_and_store_model_for_oid_empty(backend):
    """Tests that an empty or None OID is correctly identified."""
    assert backend.validate_and_store_model_for_oid(None) == State.OIDStatus.EMPTY
    assert backend.validate_and_store_model_for_oid("  ") == State.OIDStatus.EMPTY

# --- New Test Cases ---

@patch('app.backend.ThreadPoolExecutor.submit')
def test_save_model_multithreaded(mock_submit, backend, conf):
    """Tests that save_model starts a new thread task when multithreading is enabled."""
    conf.multithread = True
    backend.save_model({}, simple=False)
    assert mock_submit.call_count == 1

@patch('app.backend.ThreadPoolExecutor.submit')
def test_save_model_single_threaded(mock_submit, backend, conf):
    """Tests that save_model does NOT start a new thread task when multithreading is disabled."""
    conf.multithread = False
    backend.save_model({}, simple=False)
    mock_submit.assert_not_called()

def test_reduce_games_to_one(backend, mock_requests_session, conf):
    """Tests that reduce_games_to_one sends the correct payload to reset scores."""
    backend.reduce_games_to_one()

    expected_payload = {
        "command": "SetOverlayContent",
        "id": conf.id,
        "content": {
            'Team 1 Game 5 Score': '0', 'Team 2 Game 5 Score': '0',
            'Team 1 Game 4 Score': '0', 'Team 2 Game 4 Score': '0',
            'Team 1 Game 3 Score': '0', 'Team 2 Game 3 Score': '0',
            'Team 1 Game 2 Score': '0', 'Team 2 Game 2 Score': '0'
        }
    }
    mock_requests_session.put.assert_called_once_with(mock_requests_session.put.call_args[0][0], json=expected_payload, timeout=5.0)

def test_save_json_customization(backend, mock_requests_session, conf):
    """Tests sending a customization payload."""
    customization_data = {"Width": 50.0, "Logos": "true"}
    backend.save_json_customization(customization_data)

    expected_payload = {
        "command": "SetCustomization",
        "value": customization_data
    }
    mock_requests_session.put.assert_called_once_with(mock_requests_session.put.call_args[0][0], json=expected_payload, timeout=5.0)

def test_is_visible(backend, mock_requests_session):
    """Tests the is_visible method for both True and False API responses."""
    # Test for True
    mock_requests_session.put.return_value.json.return_value = {'payload': True}
    assert backend.is_visible() is True

    # Test for False
    mock_requests_session.put.return_value.json.return_value = {'payload': False}
    assert backend.is_visible() is False

def test_reset(backend, mock_requests_session, conf):
    """Tests that the reset method saves the correct reset model."""
    # Temporarily disable multithreading for this test
    conf.multithread = False

    state = State()
    backend.reset(state)

    expected_payload = {
        "command": "SetOverlayContent",
        "id": conf.id,
        "content": state.get_reset_model()
    }

    # Now the assertion will correctly find that .put() has been called with the timeout included
    mock_requests_session.put.assert_any_call(
        mock_requests_session.put.call_args_list[0][0][0], json=expected_payload, timeout=5.0
    )
    assert mock_requests_session.put.call_count == 1

def test_api_call_with_custom_oid(backend, mock_requests_session, conf):
    """Tests that a custom OID overrides the default one in API calls."""
    custom_oid = "my_custom_oid"
    backend.get_current_model(customOid=custom_oid)

    expected_url = f'https://app.overlays.uno/apiv2/controlapps/{custom_oid}/api'
    mock_requests_session.put.assert_called_once()
    assert mock_requests_session.put.call_args[0][0] == expected_url

@patch('app.overlay_backends.AppStorage.save')
@patch('app.overlay_backends.AppStorage.load')
def test_get_current_model_saves_result(mock_appstorage_load, mock_appstorage_save, backend, mock_requests_session):
    """Tests that get_current_model saves the result when saveResult is True."""
    mock_appstorage_load.return_value = None
    expected_model = {'Team 1 Sets': '1'}
    mock_requests_session.put.return_value.json.return_value = {'payload': expected_model}

    backend.get_current_model(customOid="some_oid", saveResult=True)

    mock_appstorage_save.assert_called_once_with(AppStorage.Category.CURRENT_MODEL, expected_model, oid="some_oid")

def test_fetch_and_update_overlay_id(backend, mock_requests_session, conf):
    """Tests that validating an oid triggers a specific GetOverlays call to dynamically map conf.id"""
    expected_mock_layout_id = State.CHAMPIONSHIP_LAYOUT_ID
    mock_requests_session.put.return_value.json.return_value = {
        'status': 200,
        'payload': [{'id': expected_mock_layout_id, 'name': 'Volleyball'}]
    }

    # Executing the fetch updates the config
    backend.fetch_and_update_overlay_id("my_custom_oid")
    assert conf.id == expected_mock_layout_id

def test_save_model_explicit_sets_display_for_new_layout(backend, mock_requests_session, conf):
    """Tests that save_model specifically injects Sets Display when config ID matches the new layout."""
    conf.id = State.CHAMPIONSHIP_LAYOUT_ID
    conf.multithread = False

    # State containing Current Set property representing "2"
    mock_state = {State.CURRENT_SET_INT: "2"}

    backend.save_model(mock_state, simple=False)

    # Expected payload should explicitly carry the Sets Display map overriding "1" strings to what the Current Set possesses
    expected_payload = {
        "command": "SetOverlayContent",
        "id": conf.id,
        "content": {State.CURRENT_SET_INT: "2", "Sets Display": "2"}
    }
    mock_requests_session.put.assert_any_call(
        mock_requests_session.put.call_args_list[0][0][0], json=expected_payload, timeout=5.0
    )
    assert mock_requests_session.put.call_count == 1

# --- Custom Alternative Overlays Testing ---
# These tests verify CustomOverlayBackend (external server via HTTP).
# APP_CUSTOM_OVERLAY_URL must be set so Backend selects CustomOverlayBackend
# instead of LocalOverlayBackend.

@patch.dict(os.environ, {"APP_CUSTOM_OVERLAY_URL": "http://localhost:8000"})
def test_custom_overlay_save_model(backend, mock_requests_session, conf):
    """Tests that a C- prefixed OID skips Uno and sends to the custom local url."""
    conf.oid = "C-test_overlay"
    conf.multithread = False

    mock_model = {"Team 1 Sets": "1"}

    # Run the save
    backend.save_model(mock_model, simple=False)

    # Ensure Uno is NOT hit
    mock_requests_session.put.assert_not_called()

    # Ensure the local overlay IS hit via session.post (raw_config save + api/state update)
    state_calls = [c for c in mock_requests_session.post.call_args_list if '/api/state/' in str(c)]
    assert len(state_calls) == 1
    assert state_calls[0][0][0] == "http://localhost:8000/api/state/test_overlay"

@patch.dict(os.environ, {"APP_CUSTOM_OVERLAY_URL": "http://localhost:8000"})
def test_custom_overlay_lowercase_prefix(backend, mock_requests_session, conf):
    """Tests that a lowercase c- prefixed OID still routes to a known custom overlay."""
    # Uses the ``test_overlay`` fixture file present in ``data/`` so the
    # resolver classifies it as CUSTOM. The legacy ``c-`` prefix is still
    # accepted (case-insensitive) — see ``resolve_overlay_kind``.
    conf.oid = "c-test_overlay"
    conf.multithread = False

    # Run the save
    backend.save_model({"Team 1 Sets": "1"}, simple=False)

    # Ensure Uno is NOT hit
    mock_requests_session.put.assert_not_called()

    # Ensure the local overlay IS hit via session.post
    state_calls = [c for c in mock_requests_session.post.call_args_list if '/api/state/' in str(c)]
    assert len(state_calls) == 1
    assert state_calls[0][0][0] == "http://localhost:8000/api/state/test_overlay"

@patch.dict(os.environ, {"APP_CUSTOM_OVERLAY_URL": "http://localhost:8000"})
@patch('app.overlay_backends.AppStorage.load')
def test_custom_overlay_visibility(mock_load, backend, mock_requests_session, conf):
    """Tests that a C- prefixed OID handles visibility locally."""
    conf.oid = "C-test_overlay"
    conf.multithread = False
    mock_load.return_value = {"Team 1 Sets": "0"}

    backend.change_overlay_visibility(True)

    # Uno bypassed
    mock_requests_session.put.assert_not_called()

    # Local overlay hit via session.post
    state_calls = [c for c in mock_requests_session.post.call_args_list if '/api/state/' in str(c)]
    assert len(state_calls) == 1

@patch.dict(os.environ, {"APP_CUSTOM_OVERLAY_URL": "http://localhost:8000"})
def test_custom_overlay_fetch_token_skips(backend, mock_requests_session, conf):
    """Tests that fetch_output_token requests the local config endpoint for custom overlays."""
    conf.oid = "C-test_overlay"

    # Setup mock to return the expected configured outputUrl
    mock_requests_session.get.return_value.json.return_value = {"outputUrl": "http://localhost:8000/overlay/test_overlay"}

    result = backend.fetch_output_token(conf.oid)

    assert result == "http://localhost:8000/overlay/test_overlay"
    mock_requests_session.get.assert_called_once()
    assert mock_requests_session.get.call_args[0][0] == "http://localhost:8000/api/config/test_overlay"

@patch.dict(os.environ, {"APP_CUSTOM_OVERLAY_URL": "http://localhost:8000"})
def test_custom_overlay_get_current_model_fallbacks(backend, mock_requests_session, conf):
    """Tests that missing backend data returns default State instead of empty dict."""
    conf.oid = "C-test_overlay"

    # Run the get
    model = backend.get_current_model()

    assert model is not None
    assert model.get("Team 1 Timeouts") == "0"
    assert model.get("Current Set") == "1"

def test_custom_overlay_get_current_customization_fallbacks(backend, mock_requests_session, conf):
    """Tests that a missing customization returns default Customization state instead of empty dict."""
    conf.oid = "C-test_overlay"

    cust = backend.get_current_customization()

    assert cust is not None
    assert cust.get("Logos") == "true"
    assert "Color 1" in cust

@patch('app.overlay_backends.AppStorage.load')
def test_custom_overlay_is_visible_fallback(mock_load, backend, mock_requests_session, conf):
    """Tests that is_visible uses local fallback and true by default for custom overlays."""
    conf.oid = "C-test_overlay"
    assert backend.is_visible() is True
    mock_requests_session.put.assert_not_called()


def test_validate_custom_overlay_oid_is_valid(backend, mock_requests_session, conf):
    """Tests that a C- prefixed custom overlay OID validates as VALID."""
    conf.oid = "C-test_overlay"
    result = backend.validate_and_store_model_for_oid("C-test_overlay")
    assert result == State.OIDStatus.VALID


def test_validate_custom_overlay_oid_with_style_is_valid(backend, mock_requests_session, conf):
    """Tests that a custom overlay OID with style suffix validates as VALID."""
    conf.oid = "C-test_overlay/line"
    result = backend.validate_and_store_model_for_oid("C-test_overlay/line")
    assert result == State.OIDStatus.VALID


def test_validate_bare_existing_overlay_oid_is_valid(backend, mock_requests_session, conf):
    """A bare overlay id (no ``C-`` prefix) resolves as a custom overlay when it
    exists locally — this is the new preferred form."""
    result = backend.validate_and_store_model_for_oid("test_overlay")
    assert result == State.OIDStatus.VALID


def test_validate_bare_existing_overlay_with_style_is_valid(backend, mock_requests_session, conf):
    """The bare form also accepts a trailing ``/style`` constraint."""
    result = backend.validate_and_store_model_for_oid("test_overlay/line")
    assert result == State.OIDStatus.VALID


def test_validate_legacy_prefix_missing_overlay_does_not_autocreate(
    backend, mock_requests_session, conf,
):
    """Legacy ``C-`` prefix on a missing overlay must not auto-create — the
    resolver returns INVALID and the call falls through to the UNO backend,
    which rejects the format."""
    from app.overlay import overlay_state_store
    assert not overlay_state_store.overlay_exists("brand_new_local")

    # Make the UNO validation endpoint reject the OID.
    mock_requests_session.put.return_value.status_code = 404

    result = backend.validate_and_store_model_for_oid("C-brand_new_local")
    assert result == State.OIDStatus.INVALID
    # And no overlay state file was created behind the scenes.
    assert not overlay_state_store.overlay_exists("brand_new_local")


def test_is_custom_overlay_recognises_bare_existing_overlay(backend, conf):
    assert backend.is_custom_overlay("test_overlay") is True


def test_is_custom_overlay_rejects_unknown_bare_oid(backend, conf):
    assert backend.is_custom_overlay("nonexistent_overlay") is False


def test_is_custom_overlay_rejects_uno_format_oid(backend, conf):
    """22-char alphanumeric OID is treated as UNO, not custom."""
    assert backend.is_custom_overlay("2cIXk2IjHvMuva6Wwele8j") is False


def test_extract_oid_preserves_underscores_in_uno_url():
    """Tests that extract_oid correctly captures OIDs with underscores from Uno URLs."""
    from app.oid_utils import extract_oid
    assert extract_oid("https://app.overlays.uno/control/abc_123") == "abc_123"


def test_extract_oid_preserves_custom_overlay_oid():
    """Tests that extract_oid returns custom overlay OIDs unchanged."""
    from app.oid_utils import extract_oid
    assert extract_oid("C-mybroadcast") == "C-mybroadcast"
    assert extract_oid("C-mybroadcast/line") == "C-mybroadcast/line"


def test_extract_oid_handles_query_params():
    """Tests that extract_oid strips query params from Uno URLs."""
    from app.oid_utils import extract_oid
    assert extract_oid("https://app.overlays.uno/control/abc123?token=x") == "abc123"


def test_api_schema_accepts_custom_overlay_oid():
    """Tests that the API InitRequest schema accepts custom overlay OID formats."""
    from app.api.schemas import InitRequest
    req = InitRequest(oid="C-mybroadcast")
    assert req.oid == "C-mybroadcast"
    req2 = InitRequest(oid="C-mybroadcast/line")
    assert req2.oid == "C-mybroadcast/line"
