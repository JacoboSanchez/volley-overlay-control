"""Tests for the REST API layer (app/api/).

Shared fixtures (``mock_conf``, ``api_backend``, ``api_session``,
``clean_sessions``) live in ``tests/conftest.py``.
"""
import json

import pytest

from app.api.game_service import GameService
from app.api.schemas import GameStateResponse
from app.api.session_manager import GameSession, SessionManager
from app.state import State

# Apply clean_sessions to every test in this module.
pytestmark = pytest.mark.usefixtures("clean_sessions")


# Local aliases so existing tests keep their short fixture names without
# duplicating the fixture definitions.
@pytest.fixture
def mock_backend(api_backend):
    return api_backend


@pytest.fixture
def session(api_session):
    return api_session


# ---------------------------------------------------------------------------
# SessionManager tests
# ---------------------------------------------------------------------------

class TestSessionManager:
    def test_get_or_create_creates_new_session(self, mock_conf, mock_backend):
        session = SessionManager.get_or_create('oid1', mock_conf, mock_backend)
        assert session is not None
        assert session.oid == 'oid1'
        assert isinstance(session, GameSession)

    def test_get_or_create_returns_existing(self, mock_conf, mock_backend):
        s1 = SessionManager.get_or_create('oid1', mock_conf, mock_backend)
        s2 = SessionManager.get_or_create('oid1', mock_conf, mock_backend)
        assert s1 is s2

    def test_get_returns_none_for_unknown(self):
        assert SessionManager.get('unknown') is None

    def test_get_returns_existing(self, session):
        found = SessionManager.get('test-oid')
        assert found is session

    def test_remove(self, session):
        SessionManager.remove('test-oid')
        assert SessionManager.get('test-oid') is None

    def test_clear(self, session):
        SessionManager.clear()
        assert SessionManager.get('test-oid') is None

    def test_update_limits_on_get_or_create(self, mock_conf, mock_backend):
        session = SessionManager.get_or_create('oid1', mock_conf, mock_backend)
        assert session.points_limit == 25
        SessionManager.get_or_create('oid1', points_limit=21)
        assert session.points_limit == 21


# ---------------------------------------------------------------------------
# GameService tests
# ---------------------------------------------------------------------------

