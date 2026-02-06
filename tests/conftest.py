import pytest
import os
import json
import importlib
import sys
from nicegui import app as nice_app
from nicegui.testing import User
from dotenv import load_dotenv
from typing import Generator
from unittest.mock import patch, MagicMock
from app.app_storage import AppStorage
from app.state import State

os.environ['PYTEST_CURRENT_TEST'] = 'true'

pytest_plugins = ['nicegui.testing.plugin']


@pytest.fixture(autouse=True)
def mock_backend():
    """
    Main fixture that simulates the Backend.
    Each test is responsible for overriding the mock's behavior as needed.
    """
    with patch('app.startup.Backend') as mock_backend_class:
        mock_instance = mock_backend_class.return_value

        # --- Default simulated behavior ---
        mock_instance.is_visible.return_value = True
        mock_instance.get_current_customization.return_value = load_fixture('base_customization')
        # Default model for simple tests. More complex tests will override this.
        mock_instance.get_current_model.return_value = load_fixture('base_model')

        # Simulates OID validation: only 'test_oid_valid' is valid.
        def validate_side_effect(oid):
            if oid is None:
                return State.OIDStatus.EMPTY
            if oid.endswith('_valid'):
                # We need to mock the get_current_model call inside validation
                if oid == 'predefined_1_valid':
                    mock_instance.get_current_model.return_value = load_fixture('predefined_overlay_1')
                elif oid == 'predefined_2_valid':
                    mock_instance.get_current_model.return_value = load_fixture('predefined_overlay_2')
                elif oid == 'manual_oid_valid':
                    mock_instance.get_current_model.return_value = load_fixture('manual_overlay')
                elif oid == 'endgame_oid_valid':
                    mock_instance.get_current_model.return_value = load_fixture('endgame_model')
                return State.OIDStatus.VALID
            return State.OIDStatus.INVALID
        
        # We need a MagicMock to allow replacing the side_effect in tests
        mock_instance.validate_and_store_model_for_oid = MagicMock(side_effect=validate_side_effect)
        yield mock_instance
    nice_app.startup_handler_registered = False  # Reset for other tests

@pytest.fixture(autouse=True)
def load_test_env(monkeypatch):
    """
    Loads environment variables from .env.test, sets a default OID,
    and cleans up both environment variables and AppStorage to ensure
    complete test isolation.
    """
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env.test')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path)

    # Sets a test OID so that most tests do not show the dialog by default.
    monkeypatch.setenv('UNO_OVERLAY_OID', 'test_oid_valid')
    
    # Clean up overlay environment variables before each test
    monkeypatch.delenv('PREDEFINED_OVERLAYS', raising=False)
    monkeypatch.delenv('HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED', raising=False)
    
    # Crucially, clear any stored data from previous tests
    AppStorage.clear_user_storage()
    
    # Reload the oid_dialog module to ensure it picks up the clean state
    # We import it via sys.modules or direct import to avoid ambiguity with 'app' variable if valid
    import app.oid_dialog
    importlib.reload(sys.modules['app.oid_dialog'])

def load_fixture(name):
    """Auxiliary function to load a JSON file from the fixtures folder."""
    path = os.path.join(os.path.dirname(__file__), 'fixtures', f'{name}.json')
    with open(path) as f:
        return json.load(f)