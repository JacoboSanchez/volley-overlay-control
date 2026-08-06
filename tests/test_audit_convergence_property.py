"""Property test: the control client's audit view converges to the server's log.

The push protocol (#446 §5) has three moving parts — the ``GET /audit`` read,
the ``audit_append`` / ``audit_invalidate`` frames on the control socket, and
the per-OID log lock that orders them. Review of #482 found five defects
living in the seams *between* those parts, none of which the per-case unit
tests caught, because each test drove one piece's happy path in isolation.
Fixing one of them (the empty-log fast path) opened another of the same
shape, which is the evidence that a per-case instrument is the wrong tool
here.

This module replaces the per-case instrument with one invariant checked over
randomised interleavings::

    Safety   — whenever the client holds version V, its records are exactly
               what the log looked like at version V.
    Liveness — whenever the client is connected, has heard every frame the
               log emitted since it connected, and its last read succeeded,
               it holds the log's current version and the log's records.

Safety is the property that makes a stale view harmless: a client that has
fallen behind is fine, a client that *believes* it is current while showing
something the server never had is not. Liveness is what forbids "fell behind
and never noticed".

**The log is real.** Every mutation goes through ``app.api.action_log`` and
every read through ``action_log.read_page`` — including the lock, the
tombstone filter, the parsed-record cache and real rotation. The client is a
port of ``frontend/src/hooks/useAuditFeed.ts`` (see :class:`ClientFeed`;
``frontend/src/test/useAuditFeed.property.test.tsx`` runs the same walk
against the real hook). Only the wire between them is faked, which is what
lets the walk drop, duplicate, reorder and disconnect at will.

Each of the five reviewed defects is pinned as a :class:`Defect` the harness
can inject, and each has a test asserting the property *fails* under it —
so a future regression of that shape is caught by this one property rather
than by remembering to write the matching one-off test.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from unittest.mock import patch

import pytest

from app.api import action_log

pytestmark = pytest.mark.usefixtures("clean_sessions")

# Mirrors ``AUDIT_FEED_LIMIT`` in frontend/src/hooks/useAuditFeed.ts — the
# client holds one bounded window, so "equal to the server" means equal to
# the server's newest ``FEED_LIMIT`` records.
FEED_LIMIT = 60

# Seeds for the main property. Fixed rather than random so a failure is
# reproducible from the test name alone, and wide enough that the rarer
# interleavings (a read fault landing between a board switch and its first
# frame, say) are actually visited.
SEEDS = tuple(range(120))

# Walk length. Long enough for the log to be cleared, re-grown, rotated and
# switched away from several times within one walk.
STEPS = 50


class Defect(str, Enum):
    """The five defects review of #482 found in this seam.

    Injected by the harness so the property can be shown to catch each one.
    The names are the bug, not the fix.
    """

    #: (1) ``read_page`` sampled the version outside the lock that built the
    #: page, so a concurrent append landed between them: the page carried a
    #: record the version did not account for, and the client applied that
    #: record's ``audit_append`` on top of it — twice in the list.
    PAGE_VERSION_OUTSIDE_LOCK = "page_version_outside_lock"

    #: (2) No resync on the *first* socket open. The mount read and the
    #: handshake overlap, and a mutation in that window is broadcast to a
    #: client that is not listening yet.
    NO_RESYNC_ON_OPEN = "no_resync_on_open"

    #: (3) A closed socket still delivered queued frames, and the audit
    #: callbacks carry no board identity — so another board's action landed
    #: in this board's history. Per-board counters all start at 0, which is
    #: what makes the version line up often enough to matter.
    FRAMES_FROM_CLOSED_SOCKET = "frames_from_closed_socket"

    #: (4) The empty-log fast path tested for the file outside the lock —
    #: the same defect as (1) in smaller print, introduced while fixing it.
    EMPTY_FAST_PATH_OUTSIDE_LOCK = "empty_fast_path_outside_lock"

    #: (5) A failed read answered with an empty page at the *live* version.
    #: The counter accounts for every record the caller did not get, so the
    #: client builds on nothing and never sees a gap. Unlike the others this
    #: one never self-heals.
    FAILED_READ_KEEPS_LIVE_VERSION = "failed_read_keeps_live_version"


# ---------------------------------------------------------------------------
# The wire — the only faked component
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Frame:
    """One ``audit_append`` / ``audit_invalidate`` message in flight."""

    oid: str
    event: str
    version: int
    record: dict | None


class Wire:
    """The control socket between ``action_log``'s observer and the client.

    Faked so the walk can inject the transport faults a real socket produces
    on its own schedule: a dropped frame, a duplicated one, a reordered
    pair, and a disconnect at an arbitrary point. Nothing buffers frames
    across a closed socket — a client that was not listening never hears
    them, which is precisely why the reconnect has to re-read.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.queue: list[Frame] = []
        self.connected = False
        self.board: str | None = None
        # Set when a frame is lost while connected. The protocol only
        # promises to heal that on the *next* frame or read, so liveness is
        # not asserted while it is set.
        self.pending_loss = False
        # Defect (3): deliver frames regardless of which board they belong to.
        self.deliver_foreign = False

    def emit(self, frame: Frame) -> None:
        """Observer callback — may run on any thread, like the real fan-out."""
        with self._lock:
            self.queue.append(frame)

    def connect(self, oid: str) -> None:
        with self._lock:
            if not self.deliver_foreign:
                self.queue.clear()
            self.connected = True
            self.board = oid
            # A reconnect is a recovery point: the client re-reads on open,
            # so whatever was missed while the socket was down is healed.
            self.pending_loss = False

    def disconnect(self) -> None:
        with self._lock:
            self.connected = False
            if not self.deliver_foreign:
                self.queue.clear()

    def take(self) -> list[Frame]:
        with self._lock:
            frames, self.queue = self.queue, []
            return frames

    def drop_one(self) -> bool:
        """Lose the oldest queued frame, as a flaky socket would."""
        with self._lock:
            if not self.queue:
                return False
            self.queue.pop(0)
            if self.connected:
                self.pending_loss = True
            return True

    def duplicate_one(self) -> bool:
        with self._lock:
            if not self.queue:
                return False
            self.queue.insert(0, self.queue[0])
            return True

    def reorder_pair(self) -> bool:
        with self._lock:
            if len(self.queue) < 2:
                return False
            self.queue[0], self.queue[1] = self.queue[1], self.queue[0]
            return True


