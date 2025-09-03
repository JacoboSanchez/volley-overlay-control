import pytest
import os
from nicegui.testing import User
from typing import Generator
from app.startup import startup
from dotenv import load_dotenv
import importlib
from app.app_storage import AppStorage

os.environ['PYTEST_CURRENT_TEST'] = 'true'

pytest_plugins = ['nicegui.testing.plugin']

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
    import app.oid_dialog
    importlib.reload(app.oid_dialog)


@pytest.fixture
def user(user: User) -> Generator[User, None, None]:
    startup()
    yield user