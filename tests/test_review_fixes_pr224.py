"""Regression tests for the four correctness issues raised by the
Gemini code review on PR #224:

* ``pop_last_forward`` rewrites the file atomically (mkstemp +
  ``os.replace``) so a crash mid-write doesn't truncate the audit
  log.
* The ``set_end`` webhook ``set_number`` reports the set that just
  ended, not the next one (``current_set`` was being read after it
  had already advanced).
* The audit log records the *final* score of the set the action
  operated on (e.g. 25-23) rather than the new set's empty 0-0.
"""
from unittest.mock import patch

import pytest

from app.api import action_log, webhooks
from app.api.game_service import GameService
from app.api.session_manager import SessionManager
from app.api.webhooks import WebhookDispatcher

pytestmark = pytest.mark.usefixtures("clean_sessions")


@pytest.fixture
def sync_dispatcher(monkeypatch):
    """Run webhook deliveries synchronously and capture them."""
    d = WebhookDispatcher()
    monkeypatch.setattr(webhooks, "webhook_dispatcher", d)
    monkeypatch.setattr("app.api.game_service.webhook_dispatcher", d)
    return d


# ---------------------------------------------------------------------------
# #1 — pop_last_forward atomic rewrite
# ---------------------------------------------------------------------------

class TestPopAtomicRewrite:
    def test_pop_uses_atomic_replace(self, monkeypatch):
        """Verify ``pop_last_forward`` writes via mkstemp + os.replace
        rather than truncating the original file.

        We patch ``open`` to record the modes it's called with.
        Pre-fix the path was opened with mode ``"w"`` (truncates
        immediately, lose-everything-on-crash). Post-fix the
        rewrite goes through ``os.fdopen`` of an mkstemp fd, so
        the original path is never opened ``"w"``.
        """
        action_log.append("oid-atomic", "add_point", {"team": 1}, {})
        path = action_log._path("oid-atomic")

        opened_modes: list[tuple[str, str]] = []
        real_open = open

        def tracking_open(file, mode="r", *args, **kwargs):
            opened_modes.append((str(file), mode))
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr("builtins.open", tracking_open)

        action_log.pop_last_forward(
            "oid-atomic", allowed_actions={"add_point"},
        )

        # The original audit path must NOT be opened with truncating
        # write mode anywhere in pop_last_forward.
        truncating_writes_to_audit = [
            (p, m) for (p, m) in opened_modes
            if p == path and m == "w"
        ]
        assert truncating_writes_to_audit == []

    def test_pop_survives_concurrent_truncation_simulation(self):
        """End-to-end check: the file ends up containing the right
        records after pop, with no duplicate or missing entries."""
        for i in range(5):
            action_log.append("oid-survive", "add_point",
                              {"team": 1, "i": i}, {})
        action_log.pop_last_forward(
            "oid-survive", allowed_actions={"add_point"},
        )
        remaining = action_log.read_all("oid-survive")
        assert len(remaining) == 4
        # The most recent forward (i=4) was popped; the rest stay
        # in original append order.
        assert [r["params"]["i"] for r in remaining] == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# #2 + #3 — set_end webhook set_number
# ---------------------------------------------------------------------------

