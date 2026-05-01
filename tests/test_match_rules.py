"""Tests for app/api/match_rules.py and the GameService.set_rules path."""
import pytest

from app.api.game_service import GameService
from app.api.match_rules import (
    PRESETS,
    compute_match_point_info,
    compute_side_switch,
    defaults_for,
    is_valid_mode,
    side_switch_interval,
)
from app.api.session_manager import SessionManager

pytestmark = pytest.mark.usefixtures("clean_sessions")


# ---------------------------------------------------------------------------
# match_rules helpers
# ---------------------------------------------------------------------------

class TestRulesHelpers:
    def test_known_modes(self):
        assert is_valid_mode("indoor") is True
        assert is_valid_mode("beach") is True
        assert is_valid_mode("BEACH") is False
        assert is_valid_mode(None) is False
        assert is_valid_mode(42) is False

    def test_indoor_preset_values(self):
        p = PRESETS["indoor"]
        assert (p.points_limit, p.points_limit_last_set, p.sets_limit) == (25, 15, 5)

    def test_beach_preset_values(self):
        p = PRESETS["beach"]
        assert (p.points_limit, p.points_limit_last_set, p.sets_limit) == (21, 15, 3)

    def test_defaults_for_unknown_falls_back_to_indoor(self):
        assert defaults_for("xyz").points_limit == 25


# ---------------------------------------------------------------------------
# Beach side-switch tracker (§2.3)
# ---------------------------------------------------------------------------

def _ss_kwargs(**overrides):
    """Default-filled kwargs for ``compute_side_switch`` so tests only
    need to mention the fields that vary. Defaults to a beach preset:
    21 / 15 / 3, set 1, 0-0."""
    base = dict(
        mode="beach",
        current_set=1,
        sets_limit=3,
        team1_score=0,
        team2_score=0,
        points_limit=21,
        points_limit_last_set=15,
    )
    base.update(overrides)
    return base


def _interval_kwargs(**overrides):
    base = dict(
        current_set=1, sets_limit=3,
        points_limit=21, points_limit_last_set=15,
    )
    base.update(overrides)
    return base


class TestSideSwitchInterval:
    def test_long_set_uses_seven(self):
        # Standard beach (21-point) regular sets.
        assert side_switch_interval(**_interval_kwargs()) == 7

    def test_short_set_uses_five(self):
        # Standard beach (15-point) deciding set.
        assert side_switch_interval(
            **_interval_kwargs(current_set=3, sets_limit=3),
        ) == 5

    def test_threshold_is_at_15(self):
        # Custom limit exactly 15 → still the short cadence.
        assert side_switch_interval(
            **_interval_kwargs(points_limit=15),
        ) == 5
        # 16 trips into the long cadence.
        assert side_switch_interval(
            **_interval_kwargs(points_limit=16),
        ) == 7

    def test_uses_last_set_target_in_deciding_set(self):
        # Even a long deciding-set target should follow target-driven
        # selection — 21-point deciding set still picks 7.
        assert side_switch_interval(
            **_interval_kwargs(
                current_set=3, sets_limit=3, points_limit_last_set=21,
            ),
        ) == 7