# ---------------------------------------------------------------------------
# The client — a port of useAuditFeed
# ---------------------------------------------------------------------------


class ClientFeed:
    """Port of ``frontend/src/hooks/useAuditFeed.ts``.

    Same three rules, same order:

    * a pushed record is applied only when its version is exactly one ahead
      of the version held; anything else re-reads,
    * an invalidate and a reconnect always re-read,
    * a failed read clears the records and the held version, because a
      stale window that silently stops tracking play is worse than an
      empty one.

    ``refresh`` drops the held version *before* re-reading so a push racing
    the in-flight read cannot be mistaken for contiguous with the records it
    is about to replace. The React hook's other asynchrony (an abandoned
    read resolving after a later one) is not modelled here — that is what
    the vitest property test drives, against the real hook.
    """

    def __init__(self, read_page: Callable[[str, int], tuple]) -> None:
        self._read_page = read_page
        self.oid: str | None = None
        self.records: list[dict] = []
        self.version: int | None = None
        self.error: str | None = None
        self.last_read_ok = False
        self._pending_read = False

    def open_board(self, oid: str) -> None:
        """Mount on a new board: the previous board's rows leave with it."""
        self.oid = oid
        self.records = []
        self.version = None
        self.error = None
        self.last_read_ok = False
        self._pending_read = True

    def refresh(self) -> None:
        self.version = None
        self._pending_read = True

    def on_append(self, version: int, record: dict) -> None:
        held = self.version
        if held is None or version != held + 1:
            self.refresh()
            return
        self.version = version
        records = [*self.records, record]
        self.records = records[-FEED_LIMIT:] if len(records) > FEED_LIMIT else records

    def on_invalidate(self, _version: int) -> None:
        self.refresh()

    def on_resync(self) -> None:
        self.refresh()

    def settle(self) -> None:
        """Resolve the pending read, if any. One read is enough: nothing
        mutates while it runs except a deliberately raced writer."""
        while self._pending_read:
            self._pending_read = False
            assert self.oid is not None
            records, _cursor, version = self._read_page(self.oid, FEED_LIMIT)
            if version is None:
                # The route answers a failed read with 503 (see
                # ``app/api/routes/audit.py``); the hook's catch path clears.
                self.records = []
                self.version = None
                self.error = "unreadable"
                self.last_read_ok = False
                continue
            self.records = list(records)
            self.version = version
            self.error = None
            self.last_read_ok = True


