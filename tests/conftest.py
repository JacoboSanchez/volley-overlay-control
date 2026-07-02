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


@pytest.fixture(autouse=True)
def isolate_session_meta(tmp_path_factory, monkeypatch):
    """Redirect session-meta persistence to a per-test temp dir.

    SessionManager.get_or_create persists a small JSON file per OID to
    survive process restarts. Without isolation those files would leak
    between tests via the real ``data/`` directory and rehydrate
    sessions with stale limits/simple-mode flags.
    """
    from app.api import session_persistence

    seed_dir = tmp_path_factory.mktemp("session_meta")
    monkeypatch.setattr(session_persistence, "_data_dir", lambda: str(seed_dir))


@pytest.fixture(autouse=True)
def isolate_action_log(tmp_path_factory, monkeypatch):
    """Redirect the per-OID audit log to a per-test temp dir.

    Also resets ``action_log``'s in-memory per-OID state (the monotonic
    timestamp tracker and the mutation-version counter) and drops the
    ``live_stats`` memoization cache. These live at module scope and are
    deliberately not persisted, so without an explicit reset a fresh test
    reusing an OID would inherit the previous test's version counter and
    could be served a stale cached stats payload for a now-empty log.
    """
    from app.api import action_log, live_stats

    seed_dir = tmp_path_factory.mktemp("action_log")
    monkeypatch.setattr(action_log, "_data_dir", lambda: str(seed_dir))
    action_log._version_per_oid.clear()
    action_log._last_ts_per_oid.clear()
    live_stats.clear_cache()


@pytest.fixture(autouse=True)
def isolate_match_archive(tmp_path_factory, monkeypatch):
    """Redirect archived match snapshots to a per-test temp dir."""
    from app.api import match_archive

    seed_dir = tmp_path_factory.mktemp("match_archive")
    monkeypatch.setattr(match_archive, "_data_dir", lambda: str(seed_dir))


@pytest.fixture(autouse=True)
def isolate_security_bootstrap(tmp_path_factory, monkeypatch):
    """Redirect the security bootstrap's data dir to a per-test temp dir.

    ``app.security_bootstrap.ensure_session_secret`` writes a persisted
    ``data/.session_secret`` file on first invocation. Tests that build a
    real FastAPI app via ``bootstrap.create_app()`` (e.g.
    ``test_trusted_hosts_and_cors``) trigger the bootstrap and would
    otherwise pollute the dev tree's real ``data/`` directory and leak
    secret state between tests.

    Mirrors the per-module isolation used for ``action_log``,
    ``match_archive``, ``session_persistence``, and
    ``overlay_state_store``.
    """
    from app import security_bootstrap

    seed_dir = tmp_path_factory.mktemp("security_bootstrap")
    monkeypatch.setattr(security_bootstrap, "_data_dir", lambda: str(seed_dir))


@pytest.fixture(autouse=True)
def reset_auth_rate_limiter():
    """Clear the per-IP auth rate-limiter between tests.

    The limiter is a process-global keyed by client IP and counts 401/403
    failures across all ``/api/v1/`` routes. Every TestClient shares the
    ``testclient`` IP, so without a reset the many auth-failure cases in the
    suite accumulate and trip the limiter (429) for later, unrelated tests.
    """
    from app.api.middleware import auth_rate_limit

    auth_rate_limit._reset_for_tests()
    yield
    auth_rate_limit._reset_for_tests()


@pytest.fixture(autouse=True)
def db_session(monkeypatch):
    """Give every test a fresh in-memory SQLite database.

    A ``StaticPool`` keeps the single in-memory connection alive for the
    whole test so the schema and rows persist across sessions. The app's
    global engine/``SessionLocal`` are pointed at it via ``configure_engine``,
    and ``db_migrate.run_migrations`` is stubbed to a no-op because the
    schema is built here with ``create_all`` (running Alembic against the
    file DB in ``database_url()`` would target the wrong database).

    Yields a live ``Session`` for tests that want to seed/inspect rows
    directly; request handlers get their own sessions via ``get_db``.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from app.db import Base, configure_engine, get_sessionmaker
    from app.db import migrate as db_migrate

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    configure_engine(engine=engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db_migrate, "run_migrations", lambda: None)

    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def isolate_webhook_dispatcher():
    """Reset the process-wide webhook dispatcher around every test.

    ``app.api.webhooks.webhook_dispatcher`` is a module-level singleton
    that caches its target list on first use and lazily owns a background
    ``ThreadPoolExecutor``. Without a reset between tests, a case that sets
    ``WEBHOOKS_URL`` leaves those targets cached on the singleton, so a
    later test that merely drives a game action — which fans out through
    ``game_audit_hooks`` to the dispatcher — fires real webhook HTTP to the
    stale URL on a background thread. Those deliveries retry with backoff
    and land, seconds later, on whichever ``requests.post`` mock or
    assertion happens to be active, making the suite order- and
    timing-dependent.

    Shutting the singleton down before and after each test drops the cached
    config (so an unconfigured test dispatches to nothing) and cancels any
    queued deliveries. Mirrors the file-local ``reset_dispatcher`` in
    ``test_webhooks.py``, promoted here so every test gets the same
    isolation.
    """
    from app.api import webhooks

    webhooks.webhook_dispatcher.shutdown()
    yield
    webhooks.webhook_dispatcher.shutdown()


def load_fixture(name):
    """Auxiliary function to load a JSON file from the fixtures folder."""
    path = os.path.join(os.path.dirname(__file__), 'fixtures', f'{name}.json')
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Cookie-auth helpers for the multi-user model.
# ---------------------------------------------------------------------------


def make_user(db_session, username="tester", *, password="password123",
              role="user", must_change_password=False):
    """Create and commit a user directly in the DB. Returns the User."""
    from app.auth import service

    user = service.create_user(
        db_session, username=username, password=password, role=role,
        must_change_password=must_change_password,
    )
    db_session.commit()
    return user


@pytest.fixture
def app_client():
    """A ``TestClient`` over a freshly-built app (unauthenticated)."""
    from fastapi.testclient import TestClient

    from app.bootstrap import create_app

    return TestClient(create_app())


def login_client(client, db_session, username="tester", *, password="password123",
                 role="user"):
    """Create a user and return *client* with its session cookie set.

    The created user's id is attached as ``client.test_user_id`` so tests
    can build the per-user storage key (``make_skey(client.test_user_id,
    oid)``) when asserting against ``SessionManager``/stores.
    """
    user = make_user(db_session, username, password=password, role=role)
    client.test_user_id = user.id
    resp = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return client


@pytest.fixture
def auth_client(app_client, db_session):
    """A ``TestClient`` already logged in as a normal user named ``tester``."""
    return login_client(app_client, db_session)


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
