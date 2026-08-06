/**
 * Property test: the audit feed converges to the server's log.
 *
 * The client half of ``tests/test_audit_convergence_property.py``. That one
 * drives the real ``action_log`` against a port of this hook; this one
 * drives the real hook against a model of the log. Between them, both sides
 * of the seam #482 found five defects in are exercised by the same
 * invariant instead of by five one-off tests.
 *
 * What is real here: ``useAuditFeed`` itself — its version arithmetic, its
 * refresh-on-anything-else rule, the abort/replace behaviour of the read
 * effect, and the board-switch reset. Faked: ``GET /audit`` (served from the
 * model below) and the socket (frames are handed to the callbacks directly,
 * which is what lets the walk drop, duplicate, reorder and disconnect).
 *
 * The invariant, in the terms this side can observe:
 *
 *   1. no phantom rows — every record shown exists in the current board's
 *      log (this is what a frame from a closed socket violates),
 *   2. no duplicates and no reordering — timestamps strictly increase,
 *   3. once caught up, the rows equal ``GET /audit`` exactly, and
 *   4. once caught up, the *version* held is the log's: probed by pushing
 *      one contiguous append and requiring it to land without a re-read.
 *
 * (4) is the observable form of "the version it holds is the log's
 * version" — the hook does not expose the counter, but a client holding the
 * wrong one cannot apply the next push.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { AUDIT_FEED_LIMIT, useAuditFeed } from '../hooks/useAuditFeed';
import * as apiClient from '../api/board';
import type { AuditRecord } from '../api/board';

// ---------------------------------------------------------------------------
// A model of app/api/action_log.py
// ---------------------------------------------------------------------------

const POP = '_pop';
const RESTORE = '_restore';

interface Frame {
  oid: string;
  event: 'append' | 'invalidate';
  version: number;
  record: AuditRecord | null;
}

/**
 * The observable contract of the per-OID log: append-only records, pops and
 * restores as tombstones, a monotonic version bumped by every mutation, and
 * one frame emitted per mutation — ``append`` only for a plain append, and
 * ``invalidate`` for everything that changes how records already delivered
 * should be read (tombstone, restore, clear, delete, rotation).
 *
 * Deliberately a model, not a port: the real module is what the pytest half
 * drives. What has to match is the *protocol*, and that is small enough to
 * state here in full.
 */
class ServerLog {
  raw: AuditRecord[] = [];
  version = 0;
  /** Every ts this board has ever logged. A stale client may still be
   *  showing a row a later clear/undo/rotation removed — that is ordinary
   *  staleness. A row this board never logged at all is a phantom. */
  everLogged = new Set<number>();

  constructor(
    readonly oid: string,
    private readonly emit: (frame: Frame) => void,
    /** Shared across boards: real timestamps are wall-clock, so a record
     *  from another board can never masquerade as one of ours. */
    private readonly nextTs: () => number,
  ) {}

  private bump(event: 'append' | 'invalidate', record: AuditRecord | null) {
    this.version += 1;
    this.emit({ oid: this.oid, event, version: this.version, record });
  }

  append(team: number): AuditRecord {
    const record = {
      ts: this.nextTs(),
      action: 'add_point',
      params: { team, undo: false },
    } as unknown as AuditRecord;
    this.raw.push(record);
    this.everLogged.add(record.ts);
    this.bump('append', record);
    return record;
  }

  /** Hide the newest visible forward record, as an undo does. */
  popLastForward(): void {
    const visible = this.visible();
    const target = visible[visible.length - 1];
    if (!target) return;
    this.raw.push({ ts: this.nextTs(), action: POP, ref_ts: target.ts } as unknown as AuditRecord);
    this.bump('invalidate', null);
  }

  tombstone(ts: number): void {
    this.raw.push({ ts: this.nextTs(), action: POP, ref_ts: ts } as unknown as AuditRecord);
    this.bump('invalidate', null);
  }

  restore(ts: number): void {
    this.raw.push({ ts: this.nextTs(), action: RESTORE, ref_ts: ts } as unknown as AuditRecord);
    this.bump('invalidate', null);
  }

  clear(): void {
    this.raw = [];
    this.bump('invalidate', null);
  }

  /** Rotation dropped the oldest slot: history is gone, so this is never
   *  an append even though the mutation that triggered it was one. */
  rotate(team: number): void {
    const record = {
      ts: this.nextTs(),
      action: 'add_point',
      params: { team, undo: false },
    } as unknown as AuditRecord;
    this.raw = [...this.raw.slice(Math.ceil(this.raw.length / 2)), record];
    this.everLogged.add(record.ts);
    this.bump('invalidate', null);
  }