# ---------------------------------------------------------------------------
# Read variants — the real one, and the defective ones being pinned
# ---------------------------------------------------------------------------


def _real_read_page(oid: str, limit: int) -> tuple:
    return action_log.read_page(oid, limit=limit)


def _yield_to_writer() -> None:
    """Widen the window a defect leaves open so a racing writer hits it.

    Only the defective copies call this. The real read has no window to
    widen: the version and the page come out of one lock hold.
    """
    time.sleep(0.005)


def _read_page_version_outside_lock(oid: str, limit: int) -> tuple:
    """Defect (1): sample the counter, *then* build the page."""
    path = action_log._path(oid)
    if path is None:
        return [], None, action_log.version(oid)
    log_version = action_log.version(oid)
    _yield_to_writer()
    try:
        with action_log._lock_for(oid):
            records = (
                action_log._read_visible_locked(path, oid)
                if limit > 0 and action_log._has_any_log_file(path)
                else []
            )
    except Exception:
        return [], None, None
    return records[-limit:] if limit > 0 else [], None, log_version


def _read_page_empty_fast_path_outside_lock(oid: str, limit: int) -> tuple:
    """Defect (4): test for "no file yet" before taking the lock."""
    path = action_log._path(oid)
    if path is None:
        return [], None, action_log.version(oid)
    if not action_log._has_any_log_file(path):
        _yield_to_writer()
        return [], None, action_log.version(oid)
    return _real_read_page(oid, limit)


def _read_page_failed_read_keeps_live_version(oid: str, limit: int) -> tuple:
    """Defect (5): answer a failed read with an empty page at the live version."""
    records, cursor, log_version = _real_read_page(oid, limit)
    if log_version is None:
        return [], None, action_log.version(oid)
    return records, cursor, log_version


_READ_VARIANTS: dict[Defect | None, Callable[[str, int], tuple]] = {
    None: _real_read_page,
    Defect.PAGE_VERSION_OUTSIDE_LOCK: _read_page_version_outside_lock,
    Defect.EMPTY_FAST_PATH_OUTSIDE_LOCK: _read_page_empty_fast_path_outside_lock,
    Defect.FAILED_READ_KEEPS_LIVE_VERSION: _read_page_failed_read_keeps_live_version,
}


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------

# Weighted by how often each happens in a live match: points dominate,
# undos are common, everything else is occasional. Listed rather than
# weighted-tupled so a failing seed's op trace reads as plain names.
OPS: tuple[str, ...] = (
    "append", "append", "append", "append", "append", "append",
    "undo_pop", "undo_pop",
    "rapid_pair",
    "race_read", "race_read",
    "drop_frame", "duplicate_frame", "reorder_frames",
    "disconnect", "reconnect",
    "switch_board", "switch_board_mid_flight",
    "read_fault",
    "rotate",
    "clear",
    "delete",
)


@dataclass
class Violation:
    step: int
    op: str
    kind: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover - only rendered on failure
        return f"step {self.step} after {self.op!r}: {self.kind} — {self.detail}"


