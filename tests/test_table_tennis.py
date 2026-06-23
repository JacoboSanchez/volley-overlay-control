"""Tests for the table-tennis match mode: serve rotation, the serve-change
indicator, per-game side switches, the one-timeout-per-match cap and the
best-of-7 widening."""
import pytest

from app.api.game_service import GameService
from app.api.match_rules import (
    PRESETS,
    compute_serve_switch,
    compute_sides_swapped_auto,
    defaults_for,
    is_valid_mode,
    table_tennis_first_server_for,
    table_tennis_server,
)
from app.api.session_manager import SessionManager

pytestmark = pytest.mark.usefixtures("clean_sessions")


# ---------------------------------------------------------------------------
# Preset / mode validity
# ---------------------------------------------------------------------------

class TestTableTennisPreset:
    def test_mode_is_valid(self):
        assert is_valid_mode("table_tennis") is True

    def test_preset_values(self):
        p = PRESETS["table_tennis"]
        assert (p.points_limit, p.points_limit_last_set, p.sets_limit) == (11, 11, 5)

    def test_defaults_for(self):
        assert defaults_for("table_tennis").points_limit == 11


# ---------------------------------------------------------------------------
# Serve rotation (pure function)
# ---------------------------------------------------------------------------

def _srv(t1, t2, *, first_server=1, current_set=1, sets_limit=5):
    return table_tennis_server(
        first_server=first_server, current_set=current_set, sets_limit=sets_limit,
        team1_score=t1, team2_score=t2, points_limit=11, points_limit_last_set=11,
    )


class TestServeRotation:
    def test_every_two_points_before_deuce(self):
        # Team 1 serves first; serve flips every 2 combined points.
        assert _srv(0, 0) == 1
        assert _srv(1, 0) == 1
        assert _srv(1, 1) == 2   # 2 points played -> handover
        assert _srv(2, 1) == 2
        assert _srv(2, 2) == 1   # 4 points played -> back to team 1
        assert _srv(3, 2) == 1

    def test_single_point_at_deuce(self):
        # From 10-10 (20 combined) the serve alternates every point.
        assert _srv(10, 10) == 1
        assert _srv(11, 10) == 2
        assert _srv(11, 11) == 1
        assert _srv(12, 11) == 2

    def test_first_server_alternates_each_game(self):
        # Game 2 flips the opening server.
        assert _srv(0, 0, current_set=2) == 2
        assert _srv(1, 1, current_set=2) == 1
        # Game 3 returns to the match first server.
        assert _srv(0, 0, current_set=3) == 1

    def test_respects_first_server_two(self):
        assert _srv(0, 0, first_server=2) == 2
        assert _srv(1, 1, first_server=2) == 1

    def test_first_server_inversion_round_trips(self):
        # For any score, picking a desired current server and feeding the
        # resulting first_server back must reproduce that server.
        for current_set in (1, 2, 3):
            for t1, t2 in ((0, 0), (3, 2), (10, 10), (11, 10)):
                for desired in (1, 2):
                    fs = table_tennis_first_server_for(
                        desired_server=desired, current_set=current_set,
                        sets_limit=5, team1_score=t1, team2_score=t2,
                        points_limit=11, points_limit_last_set=11,
                    )
                    assert _srv(t1, t2, first_server=fs, current_set=current_set) == desired


# ---------------------------------------------------------------------------
# Serve-change indicator
# ---------------------------------------------------------------------------

def _switch(t1, t2, *, mode="table_tennis", first_server=1, current_set=1, sets_limit=5):
    return compute_serve_switch(
        mode=mode, current_set=current_set, sets_limit=sets_limit,
        first_server=first_server, team1_score=t1, team2_score=t2,
        points_limit=11, points_limit_last_set=11,
    )


class TestServeSwitchIndicator:
    def test_none_for_volleyball(self):
        assert _switch(0, 0, mode="indoor") is None
        assert _switch(0, 0, mode="beach") is None

    def test_countdown_from_start(self):
        info = _switch(0, 0)
        assert info["server"] == 1
        assert info["points_until_change"] == 2
        assert info["is_change_pending"] is False

    def test_pending_on_boundary(self):
        info = _switch(1, 1)        # 2 points played
        assert info["is_change_pending"] is True
        assert info["server"] == 2
        assert info["points_until_change"] == 2

    def test_mid_block_counts_down(self):
        info = _switch(1, 0)        # 1 point played
        assert info["points_until_change"] == 1
        assert info["is_change_pending"] is False

    def test_deuce_changes_every_point(self):
        info = _switch(10, 10)
        assert info["points_until_change"] == 1
        assert info["is_change_pending"] is True