class TestComputeSideSwitch:
    def test_returns_none_for_indoor(self):
        result = compute_side_switch(**_ss_kwargs(mode="indoor", team1_score=5, team2_score=3))
        assert result is None

    def test_initial_state_points_to_first_switch(self):
        result = compute_side_switch(**_ss_kwargs())
        assert result == {
            "interval": 7,
            "points_in_set": 0,
            "next_switch_at": 7,
            "points_until_switch": 7,
            "is_switch_pending": False,
        }

    def test_pending_when_total_hits_interval(self):
        # 4-3 → total=7 → switch is pending right now.
        result = compute_side_switch(
            **_ss_kwargs(team1_score=4, team2_score=3),
        )
        assert result["points_in_set"] == 7
        assert result["is_switch_pending"] is True
        assert result["next_switch_at"] == 14
        assert result["points_until_switch"] == 7

    def test_advances_after_boundary(self):
        # 5-3 → total=8 → next switch at 14.
        result = compute_side_switch(
            **_ss_kwargs(team1_score=5, team2_score=3),
        )
        assert result["next_switch_at"] == 14
        assert result["points_until_switch"] == 6
        assert result["is_switch_pending"] is False

    def test_tiebreak_uses_five(self):
        # Beach tiebreak: 3-2 → total=5 → switch pending (cadence rule).
        result = compute_side_switch(
            **_ss_kwargs(
                current_set=3, sets_limit=3,
                team1_score=3, team2_score=2,
            ),
        )
        assert result["interval"] == 5
        assert result["is_switch_pending"] is True

    def test_tolerates_negative_inputs(self):
        result = compute_side_switch(
            **_ss_kwargs(team1_score=-3, team2_score=-1),
        )
        assert result["points_in_set"] == 0

    def test_midpoint_pending_when_leader_first_reaches_eight(self):
        # Deciding set (15), leader at 8, opponent below: indoor
        # 5th-set rule fires — switch pending even though combined=10
        # also happens to be a cadence boundary (consistent overlap).
        result = compute_side_switch(
            **_ss_kwargs(
                current_set=3, sets_limit=3,
                team1_score=8, team2_score=2,
            ),
        )
        assert result["is_switch_pending"] is True

    def test_midpoint_pending_off_boundary_still_fires(self):
        # 8-3 (combined=11, NOT a cadence boundary). The midpoint rule
        # alone keeps the alert on while only one team has crossed 8.
        result = compute_side_switch(
            **_ss_kwargs(
                current_set=3, sets_limit=3,
                team1_score=8, team2_score=3,
            ),
        )
        assert result["points_in_set"] == 11
        # Cadence next is 15 (15 % 5 == 0); 11 is not pending by cadence.
        assert result["is_switch_pending"] is True

    def test_midpoint_persists_when_leader_scores_past(self):
        # 9-2: leader has scored past the midpoint before the trailing
        # team caught up. The alert must persist as a reminder — the
        # operator may not have switched yet — until both teams cross.
        result = compute_side_switch(
            **_ss_kwargs(
                current_set=3, sets_limit=3,
                team1_score=9, team2_score=2,
            ),
        )
        assert result["is_switch_pending"] is True

    def test_midpoint_persists_until_trailing_catches_up(self):
        # 14-7: leader is one point from set/match win, trailing still
        # below the midpoint — the alert is a stale reminder that the
        # switch was missed. Stays on until trailing reaches 8.
        result = compute_side_switch(
            **_ss_kwargs(
                current_set=3, sets_limit=3,
                team1_score=14, team2_score=7,
            ),
        )
        assert result["is_switch_pending"] is True

    def test_midpoint_clears_once_both_reach_it(self):
        # 8-8: leader is no longer alone at the midpoint, alert clears.
        # (Combined=16 also misses the 5-cadence.)
        result = compute_side_switch(
            **_ss_kwargs(
                current_set=3, sets_limit=3,
                team1_score=8, team2_score=8,
            ),
        )
        assert result["is_switch_pending"] is False

    def test_midpoint_only_fires_in_last_set(self):
        # 8-2 in set 1 (regular 21-point set) → no midpoint rule.
        # Combined=10 isn't a 7-cadence boundary either, so nothing fires.
        result = compute_side_switch(
            **_ss_kwargs(team1_score=8, team2_score=2),
        )
        assert result["is_switch_pending"] is False

    def test_midpoint_rounds_up_for_odd_targets(self):
        # 13-point deciding set → midpoint = ceil(13/2) = 7.
        result = compute_side_switch(
            **_ss_kwargs(
                current_set=3, sets_limit=3,
                points_limit_last_set=13,
                team1_score=7, team2_score=2,
            ),
        )
        assert result["is_switch_pending"] is True

    def test_midpoint_for_even_target(self):
        # 16-point deciding set → midpoint = 8.
        result = compute_side_switch(
            **_ss_kwargs(
                current_set=3, sets_limit=3,
                points_limit_last_set=16,
                team1_score=8, team2_score=4,
            ),
        )
        # 16 > 15 → cadence is 7, combined=12 is not a 7 boundary.
        # The midpoint rule supplies the pending flag on its own.
        assert result["interval"] == 7
        assert result["is_switch_pending"] is True