@dataclass
class Walk:
    """One randomised interleaving of log mutations, faults and reads."""

    seed: int
    defect: Defect | None = None
    steps: int = STEPS
    violations: list[Violation] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)

    def run(self) -> list[Violation]:
        rng = random.Random(self.seed)
        # Fresh OIDs per walk: ``action_log``'s per-OID version counter,
        # timestamp tracker and record cache are module state that outlives
        # a single walk. Both boards still start at version 0, which is the
        # overlap that made defect (3) ordinary rather than exotic.
        self.boards = (f"walk{self.seed}-a", f"walk{self.seed}-b")
        # version -> what a client reading at that version should be showing.
        # Filled by ``_snapshot`` before every check, so every version the
        # client can legitimately hold has an entry.
        self.snapshots: dict[str, dict[int, tuple]] = {b: {} for b in self.boards}
        self.wire = Wire()
        self.wire.deliver_foreign = self.defect is Defect.FRAMES_FROM_CLOSED_SOCKET
        self.client = ClientFeed(_READ_VARIANTS.get(self.defect, _real_read_page))
        self.next_read_fails = False

        action_log.set_observer(
            lambda oid, event, version, record: self.wire.emit(
                Frame(oid, event, version, record),
            ),
        )
        try:
            self._board_open(self.boards[0])
            self._settle_and_check(0, "start")
            for step in range(1, self.steps + 1):
                op = rng.choice(OPS)
                self.trace.append(op)
                getattr(self, f"_op_{op}")(rng)
                self._settle_and_check(step, op)
            self._final_convergence_check()
        finally:
            action_log.set_observer(None)
            for board in self.boards:
                action_log.delete(board)
        return self.violations

    # -- server-side operations ------------------------------------------

    def _oid(self) -> str:
        assert self.client.oid is not None
        return self.client.oid

    def _append(self, oid: str, rng: random.Random | None = None) -> dict | None:
        team = 1 if rng is None else rng.choice((1, 2))
        return action_log.append(
            oid, "add_point", {"team": team, "undo": False}, {"n": team},
        )

    def _op_append(self, rng: random.Random) -> None:
        self._append(self._oid(), rng)

    def _op_undo_pop(self, _rng: random.Random) -> None:
        action_log.pop_last_forward(self._oid(), action_log.UNDOABLE_ACTIONS)

    def _op_rapid_pair(self, rng: random.Random) -> None:
        """Undo-then-revert inside the 5 s window: tombstone, then restore."""
        oid = self._oid()
        visible = action_log.read_all(oid)
        if not visible:
            return
        ref_ts = rng.choice(visible).get("ts")
        if ref_ts is None:
            return
        action_log.tombstone_ts(oid, ref_ts)
        if rng.random() < 0.7:
            action_log.restore_popped(oid, ref_ts)

    def _op_clear(self, _rng: random.Random) -> None:
        action_log.clear(self._oid())

    def _op_delete(self, _rng: random.Random) -> None:
        action_log.delete(self._oid())

    def _op_rotate(self, rng: random.Random) -> None:
        """Force a real rotation on the next append.

        Rotation can discard the oldest slot, so the log downgrades the
        append to an invalidate — a client whose window reaches into the
        dropped file cannot simply extend it.
        """
        with patch.object(action_log, "AUDIT_LOG_MAX_BYTES", 1):
            self._append(self._oid(), rng)

    # -- transport / client-side operations ------------------------------

    def _board_open(self, oid: str) -> None:
        self.client.open_board(oid)
        self.wire.connect(oid)
        if self.defect is not Defect.NO_RESYNC_ON_OPEN:
            self.client.on_resync()

    def _op_switch_board(self, _rng: random.Random) -> None:
        other = self.boards[1] if self.client.oid == self.boards[0] else self.boards[0]
        self._board_open(other)

    def _op_switch_board_mid_flight(self, rng: random.Random) -> None:
        """Switch boards with a frame for the old board still in flight.

        ``close()`` starts a handshake; it does not drop frames already
        queued for delivery. So the old socket can fire *after* the new
        board's read has landed — and the audit callbacks carry no board
        identity, so with per-board counters that all start at 0 the stale
        frame lines up as contiguous often enough to matter. The fix
        detaches the handlers before closing; here that shows up as the
        frame being addressed to a board the client is no longer on.
        """
        self._append(self._oid(), rng)
        in_flight = self.wire.take()
        self._op_switch_board(rng)
        self._deliver()
        self._client_settle()
        for frame in in_flight:
            self._dispatch(frame)

    def _op_disconnect(self, _rng: random.Random) -> None:
        self.wire.disconnect()

    def _op_reconnect(self, _rng: random.Random) -> None:
        if self.wire.connected:
            self.wire.disconnect()
        self.wire.connect(self._oid())
        if self.defect is not Defect.NO_RESYNC_ON_OPEN:
            self.client.on_resync()

    def _op_drop_frame(self, _rng: random.Random) -> None:
        self.wire.drop_one()

    def _op_duplicate_frame(self, _rng: random.Random) -> None:
        self.wire.duplicate_one()

    def _op_reorder_frames(self, _rng: random.Random) -> None:
        self.wire.reorder_pair()

    def _op_read_fault(self, _rng: random.Random) -> None:
        """Make the client's next ``GET /audit`` fail transiently."""
        self.next_read_fails = True
        self.client.refresh()

    def _op_race_read(self, rng: random.Random) -> None:
        """A writer landing while the client is re-reading.

        The real ``read_page`` samples the version and builds the page
        under one lock hold, so this append is ordered entirely before or
        entirely after the pair — never between them.
        """
        self.client.refresh()
        oid = self._oid()
        writer = threading.Thread(target=self._append, args=(oid, rng))
        writer.start()
        try:
            self._client_settle()
        finally:
            writer.join()

    # -- settling and checking -------------------------------------------

    def _client_settle(self) -> None:
        if self.next_read_fails:
            self.next_read_fails = False
            with patch.object(
                action_log, "_read_visible_locked", side_effect=OSError("disk gone"),
            ):
                self.client.settle()
            return
        self.client.settle()

    def _snapshot(self) -> None:
        """Record what each board's log looks like at its current version."""
        for board in self.boards:
            self.snapshots[board][action_log.version(board)] = tuple(
                action_log.read_all(board)[-FEED_LIMIT:],
            )

    def _dispatch(self, frame: Frame) -> None:
        if not self.wire.connected:
            return
        if frame.oid != self.client.oid and not self.wire.deliver_foreign:
            return
        if frame.event == action_log.EVENT_APPEND and frame.record is not None:
            self.client.on_append(frame.version, frame.record)
        else:
            self.client.on_invalidate(frame.version)

    def _deliver(self) -> None:
        for frame in self.wire.take():
            self._dispatch(frame)

    def _settle_and_check(self, step: int, op: str) -> None:
        self._snapshot()
        self._deliver()
        self._client_settle()
        if self.client.last_read_ok:
            self.wire.pending_loss = False
        self._check(step, op)

    def _check(self, step: int, op: str) -> None:
        client = self.client
        oid = self._oid()
        if client.version is not None:
            expected = self.snapshots[oid].get(client.version)
            if expected is not None and tuple(client.records) != expected:
                self.violations.append(Violation(
                    step, op, "safety",
                    f"holds version {client.version} with "
                    f"{len(client.records)} records, but the log at that "
                    f"version had {len(expected)}",
                ))
        caught_up = (
            self.wire.connected
            and not self.wire.queue
            and not self.wire.pending_loss
            and client.last_read_ok
        )
        if not caught_up:
            return
        live_version = action_log.version(oid)
        if client.version != live_version:
            self.violations.append(Violation(
                step, op, "liveness",
                f"caught up but holds version {client.version}, log is at "
                f"{live_version}",
            ))
        live_records = tuple(action_log.read_all(oid)[-FEED_LIMIT:])
        if tuple(client.records) != live_records:
            self.violations.append(Violation(
                step, op, "liveness",
                f"caught up but shows {len(client.records)} records, "
                f"GET /audit returns {len(live_records)}",
            ))

    def _final_convergence_check(self) -> None:
        """Heal every fault, reconnect, and require the client to be current.

        This is the "eventually" half. A client left empty by a failed read
        holds no version, so the per-step check cannot judge it — but it
        must not stay that way once the fault clears and it re-reads.
        """
        self.next_read_fails = False
        self.wire.deliver_foreign = False
        self._board_open(self._oid())
        self._deliver()
        self._client_settle()
        oid = self._oid()
        expected = tuple(action_log.read_all(oid)[-FEED_LIMIT:])
        if tuple(self.client.records) != expected:
            self.violations.append(Violation(
                self.steps, "final", "convergence",
                f"after a clean reconnect the client shows "
                f"{len(self.client.records)} records, GET /audit returns "
                f"{len(expected)}",
            ))
        if self.client.version != action_log.version(oid):
            self.violations.append(Violation(
                self.steps, "final", "convergence",
                f"after a clean reconnect the client holds version "
                f"{self.client.version}, log is at {action_log.version(oid)}",
            ))


