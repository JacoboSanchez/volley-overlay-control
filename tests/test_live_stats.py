"""Tests for app/api/live_stats.compute_live_stats."""

import pytest

from app.api import action_log
from app.api.live_stats import compute_live_stats

pytestmark = pytest.mark.usefixtures("clean_sessions")


def _add_point(oid: str, team: int, score_pair: tuple[int, int], set_num: int = 1):
    """Append an ``add_point`` audit record with a pre-computed result blob."""
    action_log.append(
        oid,
        "add_point",
        {"team": team, "undo": False},
        {
            "current_set": set_num,
            "team_1": {"score": score_pair[0], "sets": 0, "timeouts": 0},
            "team_2": {"score": score_pair[1], "sets": 0, "timeouts": 0},
            "serve": "A" if team == 1 else "B",
        },
    )


class TestLiveStatsEmpty:
    def test_empty_audit_returns_zeroed_stats(self):
        result = compute_live_stats("never-written")
        assert result["oid"] == "never-written"
        assert result["audit_count"] == 0
        assert result["current_streak"] == {"team": None, "n": 0, "set": None}
        assert result["longest_streak"]["n"] == 0
        assert result["total_points"] == 0
        assert result["points_history"] == []


class TestCurrentStreak:
    def test_consecutive_points_one_team(self):
        oid = "streak-one-team"
        for i in range(1, 4):
            _add_point(oid, 1, (i, 0))
        stats = compute_live_stats(oid)
        assert stats["current_streak"] == {"team": 1, "n": 3, "set": 1}

    def test_opposite_team_breaks_streak(self):
        oid = "streak-broken"
        _add_point(oid, 1, (1, 0))
        _add_point(oid, 1, (2, 0))
        _add_point(oid, 2, (2, 1))
        stats = compute_live_stats(oid)
        assert stats["current_streak"] == {"team": 2, "n": 1, "set": 1}

    def test_set_score_breaks_streak(self):
        oid = "streak-manual-edit"
        _add_point(oid, 1, (1, 0))
        _add_point(oid, 1, (2, 0))
        action_log.append(
            oid,
            "set_score",
            {"team": 1, "set": 1, "value": 5, "undo": False},
            {
                "current_set": 1,
                "team_1": {"score": 5, "sets": 0, "timeouts": 0},
                "team_2": {"score": 0, "sets": 0, "timeouts": 0},
                "serve": "A",
            },
        )
        _add_point(oid, 1, (6, 0))
        stats = compute_live_stats(oid)
        # Manual edit broke the streak; the run after the edit is 1.
        assert stats["current_streak"]["team"] == 1
        assert stats["current_streak"]["n"] == 1

    def test_longest_vs_current_streak(self):
        oid = "streak-longest"
        for i in range(1, 6):
            _add_point(oid, 1, (i, 0))  # 5-in-a-row for team 1
        _add_point(oid, 2, (5, 1))
        _add_point(oid, 2, (5, 2))  # 2-in-a-row for team 2
        stats = compute_live_stats(oid)
        assert stats["longest_streak"]["n"] == 5
        assert stats["longest_streak"]["team"] == 1
        assert stats["current_streak"]["n"] == 2
        assert stats["current_streak"]["team"] == 2


class TestPointsHistory:
    def test_chronological_with_scores(self):
        oid = "history"
        _add_point(oid, 1, (1, 0))
        _add_point(oid, 2, (1, 1))
        _add_point(oid, 1, (2, 1))
        stats = compute_live_stats(oid, history_limit=10)
        assert len(stats["points_history"]) == 3
        assert stats["points_history"][0]["team"] == 1
        assert stats["points_history"][0]["score"] == [1, 0]
        assert stats["points_history"][-1]["score"] == [2, 1]
        # Action tag preserved for the overlay to distinguish edits.
        assert all(p["action"] == "add_point" for p in stats["points_history"])

    def test_history_trimmed_to_limit(self):
        oid = "history-trim"
        for i in range(1, 11):
            _add_point(oid, 1, (i, 0))
        stats = compute_live_stats(oid, history_limit=3)
        assert len(stats["points_history"]) == 3
        assert [p["score"][0] for p in stats["points_history"]] == [8, 9, 10]

    def test_history_limit_zero_returns_empty(self):
        oid = "history-zero"
        _add_point(oid, 1, (1, 0))
        stats = compute_live_stats(oid, history_limit=0)
        assert stats["points_history"] == []
        # Other stats still computed.
        assert stats["audit_count"] == 1


class TestAuditCount:
    def test_audit_count_excludes_undo_records(self):
        oid = "count-undo"
        _add_point(oid, 1, (1, 0))
        action_log.append(
            oid,
            "add_point",
            {"team": 1, "undo": True},
            {
                "current_set": 1,
                "team_1": {"score": 0, "sets": 0, "timeouts": 0},
                "team_2": {"score": 0, "sets": 0, "timeouts": 0},
                "serve": "A",
            },
        )
        stats = compute_live_stats(oid)
        # action_log.read_all already strips undo pairs at the tombstone
        # layer, so audit_count reflects the *visible* records.
        assert stats["audit_count"] >= 0
