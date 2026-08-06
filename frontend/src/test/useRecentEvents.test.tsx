import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { classifyRecords, useRecentEvents } from '../hooks/useRecentEvents';
import type { AuditRecord } from '../api/client';

function rec(
  ts: number,
  action: string,
  params: Record<string, unknown>,
  result?: Record<string, unknown>,
): AuditRecord {
  return { ts, action, params, result } as unknown as AuditRecord;
}

/**
 * The strip is a projection of the audit log, so these drive
 * ``classifyRecords`` directly. It used to fetch its own copy of the log,
 * and the tests correspondingly mocked ``getAudit`` and poked at state to
 * trigger refetches — but the records now arrive from the board's live
 * feed, so the fetching (one per board, then WebSocket pushes) and its
 * failure handling are ``useAuditFeed``'s to prove.
 *
 * Every case below is stated as "given this window of the log, these are
 * the chips", which is what the rules were always really about.
 */
describe('classifyRecords', () => {
  it('classifies add_point forwards into point_add chips and skips undo records', () => {
    // The visible audit contains two forwards and one undo; the strip
    // skips the undo so the operator only sees chips that still
    // contribute to the live score. The undone action lives on in the
    // history drawer and the printable report.
    expect(
      classifyRecords([
        rec(1, 'add_point', { team: 1 }),
        rec(2, 'add_point', { team: 2, undo: true }),
        rec(3, 'add_point', { team: 1 }),
      ]),
    ).toEqual([
      { ts: 1, team: 1, kind: 'point_add' },
      { ts: 3, team: 1, kind: 'point_add' },
    ]);
  });

  it('maps params.point_type onto the point_add event', () => {
    const events = classifyRecords([
      rec(1, 'add_point', { team: 1, point_type: 'ace' }),
      rec(2, 'add_point', { team: 2, point_type: 'opp_error', error_type: 'net_fault' }),
    ]);
    expect(events).toHaveLength(2);
    expect(events[0]).toMatchObject({ team: 1, kind: 'point_add', pointType: 'ace' });
    expect(events[1]).toMatchObject({ team: 2, kind: 'point_add', pointType: 'opp_error' });
  });

  it('emits a forward timeout chip on add_timeout', () => {
    const events = classifyRecords([
      rec(
        1,
        'add_timeout',
        { team: 2 },
        {
          score_set: 1,
          team_1: { score: 0, sets: 0, timeouts: 0 },
          team_2: { score: 0, sets: 0, timeouts: 1 },
        },
      ),
    ]);
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ team: 2, kind: 'timeout' });
  });

  it('drops a stand-alone timeout undo record (no struck-clock surfaces)', () => {
    // After ``pop_last_forward`` the original forward record is gone and
    // the window only contains the undo entry. The strip surfaces nothing
    // — the undo would float without a visible counterpart to invalidate.
    expect(
      classifyRecords([
        rec(
          1,
          'add_timeout',
          { team: 1, undo: true },
          {
            score_set: 1,
            team_1: { score: 0, sets: 0, timeouts: 0 },
            team_2: { score: 0, sets: 0, timeouts: 0 },
          },
        ),
      ]),
    ).toEqual([]);
  });

  it('drops the original timeout chip once the forward is popped', () => {
    // Operator hits "+timeout" then "undo timeout": pop_last_forward
    // removes the forward record and appends an ``undo=true`` row. Both
    // are invisible to the strip, so it goes empty rather than showing a
    // struck clock with nothing to strike through.
    const beforeUndo = classifyRecords([
      rec(
        10,
        'add_timeout',
        { team: 1 },
        {
          score_set: 1,
          team_1: { score: 0, sets: 0, timeouts: 1 },
          team_2: { score: 0, sets: 0, timeouts: 0 },
        },
      ),
    ]);
    expect(beforeUndo.some((e) => e.kind === 'timeout')).toBe(true);

    expect(
      classifyRecords([
        rec(
          11,
          'add_timeout',
          { team: 1, undo: true },
          {
            score_set: 1,
            team_1: { score: 0, sets: 0, timeouts: 0 },
            team_2: { score: 0, sets: 0, timeouts: 0 },
          },
        ),
      ]),
    ).toEqual([]);
  });

  it('drops the set_won chip once a set-winning point is undone', () => {
    // Before: a baseline point (anchoring ``prevSets``) plus the
    // set-winning point.
    const beforeUndo = classifyRecords([
      rec(
        9,
        'add_point',
        { team: 1 },
        { score_set: 1, team_1: { score: 24, sets: 0 }, team_2: { score: 20, sets: 0 } },
      ),
      rec(
        10,
        'add_point',
        { team: 1 },
        { score_set: 1, team_1: { score: 25, sets: 1 }, team_2: { score: 20, sets: 0 } },
      ),
    ]);
    expect(beforeUndo.some((e) => e.kind === 'set_won')).toBe(true);

    // After: the forward was popped, leaving the baseline plus the new
    // ``undo=true`` record. No leftover star or struck chip survives.
    const afterUndo = classifyRecords([
      rec(
        9,
        'add_point',
        { team: 1 },
        { score_set: 1, team_1: { score: 24, sets: 0 }, team_2: { score: 20, sets: 0 } },
      ),
      rec(
        11,
        'add_point',
        { team: 1, undo: true },
        { score_set: 1, team_1: { score: 24, sets: 0 }, team_2: { score: 20, sets: 0 } },
      ),
    ]);
    expect(afterUndo).toHaveLength(1);
    expect(afterUndo[0]).toMatchObject({ ts: 9, team: 1, kind: 'point_add' });
  });

  it('drops the match_won chip once a match-winning point is undone', () => {
    const beforeUndo = classifyRecords([
      rec(
        9,
        'add_point',
        { team: 1 },
        {
          score_set: 3,
          team_1: { score: 24, sets: 2 },
          team_2: { score: 20, sets: 1 },
          match_finished: false,
        },
      ),
      rec(
        10,
        'add_point',
        { team: 1 },
        {
          score_set: 3,
          team_1: { score: 25, sets: 3 },
          team_2: { score: 20, sets: 1 },
          match_finished: true,
        },
      ),
    ]);
    expect(beforeUndo.some((e) => e.kind === 'match_won')).toBe(true);

    const afterUndo = classifyRecords([
      rec(
        9,
        'add_point',
        { team: 1 },
        {
          score_set: 3,
          team_1: { score: 24, sets: 2 },
          team_2: { score: 20, sets: 1 },
          match_finished: false,
        },
      ),
      rec(
        11,
        'add_point',
        { team: 1, undo: true },
        {
          score_set: 3,
          team_1: { score: 24, sets: 2 },
          team_2: { score: 20, sets: 1 },
          match_finished: false,
        },
      ),
    ]);
    expect(afterUndo).toHaveLength(1);
    expect(afterUndo[0]).toMatchObject({ ts: 9, team: 1, kind: 'point_add' });
  });

  it('does not resurrect a popped forward timeout chip when an undo is non-adjacent', () => {
    // Operator sequence: point(0→1), [popped timeout(t1: 0→1)],
    // point(1→2), undo timeout(t1: 1→0). After pop_last_forward the
    // window is the baseline point + the in-between point (still showing
    // the bumped timeout count) + the undo. Only the forward point chips
    // surface: the popped timeout forward stays hidden and the
    // standalone undo record is dropped too. Matches what the history
    // drawer and the printable report show.
    const events = classifyRecords([
      rec(
        1,
        'add_point',
        { team: 1 },
        {
          score_set: 1,
          team_1: { score: 1, sets: 0, timeouts: 0 },
          team_2: { score: 0, sets: 0, timeouts: 0 },
        },
      ),
      rec(
        2,
        'add_point',
        { team: 1 },
        {
          score_set: 1,
          team_1: { score: 2, sets: 0, timeouts: 1 },
          team_2: { score: 0, sets: 0, timeouts: 0 },
        },
      ),
      rec(
        3,
        'add_timeout',
        { team: 1, undo: true },
        {
          score_set: 1,
          team_1: { score: 2, sets: 0, timeouts: 0 },
          team_2: { score: 0, sets: 0, timeouts: 0 },
        },
      ),
    ]);
    expect(events).toHaveLength(2);
    expect(events[0]).toMatchObject({ team: 1, kind: 'point_add' });
    expect(events[1]).toMatchObject({ team: 1, kind: 'point_add' });
  });

  it('emits match_won (not set_won) when a sets++ also flips match_finished', () => {
    const events = classifyRecords([
      rec(
        1,
        'add_point',
        { team: 1 },
        {
          score_set: 1,
          team_1: { score: 24, sets: 2 },
          team_2: { score: 20, sets: 0 },
          match_finished: false,
        },
      ),
      rec(
        2,
        'add_point',
        { team: 1 },
        {
          score_set: 1,
          team_1: { score: 25, sets: 3 },
          team_2: { score: 20, sets: 0 },
          match_finished: true,
        },
      ),
    ]);
    expect(events).toHaveLength(3);
    expect(events[2]).toMatchObject({ team: 1, kind: 'match_won' });
    expect(events.some((e) => e.kind === 'set_won')).toBe(false);
  });

  it('emits set_won when team.sets advances on an explicit add_set', () => {
    const events = classifyRecords([
      rec(
        1,
        'add_point',
        { team: 1 },
        { score_set: 1, team_1: { score: 1, sets: 0 }, team_2: { score: 0, sets: 0 } },
      ),
      rec(
        2,
        'add_set',
        { team: 1 },
        { score_set: 1, team_1: { score: 25, sets: 1 }, team_2: { score: 20, sets: 0 } },
      ),
    ]);
    expect(events).toHaveLength(2);
    expect(events[0]).toMatchObject({ team: 1, kind: 'point_add' });
    expect(events[1]).toMatchObject({ team: 1, kind: 'set_won' });
  });

  it('emits set_won AND point_add when a set-winning add_point bumps team.sets', () => {
    const events = classifyRecords([
      rec(
        1,
        'add_point',
        { team: 1 },
        { score_set: 1, team_1: { score: 24, sets: 0 }, team_2: { score: 20, sets: 0 } },
      ),
      rec(
        2,
        'add_point',
        { team: 1 },
        { score_set: 1, team_1: { score: 25, sets: 1 }, team_2: { score: 20, sets: 0 } },
      ),
    ]);
    expect(events).toHaveLength(3);
    expect(events[0]).toMatchObject({ team: 1, kind: 'point_add' });
    expect(events[1]).toMatchObject({ team: 1, kind: 'point_add' });
    expect(events[2]).toMatchObject({ team: 1, kind: 'set_won' });
  });

  it('does not emit set_won when team.sets decreases (set undo)', () => {
    const events = classifyRecords([
      rec(
        1,
        'add_set',
        { team: 1 },
        { score_set: 1, team_1: { score: 25, sets: 1 }, team_2: { score: 20, sets: 0 } },
      ),
      rec(
        2,
        'add_set',
        { team: 1, undo: true },
        { score_set: 1, team_1: { score: 25, sets: 0 }, team_2: { score: 20, sets: 0 } },
      ),
    ]);
    // No set_won — the first record has no prev to diff against, and the
    // second record's sets decreased so the diff is negative.
    expect(events.some((e) => e.kind === 'set_won')).toBe(false);
  });

  it('emits manual chips with the absolute new value', () => {
    const events = classifyRecords([
      rec(
        1,
        'add_point',
        { team: 1 },
        { score_set: 1, team_1: { score: 1, sets: 0 }, team_2: { score: 0, sets: 0 } },
      ),
      rec(
        2,
        'add_point',
        { team: 1 },
        { score_set: 1, team_1: { score: 2, sets: 0 }, team_2: { score: 0, sets: 0 } },
      ),
      // Operator types 5 → chip shows 5 (absolute), not the +3 delta.
      rec(
        3,
        'set_score',
        { team: 1, set_number: 1, value: 5 },
        { score_set: 1, team_1: { score: 5, sets: 0 }, team_2: { score: 0, sets: 0 } },
      ),
      // Operator corrects down to 4 → chip shows 4.
      rec(
        4,
        'set_score',
        { team: 1, set_number: 1, value: 4 },
        { score_set: 1, team_1: { score: 4, sets: 0 }, team_2: { score: 0, sets: 0 } },
      ),
    ]);
    expect(events).toHaveLength(4);
    expect(events[2]).toMatchObject({ team: 1, kind: 'manual', value: 5 });
    expect(events[3]).toMatchObject({ team: 1, kind: 'manual', value: 4 });
  });

  it('drops manual records that match the current value (no-op corrections)', () => {
    expect(
      classifyRecords([
        rec(
          1,
          'set_score',
          { team: 1, set_number: 1, value: 0 },
          { score_set: 1, team_1: { score: 0, sets: 0 }, team_2: { score: 0, sets: 0 } },
        ),
      ]),
    ).toEqual([]);
  });

  it('keeps chips in monotonic chronological order', () => {
    // Mixed sequence (add_point, undo, add_point): the undo is dropped
    // entirely, and each surviving forward's ts is strictly greater than
    // the previous one — the projection can never reorder old chips
    // ahead of new ones.
    const events = classifyRecords([
      rec(
        1,
        'add_point',
        { team: 1 },
        { score_set: 1, team_1: { score: 1, sets: 0 }, team_2: { score: 0, sets: 0 } },
      ),
      rec(
        3,
        'add_point',
        { team: 2, undo: true },
        { score_set: 1, team_1: { score: 1, sets: 0 }, team_2: { score: 0, sets: 0 } },
      ),
      rec(
        4,
        'add_point',
        { team: 1 },
        { score_set: 1, team_1: { score: 2, sets: 0 }, team_2: { score: 0, sets: 0 } },
      ),
    ]);
    expect(events).toHaveLength(2);
    const tss = events.map((e) => e.ts);
    for (let i = 1; i < tss.length; i++) {
      expect(tss[i]!).toBeGreaterThanOrEqual(tss[i - 1]!);
    }
    expect(events[0]).toMatchObject({ ts: 1, team: 1, kind: 'point_add' });
    expect(events[1]).toMatchObject({ ts: 4, team: 1, kind: 'point_add' });
  });

  it('still emits set_won for a forward after an interposed undo', () => {
    // Regression guard: an undo record between two set-winning forwards
    // must update the ``prevSets`` baseline so the *second* forward's
    // diff fires. If undo records short-circuited the loop, the second
    // forward would diff against the stale pre-undo baseline (same sets
    // count) and lose its star chip.
    const events = classifyRecords([
      // Set-winning point — anchors prevSets to {1: 1}.
      rec(
        1,
        'add_point',
        { team: 1 },
        { score_set: 1, team_1: { score: 25, sets: 1 }, team_2: { score: 20, sets: 0 } },
      ),
      // Undo that set win — post-state sets back to 0. Must update
      // prevSets even though no chip is emitted.
      rec(
        2,
        'add_point',
        { team: 1, undo: true },
        { score_set: 1, team_1: { score: 24, sets: 0 }, team_2: { score: 20, sets: 0 } },
      ),
      // Fresh set-winning point — diff vs prevSets {1: 0} must fire.
      rec(
        3,
        'add_point',
        { team: 1 },
        { score_set: 1, team_1: { score: 25, sets: 1 }, team_2: { score: 20, sets: 0 } },
      ),
    ]);
    expect(events).toHaveLength(3);
    expect(events[0]).toMatchObject({ ts: 1, team: 1, kind: 'point_add' });
    expect(events[1]).toMatchObject({ ts: 3, team: 1, kind: 'point_add' });
    expect(events[2]).toMatchObject({ ts: 3, team: 1, kind: 'set_won' });
  });

  it('still emits manual chips for a forward after an interposed undo', () => {
    // Companion to the set_won regression test: ``lastScore`` must also
    // advance through undo records so a follow-up ``set_score`` chip
    // fires when the typed value differs from the post-undo score.
    const events = classifyRecords([
      // Operator types 5 → manual chip.
      rec(
        1,
        'set_score',
        { team: 1, set_number: 1, value: 5 },
        { score_set: 1, team_1: { score: 5, sets: 0 }, team_2: { score: 0, sets: 0 } },
      ),
      // Undo the point that took them to 5 — post-state 4. Tracker must
      // advance to 4 so the next set_score diffs against 4, not 5.
      rec(
        2,
        'add_point',
        { team: 1, undo: true },
        { score_set: 1, team_1: { score: 4, sets: 0 }, team_2: { score: 0, sets: 0 } },
      ),
      // Operator types 7 — differs from the post-undo 4 → chip.
      rec(
        3,
        'set_score',
        { team: 1, set_number: 1, value: 7 },
        { score_set: 1, team_1: { score: 7, sets: 0 }, team_2: { score: 0, sets: 0 } },
      ),
    ]);
    expect(events).toHaveLength(2);
    expect(events[0]).toMatchObject({ team: 1, kind: 'manual', value: 5 });
    expect(events[1]).toMatchObject({ team: 1, kind: 'manual', value: 7 });
  });

  it('never synthesizes chips from a sets-count drop (reset)', () => {
    // The strip is a pure projection of the log — it does not derive
    // chips from snapshot diffs. After a match reset the log is empty
    // and so is the strip, even though the sets count fell from 3 to 0.
    expect(classifyRecords([])).toEqual([]);
  });
});

