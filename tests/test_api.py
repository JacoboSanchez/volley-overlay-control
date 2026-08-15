"""Tests for the REST API layer (app/api/).

Shared fixtures (``mock_conf``, ``api_backend``, ``api_session``,
``clean_sessions``) live in ``tests/conftest.py``.
"""

import asyncio
import threading

import pytest
from starlette.concurrency import run_in_threadpool

from app.api.game_service import GameService
from app.api.routes.customization import get_customization
from app.api.routes.state import get_config
from app.api.schemas import GameStateResponse
from app.api.session_manager import GameSession, SessionManager
from app.api.state_snapshot import get_state_snapshot
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

    @pytest.mark.asyncio
    async def test_state_snapshot_waits_for_the_mutation_lock(
        self, session, monkeypatch,
    ):
        called = threading.Event()
        original = GameService.get_state.__func__

        def spy(cls, current_session):
            called.set()
            return original(cls, current_session)

        monkeypatch.setattr(GameService, "get_state", classmethod(spy))
        await session.lock.acquire()
        try:
            pending = asyncio.create_task(get_state_snapshot(session))
            await asyncio.sleep(0)
            assert not called.is_set()
        finally:
            session.lock.release()

        response = await pending
        assert called.is_set()
        assert isinstance(response, GameStateResponse)

    @pytest.mark.asyncio
    async def test_config_snapshot_serializes_with_rules_update(self, session):
        """/config must never expose a half-applied rule preset."""
        session.mode = "indoor"
        session.points_limit = 25
        session.points_limit_last_set = 15
        session.sets_limit = 5

        mid_update = threading.Event()
        release_update = threading.Event()

        def slow_set_rules():
            # Mirrors GameService.set_rules: the beach preset lands one field
            # at a time, so an unlocked reader can catch a mixed pair.
            session.mode = "beach"
            session.points_limit = 21
            mid_update.set()
            assert release_update.wait(timeout=5)
            session.points_limit_last_set = 15
            session.sets_limit = 3

        async def update():
            # Mirrors get_mutation_session: the mutation owns the session
            # lock for the whole worker-thread call.
            async with session.lock:
                await run_in_threadpool(slow_set_rules)

        writer = asyncio.create_task(update())
        try:
            assert await asyncio.to_thread(mid_update.wait, 3)
            reader = asyncio.create_task(get_config(session))
            await asyncio.sleep(0.2)
            assert not reader.done()
        finally:
            release_update.set()

        await writer
        # Never the torn mix of a 21-point beach set with 5 indoor sets.
        assert await reader == {
            "points_limit": 21,
            "points_limit_last_set": 15,
            "sets_limit": 3,
        }

    def test_get_state_on_air_and_report_fields(self, session):
        session.backend.obs_client_count = 0
        state = GameService.get_state(session)
        assert state.obs_clients == 0
        # No report link while the match isn't finished.
        assert state.last_match_id is None

    def test_get_state_obs_clients_reflects_backend_count(self, session):
        session.backend.obs_client_count = 4
        assert GameService.get_state(session).obs_clients == 4

    def test_resolve_last_match_id_prefers_session_cache(self, session):
        session.last_match_id = "match_cached_123"
        assert GameService._resolve_last_match_id(session) == "match_cached_123"

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

    def test_add_timeout_table_tennis_cap_returns_failure(self, session):
        # Table tennis allows one timeout per team per match; the second must
        # be rejected with success=False (not silently swallowed as success).
        session.mode = "table_tennis"
        assert GameService.add_timeout(session, team=1).success is True
        blocked = GameService.add_timeout(session, team=1)
        assert blocked.success is False
        assert "limit" in (blocked.message or "").lower()

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

    def test_set_sides_swapped_manual(self, session):
        result = GameService.set_sides_swapped(session, swapped=True)
        assert result.success is True
        assert result.state.sides_swapped is True
        result = GameService.set_sides_swapped(session, swapped=False)
        assert result.state.sides_swapped is False

    def test_auto_swap_sides_keeps_current_orientation_on_toggle(self, session):
        # Enabling auto must not visually jump: the manual base absorbs
        # the auto component at the moment of the toggle.
        before = GameService.get_state(session).sides_swapped
        result = GameService.set_auto_swap_sides(session, enabled=True)
        assert result.success is True
        assert result.state.auto_swap_sides is True
        assert result.state.sides_swapped == before
        result = GameService.set_auto_swap_sides(session, enabled=False)
        assert result.state.auto_swap_sides is False
        assert result.state.sides_swapped == before

    def test_auto_swap_flips_with_set_changes(self, session):
        GameService.set_auto_swap_sides(session, enabled=True)
        assert GameService.get_state(session).sides_swapped is False
        # Win a set for team 1 -> orientation flips.
        GameService.add_set(session, team=1)
        assert GameService.get_state(session).sides_swapped is True
        # Manual correction in auto mode still works (XOR base).
        GameService.set_sides_swapped(session, swapped=False)
        state = GameService.get_state(session)
        assert state.sides_swapped is False
        assert state.auto_swap_sides is True

    def test_set_set_summary_mode_toggles(self, session):
        result = GameService.set_set_summary_mode(session, enabled=True)
        assert result.success is True
        assert result.state.set_summary is True
        # set_summary_set_num resolves through _resolve_summary_set —
        # with no points yet it falls back to max(current_set-1, 1).
        assert result.state.set_summary_set_num == 1
        # Toggle off clears the resolved set num.
        result = GameService.set_set_summary_mode(session, enabled=False)
        assert result.state.set_summary is False
        assert result.state.set_summary_set_num is None

    def test_set_set_summary_style_validates_and_persists(self, session):
        result = GameService.set_set_summary_style(session, style="glass")
        assert result.success is True
        assert result.state.set_summary_style == "glass"
        # Unknown style is a no-op (FastAPI Literal blocks invalid input
        # at the schema layer; the service-level call keeps the prior
        # value rather than raising).
        result = GameService.set_set_summary_style(session, style="bogus")
        assert result.state.set_summary_style == "glass"

    def test_resolve_summary_set_falls_back_when_current_empty(self, session):
        # With current_set=1 and no points, fallback is 1 (clamped).
        session.current_set = 1
        assert GameService._resolve_summary_set(session) == 1
        # With current_set=3 and no points in any set, fallback is 2.
        session.current_set = 3
        assert GameService._resolve_summary_set(session) == 2

    def test_resolve_summary_set_ignores_set_score_only_audit(self, session):
        # Reproduce the setpt scenario: the operator parked the match
        # in set 3 (sets_won 1-1) and then went back to tweak earlier
        # scores via ``set_score``. Those records carry
        # ``result.current_set = 3`` even though no rally has been
        # played in set 3 yet — without the action-type filter the
        # resolver would pin the recap to set 3.
        GameService.add_point(session, team=1)
        GameService.add_set(session, team=1)
        GameService.add_point(session, team=2)
        GameService.add_set(session, team=2)
        assert session.current_set == 3
        # Use sub-win scores so ``check_set_won`` does not advance the
        # current set on the operator under us.
        GameService.set_score(session, team=1, set_number=1, value=24)
        GameService.set_score(session, team=2, set_number=2, value=24)
        assert session.current_set == 3
        # No ``add_point`` in set 3 → recap should show set 2.
        assert GameService._resolve_summary_set(session) == 2
        # Once a real point lands in set 3 the recap follows.
        GameService.add_point(session, team=1)
        assert GameService._resolve_summary_set(session) == 3

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

    def test_update_customization_persists_vertical_anchor(self, session):
        # Regression: ``verticalAnchor`` (edge-pinned pylons placement) must
        # survive the allow-list filter so the overlay actually receives it.
        result = GameService.update_customization(session, {"verticalAnchor": "top"})
        assert result.success is True
        assert session.customization.get_model().get("verticalAnchor") == "top"

    def test_update_customization_accepts_zone_anchor(self, session):
        # A zone anchor must survive the allow-list filter so the overlay
        # can pin the box to that screen zone.
        result = GameService.update_customization(session, {"Anchor": "top-right"})
        assert result.success is True
        assert session.customization.get_model().get("Anchor") == "top-right"

    def test_update_customization_rejects_unknown_anchor(self, session):
        result = GameService.update_customization(session, {"Anchor": "diagonal"})
        assert result.success is False
        assert "Anchor" in (result.message or "")

    def test_update_customization_accepts_supported_locale(self, session):
        result = GameService.update_customization(session, {"locale": "es"})
        assert result.success is True
        assert session.customization.get_model().get("locale") == "es"

    def test_update_customization_rejects_unknown_locale(self, session):
        result = GameService.update_customization(session, {"locale": "xx"})
        assert result.success is False
        assert "locale" in (result.message or "")

    def test_update_customization_rejects_non_string_locale(self, session):
        result = GameService.update_customization(session, {"locale": 123})
        assert result.success is False
        assert "locale" in (result.message or "")

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

    @pytest.mark.asyncio
    async def test_customization_refresh_serializes_with_update(self, session):
        """A slow stale refresh must not overwrite a newer partial update."""
        session._last_customization_fetch = None
        refresh_started = threading.Event()
        release_refresh = threading.Event()

        def stale_refresh():
            refresh_started.set()
            assert release_refresh.wait(timeout=5)
            return {"Team 1 Name": "Stale"}

        session.backend.get_current_customization.side_effect = stale_refresh
        reader = asyncio.create_task(get_customization(session))
        try:
            assert await asyncio.to_thread(refresh_started.wait, 3)

            async def update():
                # Mirrors get_mutation_session: the update owns the same
                # session lock for the whole worker-thread mutation.
                async with session.lock:
                    return await run_in_threadpool(
                        GameService.update_customization,
                        session,
                        {"Team 1 Name": "Fresh"},
                    )

            writer = asyncio.create_task(update())
            await asyncio.sleep(0.2)
            assert not writer.done()
        finally:
            release_refresh.set()

        await reader
        write_response = await writer
        assert write_response.success is True
        assert session.customization.get_model()["Team 1 Name"] == "Fresh"


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
