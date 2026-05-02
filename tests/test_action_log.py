"""Tests for app/api/action_log.py and the GameService write path."""
import json
import os

import pytest

from app.api import action_log
from app.api.game_service import GameService
from app.api.session_manager import SessionManager

pytestmark = pytest.mark.usefixtures("clean_sessions")


# ---------------------------------------------------------------------------
# action_log low-level
# ---------------------------------------------------------------------------

class TestActionLog:
    def test_append_and_read_round_trip(self):
        action_log.append("oid-a", "add_point", {"team": 1}, {"score": 1})
        action_log.append("oid-a", "add_point", {"team": 2}, {"score": 0})
        records = action_log.read_all("oid-a")
        assert len(records) == 2
        assert records[0]["action"] == "add_point"
        assert records[0]["params"] == {"team": 1}
        assert records[0]["result"] == {"score": 1}
        assert "ts" in records[0]

    def test_read_all_when_missing(self):
        assert action_log.read_all("never-written") == []

    def test_invalid_oid_silently_ignored(self):
        action_log.append("../bad", "add_point", {}, {})
        action_log.append("with/slash", "add_point", {}, {})
        action_log.append("", "add_point", {}, {})
        # Verify no files were created.
        files = [
            f for f in os.listdir(action_log._data_dir())
            if f.startswith("audit_")
        ]
        assert files == []

    def test_read_recent_returns_tail(self):
        for i in range(10):
            action_log.append("oid-tail", "add_point", {"i": i}, {})
        recent = action_log.read_recent("oid-tail", limit=3)
        assert [r["params"]["i"] for r in recent] == [7, 8, 9]

    def test_clear_truncates(self):
        action_log.append("oid-clr", "add_point", {}, {})
        action_log.clear("oid-clr")
        assert action_log.read_all("oid-clr") == []

    def test_delete_removes_file(self):
        action_log.append("oid-del", "add_point", {}, {})
        assert action_log.delete("oid-del") is True
        assert action_log.delete("oid-del") is False  # idempotent
        assert action_log.read_all("oid-del") == []

    def test_pop_last_forward_skips_undo(self):
        action_log.append("oid-pop", "add_point", {"team": 1, "undo": False}, {})
        action_log.append("oid-pop", "add_point", {"team": 2, "undo": False}, {})
        action_log.append("oid-pop", "add_point", {"team": 2, "undo": True}, {})
        # Last forward record is the team=2 forward append.
        popped = action_log.pop_last_forward("oid-pop")
        assert popped is not None
        assert popped["params"] == {"team": 2, "undo": False}
        # The undo entry remains, the popped forward entry is gone.
        remaining = action_log.read_all("oid-pop")
        assert len(remaining) == 2
        assert remaining[0]["params"] == {"team": 1, "undo": False}
        assert remaining[1]["params"] == {"team": 2, "undo": True}

    def test_pop_last_forward_when_empty(self):
        assert action_log.pop_last_forward("never-existed") is None

    def test_pop_last_forward_when_only_undo(self):
        action_log.append("oid-allundo", "add_point", {"undo": True}, {})
        action_log.append("oid-allundo", "add_point", {"undo": True}, {})
        assert action_log.pop_last_forward("oid-allundo") is None

    def test_lock_pool_is_fixed_and_stable_per_oid(self):
        """The lock pool is a fixed-size tuple and ``_lock_for`` must
        return the *same* lock object for the same OID across calls.

        A stable per-OID lock is the correctness invariant the pool
        replaced the old LRU dict with: an LRU could evict a held
        lock and let a concurrent caller mint a fresh, independent
        one for the same OID, breaking mutual exclusion on the
        backing JSONL file.
        """
        assert len(action_log._locks_pool) == action_log._LOCKS_POOL_SIZE
        # Same OID → same lock identity, no matter how many times we ask.
        assert action_log._lock_for("oid-stable") is action_log._lock_for(
            "oid-stable"
        )
        # Lock identities span at most the pool size, even with many OIDs.
        seen = {id(action_log._lock_for(f"oid-{i}")) for i in range(1024)}
        assert len(seen) <= action_log._LOCKS_POOL_SIZE

    def test_skips_malformed_lines(self):
        path = action_log._path("oid-bad")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("not json\n")
            f.write(json.dumps({"ts": 1, "action": "ok"}) + "\n")
            f.write("\n")
            f.write("garbage{}garbage\n")
        records = action_log.read_all("oid-bad")
        assert len(records) == 1
        assert records[0]["action"] == "ok"


# ---------------------------------------------------------------------------
# GameService write path
# ---------------------------------------------------------------------------

class TestGameServiceWritesAudit:
    def test_add_point_writes_record(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("audit-1", mock_conf, api_backend)
        GameService.add_point(session, team=1)
        records = action_log.read_all("audit-1")
        assert len(records) == 1
        assert records[0]["action"] == "add_point"
        assert records[0]["params"] == {"team": 1, "undo": False}
        assert records[0]["result"]["team_1"]["score"] == 1
        assert records[0]["result"]["match_finished"] is False

    def test_per_type_undo_pops_matching_forward_and_records_undo(
            self, mock_conf, api_backend):
        """Per-type undo (``add_point(undo=True)`` etc.) now shares the
        audit-log stack with ``POST /game/undo``: the matching forward
        record is popped, an undo record is appended, so a follow-up
        generic undo cannot double-revert the same action."""
        session = SessionManager.get_or_create("audit-2", mock_conf, api_backend)
        GameService.add_point(session, team=1)
        GameService.add_point(session, team=1, undo=True)
        records = action_log.read_all("audit-2")
        assert len(records) == 1
        assert records[0]["params"]["undo"] is True

    def test_add_set_writes_record(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("audit-3", mock_conf, api_backend)
        GameService.add_set(session, team=2)
        records = action_log.read_all("audit-3")
        assert any(r["action"] == "add_set" for r in records)

    def test_reset_clears_log_and_writes_marker(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("audit-4", mock_conf, api_backend)
        GameService.add_point(session, team=1)
        GameService.add_point(session, team=1)
        GameService.reset(session)
        records = action_log.read_all("audit-4")
        # After reset the log should contain only the reset marker.
        assert len(records) == 1
        assert records[0]["action"] == "reset"

    def test_change_serve_writes_record(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("audit-5", mock_conf, api_backend)
        GameService.change_serve(session, team=1)
        records = action_log.read_all("audit-5")
        assert any(r["action"] == "change_serve" for r in records)

    def test_set_score_writes_record(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("audit-6", mock_conf, api_backend)
        GameService.set_score(session, team=1, set_number=1, value=10)
        records = action_log.read_all("audit-6")
        rec = next(r for r in records if r["action"] == "set_score")
        assert rec["params"] == {"team": 1, "set_number": 1, "value": 10}
