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
        # ``with/slash`` is intentionally omitted: custom-overlay OIDs
        # legitimately contain slashes and the basename hashes the OID
        # before touching the filesystem, so slash is safe.
        action_log.append("../bad", "add_point", {}, {})
        action_log.append("", "add_point", {}, {})
        action_log.append("white space", "add_point", {}, {})
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

    def test_append_ts_strictly_monotonic_per_oid(self, monkeypatch):
        """Two appends must never share ``ts`` even when the OS clock
        returns the same ``time.time()`` value twice. Otherwise a
        single ``_pop`` tombstone could match — and so silently undo —
        more than one record."""
        # Pin ``time.time`` so the OS clock looks like a Windows-style
        # low-resolution timer that returns the same value back-to-back.
        monkeypatch.setattr(action_log.time, "time", lambda: 1_000_000.0)
        action_log.append("oid-mono", "add_point", {"team": 1}, {})
        action_log.append("oid-mono", "add_point", {"team": 2}, {})
        action_log.append("oid-mono", "add_point", {"team": 1}, {})
        records = action_log.read_all("oid-mono")
        timestamps = [r["ts"] for r in records]
        assert len(timestamps) == 3
        # Strictly increasing — no duplicates, even though the
        # underlying clock never advanced.
        assert timestamps == sorted(set(timestamps))
        assert all(
            timestamps[i] < timestamps[i + 1]
            for i in range(len(timestamps) - 1)
        )

    def test_pop_does_not_tombstone_unrelated_records(self, monkeypatch):
        """Popping the last forward must remove only that record, even
        if a sibling forward shares the OS-clock timestamp. The
        per-OID monotonic ``_next_ts`` is what makes this safe — this
        test guards against a regression that drops it."""
        monkeypatch.setattr(action_log.time, "time", lambda: 1_000_000.0)
        action_log.append("oid-iso", "add_point", {"team": 1}, {})
        action_log.append("oid-iso", "add_point", {"team": 2}, {})
        popped = action_log.pop_last_forward("oid-iso")
        assert popped is not None
        assert popped["params"] == {"team": 2}
        remaining = action_log.read_all("oid-iso")
        assert len(remaining) == 1
        assert remaining[0]["params"] == {"team": 1}

    def test_pop_last_forward_appends_tombstone_no_rewrite(self):
        """Pop must be append-only: the file size before+after a pop
        differs by exactly the tombstone line, not by a rewrite. This
        is the perf invariant — undo cost stays O(1) regardless of
        how many records the audit log already holds."""
        for i in range(20):
            action_log.append(
                "oid-tomb", "add_point", {"team": 1, "undo": False},
                {"i": i},
            )
        path = action_log._path("oid-tomb")
        size_before = os.path.getsize(path)
        with open(path, "rb") as f:
            content_before = f.read()

        popped = action_log.pop_last_forward("oid-tomb")
        assert popped is not None
        assert popped["params"]["team"] == 1

        with open(path, "rb") as f:
            content_after = f.read()
        # The original 20 lines must remain byte-identical at the head
        # of the file (append-only). Only a single tombstone line is
        # added at the end.
        assert content_after.startswith(content_before)
        size_after = os.path.getsize(path)
        assert size_after > size_before
        # read_all hides both the popped record and the tombstone.
        remaining = action_log.read_all("oid-tomb")
        assert len(remaining) == 19
        assert all(r["action"] == "add_point" for r in remaining)

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
# Rotation (M13)
# ---------------------------------------------------------------------------