class TestGameService:
    def test_get_state_returns_initial(self, session):
        state = GameService.get_state(session)
        assert isinstance(state, GameStateResponse)
        assert state.current_set == 1
        assert state.team_1.sets == 0
        assert state.team_2.sets == 0
        assert state.match_finished is False

    def test_add_point(self, session):
        result = GameService.add_point(session, team=1)
        assert result.success is True
        assert result.state.team_1.scores['set_1'] == 1
        assert result.state.team_2.scores['set_1'] == 0
        assert result.state.team_1.serving is True

    def test_add_point_team2(self, session):
        result = GameService.add_point(session, team=2)
        assert result.success is True
        assert result.state.team_2.scores['set_1'] == 1
        assert result.state.team_2.serving is True

    def test_add_point_undo(self, session):
        GameService.add_point(session, team=1)
        result = GameService.add_point(session, team=1, undo=True)
        assert result.success is True
        assert result.state.team_1.scores['set_1'] == 0

    def test_add_set(self, session):
        result = GameService.add_set(session, team=1)
        assert result.success is True
        assert result.state.team_1.sets == 1

    def test_add_timeout(self, session):
        result = GameService.add_timeout(session, team=1)
        assert result.success is True
        assert result.state.team_1.timeouts == 1

    def test_add_timeout_undo(self, session):
        GameService.add_timeout(session, team=1)
        result = GameService.add_timeout(session, team=1, undo=True)
        assert result.success is True
        assert result.state.team_1.timeouts == 0

    def test_change_serve(self, session):
        result = GameService.change_serve(session, team=2)
        assert result.success is True
        assert result.state.team_2.serving is True
        assert result.state.team_1.serving is False

    def test_set_score(self, session):
        result = GameService.set_score(session, team=1, set_number=1, value=10)
        assert result.success is True
        assert result.state.team_1.scores['set_1'] == 10

    def test_set_score_rejects_set_number_over_limit(self, session):
        # Default mock_conf has sets_limit=5; 6 must be rejected.
        result = GameService.set_score(session, team=1, set_number=6, value=10)
        assert result.success is False
        assert 'out of range' in (result.message or '')
        # State must be unchanged.
        assert result.state.team_1.scores['set_1'] == 0

    def test_set_score_rejects_set_number_below_one(self, session):
        # Sets use 1-based indexing; 0 and negative values are invalid.
        result = GameService.set_score(session, team=1, set_number=0, value=10)
        assert result.success is False
        assert 'out of range' in (result.message or '')
        assert result.state.team_1.scores['set_1'] == 0

    def test_set_sets_value(self, session):
        result = GameService.set_sets_value(session, team=1, value=2)
        assert result.success is True
        assert result.state.team_1.sets == 2

    def test_reset(self, session):
        GameService.add_point(session, team=1)
        GameService.add_point(session, team=1)
        # After reset, backend.get_current_model returns the reset state
        session.backend.get_current_model.return_value = State().get_reset_model()
        result = GameService.reset(session)
        assert result.success is True
        assert result.state.team_1.scores['set_1'] == 0

    def test_set_visibility(self, session):
        result = GameService.set_visibility(session, visible=False)
        assert result.success is True
        assert result.state.visible is False

    def test_set_simple_mode(self, session):
        result = GameService.set_simple_mode(session, enabled=True)
        assert result.success is True
        assert result.state.simple_mode is True

    def test_match_finished_blocks_point(self, session):
        # Win 3 sets for team 1 to finish a best-of-5 match
        for _ in range(3):
            GameService.add_set(session, team=1)
        result = GameService.add_point(session, team=1)
        assert result.success is False
        assert 'finished' in result.message.lower()

    def test_get_customization(self, session):
        cust = GameService.get_customization(session)
        assert isinstance(cust, dict)

    def test_update_customization(self, session):
        new_data = {"Team 1 Color": "#ff0000"}
        result = GameService.update_customization(session, new_data)
        assert result.success is True

    def test_refresh_customization_caches_within_ttl(self, session):
        """Back-to-back refreshes within the TTL must hit the backend once."""
        session.backend.get_current_customization.reset_mock()
        GameService.refresh_customization(session)
        GameService.refresh_customization(session)
        GameService.refresh_customization(session)
        # The first call actually fetches; the next two short-circuit.
        assert session.backend.get_current_customization.call_count == 1

    def test_refresh_customization_first_call_always_fetches(self, session):
        """First refresh on a fresh session must hit the backend even when
        ``time.monotonic()`` returns a small value (e.g. right after boot).

        A sentinel-``None`` default prevents the ``now - last < TTL``
        comparison from accidentally short-circuiting on the very first call.
        """
        # Explicitly ensure the timestamp has never been set.
        assert not hasattr(session, "_last_customization_fetch") or \
            session._last_customization_fetch is None
        session.backend.get_current_customization.reset_mock()
        GameService.refresh_customization(session)
        assert session.backend.get_current_customization.call_count == 1

    def test_refresh_customization_refetches_after_ttl(self, session, monkeypatch):
        """Once the cache window expires, refresh hits the backend again."""
        import app.api.game_service as gs
        # Shrink the TTL so the test is quick; existing session state wins.
        monkeypatch.setattr(gs, "CUSTOMIZATION_CACHE_TTL_SECONDS", 0.0)
        session.backend.get_current_customization.reset_mock()
        GameService.refresh_customization(session)
        GameService.refresh_customization(session)
        assert session.backend.get_current_customization.call_count == 2

    def test_update_customization_primes_cache(self, session):
        """A write must prevent the immediate next refresh from re-fetching."""
        GameService.update_customization(session, {"Team 1 Color": "#ff0000"})
        session.backend.get_current_customization.reset_mock()
        GameService.refresh_customization(session)
        session.backend.get_current_customization.assert_not_called()


# ---------------------------------------------------------------------------
# GameSession compute_current_set tests
# ---------------------------------------------------------------------------

class TestGameSession:
    def test_initial_current_set(self, session):
        assert session.current_set == 1

    def test_current_set_advances(self, session):
        GameService.add_set(session, team=1)
        assert session.current_set == 2

    def test_points_limit_respected(self, session):
        assert session.points_limit == 25
        assert session.points_limit_last_set == 15
        assert session.sets_limit == 5


# ---------------------------------------------------------------------------
# API Key auth tests
# ---------------------------------------------------------------------------

class TestAPIKeyAuth:
    def test_check_api_key_no_users(self, monkeypatch):
        from app.authentication import PasswordAuthenticator
        monkeypatch.setenv('SCOREBOARD_USERS', '')
        assert PasswordAuthenticator.check_api_key('any') is False

    def test_check_api_key_valid(self, monkeypatch):
        from app.authentication import PasswordAuthenticator
        users = json.dumps({"admin": {"password": "secret123"}})
        monkeypatch.setenv('SCOREBOARD_USERS', users)
        assert PasswordAuthenticator.check_api_key('secret123') is True

    def test_check_api_key_invalid(self, monkeypatch):
        from app.authentication import PasswordAuthenticator
        users = json.dumps({"admin": {"password": "secret123"}})
        monkeypatch.setenv('SCOREBOARD_USERS', users)
        assert PasswordAuthenticator.check_api_key('wrong') is False
