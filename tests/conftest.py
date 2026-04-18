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
        "_all_overlays_scanned": overlay_state_store._all_overlays_scanned,
    }
    overlay_state_store._data_dir = str(seed_dir)
    overlay_state_store._overlays = {}
    overlay_state_store._output_key_cache = {}
    overlay_state_store._available_styles = None
    overlay_state_store._all_overlays_scanned = False
    overlay_state_store.create_overlay("test_overlay")

    yield

    overlay_state_store._data_dir = saved["_data_dir"]
    overlay_state_store._overlays = saved["_overlays"]
    overlay_state_store._output_key_cache = saved["_output_key_cache"]
    overlay_state_store._available_styles = saved["_available_styles"]
    overlay_state_store._all_overlays_scanned = saved["_all_overlays_scanned"]


def load_fixture(name):
    """Auxiliary function to load a JSON file from the fixtures folder."""
    path = os.path.join(os.path.dirname(__file__), 'fixtures', f'{name}.json')
    with open(path) as f:
        return json.load(f)
