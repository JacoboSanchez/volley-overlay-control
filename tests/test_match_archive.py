"""Tests for app/api/match_archive.py and the GameService archive trigger."""
import time

import pytest

from app.api import action_log, match_archive
from app.api.game_service import GameService
from app.api.session_manager import SessionManager

pytestmark = pytest.mark.usefixtures("clean_sessions")


# ---------------------------------------------------------------------------
# match_archive low-level
# ---------------------------------------------------------------------------

class TestMatchArchive:
    def test_archive_round_trip(self):
        action_log.append("oid-x", "add_point", {"team": 1}, {"score": 1})
        match_id = match_archive.archive_match(
            oid="oid-x",
            final_state={"team_1": {"sets": 3}, "team_2": {"sets": 1},
                         "current_set": 4},
            customization={"Team 1 Name": "Home"},
            started_at=time.time() - 1800,
            winning_team=1,
            points_limit=25,
            points_limit_last_set=15,
            sets_limit=5,
        )
        assert match_id is not None

        loaded = match_archive.load_match(match_id)
        assert loaded is not None
        assert loaded["oid"] == "oid-x"
        assert loaded["winning_team"] == 1
        assert loaded["final_state"]["team_1"]["sets"] == 3
        assert loaded["customization"]["Team 1 Name"] == "Home"
        assert loaded["audit_log"][0]["action"] == "add_point"
        assert loaded["config"]["points_limit"] == 25
        assert loaded["duration_s"] is not None and loaded["duration_s"] > 0

    def test_invalid_oid_returns_none(self):
        assert match_archive.archive_match(
            oid="../escape", final_state={}, winning_team=1,
        ) is None

    def test_list_matches_filters_by_oid(self):
        match_archive.archive_match(
            oid="oid-a", final_state={"current_set": 5}, winning_team=2,
        )
        match_archive.archive_match(
            oid="oid-b", final_state={"current_set": 4}, winning_team=1,
        )
        matches_a = match_archive.list_matches(oid="oid-a")
        assert len(matches_a) == 1
        assert matches_a[0]["oid"] == "oid-a"

        all_matches = match_archive.list_matches()
        assert len(all_matches) == 2

    def test_list_matches_orders_newest_first(self):
        # Microsecond-resolution timestamps mean two back-to-back
        # archives produce distinct ``match_id`` values without sleeps.
        match_archive.archive_match(
            oid="oid-ord",
            final_state={"team_1": {"sets": 0}, "team_2": {"sets": 3}},
            winning_team=2,
        )
        match_archive.archive_match(
            oid="oid-ord",
            final_state={"team_1": {"sets": 3}, "team_2": {"sets": 1}},
            winning_team=1,
        )
        matches = match_archive.list_matches(oid="oid-ord")
        assert matches[0]["winning_team"] == 1
        assert matches[1]["winning_team"] == 2

    def test_load_match_rejects_traversal(self):
        assert match_archive.load_match("../etc/passwd") is None
        assert match_archive.load_match("nope") is None
        assert match_archive.load_match("match_zzzz_invalid") is None

    def test_back_to_back_archives_get_distinct_ids(self):
        ids = {
            match_archive.archive_match(
                oid="oid-back2back", final_state={}, winning_team=1,
            )
            for _ in range(5)
        }
        assert None not in ids
        assert len(ids) == 5

    def test_delete_for_oid_removes_files(self):
        for _ in range(3):
            match_archive.archive_match(
                oid="oid-del", final_state={}, winning_team=1,
            )
        assert len(match_archive.list_matches(oid="oid-del")) == 3
        removed = match_archive.delete_for_oid("oid-del")
        assert removed == 3
        assert match_archive.list_matches(oid="oid-del") == []


# ---------------------------------------------------------------------------
# GameService archive trigger
# ---------------------------------------------------------------------------

class TestArchiveTrigger:
    def _drive_to_match_end(self, session, *, via_set):
        """Helper: get the session to match_finished using add_set or add_point."""
        if via_set:
            for _ in range(3):
                GameService.add_set(session, team=1)
        else:
            # Score 25-0 three times.
            for _set_num in range(1, 4):
                # Each iteration: 25 points to team 1
                for _ in range(25):
                    GameService.add_point(session, team=1)

    def test_match_end_via_add_set_archives(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("arch-1", mock_conf, api_backend)
        # mock_conf: sets=5 → soft limit 3 → 3 sets win the match.
        self._drive_to_match_end(session, via_set=True)
        matches = match_archive.list_matches(oid="arch-1")
        assert len(matches) == 1
        assert matches[0]["winning_team"] == 1

    def test_match_end_via_add_point_archives(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("arch-2", mock_conf, api_backend)
        self._drive_to_match_end(session, via_set=False)
        matches = match_archive.list_matches(oid="arch-2")
        assert len(matches) == 1
        # Check the audit log was bundled in.
        full = match_archive.load_match(matches[0]["match_id"])
        assert any(r["action"] == "add_point" for r in full["audit_log"])

    def test_no_archive_when_match_in_progress(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("arch-3", mock_conf, api_backend)
        GameService.add_set(session, team=1)
        GameService.add_set(session, team=2)
        assert match_archive.list_matches(oid="arch-3") == []

    def test_archive_failure_does_not_break_action(
            self, mock_conf, api_backend, monkeypatch):
        session = SessionManager.get_or_create("arch-4", mock_conf, api_backend)
        monkeypatch.setattr(
            match_archive, "archive_match",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        # Drive to match end — even with archive throwing, the action
        # response should still succeed.
        for _ in range(2):
            GameService.add_set(session, team=1)
        response = GameService.add_set(session, team=1)
        assert response.success is True

    def test_match_started_at_persists_across_restart(
            self, mock_conf, api_backend):
        session = SessionManager.get_or_create("arch-5", mock_conf, api_backend)
        original = session.match_started_at
        GameService.add_point(session, team=1)
        SessionManager.clear()

        restored = SessionManager.get_or_create("arch-5", mock_conf, api_backend)
        assert restored.match_started_at == pytest.approx(original)

    def test_match_started_at_resets_on_reset(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("arch-6", mock_conf, api_backend)
        old = session.match_started_at - 100
        session.match_started_at = old
        GameService.reset(session)
        assert session.match_started_at > old
