"""Tests for the server-side undo stack: GameService.undo_last."""
import pytest

from app.api import action_log
from app.api.game_service import GameService
from app.api.session_manager import SessionManager

pytestmark = pytest.mark.usefixtures("clean_sessions")


class TestUndoLast:
    def test_undo_with_empty_log(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("undo-1", mock_conf, api_backend)
        response = GameService.undo_last(session)
        assert response.success is False
        assert "Nothing to undo" in (response.message or "")

    def test_undo_reverses_add_point(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("undo-2", mock_conf, api_backend)
        GameService.add_point(session, team=1)
        GameService.add_point(session, team=1)
        # Score is 2-0.
        assert session.game_manager.get_current_state().get_game(1, 1) == 2

        response = GameService.undo_last(session)
        assert response.success is True
        assert session.game_manager.get_current_state().get_game(1, 1) == 1

    def test_undo_reverses_add_timeout(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("undo-3", mock_conf, api_backend)
        GameService.add_timeout(session, team=2)
        assert session.game_manager.get_current_state().get_timeout(2) == 1

        GameService.undo_last(session)
        assert session.game_manager.get_current_state().get_timeout(2) == 0

    def test_undo_reverses_most_recent_regardless_of_team(
            self, mock_conf, api_backend):
        session = SessionManager.get_or_create("undo-4", mock_conf, api_backend)
        GameService.add_point(session, team=1)
        GameService.add_point(session, team=2)
        # 1-1.

        GameService.undo_last(session)
        # Most recent was team 2, so team 2's score should drop.
        state = session.game_manager.get_current_state()
        assert state.get_game(1, 1) == 1
        assert state.get_game(2, 1) == 0

    def test_undo_skips_non_undoable_records(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("undo-5", mock_conf, api_backend)
        GameService.add_point(session, team=1)
        # change_serve is logged but not undoable — undo should jump past it
        # to the add_point.
        GameService.change_serve(session, team=2)
        GameService.undo_last(session)
        state = session.game_manager.get_current_state()
        assert state.get_game(1, 1) == 0
        # The change_serve entry stays in the log.
        records = action_log.read_all("undo-5")
        assert any(r["action"] == "change_serve" for r in records)

    def test_state_response_timeouts_match_session_current_set(
        self, mock_conf, api_backend,
    ):
        """After a set-winning point, the broadcast response must report
        the new set's timeout count (0), not the closed set's count.

        ``state._state.current_set`` lags ``session.current_set`` by one
        tick — it only updates in ``GameManager.save`` which runs after
        ``get_state``. The legacy ``timeouts`` field therefore has to
        pin to ``session.current_set`` explicitly; if it falls back to
        ``state.current_set`` (the default), the response would expose
        the closed set's count under the new set's banner.
        """
        session = SessionManager.get_or_create("timeouts-current-set", mock_conf, api_backend)
        # Burn one timeout for each team in set 1.
        GameService.add_timeout(session, team=1)
        GameService.add_timeout(session, team=2)
        # Drive team 1 to 25-0 — the last point wins the set.
        for _ in range(25):
            response = GameService.add_point(session, team=1)
        # Session advanced to set 2; the broadcast response must show 0
        # timeouts for both teams (the new set's count), not 1 each.
        assert response.state.current_set == 2
        assert response.state.team_1.timeouts == 0
        assert response.state.team_2.timeouts == 0
        # The per-set history still records set 1's burns.
        assert response.state.team_1.timeouts_by_set["set_1"] == 1
        assert response.state.team_2.timeouts_by_set["set_1"] == 1

    def test_undo_does_not_pop_undo_entries(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("undo-6", mock_conf, api_backend)
        GameService.add_point(session, team=1)
        GameService.add_point(session, team=1)
        GameService.undo_last(session)  # Pops the second add_point.
        GameService.undo_last(session)  # Pops the first add_point.
        # No more forward entries — third undo should report "Nothing to undo."
        response = GameService.undo_last(session)
        assert response.success is False

    def test_undo_appends_undo_audit_record(
        self, mock_conf, api_backend, monkeypatch,
    ):
        """Outside the rapid-pair window the legacy unified-undo
        flow is preserved: pop the forward, append an orphan undo.

        Time has to be mocked because the default 5 s rapid-pair
        window would otherwise absorb both halves into a no-op
        (Case A) and the assertion would see an empty log.
        """
        import time as _time

        from app.api import game_service as gs

        clock = [1_000_000.0]
        monkeypatch.setattr(gs.time, "time", lambda: clock[0])
        monkeypatch.setattr(_time, "time", lambda: clock[0])

        session = SessionManager.get_or_create("undo-7", mock_conf, api_backend)
        GameService.add_point(session, team=1)
        clock[0] += gs.RAPID_PAIR_WINDOW_S + 0.1
        GameService.undo_last(session)
        records = action_log.read_all("undo-7")
        # The forward record was popped, the undo record was appended.
        assert len(records) == 1
        assert records[0]["params"]["undo"] is True

    def test_immediate_undo_collapses_via_rapid_pair(
        self, mock_conf, api_backend,
    ):
        """A tap immediately followed by an undo (well within the
        rapid-pair window) collapses to nothing in the audit log —
        same final state, nothing for the report or drawer to
        render.
        """
        session = SessionManager.get_or_create(
            "undo-7-rapid", mock_conf, api_backend,
        )
        GameService.add_point(session, team=1)
        GameService.undo_last(session)
        assert action_log.read_all("undo-7-rapid") == []
        assert session.undoable_forward_count == 0

    def test_two_undos_walk_back_two_steps(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("undo-8", mock_conf, api_backend)
        GameService.add_point(session, team=1)
        GameService.add_point(session, team=2)
        GameService.add_point(session, team=1)
        # Score 2-1.
        GameService.undo_last(session)  # → 1-1
        GameService.undo_last(session)  # → 1-0
        state = session.game_manager.get_current_state()
        assert state.get_game(1, 1) == 1
        assert state.get_game(2, 1) == 0

    def test_undo_reverses_set_winning_point(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("undo-9", mock_conf, api_backend)
        # Drive set 1 to 24-0, then 25th point ends the set.
        for _ in range(24):
            GameService.add_point(session, team=1)
        GameService.add_point(session, team=1)
        # Set 1 won by team 1 → sets become 1-0, current_set advances.
        assert session.game_manager.get_current_state().get_sets(1) == 1

        GameService.undo_last(session)
        # The set win should be undone: sets revert to 0-0 and the 25th
        # point reverts to 24.
        state = session.game_manager.get_current_state()
        assert state.get_sets(1) == 0
        assert state.get_game(1, 1) == 24
