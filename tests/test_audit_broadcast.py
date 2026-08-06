"""Tests for the audit-log → WebSocket bridge.

Covers the ``action_log`` observer contract (what each mutation reports)
and the ``audit_broadcast`` wiring that puts it on the control socket.

The invariant these protect: a client can only *extend* its copy of the log
when the version it holds is exactly one behind the version it is told
about. Everything else — tombstones, restores, clears, rotation, a dropped
message — has to force a re-read, because those change how records already
delivered should be interpreted.
"""
import json
from unittest.mock import patch

import pytest

from app.api import action_log, audit_broadcast

pytestmark = pytest.mark.usefixtures("clean_sessions")


@pytest.fixture
def events():
    """Install a recording observer and remove it afterwards."""
    captured: list[tuple[str, str, int, dict | None]] = []

    def _observer(oid, event, version, record):
        captured.append((oid, event, version, record))

    action_log.set_observer(_observer)
    try:
        yield captured
    finally:
        action_log.set_observer(None)


class TestObserverContract:
    def test_append_reports_append_with_the_written_record(self, events):
        action_log.append("oid-a", "add_point", {"team": 1}, {"score": 1})

        assert len(events) == 1
        oid, event, version, record = events[0]
        assert oid == "oid-a"
        assert event == action_log.EVENT_APPEND
        assert version == action_log.version("oid-a")
        assert record is not None
        assert record["action"] == "add_point"
        assert record["params"] == {"team": 1}
        # The record carries the ts the log assigned, so a client can key
        # off it without a follow-up read.
        assert record["ts"] == action_log.read_all("oid-a")[-1]["ts"]

    def test_versions_are_contiguous_across_appends(self, events):
        for i in range(5):
            action_log.append("oid-a", "add_point", {"team": 1}, {"n": i})

        versions = [v for _, _, v, _ in events]
        assert versions == list(range(versions[0], versions[0] + 5))

    def test_pop_reports_invalidate_not_append(self, events):
        action_log.append("oid-a", "add_point", {"team": 1}, {})
        events.clear()

        popped = action_log.pop_last_forward("oid-a")

        assert popped is not None
        assert len(events) == 1
        _, event, version, record = events[0]
        # A pop hides a record the client may already be showing. Handing
        # it an "append" would leave the cancelled row on screen forever.
        assert event == action_log.EVENT_INVALIDATE
        assert record is None
        assert version == action_log.version("oid-a")

    def test_tombstone_and_restore_report_invalidate(self, events):
        written = action_log.append("oid-a", "add_point", {"team": 1}, {})
        assert written is not None
        events.clear()

        assert action_log.tombstone_ts("oid-a", written["ts"]) is True
        assert action_log.restore_popped("oid-a", written["ts"]) is True

        assert [e for _, e, _, _ in events] == [
            action_log.EVENT_INVALIDATE,
            action_log.EVENT_INVALIDATE,
        ]
        assert all(r is None for _, _, _, r in events)

    def test_clear_reports_invalidate(self, events):
        action_log.append("oid-a", "add_point", {"team": 1}, {})
        events.clear()

        action_log.clear("oid-a")

        assert len(events) == 1
        _, event, version, record = events[0]
        assert event == action_log.EVENT_INVALIDATE
        assert record is None
        assert version == action_log.version("oid-a")

    def test_delete_reports_invalidate(self, events):
        action_log.append("oid-a", "add_point", {"team": 1}, {})
        events.clear()

        assert action_log.delete("oid-a") is True

        assert [e for _, e, _, _ in events] == [action_log.EVENT_INVALIDATE]

    def test_rotation_downgrades_an_append_to_invalidate(self, events):
        # Rotation can discard the oldest slot, so a client whose window
        # reaches into the dropped file cannot simply extend.
        action_log.append("oid-a", "add_point", {"team": 1}, {})
        events.clear()

        with patch("app.api.action_log._rotate_if_needed_locked", return_value=True):
            action_log.append("oid-a", "add_point", {"team": 2}, {})

        assert len(events) == 1
        _, event, _, record = events[0]
        assert event == action_log.EVENT_INVALIDATE
        assert record is None

    def test_reads_do_not_notify(self, events):
        action_log.append("oid-a", "add_point", {"team": 1}, {})
        events.clear()

        action_log.read_all("oid-a")
        action_log.read_recent("oid-a", 10)
        action_log.read_page("oid-a", limit=10)
        action_log.peek_last_forward("oid-a")
        action_log.count_undoable_forwards("oid-a")

        assert events == []

    def test_no_observer_installed_is_a_no_op(self):
        action_log.set_observer(None)
        # Must not raise — the whole feature is optional.
        action_log.append("oid-a", "add_point", {"team": 1}, {})
        assert len(action_log.read_all("oid-a")) == 1

    def test_observer_failure_never_breaks_the_write(self):
        def _boom(*_args):
            raise RuntimeError("observer exploded")

        action_log.set_observer(_boom)
        try:
            written = action_log.append("oid-a", "add_point", {"team": 1}, {})
        finally:
            action_log.set_observer(None)

        # The append itself succeeded and is readable: the live push is an
        # optimisation and can never cost us a durable audit row.
        assert written is not None
        assert len(action_log.read_all("oid-a")) == 1

    def test_notify_runs_outside_the_per_oid_lock(self, events):
        # A slow observer must not hold the write lock — otherwise one
        # stalled WebSocket client would block the next scored point.
        acquired: list[bool] = []

        def _observer(oid, _event, _version, _record):
            lock = action_log._lock_for(oid)
            acquired.append(lock.acquire(blocking=False))
            if acquired[-1]:
                lock.release()

        action_log.set_observer(_observer)
        try:
            action_log.append("oid-a", "add_point", {"team": 1}, {})
            action_log.pop_last_forward("oid-a")
            action_log.clear("oid-a")
        finally:
            action_log.set_observer(None)

        assert acquired == [True, True, True]


