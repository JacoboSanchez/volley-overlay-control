import json
import os
from unittest.mock import MagicMock

import pytest
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


@pytest.fixture(autouse=True)
def isolate_overlay_store(tmp_path_factory):
    """Point the overlay state store at a per-test temp dir and seed
    ``test_overlay`` so the OID resolver classifies it as CUSTOM.

    The repository's ``data/`` directory is gitignored, so CI never has the
    developer-local fixture files. Without seeding, ``resolve_overlay_kind``
    falls through to UNO and the custom-overlay tests assert against the
    wrong backend.

    Uses a dedicated tmp dir (not the per-test ``tmp_path``) so tests that
    own their own data dir via ``tmp_path`` (e.g. ``test_admin.py``) are not
    polluted by the seeded fixture file.
    """
    from app.overlay import overlay_state_store

    seed_dir = tmp_path_factory.mktemp("overlay_seed")
    saved = {
        "_data_dir": overlay_state_store._data_dir,
        "_overlays": overlay_state_store._overlays,
        "_output_key_cache": overlay_state_store._output_key_cache,
        "_available_styles": overlay_state_store._available_styles,
        "_renderable_styles": overlay_state_store._renderable_styles,
        "_all_overlays_scanned": overlay_state_store._all_overlays_scanned,
    }
    overlay_state_store._data_dir = str(seed_dir)
    overlay_state_store._overlays = {}
    overlay_state_store._output_key_cache = {}
    overlay_state_store._available_styles = None
    overlay_state_store._renderable_styles = None
    overlay_state_store._all_overlays_scanned = False
    overlay_state_store.create_overlay("test_overlay")

    yield

    overlay_state_store._data_dir = saved["_data_dir"]
    overlay_state_store._overlays = saved["_overlays"]
    overlay_state_store._output_key_cache = saved["_output_key_cache"]
    overlay_state_store._available_styles = saved["_available_styles"]
    overlay_state_store._renderable_styles = saved["_renderable_styles"]
    overlay_state_store._all_overlays_scanned = saved["_all_overlays_scanned"]


def load_fixture(name):
    """Auxiliary function to load a JSON file from the fixtures folder."""
    path = os.path.join(os.path.dirname(__file__), 'fixtures', f'{name}.json')
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Shared API-layer fixtures (previously duplicated in test_api.py).
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_sessions():
    """Ensure a clean SessionManager and WSHub for every test."""
    from app.api.session_manager import SessionManager
    from app.api.ws_hub import WSHub

    SessionManager.clear()
    WSHub.clear()
    yield
    SessionManager.clear()
    WSHub.clear()


@pytest.fixture
def mock_conf():
    conf = MagicMock()
    conf.oid = 'test-oid'
    conf.output = None
    conf.points = 25
    conf.points_last_set = 15
    conf.sets = 5
    conf.multithread = False
    conf.rest_user_agent = 'test'
    conf.id = 'test-layout'
    conf.single_overlay = True
    return conf


@pytest.fixture
def api_backend():
    """MagicMock Backend that returns canned customization/model fixtures.

    Named ``api_backend`` (not ``mock_backend``) so it does not collide with
    ``test_game_manager.py``'s local ``mock_backend`` which is ``spec=Backend``.
    """
    backend = MagicMock()
    backend.get_current_model.return_value = load_fixture('base_model')
    backend.get_current_customization.return_value = load_fixture('base_customization')
    backend.is_visible.return_value = True
    backend.is_custom_overlay.return_value = False
    return backend


@pytest.fixture
def api_session(mock_conf, api_backend, clean_sessions):
    from app.api.session_manager import SessionManager
    return SessionManager.get_or_create('test-oid', mock_conf, api_backend)
