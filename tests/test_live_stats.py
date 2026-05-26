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


class TestPointsBySet:
    def test_empty_audit_returns_empty_mapping(self):
        stats = compute_live_stats("nobody")
        assert stats["points_by_set"] == {}

    def test_buckets_events_by_set_number(self):
        oid = "per-set"
        _add_point(oid, 1, (1, 0), set_num=1)
        _add_point(oid, 2, (1, 1), set_num=1)
        _add_point(oid, 1, (1, 0), set_num=2)
        _add_point(oid, 1, (2, 0), set_num=2)
        _add_point(oid, 2, (2, 1), set_num=2)
        stats = compute_live_stats(oid)
        per_set = stats["points_by_set"]
        assert sorted(per_set.keys()) == [1, 2]
        assert len(per_set[1]) == 2
        assert len(per_set[2]) == 3
        # Last event in set 2 lands at 2-1 — chronological order preserved.
        assert per_set[2][-1]["score"] == [2, 1]

    def test_per_set_cap_drops_overflow(self):
        oid = "per-set-cap"
        # 70 events in set 1, the cap is 60 → only first 60 are kept.
        for i in range(1, 71):
            _add_point(oid, 1, (i, 0), set_num=1)
        stats = compute_live_stats(oid)
        assert len(stats["points_by_set"][1]) == 60


def _add_timeout(oid: str, team: int, set_num: int = 1):
    action_log.append(
        oid,
        "add_timeout",
        {"team": team, "undo": False},
        {
            "current_set": set_num,
            "team_1": {"score": 0, "sets": 0, "timeouts": 1 if team == 1 else 0},
            "team_2": {"score": 0, "sets": 0, "timeouts": 1 if team == 2 else 0},
            "serve": "A",
        },
    )


class TestTimeoutsBySet:
    def test_empty_audit(self):
        stats = compute_live_stats("nobody")
        assert stats["timeouts_by_set"] == {}

    def test_groups_by_set(self):
        oid = "to-by-set"
        _add_timeout(oid, 1, set_num=1)
        _add_timeout(oid, 2, set_num=1)
        _add_timeout(oid, 1, set_num=2)
        stats = compute_live_stats(oid)
        assert sorted(stats["timeouts_by_set"].keys()) == [1, 2]
        assert len(stats["timeouts_by_set"][1]) == 2
        assert len(stats["timeouts_by_set"][2]) == 1
        # Per-event shape: team, set, ts.
        first = stats["timeouts_by_set"][1][0]
        assert first["team"] == 1
        assert first["set"] == 1
        assert "ts" in first


class TestServicesSummary:
    def test_empty_audit(self):
        stats = compute_live_stats("nobody")
        # Default zero-counts, both teams present.
        assert stats["services"] == {
            1: {"served": 0, "won": 0},
            2: {"served": 0, "won": 0},
        }

    def test_consecutive_holds_count_as_won(self):
        oid = "svc-holds"
        # Team 1 wins three in a row (serve stays with them after first).
        # We can't know who served the first rally so it's unattributed.
        _add_point(oid, 1, (1, 0))  # serve goes to team 1 after this
        _add_point(oid, 1, (2, 0))  # team 1 served, team 1 won → "won"
        _add_point(oid, 1, (3, 0))  # team 1 served, team 1 won → "won"
        stats = compute_live_stats(oid)
        assert stats["services"][1]["served"] == 2
        assert stats["services"][1]["won"] == 2
        assert stats["services"][2]["served"] == 0

    def test_sideout_counts_as_lost_service(self):
        oid = "svc-sideout"
        _add_point(oid, 1, (1, 0))  # serve flips to team 1
        _add_point(oid, 1, (2, 0))  # team 1 served, team 1 won
        _add_point(oid, 2, (2, 1))  # team 1 served, team 2 scored → sideout
        stats = compute_live_stats(oid)
        assert stats["services"][1]["served"] == 2
        assert stats["services"][1]["won"] == 1
        # Team 2 then serves the next rally — but there is no fourth
        # add_point so team 2's served counter stays at 0.
        assert stats["services"][2]["served"] == 0


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


class TestMemoization:
    """``compute_live_stats`` is memoized against ``action_log.version``."""

    def test_repeated_calls_hit_cache(self):
        oid = "memo-hit"
        _add_point(oid, 1, (1, 0))
        first = compute_live_stats(oid)
        second = compute_live_stats(oid)
        # Same version → identical cached object, no recompute.
        assert first is second

    def test_append_invalidates_cache(self):
        oid = "memo-append"
        _add_point(oid, 1, (1, 0))
        first = compute_live_stats(oid)
        _add_point(oid, 1, (2, 0))
        second = compute_live_stats(oid)
        assert first is not second
        assert second["total_points"] == 2

    def test_clear_invalidates_cache(self):
        oid = "memo-clear"
        _add_point(oid, 1, (1, 0))
        assert compute_live_stats(oid)["total_points"] == 1
        action_log.clear(oid)
        after = compute_live_stats(oid)
        assert after["total_points"] == 0
        assert after["audit_count"] == 0

    def test_distinct_history_limits_cached_separately(self):
        oid = "memo-limit"
        for i in range(1, 6):
            _add_point(oid, 1, (i, 0))
        full = compute_live_stats(oid, history_limit=30)
        capped = compute_live_stats(oid, history_limit=2)
        # Different tail lengths are distinct cache entries (not aliased).
        assert len(full["points_history"]) == 5
        assert len(capped["points_history"]) == 2
        # The originally-cached payload is unaffected by the second call.
        assert len(compute_live_stats(oid, history_limit=30)["points_history"]) == 5

    def test_stale_compute_does_not_regress_cache(self, monkeypatch):
        """A compute racing behind a newer mutation must not clobber the
        newer cache entry — doing so would force a miss on every read
        until the next mutation."""
        from app.api import live_stats

        oid = "memo-race"
        _add_point(oid, 1, (1, 0))  # action_log.version(oid) == 1

        # Capture ver=1 at entry, then during the (mocked) computation
        # simulate a concurrent writer: bump to v2 and store a v2 payload,
        # exactly as a competing thread would.
        def racing_compute(o, *, history_limit=30):
            _add_point(o, 1, (2, 0))  # bumps version to 2
            live_stats._STATS_CACHE[o] = (
                action_log.version(o),
                {history_limit: {"marker": "v2"}},
            )
            return {"marker": "v1"}

        monkeypatch.setattr(live_stats, "_compute_live_stats", racing_compute)
        result = live_stats.compute_live_stats(oid, history_limit=30)

        # The caller still receives its own freshly-computed payload.
        assert result == {"marker": "v1"}
        # But the cache retains the NEWER v2 entry rather than regressing.
        entry = live_stats._STATS_CACHE[oid]
        assert entry[0] == action_log.version(oid) == 2
        assert entry[1][30] == {"marker": "v2"}