class TestPageVersionAtomicity:
    """``read_page`` must hand back a page and a version that agree.

    This is what makes the client's gap check sound. If the version could
    be sampled outside the lock that builds the page, a mutation landing
    in between produces one of two live-client bugs: a page containing a
    record the version does not count (the matching ``audit_append`` then
    looks contiguous and the record is applied twice), or a version that
    counts a record the page is missing (the *next* append looks
    contiguous and the missing record is never fetched).
    """

    def test_version_accounts_for_every_record_in_the_page(self, events):
        for i in range(3):
            action_log.append("oid-a", "add_point", {"team": 1}, {"n": i})

        records, _, page_version = action_log.read_page("oid-a", limit=50)

        assert len(records) == 3
        assert page_version == action_log.version("oid-a")
        # The version each append reported, in order. The page's version
        # must be the one belonging to its newest record — not older
        # (record unaccounted for) and not newer (record missing).
        assert page_version == [v for _, _, v, _ in events][-1]

    def test_page_and_version_move_together_across_a_mutation(self):
        action_log.append("oid-a", "add_point", {"team": 1}, {})
        first_records, _, first_version = action_log.read_page("oid-a", limit=50)

        action_log.append("oid-a", "add_point", {"team": 2}, {})
        second_records, _, second_version = action_log.read_page("oid-a", limit=50)

        assert len(second_records) == len(first_records) + 1
        assert second_version == first_version + 1

    def test_version_is_stable_while_the_log_is_unchanged(self):
        action_log.append("oid-a", "add_point", {"team": 1}, {})

        _, _, first = action_log.read_page("oid-a", limit=50)
        _, _, second = action_log.read_page("oid-a", limit=50)

        # Reading must not itself advance the counter, or every fetch
        # would look to the client like a missed message.
        assert first == second

    def test_empty_and_degenerate_reads_still_report_a_version(self):
        assert action_log.read_page("never-written", limit=10) == ([], None, 0)

        action_log.append("oid-a", "add_point", {"team": 1}, {})
        _, _, zero_limit_version = action_log.read_page("oid-a", limit=0)
        assert zero_limit_version == action_log.version("oid-a")

    def test_empty_log_check_happens_under_the_lock(self):
        # The "no file yet" shortcut has to be inside the same lock as the
        # populated path. Outside it, the first append can land between
        # the existence test and the version sample, and the caller is
        # told "empty, at version 1" — after which it reads the *next*
        # append as contiguous and loses the first record for good.
        held_during_check: list[bool] = []
        real_has_any = action_log._has_any_log_file

        def _spy(path):
            lock = action_log._lock_for("oid-empty")
            acquired = lock.acquire(blocking=False)
            # Failing to acquire means this thread already holds it.
            held_during_check.append(not acquired)
            if acquired:
                lock.release()
            return real_has_any(path)

        with patch.object(action_log, "_has_any_log_file", _spy):
            records, _, log_version = action_log.read_page("oid-empty", limit=10)

        assert records == []
        assert log_version == 0
        assert held_during_check == [True]

    def test_version_sample_is_under_the_lock_for_a_populated_log(self):
        action_log.append("oid-a", "add_point", {"team": 1}, {})
        held_during_read: list[bool] = []
        real_read = action_log._read_visible_locked

        def _spy(path, oid):
            lock = action_log._lock_for(oid)
            acquired = lock.acquire(blocking=False)
            held_during_read.append(not acquired)
            if acquired:
                lock.release()
            return real_read(path, oid)

        with patch.object(action_log, "_read_visible_locked", _spy):
            records, _, log_version = action_log.read_page("oid-a", limit=10)

        assert len(records) == 1
        assert log_version == action_log.version("oid-a")
        assert held_during_read == [True]

    def test_a_concurrent_append_cannot_split_page_from_version(self):
        # Hammer the read against a writer. Every observation must satisfy
        # "this version accounts for exactly these records" — with the
        # per-record versions being contiguous from 1, the invariant is
        # simply len(records) == version.
        import threading

        stop = threading.Event()
        violations: list[tuple[int, int]] = []

        def _writer():
            for i in range(60):
                if stop.is_set():
                    return
                action_log.append("oid-race", "add_point", {"team": 1}, {"n": i})

        writer = threading.Thread(target=_writer)
        writer.start()
        try:
            for _ in range(300):
                records, _, log_version = action_log.read_page("oid-race", limit=1000)
                if len(records) != log_version:
                    violations.append((len(records), log_version))
        finally:
            stop.set()
            writer.join()

        assert violations == []

    def test_a_failed_read_reports_no_version_at_all(self):
        action_log.append("oid-a", "add_point", {"team": 1}, {})
        action_log.append("oid-a", "add_point", {"team": 2}, {})

        with patch.object(
            action_log, "_read_visible_locked", side_effect=OSError("disk gone"),
        ):
            records, cursor, log_version = action_log.read_page("oid-a", limit=10)

        # Not the live counter. That counter accounts for both records the
        # caller just failed to get, so handing it back would tell a
        # following client it is up to date and let it build on nothing.
        assert records == []
        assert cursor is None
        assert log_version is None
        # The log itself is untouched and still readable once the fault
        # clears — best-effort reads must not cost durable data.
        assert len(action_log.read_all("oid-a")) == 2

    def test_version_survives_a_tombstone(self):
        action_log.append("oid-a", "add_point", {"team": 1}, {})
        action_log.append("oid-a", "add_point", {"team": 2}, {})
        action_log.pop_last_forward("oid-a")

        records, _, page_version = action_log.read_page("oid-a", limit=50)

        # The popped record is gone from the page and the version has
        # advanced past it, so a client re-reading after the invalidate
        # cannot resurrect it.
        assert len(records) == 1
        assert page_version == action_log.version("oid-a")