  /** Tombstone-filtered view — what ``read_all`` returns. */
  visible(): AuditRecord[] {
    const hidden = new Set<number>();
    for (const r of this.raw) {
      const action = (r as unknown as { action: string }).action;
      const ref = (r as unknown as { ref_ts?: number }).ref_ts;
      if (action === POP && ref !== undefined) hidden.add(ref);
      else if (action === RESTORE && ref !== undefined) hidden.delete(ref);
    }
    return this.raw.filter((r) => {
      const action = (r as unknown as { action: string }).action;
      return action !== POP && action !== RESTORE && !hidden.has(r.ts);
    });
  }

  /** What ``GET /audit?limit=N`` answers: the newest N records, and the
   *  version they were read at — sampled together, never separately. */
  page(limit: number): { records: AuditRecord[]; version: number } {
    return { records: this.visible().slice(-limit), version: this.version };
  }
}

// ---------------------------------------------------------------------------
// Defects
// ---------------------------------------------------------------------------

/**
 * The reviewed defects, in the form this side of the seam sees them. The
 * three read defects (#482 1, 4 and 5) all reach the client as the same
 * thing — a page and a version that disagree — so they are pinned here as
 * one, and separately as three in the pytest half where the read is real.
 */
type Defect = 'no_resync_on_open' | 'frames_from_closed_socket' | 'inconsistent_page_and_version';

const DEFECTS: Defect[] = [
  'no_resync_on_open',
  'frames_from_closed_socket',
  'inconsistent_page_and_version',
];

/** The operation that models each defect — see the assertion that uses it. */
const EXPOSED_BY: Record<Defect, string> = {
  no_resync_on_open: 'board_open_load_race',
  frames_from_closed_socket: 'switch_board_mid_flight',
  // Any read at all: a page and a version that disagree is not tied to a
  // particular interleaving.
  inconsistent_page_and_version: 'step',
};

// ---------------------------------------------------------------------------
// The walk
// ---------------------------------------------------------------------------

/** Deterministic PRNG — a failing seed reproduces from the test name. */
function mulberry32(seed: number): () => number {
  let a = seed + 0x6d2b79f5;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const OPS = [
  'append',
  'append',
  'append',
  'append',
  'append',
  'undo_pop',
  'undo_pop',
  'rapid_pair',
  'drop_frame',
  'duplicate_frame',
  'reorder_frames',
  'disconnect',
  'reconnect',
  'switch_board',
  'switch_board_mid_flight',
  'board_open_load_race',
  'read_fault',
  'rotate',
  'clear',
] as const;

type Op = (typeof OPS)[number];

const SEEDS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19];
const STEPS = 24;

interface WalkResult {
  violations: string[];
  trace: Op[];
}