# ---------------------------------------------------------------------------
# Side switch (auto orientation)
# ---------------------------------------------------------------------------

def _swapped(t1, t2, *, current_set=1, sets_limit=5, completed=None):
    return compute_sides_swapped_auto(
        mode="table_tennis", current_set=current_set, sets_limit=sets_limit,
        team1_score=t1, team2_score=t2, points_limit=11, points_limit_last_set=11,
        completed_set_scores=completed,
    )


class TestTableTennisSideSwitch:
    def test_switches_every_game(self):
        assert _swapped(3, 1, current_set=1) is False
        assert _swapped(0, 0, current_set=2) is True
        assert _swapped(0, 0, current_set=3) is False

    def test_decider_midpoint_switch(self):
        # Best-of-5 decider (set 5): switch when a player first reaches 5.
        assert _swapped(4, 0, current_set=5) is False
        assert _swapped(5, 0, current_set=5) is True


# ---------------------------------------------------------------------------
# Integration through GameService
# ---------------------------------------------------------------------------

def _tt_session(mock_conf, api_backend):
    s = SessionManager.get_or_create("tt", mock_conf, api_backend)
    GameService.set_rules(s, mode="table_tennis", reset_to_defaults=True)
    # The shared ``base_model`` fixture can carry non-zero scores when other
    # tests have run first; reset guarantees a clean 0-0 game so the serve
    # rotation assertions below are deterministic.
    GameService.reset(s)
    return s


class TestTableTennisIntegration:
    def test_rules_applied(self, mock_conf, api_backend):
        s = _tt_session(mock_conf, api_backend)
        assert s.mode == "table_tennis"
        assert (s.points_limit, s.points_limit_last_set, s.sets_limit) == (11, 11, 5)

    def test_serve_rotates_on_points(self, mock_conf, api_backend):
        s = _tt_session(mock_conf, api_backend)
        # First point: still team 1's serve block.
        r = GameService.add_point(s, team=1)
        assert r.state.serve == "A"
        assert r.state.serve_switch.server == 1
        # Second point hands the serve to team 2.
        r = GameService.add_point(s, team=2)
        assert r.state.serve == "B"
        assert r.state.serve_switch.server == 2
        assert r.state.serve_switch.is_change_pending is True

    def test_undo_rewinds_serve(self, mock_conf, api_backend):
        s = _tt_session(mock_conf, api_backend)
        GameService.add_point(s, team=1)
        GameService.add_point(s, team=2)        # serve -> B
        r = GameService.add_point(s, team=2, undo=True)
        assert r.state.serve == "A"
        assert r.state.serve_switch.server == 1

    def test_change_serve_rebases_first_server(self, mock_conf, api_backend):
        s = _tt_session(mock_conf, api_backend)
        r = GameService.change_serve(s, team=2)
        assert r.state.serve == "B"
        assert s.first_server == 2

    def test_one_timeout_per_match(self, mock_conf, api_backend):
        s = _tt_session(mock_conf, api_backend)
        GameService.add_timeout(s, team=1)
        state = s.game_manager.get_current_state()
        assert sum(state.get_timeouts_by_set(1).values()) == 1
        # The second request is rejected (capped) — count stays at 1.
        GameService.add_timeout(s, team=1)
        state = s.game_manager.get_current_state()
        assert sum(state.get_timeouts_by_set(1).values()) == 1

    def test_best_of_seven_accepted(self, mock_conf, api_backend):
        s = SessionManager.get_or_create("bo7", mock_conf, api_backend)
        GameService.set_rules(s, mode="table_tennis", sets_limit=7)
        assert s.sets_limit == 7
        # Scores can be recorded in set 7 without raising.
        GameService.set_score(s, team=1, set_number=7, value=5)
        assert s.game_manager.get_current_state().get_game(1, 7) == 5