# ---------------------------------------------------------------------------
# Set-point / match-point helpers
# ---------------------------------------------------------------------------

def _mp_kwargs(**overrides):
    """Default-filled kwargs for ``compute_match_point_info`` so tests
    only need to mention the fields that vary."""
    base = dict(
        current_set=1,
        sets_limit=5,
        team1_sets=0,
        team2_sets=0,
        team1_score=0,
        team2_score=0,
        points_limit=25,
        points_limit_last_set=15,
        match_finished=False,
    )
    base.update(overrides)
    return base


class TestComputeMatchPointInfo:
    def test_no_flags_at_start(self):
        info = compute_match_point_info(**_mp_kwargs())
        assert info == {
            "team_1_set_point": False,
            "team_2_set_point": False,
            "team_1_match_point": False,
            "team_2_match_point": False,
        }

    def test_set_point_at_24_22(self):
        # 24-22 → next point makes it 25-22 (margin 3 > 1, hits 25). Set point.
        info = compute_match_point_info(
            **_mp_kwargs(team1_score=24, team2_score=22),
        )
        assert info["team_1_set_point"] is True
        assert info["team_2_set_point"] is False
        # Best-of-5, sets won 0-0 → not a match point yet.
        assert info["team_1_match_point"] is False

    def test_no_set_point_at_24_24_deuce(self):
        # 24-24 → next point makes it 25-24 (margin 1, NOT a win). Neither side.
        info = compute_match_point_info(
            **_mp_kwargs(team1_score=24, team2_score=24),
        )
        assert info["team_1_set_point"] is False
        assert info["team_2_set_point"] is False

    def test_set_point_after_deuce_at_26_24(self):
        info = compute_match_point_info(
            **_mp_kwargs(team1_score=26, team2_score=24),
        )
        # 26 already wins, but state isn't transitioned yet — score+1=27,
        # margin=3, hits 25. Treat as still set point so the indicator
        # remains visible until the set actually closes.
        assert info["team_1_set_point"] is True

    def test_match_point_when_one_set_from_clinch(self):
        # Best of 5, 2-0 lead, 24-10 → next point wins set #3 and the match.
        info = compute_match_point_info(
            **_mp_kwargs(
                current_set=3, team1_sets=2, team2_sets=0,
                team1_score=24, team2_score=10,
            ),
        )
        assert info["team_1_set_point"] is True
        assert info["team_1_match_point"] is True
        assert info["team_2_match_point"] is False

    def test_set_point_but_not_match_point_with_only_one_set_won(self):
        info = compute_match_point_info(
            **_mp_kwargs(
                current_set=2, team1_sets=1, team2_sets=0,
                team1_score=24, team2_score=10,
            ),
        )
        assert info["team_1_set_point"] is True
        # Team 1 would only reach 2 sets — best-of-5 needs 3.
        assert info["team_1_match_point"] is False

    def test_last_set_uses_short_target(self):
        # Indoor 5th set: target 15, not 25.
        info = compute_match_point_info(
            **_mp_kwargs(
                current_set=5, sets_limit=5,
                team1_sets=2, team2_sets=2,
                team1_score=14, team2_score=10,
            ),
        )
        assert info["team_1_set_point"] is True
        assert info["team_1_match_point"] is True

    def test_best_of_1_first_set_wins_match(self):
        # Single set: any set point IS a match point.
        info = compute_match_point_info(
            **_mp_kwargs(
                current_set=1, sets_limit=1,
                team1_sets=0, team2_sets=0,
                team1_score=14, team2_score=12,
                points_limit=25, points_limit_last_set=15,
            ),
        )
        assert info["team_1_set_point"] is True
        assert info["team_1_match_point"] is True

    def test_match_finished_clears_all_flags(self):
        info = compute_match_point_info(
            **_mp_kwargs(
                team1_score=24, team2_score=22, match_finished=True,
            ),
        )
        assert all(v is False for v in info.values())

    def test_at_most_one_team_holds_set_point(self):
        # Mathematically impossible for both due to win-by-2 rule, but
        # exercise a near-boundary input to confirm.
        for s1 in range(0, 30):
            for s2 in range(0, 30):
                info = compute_match_point_info(
                    **_mp_kwargs(team1_score=s1, team2_score=s2),
                )
                both = info["team_1_set_point"] and info["team_2_set_point"]
                assert both is False, f"both holding set point at {s1}-{s2}"


