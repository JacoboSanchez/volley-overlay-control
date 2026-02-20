# tests/test_backend.py
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Add the project's root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.backend import Backend
from app.conf import Conf
from app.state import State
from app.app_storage import AppStorage

# The autouse fixture that was here has been moved to conftest.py
# to be applied globally to all tests, ensuring UI tests are also isolated.

@pytest.fixture
def mock_requests_session():
    """Fixture to mock the requests.Session object."""
    with patch('app.backend.requests.Session') as mock_session_class:
        mock_session_instance = mock_session_class.return_value
        # Default successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session_instance.put.return_value = mock_response
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
        be = Backend(conf)
        
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

@patch('app.backend.AppStorage.load')
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

@patch('app.backend.AppStorage.save')
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
    mock_submit.assert_called_once()

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
    mock_requests_session.put.assert_called_once_with(
        mock_requests_session.put.call_args[0][0], json=expected_payload, timeout=5.0
    )

def test_api_call_with_custom_oid(backend, mock_requests_session, conf):
    """Tests that a custom OID overrides the default one in API calls."""
    custom_oid = "my_custom_oid"
    backend.get_current_model(customOid=custom_oid)
    
    expected_url = f'https://app.overlays.uno/apiv2/controlapps/{custom_oid}/api'
    mock_requests_session.put.assert_called_once()
    assert mock_requests_session.put.call_args[0][0] == expected_url

@patch('app.backend.AppStorage.save')
def test_get_current_model_saves_result(mock_appstorage_save, backend, mock_requests_session):
    """Tests that get_current_model saves the result when saveResult is True."""
    expected_model = {'Team 1 Sets': '1'}
    mock_requests_session.put.return_value.json.return_value = {'payload': expected_model}

    backend.get_current_model(customOid="some_oid", saveResult=True)

    mock_appstorage_save.assert_called_once_with(AppStorage.Category.CURRENT_MODEL, expected_model, oid="some_oid")