class TestSetEndWebhookSetNumber:
    def _drive_set1_to_24(self, session, team: int):
        for _ in range(24):
            GameService.add_point(session, team=team)

    def test_set_winning_point_reports_set_that_ended(
            self, mock_conf, api_backend, sync_dispatcher, monkeypatch):
        monkeypatch.setenv("WEBHOOKS_URL", "https://x.example.com")
        sync_dispatcher.reload()

        session = SessionManager.get_or_create(
            "set-end-1", mock_conf, api_backend,
        )
        self._drive_set1_to_24(session, team=1)
        # The 25th point wins set 1. ``current_set`` advances to 2.
        with patch.object(sync_dispatcher, "dispatch") as dispatch:
            GameService.add_point(session, team=1)

        set_end = next(
            c for c in dispatch.call_args_list if c.args[0] == "set_end"
        )
        # Pre-fix this asserted ``set_number == 2`` (the next set).
        assert set_end.args[2]["details"]["set_number"] == 1

    def test_match_winning_point_reports_final_set(
            self, mock_conf, api_backend, sync_dispatcher, monkeypatch):
        monkeypatch.setenv("WEBHOOKS_URL", "https://x.example.com")
        sync_dispatcher.reload()

        session = SessionManager.get_or_create(
            "set-end-2", mock_conf, api_backend,
        )
        # mock_conf: best of 5 → soft limit 3 sets win the match.
        # Win set 1 and set 2 the slow way.
        for _ in range(2):
            for _ in range(25):
                GameService.add_point(session, team=1)

        # Now drive set 3 to 14, then the 15th point... wait, set 3
        # uses points_limit=25 since this isn't the *deciding* set
        # (deciding set is set 5 in a best-of-5). To get a match win
        # at set 3 we need to actually finish via add_set, not by
        # natural points. Use add_set instead.
        with patch.object(sync_dispatcher, "dispatch") as dispatch:
            GameService.add_set(session, team=1)

        set_end_calls = [
            c for c in dispatch.call_args_list if c.args[0] == "set_end"
        ]
        match_end_calls = [
            c for c in dispatch.call_args_list if c.args[0] == "match_end"
        ]
        assert len(set_end_calls) == 1
        assert len(match_end_calls) == 1
        # The set that ended IS set 3 (the match-winning one).
        # ``current_set`` is not advanced past the winning set on a
        # match-finishing call, so the reported ``set_number`` is the
        # winning set itself.
        assert set_end_calls[0].args[2]["details"]["set_number"] == 3

    def test_add_set_non_finishing_reports_set_that_ended(
            self, mock_conf, api_backend, sync_dispatcher, monkeypatch):
        monkeypatch.setenv("WEBHOOKS_URL", "https://x.example.com")
        sync_dispatcher.reload()

        session = SessionManager.get_or_create(
            "set-end-3", mock_conf, api_backend,
        )
        with patch.object(sync_dispatcher, "dispatch") as dispatch:
            GameService.add_set(session, team=1)

        set_end = next(
            c for c in dispatch.call_args_list if c.args[0] == "set_end"
        )
        # Set 1 just ended; current_set is now 2.
        assert set_end.args[2]["details"]["set_number"] == 1


# ---------------------------------------------------------------------------
# #4 — audit log scores at set end
# ---------------------------------------------------------------------------

class TestAuditLogScoresAtSetEnd:
    def test_set_winning_point_records_final_score(
            self, mock_conf, api_backend):
        session = SessionManager.get_or_create(
            "audit-final-1", mock_conf, api_backend,
        )
        # Drive team 1 to 24, team 2 to 23.
        for _ in range(24):
            GameService.add_point(session, team=1)
        for _ in range(23):
            GameService.add_point(session, team=2)

        # 25th point for team 1 wins set 1. Pre-fix the audit
        # entry recorded team_1.score=0 for the new (empty) set 2.
        GameService.add_point(session, team=1)

        records = action_log.read_all("audit-final-1")
        # Find the set-winning add_point — the 48th record overall
        # (24 + 23 + 1) with team_1 sets becoming 1.
        winning = next(
            r for r in records
            if r["action"] == "add_point"
            and r["result"]["team_1"]["sets"] == 1
        )
        assert winning["result"]["score_set"] == 1
        assert winning["result"]["team_1"]["score"] == 25
        assert winning["result"]["team_2"]["score"] == 23
        # The session has advanced to set 2 — visible in current_set.
        assert winning["result"]["current_set"] == 2

    def test_non_set_winning_point_uses_current_set(
            self, mock_conf, api_backend):
        session = SessionManager.get_or_create(
            "audit-final-2", mock_conf, api_backend,
        )
        GameService.add_point(session, team=1)

        records = action_log.read_all("audit-final-2")
        assert len(records) == 1
        # Plain add_point: score_set == current_set == 1.
        assert records[0]["result"]["score_set"] == 1
        assert records[0]["result"]["current_set"] == 1
        assert records[0]["result"]["team_1"]["score"] == 1

    def test_add_set_records_final_score_of_ended_set(
            self, mock_conf, api_backend):
        session = SessionManager.get_or_create(
            "audit-final-3", mock_conf, api_backend,
        )
        # Team 1 has some score in set 1 before someone forces the
        # set via add_set.
        for _ in range(7):
            GameService.add_point(session, team=1)
        for _ in range(3):
            GameService.add_point(session, team=2)
        # Force-end set 1 in team 1's favour.
        GameService.add_set(session, team=1)

        records = action_log.read_all("audit-final-3")
        add_set_record = next(
            r for r in records
            if r["action"] == "add_set" and not r["params"].get("undo")
        )
        # The set that just ended is set 1 — capture its final score.
        assert add_set_record["result"]["score_set"] == 1
        assert add_set_record["result"]["team_1"]["score"] == 7
        assert add_set_record["result"]["team_2"]["score"] == 3
        assert add_set_record["result"]["current_set"] == 2