# ---------------------------------------------------------------------------
# GameService.set_rules
# ---------------------------------------------------------------------------

class TestSetRules:
    def test_switch_to_beach_resets_defaults(self, mock_conf, api_backend):
        s = SessionManager.get_or_create("rules-1", mock_conf, api_backend)
        # Default conf is indoor (25/15/5).
        assert s.mode == "indoor"
        response = GameService.set_rules(
            s, mode="beach", reset_to_defaults=True,
        )
        assert response.success is True
        assert s.mode == "beach"
        assert s.points_limit == 21
        assert s.points_limit_last_set == 15
        assert s.sets_limit == 3

    def test_switch_to_beach_without_reset_keeps_limits(
            self, mock_conf, api_backend):
        s = SessionManager.get_or_create("rules-2", mock_conf, api_backend)
        # Operator-customised limits — flipping mode without reset
        # should not silently overwrite them.
        s.points_limit = 27
        s.sets_limit = 5
        GameService.set_rules(s, mode="beach")
        assert s.mode == "beach"
        assert s.points_limit == 27
        assert s.sets_limit == 5

    def test_per_field_override_wins_over_reset(self, mock_conf, api_backend):
        s = SessionManager.get_or_create("rules-3", mock_conf, api_backend)
        GameService.set_rules(
            s, mode="beach", reset_to_defaults=True, points_limit=27,
        )
        assert s.points_limit == 27               # override wins
        assert s.points_limit_last_set == 15      # reset applied
        assert s.sets_limit == 3                  # reset applied

    def test_invalid_mode_is_rejected(self, mock_conf, api_backend):
        s = SessionManager.get_or_create("rules-4", mock_conf, api_backend)
        prior = s.mode
        response = GameService.set_rules(s, mode="ultimate")
        assert response.success is False
        assert s.mode == prior

    def test_clamps_sets_limit_to_supported_range(
            self, mock_conf, api_backend):
        s = SessionManager.get_or_create("rules-5", mock_conf, api_backend)
        GameService.set_rules(s, sets_limit=99)
        assert s.sets_limit == 5
        GameService.set_rules(s, sets_limit=0)
        assert s.sets_limit == 1

    def test_persists_across_session_clear(self, mock_conf, api_backend):
        s = SessionManager.get_or_create("rules-6", mock_conf, api_backend)
        GameService.set_rules(s, mode="beach", reset_to_defaults=True)
        SessionManager.clear()

        restored = SessionManager.get_or_create("rules-6", mock_conf, api_backend)
        assert restored.mode == "beach"
        assert restored.points_limit == 21
        assert restored.sets_limit == 3

    def test_state_response_includes_mode_in_config(
            self, mock_conf, api_backend):
        s = SessionManager.get_or_create("rules-7", mock_conf, api_backend)
        GameService.set_rules(s, mode="beach", reset_to_defaults=True)
        state = GameService.get_state(s)
        assert state.config["mode"] == "beach"
        assert state.config["points_limit"] == 21

    def test_state_response_includes_side_switch_for_beach(
            self, mock_conf, api_backend):
        s = SessionManager.get_or_create("rules-8", mock_conf, api_backend)
        GameService.set_rules(s, mode="beach", reset_to_defaults=True)
        state = GameService.get_state(s)
        assert state.beach_side_switch is not None
        assert state.beach_side_switch.interval == 7

    def test_state_response_omits_side_switch_for_indoor(
            self, mock_conf, api_backend):
        s = SessionManager.get_or_create("rules-9", mock_conf, api_backend)
        # mock_conf default is indoor.
        state = GameService.get_state(s)
        assert state.beach_side_switch is None

    def test_smaller_sets_limit_clamps_current_set(
            self, mock_conf, api_backend):
        s = SessionManager.get_or_create("rules-10", mock_conf, api_backend)
        # Force current_set above the new limit before tightening.
        s.current_set = 5
        GameService.set_rules(s, sets_limit=3)
        assert s.current_set <= 3