def _run(seed: int, defect: Defect | None = None, steps: int = STEPS) -> Walk:
    walk = Walk(seed=seed, defect=defect, steps=steps)
    walk.run()
    return walk


# ---------------------------------------------------------------------------
# The property
# ---------------------------------------------------------------------------


class TestAuditConvergenceProperty:
    @pytest.mark.parametrize("seed", SEEDS)
    def test_client_converges_to_the_log(self, seed):
        walk = _run(seed)
        assert not walk.violations, (
            f"seed {seed} violated the invariant:\n  "
            + "\n  ".join(str(v) for v in walk.violations)
            + f"\n  ops: {walk.trace}"
        )

    def test_the_walk_actually_exercises_every_operation(self):
        """A property that never reaches the interesting states proves nothing.

        Cheap insurance against a future edit to ``OPS`` (or to an op that
        silently becomes a no-op) quietly reducing this file to a very slow
        way of asserting that appends work.
        """
        seen: set[str] = set()
        for seed in SEEDS[:20]:
            seen.update(_run(seed).trace)
        assert seen == set(OPS)

    def test_the_log_is_the_real_one(self):
        """Guard against the harness drifting into a mock of the thing.

        The walk is only worth its runtime if the reads and mutations it
        drives are the shipped implementation.
        """
        assert _READ_VARIANTS[None] is _real_read_page
        walk = Walk(seed=0)
        with patch.object(
            action_log, "read_page", wraps=action_log.read_page,
        ) as spy_read, patch.object(
            action_log, "append", wraps=action_log.append,
        ) as spy_append:
            walk.run()
        assert spy_read.called
        assert spy_append.called


