"""Tests for the env-var overrides of the tunable constants in
``app.constants``.

The constants are read at import time, so each test uses
``importlib.reload`` after ``monkeypatch.setenv`` to force re-evaluation
under the patched environment. ``importlib.reload`` is preferred over
re-importing because the module may already be cached by other test
fixtures (``app.api.session_manager`` re-exports
``SESSION_TTL_SECONDS``).
"""
import importlib

import pytest

from app import constants as _constants


@pytest.fixture
def reloaded_constants(monkeypatch):
    """Yield a callable that reloads ``app.constants`` under the current
    ``monkeypatch`` env, and restores the module's defaults on teardown."""
    def _reload():
        return importlib.reload(_constants)
    yield _reload
    # Tear down: clear any env vars the test set and reload once more so
    # later tests see the unmodified defaults.
    for key in (
        "SESSION_TTL_SECONDS",
        "WS_BROADCAST_SEND_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)
    importlib.reload(_constants)


class TestSessionTtlOverride:
    def test_default_is_24_hours(self, reloaded_constants):
        c = reloaded_constants()
        assert c.SESSION_TTL_SECONDS == 24 * 60 * 60

    def test_env_override_respected(self, monkeypatch, reloaded_constants):
        monkeypatch.setenv("SESSION_TTL_SECONDS", "60")
        c = reloaded_constants()
        assert c.SESSION_TTL_SECONDS == 60

    def test_garbage_falls_back_to_default(self, monkeypatch, reloaded_constants):
        monkeypatch.setenv("SESSION_TTL_SECONDS", "not-a-number")
        c = reloaded_constants()
        assert c.SESSION_TTL_SECONDS == 24 * 60 * 60

    def test_negative_falls_back_to_default(self, monkeypatch, reloaded_constants):
        monkeypatch.setenv("SESSION_TTL_SECONDS", "-5")
        c = reloaded_constants()
        assert c.SESSION_TTL_SECONDS == 24 * 60 * 60

    def test_zero_falls_back_to_default(self, monkeypatch, reloaded_constants):
        # Zero is non-positive — a 0-second TTL would expire every
        # session immediately, which is never what the operator wants.
        monkeypatch.setenv("SESSION_TTL_SECONDS", "0")
        c = reloaded_constants()
        assert c.SESSION_TTL_SECONDS == 24 * 60 * 60

    def test_empty_string_falls_back_to_default(self, monkeypatch, reloaded_constants):
        monkeypatch.setenv("SESSION_TTL_SECONDS", "")
        c = reloaded_constants()
        assert c.SESSION_TTL_SECONDS == 24 * 60 * 60

    def test_whitespace_only_falls_back_to_default(self, monkeypatch, reloaded_constants):
        monkeypatch.setenv("SESSION_TTL_SECONDS", "   ")
        c = reloaded_constants()
        assert c.SESSION_TTL_SECONDS == 24 * 60 * 60


class TestWebSocketTimeouts:
    def test_defaults_match_legacy_values(self, reloaded_constants):
        c = reloaded_constants()
        assert c.WS_BROADCAST_SEND_TIMEOUT_SECONDS == 2.0

    def test_broadcast_timeout_env_override(self, monkeypatch, reloaded_constants):
        monkeypatch.setenv("WS_BROADCAST_SEND_TIMEOUT_SECONDS", "0.5")
        c = reloaded_constants()
        assert c.WS_BROADCAST_SEND_TIMEOUT_SECONDS == 0.5

    def test_garbage_float_falls_back(self, monkeypatch, reloaded_constants):
        monkeypatch.setenv("WS_BROADCAST_SEND_TIMEOUT_SECONDS", "fast")
        c = reloaded_constants()
        assert c.WS_BROADCAST_SEND_TIMEOUT_SECONDS == 2.0

    def test_negative_float_falls_back(self, monkeypatch, reloaded_constants):
        monkeypatch.setenv("WS_BROADCAST_SEND_TIMEOUT_SECONDS", "-1.5")
        c = reloaded_constants()
        assert c.WS_BROADCAST_SEND_TIMEOUT_SECONDS == 2.0


class TestLegacyAliasesPickUpReload:
    """The legacy module-level names re-export from ``app.constants`` at
    import time; they must reflect any env override after a reload."""

    def test_session_manager_alias_follows_env(self, monkeypatch, reloaded_constants):
        import app.api.session_manager as session_manager
        monkeypatch.setenv("SESSION_TTL_SECONDS", "120")
        reloaded_constants()
        importlib.reload(session_manager)
        assert session_manager.SESSION_TTL_SECONDS == 120