class TestWebSocketBridge:
    def test_install_routes_mutations_to_the_hub(self):
        audit_broadcast.install()
        try:
            with patch("app.api.audit_broadcast.WSHub") as hub:
                written = action_log.append("oid-a", "add_point", {"team": 1}, {})
                action_log.pop_last_forward("oid-a")
        finally:
            audit_broadcast.uninstall()

        assert written is not None
        calls = hub.broadcast_audit_sync.call_args_list
        assert len(calls) == 2
        # skey in, skey out — the hub is keyed the same way the log is, so
        # the fan-out reaches only this user's board.
        assert calls[0].args[0] == "oid-a"
        assert calls[0].args[1] == action_log.EVENT_APPEND
        assert calls[0].args[3]["action"] == "add_point"
        assert calls[1].args[1] == action_log.EVENT_INVALIDATE
        assert calls[1].args[3] is None

    def test_uninstall_stops_the_bridge(self):
        audit_broadcast.install()
        audit_broadcast.uninstall()

        with patch("app.api.audit_broadcast.WSHub") as hub:
            action_log.append("oid-a", "add_point", {"team": 1}, {})

        hub.broadcast_audit_sync.assert_not_called()


class TestHubEnvelope:
    async def test_append_envelope_shape(self):
        from app.api.ws_hub import WSHub

        sent: list[str] = []
        with patch.object(
            WSHub, "_broadcast_text", side_effect=lambda _oid, msg: sent.append(msg),
        ):
            await WSHub.broadcast_audit(
                "oid-a", action_log.EVENT_APPEND, 7, {"action": "add_point"},
            )

        assert json.loads(sent[0]) == {
            "type": "audit_append",
            "data": {"version": 7, "record": {"action": "add_point"}},
        }

    async def test_invalidate_envelope_shape(self):
        from app.api.ws_hub import WSHub

        sent: list[str] = []
        with patch.object(
            WSHub, "_broadcast_text", side_effect=lambda _oid, msg: sent.append(msg),
        ):
            await WSHub.broadcast_audit("oid-a", action_log.EVENT_INVALIDATE, 8)

        assert json.loads(sent[0]) == {
            "type": "audit_invalidate",
            "data": {"version": 8, "record": None},
        }