class TestPropertyCatchesTheReviewedDefects:
    """Each reviewed defect, re-injected, must break the property.

    These are the regression seeds asked for in #488: they pin the five
    findings of #482 to the one invariant, so the next defect of the same
    shape is caught by the property instead of by whoever remembers to
    write its one-off test.
    """

    @staticmethod
    def _first_violating_seed(defect: Defect) -> Walk | None:
        for seed in SEEDS:
            walk = _run(seed, defect=defect)
            if walk.violations:
                return walk
        return None

    @pytest.mark.parametrize("defect", list(Defect))
    def test_defect_is_caught(self, defect):
        walk = self._first_violating_seed(defect)
        assert walk is not None, (
            f"the property did not catch {defect.value} in {len(SEEDS)} walks "
            f"— it is no longer an instrument for this class of bug"
        )

    def test_a_duplicated_or_reordered_frame_is_not_a_defect(self):
        """The counter-check: the property must not fire on healthy faults.

        Duplication and reordering are resolved by the version check (one
        extra read each). A property that flagged them would be measuring
        the wire, not the protocol, and its failures would carry no signal.
        """
        healthy = {"duplicate_frame", "reorder_frames"}
        seen: set[str] = set()
        for seed in SEEDS[:20]:
            walk = _run(seed)
            assert not walk.violations, f"seed {seed}: {walk.violations[0]}"
            seen.update(healthy & set(walk.trace))
        assert seen == healthy


class TestConcurrentWriterConvergence:
    """The same invariant with a real writer thread, not a scripted race.

    ``TestPageVersionAtomicity`` in ``test_audit_broadcast.py`` hammers
    ``read_page`` against a writer and asserts the page and version agree.
    This generalises that to the whole loop: the client applies what the
    reads and frames tell it, and must still land exactly on the log.
    """

    def test_client_lands_on_the_log_after_a_concurrent_writer(self):
        oid = "oid-concurrent"
        wire = Wire()
        action_log.set_observer(
            lambda o, e, v, r: wire.emit(Frame(o, e, v, r)),
        )
        client = ClientFeed(_real_read_page)
        try:
            client.open_board(oid)
            wire.connect(oid)
            client.on_resync()
            client.settle()

            stop = threading.Event()

            def _writer():
                for i in range(120):
                    if stop.is_set():
                        return
                    action_log.append(
                        oid, "add_point", {"team": 1, "undo": False}, {"n": i},
                    )

            writer = threading.Thread(target=_writer)
            writer.start()
            try:
                for _ in range(200):
                    for frame in wire.take():
                        if frame.event == action_log.EVENT_APPEND and frame.record:
                            client.on_append(frame.version, frame.record)
                        else:
                            client.on_invalidate(frame.version)
                    client.settle()
                    # Safety mid-flight: the client may be behind, but every
                    # record it holds must be a prefix-consistent tail of the
                    # log — never a record the log does not have, and never
                    # one twice.
                    held = [r["ts"] for r in client.records]
                    assert held == sorted(set(held))
            finally:
                stop.set()
                writer.join()

            # Quiescent: drain, re-read, and require exact equality.
            for frame in wire.take():
                if frame.event == action_log.EVENT_APPEND and frame.record:
                    client.on_append(frame.version, frame.record)
                else:
                    client.on_invalidate(frame.version)
            client.on_resync()
            client.settle()
            assert client.records == action_log.read_all(oid)[-FEED_LIMIT:]
            assert client.version == action_log.version(oid)
        finally:
            action_log.set_observer(None)
            action_log.delete(oid)
