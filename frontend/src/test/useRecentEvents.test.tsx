import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useRecentEvents } from '../hooks/useRecentEvents';
import type { GameState } from '../api/client';
import * as apiClient from '../api/client';

function makeState(
  t1Points = 0,
  t2Points = 0,
  t1Sets = 0,
  t2Sets = 0,
  t1Timeouts = 0,
  t2Timeouts = 0,
): GameState {
  return {
    team_1: {
      sets: t1Sets,
      timeouts: t1Timeouts,
      serving: true,
      scores: { set_1: t1Points },
    },
    team_2: {
      sets: t2Sets,
      timeouts: t2Timeouts,
      serving: false,
      scores: { set_1: t2Points },
    },
    visible: true,
    simple_mode: false,
    match_finished: false,
    current_set: 1,
    serve: 'A',
    config: { sets_limit: 5, points_limit: 25 },
    can_undo: false,
  } as unknown as GameState;
}

function rec(
  ts: number,
  action: string,
  params: Record<string, unknown>,
  result?: Record<string, unknown>,
) {
  return { ts, action, params, result };
}

describe('useRecentEvents', () => {
  let getAuditSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    getAuditSpy = vi.spyOn(apiClient, 'getAudit');
  });

  afterEach(() => {
    getAuditSpy.mockRestore();
  });

  it('returns empty and does not fetch when disabled', () => {
    getAuditSpy.mockResolvedValue({ oid: 'x', count: 0, records: [] });
    const { result } = renderHook(() =>
      useRecentEvents('oid', false, makeState(5, 3)),
    );
    expect(result.current).toEqual([]);
    expect(getAuditSpy).not.toHaveBeenCalled();
  });

  it('returns empty and does not fetch when oid is null', () => {
    getAuditSpy.mockResolvedValue({ oid: 'x', count: 0, records: [] });
    const { result } = renderHook(() =>
      useRecentEvents(null, true, makeState(5, 3)),
    );
    expect(result.current).toEqual([]);
    expect(getAuditSpy).not.toHaveBeenCalled();
  });

  it('classifies add_point forwards into point_add chips and skips undo records', async () => {
    // The visible audit contains two forwards and one undo; the
    // strip skips the undo so the operator only sees chips that
    // still contribute to the live score. The undone action lives
    // on in the history drawer and the printable report.
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 3,
      records: [
        rec(1, 'add_point', { team: 1 }),
        rec(2, 'add_point', { team: 2, undo: true }),
        rec(3, 'add_point', { team: 1 }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(2, 0), 8),
    );
    await waitFor(() => expect(result.current).toHaveLength(2));
    expect(result.current).toEqual([
      { ts: 1, team: 1, kind: 'point_add' },
      { ts: 3, team: 1, kind: 'point_add' },
    ]);
  });

  it('emits a forward timeout chip on add_timeout', async () => {
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 1,
      records: [
        rec(1, 'add_timeout', { team: 2 }, {
          score_set: 1,
          team_1: { score: 0, sets: 0, timeouts: 0 },
          team_2: { score: 0, sets: 0, timeouts: 1 },
        }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(0, 0, 0, 0, 0, 1), 8),
    );
    await waitFor(() => expect(result.current).toHaveLength(1));
    expect(result.current[0]).toMatchObject({ team: 2, kind: 'timeout' });
  });

  it('drops the original timeout chip when the operator undoes an adjacent timeout (and emits no struck chip)', async () => {
    // Real-life flow across two fetches:
    //  1. Operator hits "+timeout" → audit gets the forward record →
    //     strip shows [clock].
    //  2. Operator hits "undo timeout" → ``pop_last_forward`` deletes
    //     the forward record and a new ``undo=true`` row is appended.
    //     The strip drops the undo record entirely so the operator
    //     sees an empty strip — the floating struck clock would
    //     have no visible counterpart to invalidate.
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 1,
      records: [
        rec(10, 'add_timeout', { team: 1 }, {
          score_set: 1,
          team_1: { score: 0, sets: 0, timeouts: 1 },
          team_2: { score: 0, sets: 0, timeouts: 0 },
        }),
      ],
    });
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 1,
      records: [
        rec(11, 'add_timeout', { team: 1, undo: true }, {
          score_set: 1,
          team_1: { score: 0, sets: 0, timeouts: 0 },
          team_2: { score: 0, sets: 0, timeouts: 0 },
        }),
      ],
    });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentEvents('oid', true, s, 8),
      { initialProps: { s: makeState(0, 0, 0, 0, 1, 0) } },
    );
    await waitFor(() =>
      expect(result.current.some((e) => e.kind === 'timeout')).toBe(true),
    );
    rerender({ s: makeState(0, 0, 0, 0, 0, 0) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current).toEqual([]));
  });

  it('drops the set_won chip when the operator undoes a set-winning point (no surviving struck chip)', async () => {
    // First fetch: a baseline point (so ``prevSets`` is anchored) and
    // the set-winning ``add_point`` are both in the audit.
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 2,
      records: [
        rec(9, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 24, sets: 0 },
          team_2: { score: 20, sets: 0 },
        }),
        rec(10, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 25, sets: 1 },
          team_2: { score: 20, sets: 0 },
        }),
      ],
    });
    // Second fetch: forward was popped, leaving the baseline point
    // plus the new ``undo=true`` record. The strip drops the undo
    // chip and keeps only the baseline — no leftover star or struck
    // chip survives the undo.
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 2,
      records: [
        rec(9, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 24, sets: 0 },
          team_2: { score: 20, sets: 0 },
        }),
        rec(11, 'add_point', { team: 1, undo: true }, {
          score_set: 1,
          team_1: { score: 24, sets: 0 },
          team_2: { score: 20, sets: 0 },
        }),
      ],
    });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentEvents('oid', true, s, 8),
      { initialProps: { s: makeState(25, 20, 1, 0) } },
    );
    await waitFor(() =>
      expect(result.current.some((e) => e.kind === 'set_won')).toBe(true),
    );
    rerender({ s: makeState(24, 20, 0, 0) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current).toHaveLength(1));
    expect(result.current[0]).toMatchObject({ ts: 9, team: 1, kind: 'point_add' });
  });

  it('drops the match_won chip on a match-winning undo (no surviving struck chip)', async () => {
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 2,
      records: [
        rec(9, 'add_point', { team: 1 }, {
          score_set: 3,
          team_1: { score: 24, sets: 2 },
          team_2: { score: 20, sets: 1 },
          match_finished: false,
        }),
        rec(10, 'add_point', { team: 1 }, {
          score_set: 3,
          team_1: { score: 25, sets: 3 },
          team_2: { score: 20, sets: 1 },
          match_finished: true,
        }),
      ],
    });
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 2,
      records: [
        rec(9, 'add_point', { team: 1 }, {
          score_set: 3,
          team_1: { score: 24, sets: 2 },
          team_2: { score: 20, sets: 1 },
          match_finished: false,
        }),
        rec(11, 'add_point', { team: 1, undo: true }, {
          score_set: 3,
          team_1: { score: 24, sets: 2 },
          team_2: { score: 20, sets: 1 },
          match_finished: false,
        }),
      ],
    });
    const finishedState = (): GameState => ({
      ...makeState(25, 20, 3, 1),
      match_finished: true,
    } as unknown as GameState);
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentEvents('oid', true, s, 8),
      { initialProps: { s: finishedState() } },
    );
    await waitFor(() =>
      expect(result.current.some((e) => e.kind === 'match_won')).toBe(true),
    );
    rerender({ s: makeState(24, 20, 2, 1) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current).toHaveLength(1));
    expect(result.current[0]).toMatchObject({ ts: 9, team: 1, kind: 'point_add' });
  });

  it('drops a stand-alone timeout undo record (no struck-clock surfaces)', async () => {
    // After ``pop_last_forward`` the original forward record is gone
    // and the audit response only contains the undo entry. The strip
    // surfaces nothing — the undo would float without a visible
    // counterpart to invalidate.
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 1,
      records: [
        rec(1, 'add_timeout', { team: 1, undo: true }, {
          score_set: 1,
          team_1: { score: 0, sets: 0, timeouts: 0 },
          team_2: { score: 0, sets: 0, timeouts: 0 },
        }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(0, 0), 8),
    );
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalled());
    expect(result.current).toEqual([]);
  });

  it('does not synthesize set/match undo chips from a sets-count drop between refetches', async () => {
    // The strip is a pure projection of the audit log — it does NOT
    // try to surface set/match undoes via a snapshot diff. The undo
    // record is invisible (its forward was tombstoned) so the strip
    // simply forgets the previously-emitted ``set_won`` chip on the
    // next fetch.
    getAuditSpy.mockResolvedValue({ oid: 'oid', count: 0, records: [] });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentEvents('oid', true, s, 8),
      { initialProps: { s: makeState(0, 0, 1, 0) } },
    );
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(1));
    rerender({ s: makeState(24, 20, 0, 0) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current).toEqual([]));
  });

  it('does not resurrect a popped forward timeout chip when an undo is non-adjacent (matches history / report)', async () => {
    // Operator sequence: point(0→1), [popped timeout(t1: 0→1)],
    // point(1→2), undo timeout(t1: 1→0).
    // After pop_last_forward the audit response is the baseline
    // point + the in-between point (still showing the bumped
    // timeout count) + the undo. The strip surfaces only the
    // forward chips — the popped timeout forward stays hidden,
    // and the standalone undo record is dropped too.
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 3,
      records: [
        rec(1, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 1, sets: 0, timeouts: 0 },
          team_2: { score: 0, sets: 0, timeouts: 0 },
        }),
        rec(2, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 2, sets: 0, timeouts: 1 },
          team_2: { score: 0, sets: 0, timeouts: 0 },
        }),
        rec(3, 'add_timeout', { team: 1, undo: true }, {
          score_set: 1,
          team_1: { score: 2, sets: 0, timeouts: 0 },
          team_2: { score: 0, sets: 0, timeouts: 0 },
        }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(2, 0), 8),
    );
    await waitFor(() => expect(result.current).toHaveLength(2));
    expect(result.current[0]).toMatchObject({ team: 1, kind: 'point_add' });
    expect(result.current[1]).toMatchObject({ team: 1, kind: 'point_add' });
  });

  it('emits match_won (not set_won) when a sets++ also flips match_finished', async () => {
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 2,
      records: [
        rec(1, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 24, sets: 2 },
          team_2: { score: 20, sets: 0 },
          match_finished: false,
        }),
        rec(2, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 25, sets: 3 },
          team_2: { score: 20, sets: 0 },
          match_finished: true,
        }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(0, 0, 3, 0), 8),
    );
    await waitFor(() => expect(result.current).toHaveLength(3));
    expect(result.current[2]).toMatchObject({ team: 1, kind: 'match_won' });
    expect(result.current.some((e) => e.kind === 'set_won')).toBe(false);
  });

  it('emits set_won when team.sets advances on an explicit add_set', async () => {
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 2,
      records: [
        rec(1, 'add_point', { team: 1 }, {
          score_set: 1, team_1: { score: 1, sets: 0 }, team_2: { score: 0, sets: 0 },
        }),
        rec(2, 'add_set', { team: 1 }, {
          score_set: 1, team_1: { score: 25, sets: 1 }, team_2: { score: 20, sets: 0 },
        }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(0, 0, 1, 0), 8),
    );
    await waitFor(() => expect(result.current).toHaveLength(2));
    expect(result.current[0]).toMatchObject({ team: 1, kind: 'point_add' });
    expect(result.current[1]).toMatchObject({ team: 1, kind: 'set_won' });
  });

  it('emits set_won AND point_add when a set-winning add_point bumps team.sets', async () => {
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 2,
      records: [
        rec(1, 'add_point', { team: 1 }, {
          score_set: 1, team_1: { score: 24, sets: 0 }, team_2: { score: 20, sets: 0 },
        }),
        rec(2, 'add_point', { team: 1 }, {
          score_set: 1, team_1: { score: 25, sets: 1 }, team_2: { score: 20, sets: 0 },
        }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(0, 0, 1, 0), 8),
    );
    await waitFor(() => expect(result.current).toHaveLength(3));
    expect(result.current[0]).toMatchObject({ team: 1, kind: 'point_add' });
    expect(result.current[1]).toMatchObject({ team: 1, kind: 'point_add' });
    expect(result.current[2]).toMatchObject({ team: 1, kind: 'set_won' });
  });

  it('does not emit set_won when team.sets decreases (set undo)', async () => {
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 2,
      records: [
        rec(1, 'add_set', { team: 1 }, {
          score_set: 1, team_1: { score: 25, sets: 1 }, team_2: { score: 20, sets: 0 },
        }),
        rec(2, 'add_set', { team: 1, undo: true }, {
          score_set: 1, team_1: { score: 25, sets: 0 }, team_2: { score: 20, sets: 0 },
        }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(0, 0, 0, 0), 8),
    );
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalled());
    // No set_won — first record has no prev to diff against, second
    // record's sets decreased so the diff is negative.
    expect(result.current.some((e) => e.kind === 'set_won')).toBe(false);
  });

  it('emits manual chips with the absolute new value', async () => {
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 4,
      records: [
        rec(1, 'add_point', { team: 1 }, {
          score_set: 1, team_1: { score: 1, sets: 0 }, team_2: { score: 0, sets: 0 },
        }),
        rec(2, 'add_point', { team: 1 }, {
          score_set: 1, team_1: { score: 2, sets: 0 }, team_2: { score: 0, sets: 0 },
        }),
        // Operator types 5 → chip shows 5 (absolute), not the +3 delta.
        rec(3, 'set_score', { team: 1, set_number: 1, value: 5 }, {
          score_set: 1, team_1: { score: 5, sets: 0 }, team_2: { score: 0, sets: 0 },
        }),
        // Operator corrects down to 4 → chip shows 4.
        rec(4, 'set_score', { team: 1, set_number: 1, value: 4 }, {
          score_set: 1, team_1: { score: 4, sets: 0 }, team_2: { score: 0, sets: 0 },
        }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(4, 0), 8),
    );
    await waitFor(() => expect(result.current).toHaveLength(4));
    expect(result.current[2]).toMatchObject({ team: 1, kind: 'manual', value: 5 });
    expect(result.current[3]).toMatchObject({ team: 1, kind: 'manual', value: 4 });
  });

  it('drops manual records that match the current value (no-op corrections)', async () => {
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 1,
      records: [
        rec(1, 'set_score', { team: 1, set_number: 1, value: 0 }, {
          score_set: 1, team_1: { score: 0, sets: 0 }, team_2: { score: 0, sets: 0 },
        }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(0, 0), 8),
    );
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalled());
    expect(result.current).toEqual([]);
  });

  it('refetches when only timeouts change (so the clock chip is not delayed)', async () => {
    getAuditSpy.mockResolvedValue({ oid: 'oid', count: 0, records: [] });
    const { rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentEvents('oid', true, s, 8),
      { initialProps: { s: makeState(5, 3, 0, 0, 0, 0) } },
    );
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(1));
    // Same scores+sets but one team's timeouts went up → must refetch.
    rerender({ s: makeState(5, 3, 0, 0, 1, 0) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
  });

  it('truncates to the last `max` events', async () => {
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 5,
      records: [
        rec(1, 'add_point', { team: 1 }),
        rec(2, 'add_point', { team: 1 }),
        rec(3, 'add_point', { team: 2 }),
        rec(4, 'add_point', { team: 1 }),
        rec(5, 'add_point', { team: 2 }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(3, 2), 3),
    );
    await waitFor(() => expect(result.current).toHaveLength(3));
    expect(result.current.map((e) => e.ts)).toEqual([3, 4, 5]);
  });

  it('refetches when scoring key changes', async () => {
    getAuditSpy.mockResolvedValue({ oid: 'oid', count: 0, records: [] });
    const { rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentEvents('oid', true, s, 8),
      { initialProps: { s: makeState(5, 3) } },
    );
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(1));
    rerender({ s: makeState(5, 3) });
    expect(getAuditSpy).toHaveBeenCalledTimes(1);
    rerender({ s: makeState(6, 3) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
  });

  it('refetches and stays empty on reset when scores stayed at zero', async () => {
    // Operator added a point then undid it back to 0:0 — strip is
    // already empty because we drop undo records. Now they hit
    // reset: the score is *still* 0:0 (no numeric change in the key),
    // but ``match_started_at`` flips. The hook refetches and the
    // empty audit keeps the strip empty.
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 1,
      records: [
        rec(10, 'add_point', { team: 1, undo: true }, {
          score_set: 1,
          team_1: { score: 0, sets: 0 },
          team_2: { score: 0, sets: 0 },
        }),
      ],
    });
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 0,
      records: [],
    });
    const stateWithStart = (started: number | null): GameState => ({
      ...makeState(0, 0),
      match_started_at: started,
    } as unknown as GameState);
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentEvents('oid', true, s, 8),
      { initialProps: { s: stateWithStart(1000) } },
    );
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(result.current).toEqual([]));
    // Operator hits reset: ``match_started_at`` becomes null. The
    // effect must re-run even though scores didn't change.
    rerender({ s: stateWithStart(null) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current).toEqual([]));
  });

  it('drops chips from the previous match when match_started_at changes (new match boundary)', async () => {
    // First fetch: a forward point lives in the audit and surfaces
    // a chip in the strip.
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 1,
      records: [
        rec(10, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 1, sets: 0 },
          team_2: { score: 0, sets: 0 },
        }),
      ],
    });
    // Second fetch (after match reset): empty audit, fresh
    // ``match_started_at``. The chip from the previous match must
    // not bleed into the new one.
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 0,
      records: [],
    });
    const stateWithStart = (started: number, points = 1): GameState => ({
      ...makeState(points, 0),
      match_started_at: started,
    } as unknown as GameState);
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentEvents('oid', true, s, 8),
      { initialProps: { s: stateWithStart(1000) } },
    );
    await waitFor(() => expect(result.current).toHaveLength(1));
    // Match resets: start time changes, score back to zero.
    rerender({ s: stateWithStart(2000, 0) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current).toEqual([]));
  });

  it('does not regenerate chips on a match reset that drops the sets count', async () => {
    // Regression guard: after a match where team 1 won 3 sets, the
    // operator hits reset. Sets count falls from 3→0 without any
    // undo. The strip stays empty — no synthetic set_undo chips
    // are emitted (we never derive chips from snapshot diffs now).
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 1,
      records: [
        rec(1, 'add_set', { team: 1 }, {
          score_set: 1,
          team_1: { score: 25, sets: 3 },
          team_2: { score: 20, sets: 1 },
        }),
      ],
    });
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 0,
      records: [],
    });
    const stateWithStart = (
      started: number | null,
      t1Sets: number,
      t2Sets: number,
    ): GameState => ({
      ...makeState(0, 0, t1Sets, t2Sets),
      match_started_at: started,
    } as unknown as GameState);
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentEvents('oid', true, s, 8),
      { initialProps: { s: stateWithStart(1000, 3, 1) } },
    );
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(1));
    rerender({ s: stateWithStart(null, 0, 0) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current).toEqual([]));
  });

  it('drops the chip on a rapid-pair forward+undo within 5s (audit empty after collapse)', async () => {
    // Rapid-pair Case A: operator taps a point and immediately
    // taps undo within ``RAPID_PAIR_WINDOW_S`` (5 s). The backend
    // tombstones the just-added forward and writes *no* undo
    // record — net audit for the pair is empty. The strip
    // converges to the same empty view the history drawer and
    // printable report show.
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 1,
      records: [
        rec(10, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 1, sets: 0 },
          team_2: { score: 0, sets: 0 },
        }),
      ],
    });
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 0,
      records: [],
    });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentEvents('oid', true, s, 8),
      { initialProps: { s: makeState(1, 0) } },
    );
    await waitFor(() =>
      expect(result.current.some((e) => e.kind === 'point_add')).toBe(true),
    );
    rerender({ s: makeState(0, 0) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current).toEqual([]));
  });

  it('keeps chips in monotonic chronological order across refetches', async () => {
    // Mixed sequence (add_point, undo, add_point) — each subsequent
    // forward chip's ts is strictly greater than the previous one.
    // No carry-forward buffer means the next refetch can never
    // reorder old chips ahead of new ones; the undo record is
    // dropped entirely so the surviving chips are just the
    // forwards.
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 2,
      records: [
        rec(1, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 1, sets: 0 },
          team_2: { score: 0, sets: 0 },
        }),
        rec(2, 'add_point', { team: 2 }, {
          score_set: 1,
          team_1: { score: 1, sets: 0 },
          team_2: { score: 1, sets: 0 },
        }),
      ],
    });
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 3,
      records: [
        rec(1, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 1, sets: 0 },
          team_2: { score: 0, sets: 0 },
        }),
        rec(3, 'add_point', { team: 2, undo: true }, {
          score_set: 1,
          team_1: { score: 1, sets: 0 },
          team_2: { score: 0, sets: 0 },
        }),
        rec(4, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 2, sets: 0 },
          team_2: { score: 0, sets: 0 },
        }),
      ],
    });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentEvents('oid', true, s, 8),
      { initialProps: { s: makeState(1, 1) } },
    );
    await waitFor(() => expect(result.current).toHaveLength(2));
    rerender({ s: makeState(2, 0) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current).toHaveLength(2));
    const tss = result.current.map((e) => e.ts);
    for (let i = 1; i < tss.length; i++) {
      expect(tss[i]!).toBeGreaterThanOrEqual(tss[i - 1]!);
    }
    expect(result.current[0]).toMatchObject({ ts: 1, team: 1, kind: 'point_add' });
    expect(result.current[1]).toMatchObject({ ts: 4, team: 1, kind: 'point_add' });
  });

  it('still emits set_won for a forward after an interposed undo (state trackers stay in sync)', async () => {
    // Regression guard: an undo record between two set-winning
    // forwards must update the ``prevSets`` baseline so the
    // *second* forward's diff fires. If undo records short-circuit
    // the loop, the second forward would diff against the stale
    // pre-undo baseline (same sets count) and lose its star chip.
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 3,
      records: [
        // Set-winning point — anchors prevSets to {1: 1}.
        rec(1, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 25, sets: 1 },
          team_2: { score: 20, sets: 0 },
        }),
        // Undo that set win — post-state sets back to 0. Must
        // update prevSets even though no chip is emitted.
        rec(2, 'add_point', { team: 1, undo: true }, {
          score_set: 1,
          team_1: { score: 24, sets: 0 },
          team_2: { score: 20, sets: 0 },
        }),
        // Fresh set-winning point — diff vs prevSets {1: 0} must
        // fire the trophy.
        rec(3, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 25, sets: 1 },
          team_2: { score: 20, sets: 0 },
        }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(25, 20, 1, 0), 8),
    );
    await waitFor(() => expect(result.current).toHaveLength(3));
    expect(result.current[0]).toMatchObject({ ts: 1, team: 1, kind: 'point_add' });
    expect(result.current[1]).toMatchObject({ ts: 3, team: 1, kind: 'point_add' });
    expect(result.current[2]).toMatchObject({ ts: 3, team: 1, kind: 'set_won' });
  });

  it('still emits manual chips for a forward after an interposed undo (lastScore tracker stays in sync)', async () => {
    // Companion to the set_won regression test: ``lastScore`` must
    // also advance through undo records so a follow-up ``set_score``
    // chip fires when the typed value differs from the current
    // (post-undo) score.
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 3,
      records: [
        // Operator types 5 → manual chip.
        rec(1, 'set_score', { team: 1, set_number: 1, value: 5 }, {
          score_set: 1,
          team_1: { score: 5, sets: 0 },
          team_2: { score: 0, sets: 0 },
        }),
        // Undo the point that took them to 5 — post-state 4.
        // Tracker must advance to 4 so the next set_score's diff
        // is computed against 4, not against the stale 5.
        rec(2, 'add_point', { team: 1, undo: true }, {
          score_set: 1,
          team_1: { score: 4, sets: 0 },
          team_2: { score: 0, sets: 0 },
        }),
        // Operator types 7 — differs from the post-undo 4 → chip.
        rec(3, 'set_score', { team: 1, set_number: 1, value: 7 }, {
          score_set: 1,
          team_1: { score: 7, sets: 0 },
          team_2: { score: 0, sets: 0 },
        }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(7, 0), 8),
    );
    await waitFor(() => expect(result.current).toHaveLength(2));
    expect(result.current[0]).toMatchObject({ team: 1, kind: 'manual', value: 5 });
    expect(result.current[1]).toMatchObject({ team: 1, kind: 'manual', value: 7 });
  });

  it('clears events on fetch error', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    getAuditSpy.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(1, 0), 8),
    );
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalled());
    expect(result.current).toEqual([]);
    warn.mockRestore();
  });
});