describe('useRecentEvents', () => {
  it('returns the classified chips for the records it is given', () => {
    const { result } = renderHook(() =>
      useRecentEvents([rec(1, 'add_point', { team: 1 }), rec(2, 'add_point', { team: 2 })], 8),
    );
    expect(result.current).toEqual([
      { ts: 1, team: 1, kind: 'point_add' },
      { ts: 2, team: 2, kind: 'point_add' },
    ]);
  });

  it('truncates to the last `max` events', () => {
    const { result } = renderHook(() =>
      useRecentEvents(
        [
          rec(1, 'add_point', { team: 1 }),
          rec(2, 'add_point', { team: 1 }),
          rec(3, 'add_point', { team: 2 }),
          rec(4, 'add_point', { team: 1 }),
          rec(5, 'add_point', { team: 2 }),
        ],
        3,
      ),
    );
    expect(result.current).toHaveLength(3);
    expect(result.current.map((e) => e.ts)).toEqual([3, 4, 5]);
  });

  it('returns empty for an empty window', () => {
    const { result } = renderHook(() => useRecentEvents([], 8));
    expect(result.current).toEqual([]);
  });

  it('re-projects when the records change and keeps identity when they do not', () => {
    const first = [rec(1, 'add_point', { team: 1 })];
    const { result, rerender } = renderHook(
      ({ r }: { r: AuditRecord[] }) => useRecentEvents(r, 8),
      { initialProps: { r: first } },
    );
    const initial = result.current;
    expect(initial).toHaveLength(1);

    // Same array identity — the memo must not rebuild the chip list on
    // every unrelated board render.
    rerender({ r: first });
    expect(result.current).toBe(initial);

    rerender({ r: [...first, rec(2, 'add_point', { team: 2 })] });
    expect(result.current).toHaveLength(2);
  });
});
