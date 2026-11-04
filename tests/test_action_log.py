"""Tests for app/api/action_log.py and the GameService write path."""

import pytest

from app.api import action_log
from app.api.game_service import GameService
from app.api.session_manager import SessionManager

pytestmark = pytest.mark.usefixtures("clean_sessions")


def _stored_records(engine, oid: str) -> list[dict]:
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.runtime import AuditEvent

    with Session(engine) as db:
        return list(db.scalars(
            select(AuditEvent.record)
            .where(AuditEvent.store_key == oid)
            .order_by(AuditEvent.id)
        ))


def _row_count(engine, oid: str | None = None) -> int:
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from app.db.runtime import AuditEvent

    query = select(func.count()).select_from(AuditEvent)
    if oid is not None:
        query = query.where(AuditEvent.store_key == oid)
    with Session(engine) as db:
        return int(db.scalar(query) or 0)


def _stored_bytes(engine, oid: str) -> int:
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from app.db.runtime import AuditEvent

    with Session(engine) as db:
        return int(db.scalar(
            select(func.coalesce(func.sum(AuditEvent.size), 0))
            .where(AuditEvent.store_key == oid)
        ) or 0)


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

    def test_invalid_oid_silently_ignored(self, runtime_db):
        # ``with/slash`` is intentionally omitted: custom-overlay OIDs
        # legitimately contain slashes.
        action_log.append("../bad", "add_point", {}, {})
        action_log.append("", "add_point", {}, {})
        action_log.append("white space", "add_point", {}, {})
        # Verify no rows were created.
        assert _row_count(runtime_db) == 0

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

    def test_pop_last_forward_appends_tombstone_no_rewrite(self, runtime_db):
        """Pop must be append-only: the stored rows before a pop are left
        exactly as they were and a single tombstone row is added. This is
        the perf invariant — undo cost stays O(1) regardless of how many
        records the audit log already holds."""
        for i in range(20):
            action_log.append(
                "oid-tomb", "add_point", {"team": 1, "undo": False},
                {"i": i},
            )
        rows_before = _stored_records(runtime_db, "oid-tomb")

        popped = action_log.pop_last_forward("oid-tomb")
        assert popped is not None
        assert popped["params"]["team"] == 1

        rows_after = _stored_records(runtime_db, "oid-tomb")
        # The original 20 rows remain identical at the head (append-only);
        # only a single tombstone row is added at the end.
        assert rows_after[:20] == rows_before
        assert len(rows_after) == 21
        assert rows_after[-1]["action"] == "_pop"
        assert rows_after[-1]["ref_ts"] == popped["ts"]
        # read_all hides both the popped record and the tombstone.
        remaining = action_log.read_all("oid-tomb")
        assert len(remaining) == 19
        assert all(r["action"] == "add_point" for r in remaining)

    def test_skips_non_object_records(self):
        """A stored value that is not a JSON object is ignored, not fatal."""
        from app.db.runtime import AuditEvent, runtime_session

        with runtime_session() as db:
            db.add(AuditEvent(store_key="oid-bad", ts=0.5, size=6, record=["x"]))
            db.add(AuditEvent(store_key="oid-bad", ts=1.0, size=20,
                              record={"ts": 1, "action": "ok"}))
        records = action_log.read_all("oid-bad")
        assert len(records) == 1
        assert records[0]["action"] == "ok"

    def test_float_timestamps_round_trip_exactly(self):
        """Tombstones match their target by ``ts`` equality, so the stored
        float must come back bit-identical after a cold read."""
        written = action_log.append("oid-ts", "add_point", {"team": 1}, {})
        action_log._raw_cache.clear()
        (record,) = action_log.read_all("oid-ts")
        assert record["ts"] == written["ts"]
        assert action_log.pop_last_forward("oid-ts") is not None
        action_log._raw_cache.clear()
        assert action_log.read_all("oid-ts") == []


# ---------------------------------------------------------------------------
# Retention cap (replaces file rotation)
# ---------------------------------------------------------------------------


