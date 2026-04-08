import pytest
import os
import json
from dotenv import load_dotenv
from app.app_storage import AppStorage

os.environ['PYTEST_CURRENT_TEST'] = 'true'


@pytest.fixture(autouse=True)
def load_test_env(monkeypatch):
    """
    Loads environment variables from .env.test, sets a default OID,
    and cleans up AppStorage to ensure test isolation.
    """
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env.test')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path)

    monkeypatch.setenv('UNO_OVERLAY_OID', 'test_oid_valid')
    monkeypatch.delenv('PREDEFINED_OVERLAYS', raising=False)
    monkeypatch.delenv('HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED', raising=False)

    AppStorage.clear_user_storage()


def load_fixture(name):
    """Auxiliary function to load a JSON file from the fixtures folder."""
    path = os.path.join(os.path.dirname(__file__), 'fixtures', f'{name}.json')
    with open(path) as f:
        return json.load(f)