async function runWalk(seed: number, defect: Defect | null = null): Promise<WalkResult> {
  const rand = mulberry32(seed);
  const violations: string[] = [];
  const trace: Op[] = [];

  const boards = ['prop-a', 'prop-b'];
  let queue: Frame[] = [];
  let tsSeq = 0;
  const nextTs = () => (tsSeq += 1);
  const logs = new Map<string, ServerLog>(
    boards.map((oid) => [oid, new ServerLog(oid, (f) => queue.push(f), nextTs)]),
  );

  let connected = false;
  let board = boards[0]!;
  // A frame lost while connected is only healed by the next frame or the
  // next read, so liveness is not asserted while this is set.
  let pendingLoss = false;
  let readFails = false;
  let lastReadOk = false;
  let reads = 0;
  // Holds the next read's *response* while its page stays sampled at the
  // moment of the call. See the load-race operation below.
  let deferNextRead = false;
  let releaseRead: (() => void) | null = null;

  const log = () => logs.get(board)!;

  const getAudit = vi
    .spyOn(apiClient, 'getAudit')
    .mockImplementation(async (oid: string, limit: number = AUDIT_FEED_LIMIT) => {
      reads += 1;
      if (readFails) {
        readFails = false;
        lastReadOk = false;
        // The route answers an unreadable log with 503 rather than an
        // empty page at the live version. See app/api/routes/audit.py.
        throw new Error('Audit log is temporarily unreadable.');
      }
      const source = logs.get(oid)!;
      // Sampled now, like the server's one lock hold — the response can
      // land much later, which is what makes a load-time gap possible.
      const { records, version } = source.page(limit);
      if (deferNextRead) {
        deferNextRead = false;
        await new Promise<void>((resolve) => {
          releaseRead = resolve;
        });
      }
      lastReadOk = true;
      pendingLoss = false;
      if (defect === 'inconsistent_page_and_version') {
        // The shape all three read defects present to the client: rows and
        // counter that do not describe the same moment.
        return { oid, count: 0, records: [], version } as apiClient.AuditResponse;
      }
      return { oid, count: records.length, version, records } as apiClient.AuditResponse;
    });

  const { result, rerender, unmount } = renderHook(
    ({ oid }: { oid: string }) => useAuditFeed(oid, true),
    { initialProps: { oid: board } },
  );

  /** Let every pending read resolve and every effect it schedules run. */
  const settle = async () => {
    let seen = -1;
    for (let i = 0; i < 25 && seen !== reads; i += 1) {
      seen = reads;
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });
    }
  };

  const dispatch = (frame: Frame) => {
    if (!connected) return;
    // The fix for (3) detaches the socket's handlers before closing, so a
    // frame addressed to a board the client has left never reaches the
    // callbacks. Under the defect it does.
    if (frame.oid !== board && defect !== 'frames_from_closed_socket') return;
    act(() => {
      if (frame.event === 'append' && frame.record) {
        result.current.onAppend(frame.version, frame.record);
      } else {
        result.current.onInvalidate(frame.version);
      }
    });
  };

  const deliver = () => {
    const frames = queue;
    queue = [];
    frames.forEach(dispatch);
  };

  const openBoard = async (oid: string) => {
    board = oid;
    rerender({ oid });
    connected = true;
    pendingLoss = false;
    if (defect !== 'no_resync_on_open') act(() => result.current.onResync());
    await settle();
  };

  /**
   * Open a board with a mutation landing in the load-time gap.
   *
   * The mount read and the socket handshake overlap, so this orders them
   * the way that hurts: the read samples the log, *then* another client
   * scores, and only *then* does this socket finish connecting. The frame
   * for that record is broadcast to a client that is not listening yet,
   * and the handshake replays the state snapshot, never missed audit rows
   * — so nothing but the resync on open can close it.
   *
   * Without it the board sits on a log one record short while believing it
   * is current, until the next mutation exposes the gap.
   */
  const openBoardWithLoadRace = async (oid: string) => {
    board = oid;
    connected = false;
    deferNextRead = true;
    rerender({ oid });
    // The read must be in flight with its page already sampled, or the
    // mutation below would simply be included and there would be no gap.
    expect(deferNextRead).toBe(false);
    logs.get(oid)!.append(1);
    // Not connected yet: nothing buffers frames for a socket that does not
    // exist, so this one reaches nobody.
    queue = [];
    await act(async () => {
      releaseRead?.();
      releaseRead = null;
    });
    await settle();
    connected = true;
    pendingLoss = false;
    if (defect !== 'no_resync_on_open') act(() => result.current.onResync());
    await settle();
  };

  const check = (step: number, op: string) => {
    const rows = result.current.records;
    const visible = log().visible();
    const known = log().everLogged;
    for (const row of rows) {
      if (!known.has(row.ts)) {
        violations.push(
          `step ${step} after ${op}: shows ts=${row.ts}, which board ${board} never logged`,
        );
        break;
      }
    }
    for (let i = 1; i < rows.length; i += 1) {
      if (rows[i]!.ts <= rows[i - 1]!.ts) {
        violations.push(`step ${step} after ${op}: rows out of order or duplicated at index ${i}`);
        break;
      }
    }
    const caughtUp = connected && queue.length === 0 && !pendingLoss && lastReadOk;
    if (!caughtUp) return;
    const expected = visible.slice(-AUDIT_FEED_LIMIT);
    if (rows.length !== expected.length || rows.some((r, i) => r.ts !== expected[i]!.ts)) {
      violations.push(
        `step ${step} after ${op}: caught up but shows ${rows.length} rows, ` +
          `GET /audit returns ${expected.length}`,
      );
    }
  };

  const ops: Record<Op, () => void> = {
    append: () => log().append(rand() < 0.5 ? 1 : 2),
    undo_pop: () => log().popLastForward(),
    rapid_pair: () => {
      const visible = log().visible();
      if (!visible.length) return;
      const target = visible[Math.floor(rand() * visible.length)]!;
      log().tombstone(target.ts);
      if (rand() < 0.7) log().restore(target.ts);
    },
    rotate: () => log().rotate(1),
    clear: () => log().clear(),
    drop_frame: () => {
      if (!queue.length) return;
      queue.shift();
      if (connected) pendingLoss = true;
    },
    duplicate_frame: () => {
      if (queue.length) queue.unshift(queue[0]!);
    },
    reorder_frames: () => {
      if (queue.length >= 2) [queue[0], queue[1]] = [queue[1]!, queue[0]!];
    },
    disconnect: () => {
      connected = false;
      queue = [];
    },
    reconnect: () => {
      // Always resyncs, defect or not. #482 (2) was specifically the first
      // open — reconnects already re-read. Suppressing this one too would
      // let the defect be caught here, which says nothing about the
      // load-time gap it is actually about.
      queue = [];
      connected = true;
      pendingLoss = false;
      act(() => result.current.onResync());
    },
    switch_board: () => {},
    switch_board_mid_flight: () => {},
    board_open_load_race: () => {},
    read_fault: () => {
      readFails = true;
      act(() => result.current.refresh());
    },
  };

  try {
    await openBoard(board);
    check(0, 'start');

    for (let step = 1; step <= STEPS; step += 1) {
      const op = OPS[Math.floor(rand() * OPS.length)]!;
      trace.push(op);
      const other = board === boards[0] ? boards[1]! : boards[0]!;
      if (op === 'switch_board') {
        await openBoard(other);
      } else if (op === 'board_open_load_race') {
        await openBoardWithLoadRace(other);
      } else if (op === 'switch_board_mid_flight') {
        // ``close()`` starts a handshake; it does not drop frames already
        // queued. So the old socket can still fire after the new board's
        // read has landed — and with per-board counters that all start at
        // 0, a stale frame lines up as contiguous often enough to matter.
        log().append(1);
        const inFlight = queue;
        queue = [];
        await openBoard(other);
        inFlight.forEach(dispatch);
      } else {
        ops[op]();
      }
      deliver();
      await settle();
      check(step, op);
    }

    // Eventually: clear every fault, reconnect, and require exact equality.
    readFails = false;
    connected = true;
    queue = [];
    act(() => result.current.onResync());
    await settle();
    const expected = log().visible().slice(-AUDIT_FEED_LIMIT);
    const rows = result.current.records;
    if (rows.length !== expected.length || rows.some((r, i) => r.ts !== expected[i]!.ts)) {
      violations.push(
        `after a clean reconnect the client shows ${rows.length} rows, ` +
          `GET /audit returns ${expected.length}`,
      );
    }

    // …and holds the log's *version*, not merely its rows: one contiguous
    // push has to land without a re-read. A client holding a stale counter
    // would refetch instead, and one holding a counter that has run ahead
    // would drop the row.
    const before = reads;
    const pushed = log().append(1);
    deliver();
    await settle();
    if (reads !== before) {
      violations.push('a contiguous push forced a re-read: the held version is not the log’s');
    }
    if (!result.current.records.some((r) => r.ts === pushed.ts)) {
      violations.push('a contiguous push was not applied: the held version is not the log’s');
    }
  } finally {
    unmount();
    getAudit.mockRestore();
  }

  return { violations, trace };
}