class TestActionLogRetention:
    """The per-OID byte cap drops the oldest rows, one "file" at a time."""

    @pytest.fixture
    def small_cap(self, monkeypatch):
        """Shrink the cap so it is reachable from a test.

        The constants are read at import time; patch the module attributes
        so the next ``append`` sees them. Cap = 200 B x 3 = 600 B.
        """
        monkeypatch.setattr(action_log, "AUDIT_LOG_MAX_BYTES", 200)
        monkeypatch.setattr(action_log, "AUDIT_LOG_MAX_FILES", 3)
        yield

    def _spam(self, oid: str, n: int) -> None:
        for i in range(n):
            action_log.append(oid, "add_point", {"team": 1, "i": i}, {"x": i})

    def test_nothing_dropped_under_cap(self, small_cap):
        action_log.append("rot-1", "add_point", {"team": 1}, {"x": 1})
        action_log.append("rot-1", "add_point", {"team": 2}, {"x": 2})
        assert len(action_log.read_all("rot-1")) == 2

    def test_large_cap_keeps_everything_in_order(self, monkeypatch):
        monkeypatch.setattr(action_log, "AUDIT_LOG_MAX_BYTES", 200)
        monkeypatch.setattr(action_log, "AUDIT_LOG_MAX_FILES", 10)
        self._spam("rot-2", 10)
        records = action_log.read_all("rot-2")
        assert [r["params"]["i"] for r in records] == list(range(10))

    def test_stored_bytes_never_exceed_cap_after_an_append(self, small_cap, runtime_db):
        cap = 200 * 3
        for i in range(60):
            action_log.append("rot-3", "add_point", {"team": 1, "i": i}, {"x": i})
            # The cap is enforced before each insert, so the total may exceed
            # it by at most the one record just written.
            assert _stored_bytes(runtime_db, "rot-3") <= cap + 200

    def test_oldest_records_dropped_when_cap_hit(self, small_cap):
        self._spam("rot-4", 60)
        records = action_log.read_all("rot-4")
        ids = [r["params"]["i"] for r in records]
        assert ids == sorted(ids)
        assert ids[-1] == 59
        assert ids[0] > 0

    def test_prune_drops_a_whole_file_worth_at_once(self, small_cap, runtime_db):
        """Pruning frees ~AUDIT_LOG_MAX_BYTES, not just one row, so it does
        not run on every append once the cap is reached."""
        self._spam("rot-8", 60)
        assert _stored_bytes(runtime_db, "rot-8") <= 200 * 2 + 200

    def test_running_total_reseeds_from_the_table(self, small_cap, runtime_db):
        """A fresh process has no in-memory byte total; it must seed from
        the stored rows rather than assume zero and overrun the cap."""
        self._spam("rot-9", 20)
        action_log._bytes_per_oid.clear()
        self._spam("rot-9", 40)
        assert _stored_bytes(runtime_db, "rot-9") <= 200 * 3 + 200

    def test_pop_first_after_restart_seeds_the_running_total(self, small_cap, runtime_db):
        """A tombstone can be the first write after a restart; it must seed
        the byte total from the table instead of counting from zero."""
        self._spam("rot-11", 5)
        stored = _stored_bytes(runtime_db, "rot-11")
        action_log._bytes_per_oid.clear()
        action_log._raw_cache.clear()
        assert action_log.pop_last_forward("rot-11") is not None
        assert action_log._bytes_per_oid["rot-11"] == _stored_bytes(runtime_db, "rot-11")
        assert action_log._bytes_per_oid["rot-11"] > stored

    def test_overcounted_total_is_corrected_by_a_prune(self, small_cap, runtime_db):
        self._spam("rot-12", 3)
        action_log._bytes_per_oid["rot-12"] = 10_000  # rows vanished elsewhere
        action_log.append("rot-12", "add_point", {"team": 1}, {})
        assert action_log._bytes_per_oid["rot-12"] == _stored_bytes(runtime_db, "rot-12")

    def test_single_slot_cap_truncates_on_overflow(self, monkeypatch):
        monkeypatch.setattr(action_log, "AUDIT_LOG_MAX_BYTES", 200)
        monkeypatch.setattr(action_log, "AUDIT_LOG_MAX_FILES", 1)
        self._spam("rot-10", 30)
        assert len(action_log.read_all("rot-10")) < 30

    def test_clear_removes_all_rows(self, small_cap, runtime_db):
        self._spam("rot-5", 60)
        action_log.clear("rot-5")
        assert _row_count(runtime_db, "rot-5") == 0
        assert action_log.read_all("rot-5") == []

    def test_delete_removes_all_rows(self, small_cap, runtime_db):
        self._spam("rot-6", 60)
        assert action_log.delete("rot-6") is True
        assert _row_count(runtime_db, "rot-6") == 0
        # Second delete returns False (idempotent).
        assert action_log.delete("rot-6") is False

    def test_delete_leaves_other_overlays_alone(self, runtime_db):
        self._spam("keep-me", 3)
        self._spam("drop-me", 3)
        action_log.delete("drop-me")
        assert len(action_log.read_all("keep-me")) == 3

    def test_pop_after_pruning_still_hides_target(self, small_cap):
        self._spam("rot-7", 30)
        target = action_log.pop_last_forward("rot-7")
        assert target is not None
        records = action_log.read_all("rot-7")
        assert target not in records
        assert all(r["action"] != "_pop" for r in records)