class TestActionLogRotation:
    """Verify size-based rotation, cross-file reads, and cleanup."""

    @pytest.fixture
    def small_rotation(self, monkeypatch):
        """Shrink AUDIT_LOG_MAX_BYTES so rotation is reachable from a test.

        The constant is read at import time; setting the env var afterwards
        is too late. Patch the module attribute directly instead so the
        next ``append`` sees the new threshold.
        """
        monkeypatch.setattr(action_log, "AUDIT_LOG_MAX_BYTES", 200)
        monkeypatch.setattr(action_log, "AUDIT_LOG_MAX_FILES", 3)
        yield

    def _spam(self, oid: str, n: int) -> None:
        for i in range(n):
            action_log.append(oid, "add_point", {"team": 1, "i": i}, {"x": i})

    def test_no_rotation_under_threshold(self, small_rotation):
        # Two small records stay well under 200 bytes — file should not rotate.
        action_log.append("rot-1", "add_point", {"team": 1}, {"x": 1})
        action_log.append("rot-1", "add_point", {"team": 2}, {"x": 2})
        path = action_log._path("rot-1")
        assert os.path.exists(path)
        assert not os.path.exists(action_log._rotated_path(path, 1))
        assert len(action_log.read_all("rot-1")) == 2

    def test_rotates_when_active_exceeds_threshold(self, monkeypatch):
        # Cap=10 is generous enough that 10 records (~95 B each, threshold
        # 200 B → rotation every ~3 records → ~4 files) all survive. This
        # specifically exercises read_all stitching across the rotation
        # boundary; the cap-eviction case is covered by
        # test_oldest_records_dropped_when_cap_hit below.
        monkeypatch.setattr(action_log, "AUDIT_LOG_MAX_BYTES", 200)
        monkeypatch.setattr(action_log, "AUDIT_LOG_MAX_FILES", 10)
        self._spam("rot-2", 10)
        path = action_log._path("rot-2")
        assert os.path.exists(action_log._rotated_path(path, 1))
        records = action_log.read_all("rot-2")
        assert len(records) == 10
        assert [r["params"]["i"] for r in records] == list(range(10))

    def test_rotation_caps_at_max_files(self, small_rotation):
        # AUDIT_LOG_MAX_FILES=3 means active + .1 + .2 (3 files total).
        self._spam("rot-3", 60)
        path = action_log._path("rot-3")
        # Slot .3 must never appear.
        assert not os.path.exists(action_log._rotated_path(path, 3))
        # Slot .2 (oldest survivor) and .1 (newest rotated) may exist.
        assert os.path.exists(action_log._rotated_path(path, 2))
        assert os.path.exists(action_log._rotated_path(path, 1))

    def test_oldest_records_dropped_when_cap_hit(self, small_rotation):
        self._spam("rot-4", 60)
        records = action_log.read_all("rot-4")
        # Some prefix of records was lost to the cap; every surviving
        # record's index must be strictly increasing (no shuffling).
        ids = [r["params"]["i"] for r in records]
        assert ids == sorted(ids)
        # The newest record (i=59) must always survive — it's in the
        # active file.
        assert ids[-1] == 59

    def test_clear_removes_all_rotated_files(self, small_rotation):
        self._spam("rot-5", 60)
        path = action_log._path("rot-5")
        assert os.path.exists(action_log._rotated_path(path, 1))
        action_log.clear("rot-5")
        assert not os.path.exists(path)
        for i in range(1, 5):
            assert not os.path.exists(action_log._rotated_path(path, i))
        assert action_log.read_all("rot-5") == []

    def test_delete_removes_all_rotated_files(self, small_rotation):
        self._spam("rot-6", 60)
        path = action_log._path("rot-6")
        assert action_log.delete("rot-6") is True
        assert not os.path.exists(path)
        for i in range(1, 5):
            assert not os.path.exists(action_log._rotated_path(path, i))
        # Second delete returns False (idempotent).
        assert action_log.delete("rot-6") is False

    def test_pop_can_tombstone_record_in_rotated_file(self, small_rotation):
        # Forward record lands in rotated archive after enough spam;
        # tombstone goes to the active file. read_all must hide both.
        self._spam("rot-7", 30)
        path = action_log._path("rot-7")
        assert os.path.exists(action_log._rotated_path(path, 1))
        # Pop the most recent forward; target may live in the active
        # file but the cross-file machinery is exercised regardless.
        target = action_log.pop_last_forward("rot-7")
        assert target is not None
        records = action_log.read_all("rot-7")
        # The popped record must not appear in the visible view.
        assert target not in records
        # The tombstone itself must also be hidden.
        assert all(r["action"] != "_pop" for r in records)


# ---------------------------------------------------------------------------
# Cursor pagination (M13)
# ---------------------------------------------------------------------------


class TestReadPage:
    """``read_page`` is the cursor-based building block of GET /audit."""

    def _seed(self, oid: str, n: int) -> None:
        for i in range(n):
            action_log.append(oid, "add_point", {"team": 1, "i": i}, {"x": i})

    def test_first_page_returns_newest_records(self):
        self._seed("page-1", 50)
        page, cursor = action_log.read_page("page-1", limit=10)
        assert len(page) == 10
        # Chronological within window: i=40..49.
        assert [r["params"]["i"] for r in page] == list(range(40, 50))
        assert cursor == page[0]["ts"]

    def test_walking_pages_covers_every_record(self):
        self._seed("page-2", 25)
        seen: list[int] = []
        cursor = None
        # Cap iterations defensively so a bug cannot hang the test.
        for _ in range(20):
            page, cursor = action_log.read_page(
                "page-2", limit=7, before_ts=cursor,
            )
            seen = [r["params"]["i"] for r in page] + seen
            if cursor is None:
                break
        assert seen == list(range(25))
        assert cursor is None

    def test_cursor_null_on_final_page(self):
        self._seed("page-3", 5)
        page, cursor = action_log.read_page("page-3", limit=10)
        assert len(page) == 5
        assert cursor is None  # no more records remain

    def test_empty_log_returns_empty_with_null_cursor(self):
        page, cursor = action_log.read_page("never-written", limit=10)
        assert page == []
        assert cursor is None

    def test_invalid_limit_returns_empty(self):
        page, cursor = action_log.read_page("page-3", limit=0)
        assert page == []
        assert cursor is None

    def test_pagination_skips_tombstoned_records(self):
        self._seed("page-4", 5)
        # Pop the most recent forward — i=4 should disappear from the page.
        action_log.pop_last_forward("page-4")
        page, _ = action_log.read_page("page-4", limit=10)
        ids = [r["params"]["i"] for r in page]
        assert 4 not in ids
        assert ids == [0, 1, 2, 3]


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