describe('useAuditFeed convergence property', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each(SEEDS)('converges to the log for seed %i', async (seed) => {
    const { violations } = await runWalk(seed);
    expect(violations).toEqual([]);
  });

  it('visits every operation the walk can generate', async () => {
    // A property that never reaches the interesting states proves nothing.
    const seen = new Set<Op>();
    for (const seed of SEEDS.slice(0, 8)) {
      const { trace } = await runWalk(seed);
      trace.forEach((op) => seen.add(op));
    }
    expect([...seen].sort()).toEqual([...new Set(OPS)].sort());
  });

  it.each(DEFECTS)('catches the %s defect', async (defect) => {
    let caught: string[] = [];
    for (const seed of SEEDS) {
      const { violations } = await runWalk(seed, defect);
      if (violations.length) {
        caught = violations;
        break;
      }
    }
    // Failing here means the property stopped being an instrument for this
    // class of bug — not that the bug is gone.
    expect(caught.length).toBeGreaterThan(0);
    // …and it has to be caught by the operation that models the race it
    // names. "Caught" alone is not enough: while the first-open injection
    // also suppressed the reconnect resync, it was caught there, and the
    // load-time gap it is actually about went unmodelled.
    expect(caught[0]).toContain(EXPOSED_BY[defect]);
  });
});