# ---------------------------------------------------------------------------
# Parsed-record cache
# ---------------------------------------------------------------------------


class TestParsedRecordCache:
    """Appends must not force a full re-read and re-parse of the log.

    ``GameService.add_point`` audits before building its state response,
    which invalidates the live-stats memo, whose recompute calls
    ``read_all``. Without the cache every scored point would re-read the
    whole log.
    """

    @pytest.fixture
    def count_file_reads(self, runtime_db):
        """Count full-log SELECTs against the audit table."""
        from sqlalchemy import event

        calls = []

        def _on_execute(conn, cursor, statement, params, context, executemany):
            if statement.lstrip().upper().startswith("SELECT") and (
                "runtime_audit_events.record" in statement
            ):
                calls.append(statement)

        event.listen(runtime_db, "before_cursor_execute", _on_execute)
        yield calls
        event.remove(runtime_db, "before_cursor_execute", _on_execute)

    def test_append_then_read_does_not_reparse(self, count_file_reads):
        action_log.append("cache-1", "add_point", {"team": 1}, {"x": 1})
        # First read populates the cache from the table.
        assert len(action_log.read_all("cache-1")) == 1
        assert len(count_file_reads) == 1

        # Steady state: each append folds itself into the cache, so the
        # follow-up read costs zero table reads.
        count_file_reads.clear()
        for i in range(20):
            action_log.append("cache-1", "add_point", {"team": 1}, {"x": i})
            action_log.read_all("cache-1")
        assert count_file_reads == []
        assert len(action_log.read_all("cache-1")) == 21

    def test_cached_view_matches_disk(self):
        """The cache must never diverge from a cold read of the table."""
        for i in range(10):
            action_log.append("cache-2", "add_point", {"team": 1, "i": i}, {"x": i})
        action_log.pop_last_forward("cache-2")
        warm = action_log.read_all("cache-2")

        # Drop the cache and read the same log straight from the table.
        action_log._raw_cache.pop("cache-2", None)
        cold = action_log.read_all("cache-2")
        assert warm == cold

    def test_rotation_invalidates_cache(self, monkeypatch):
        """Pruning discards the oldest rows; the cache must not keep
        serving records that are no longer stored."""
        monkeypatch.setattr(action_log, "AUDIT_LOG_MAX_BYTES", 200)
        monkeypatch.setattr(action_log, "AUDIT_LOG_MAX_FILES", 2)
        for i in range(40):
            action_log.append("cache-3", "add_point", {"team": 1, "i": i}, {"x": i})
            action_log.read_all("cache-3")

        warm = action_log.read_all("cache-3")
        action_log._raw_cache.pop("cache-3", None)
        cold = action_log.read_all("cache-3")
        assert warm == cold
        # Pruning actually dropped records, so this is a real check.
        assert len(cold) < 40

    def test_clear_drops_cache(self):
        action_log.append("cache-4", "add_point", {"team": 1}, {"x": 1})
        assert len(action_log.read_all("cache-4")) == 1
        action_log.clear("cache-4")
        assert action_log.read_all("cache-4") == []
        assert "cache-4" not in action_log._raw_cache

    def test_evict_cache_releases_memory(self):
        action_log.append("cache-5", "add_point", {"team": 1}, {"x": 1})
        action_log.read_all("cache-5")
        assert "cache-5" in action_log._raw_cache
        action_log.evict_cache("cache-5")
        assert "cache-5" not in action_log._raw_cache
        # Eviction is a memory concern only — the records stay stored.
        assert len(action_log.read_all("cache-5")) == 1

    def test_evict_cache_keeps_timestamps_monotonic(self, monkeypatch):
        """Eviction must not drop the monotonic timestamp tracker.

        The log rows outlive the session, so if ``_last_ts_per_oid`` were
        cleared here a wall-clock rollback would let the next append reuse a
        timestamp already stored. Tombstones reference records by ``ts``, so
        a duplicate lets one ``_pop`` cancel two records.
        """
        clock = [1_000_000.0]
        monkeypatch.setattr(action_log.time, "time", lambda: clock[0])

        action_log.append("cache-7", "add_point", {"team": 1}, {"x": 1})
        action_log.evict_cache("cache-7")

        # Clock jumps backwards while the log rows are still stored.
        clock[0] -= 60.0
        action_log.append("cache-7", "add_point", {"team": 1}, {"x": 2})

        records = action_log.read_all("cache-7")
        assert len(records) == 2
        assert records[1]["ts"] > records[0]["ts"]

    def test_caller_cannot_mutate_the_cache(self):
        action_log.append("cache-6", "add_point", {"team": 1}, {"x": 1})
        records = action_log.read_all("cache-6")
        records.append({"ts": 0, "action": "injected"})
        assert len(action_log.read_all("cache-6")) == 1


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
        page, cursor, _ = action_log.read_page("page-1", limit=10)
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
            page, cursor, _ = action_log.read_page(
                "page-2", limit=7, before_ts=cursor,
            )
            seen = [r["params"]["i"] for r in page] + seen
            if cursor is None:
                break
        assert seen == list(range(25))
        assert cursor is None

    def test_cursor_null_on_final_page(self):
        self._seed("page-3", 5)
        page, cursor, _ = action_log.read_page("page-3", limit=10)
        assert len(page) == 5
        assert cursor is None  # no more records remain

    def test_empty_log_returns_empty_with_null_cursor(self):
        page, cursor, _ = action_log.read_page("never-written", limit=10)
        assert page == []
        assert cursor is None

    def test_invalid_limit_returns_empty(self):
        page, cursor, _ = action_log.read_page("page-3", limit=0)
        assert page == []
        assert cursor is None

    def test_pagination_skips_tombstoned_records(self):
        self._seed("page-4", 5)
        # Pop the most recent forward — i=4 should disappear from the page.
        action_log.pop_last_forward("page-4")
        page, _, _ = action_log.read_page("page-4", limit=10)
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
            self, mock_conf, api_backend, monkeypatch):
        """Per-type undo (``add_point(undo=True)`` etc.) outside the
        rapid-pair window: the matching forward record is popped and
        an undo record is appended so a follow-up generic undo
        cannot double-revert the same action.

        Time is mocked so the undo lands beyond
        ``RAPID_PAIR_WINDOW_S`` — otherwise the rapid-pair flow
        would collapse both halves into a no-op (covered by
        ``tests/test_rapid_pair_undo.py``).
        """
        import time as _time

        from app.api import game_service as gs

        clock = [1_000_000.0]
        monkeypatch.setattr(gs.time, "time", lambda: clock[0])
        monkeypatch.setattr(_time, "time", lambda: clock[0])

        session = SessionManager.get_or_create("audit-2", mock_conf, api_backend)
        GameService.add_point(session, team=1)
        clock[0] += gs.RAPID_PAIR_WINDOW_S + 0.1
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
