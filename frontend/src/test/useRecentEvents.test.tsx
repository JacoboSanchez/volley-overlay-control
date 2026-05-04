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

  it('classifies add_point forward and undo into point_add / point_undo', async () => {
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
    await waitFor(() => expect(result.current).toHaveLength(3));
    expect(result.current).toEqual([
      { ts: 1, team: 1, kind: 'point_add' },
      { ts: 2, team: 2, kind: 'point_undo' },
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

  it('keeps the original timeout chip and appends a struck-clock when the operator undoes an adjacent timeout', async () => {
    // Real-life flow across two fetches:
    //  1. Operator hits "+timeout" → audit gets the forward record →
    //     strip shows [clock].
    //  2. Operator hits "undo timeout" → ``pop_last_forward`` deletes
    //     the forward record and a new ``undo=true`` row is appended.
    //     The fresh re-classification only sees the undo, so without
    //     stickiness the clock chip would silently morph into the
    //     struck variant. The hook must instead keep the original
    //     clock visible *and* append the struck-clock beside it.
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
    await waitFor(() => expect(result.current).toHaveLength(2));
    expect(result.current.map((e) => e.kind)).toEqual(['timeout', 'timeout_undo']);
  });

  it('keeps the original set_won chip and surfaces both point_undo and set_undo when the operator undoes a set-winning point', async () => {
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
    // plus the new ``undo=true`` record.
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
    await waitFor(() =>
      expect(result.current.some((e) => e.kind === 'set_undo')).toBe(true),
    );
    const kinds = result.current.map((e) => e.kind);
    expect(kinds).toContain('point_add');
    expect(kinds).toContain('set_won');
    expect(kinds).toContain('point_undo');
    expect(kinds).toContain('set_undo');
  });

  it('keeps the original match_won chip and surfaces both point_undo and match_undo on a match-winning undo', async () => {
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
    await waitFor(() =>
      expect(result.current.some((e) => e.kind === 'match_undo')).toBe(true),
    );
    const kinds = result.current.map((e) => e.kind);
    expect(kinds).toContain('point_add');
    expect(kinds).toContain('match_won');
    expect(kinds).toContain('point_undo');
    expect(kinds).toContain('match_undo');
    // Trophy preempts the star — undoing a match-winning point should
    // not also push a struck-star alongside the struck-trophy.
    expect(kinds).not.toContain('set_undo');
  });

  it('always emits a struck-clock chip on timeout undo (adjacent case → just struck)', async () => {
    // After ``pop_last_forward`` the original forward record is gone,
    // so the audit response only contains the undo entry. We always
    // emit the struck chip — consistent with point_undo's behaviour —
    // and skip synthesizing the forward (no in-between record carries
    // the bumped count to anchor it).
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
    await waitFor(() => expect(result.current).toHaveLength(1));
    expect(result.current[0]).toMatchObject({ team: 1, kind: 'timeout_undo' });
  });

  it('injects a struck-star chip when a team\'s sets count drops between refetches', async () => {
    getAuditSpy.mockResolvedValue({ oid: 'oid', count: 0, records: [] });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentEvents('oid', true, s, 8),
      { initialProps: { s: makeState(0, 0, 1, 0) } },
    );
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(1));
    // Operator clicks undo on the set-winning point — sets drops.
    rerender({ s: makeState(24, 20, 0, 0) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(result.current.some((e) => e.kind === 'set_undo' && e.team === 1)).toBe(true),
    );
  });

  it('injects a struck-trophy chip when match_finished flips back to false with a sets drop', async () => {
    getAuditSpy.mockResolvedValue({ oid: 'oid', count: 0, records: [] });
    const finishedState = (): GameState => ({
      ...makeState(0, 0, 3, 0),
      match_finished: true,
    } as unknown as GameState);
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentEvents('oid', true, s, 8),
      { initialProps: { s: finishedState() } },
    );
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(1));
    // Operator undoes the match-winning point.
    rerender({ s: makeState(24, 20, 2, 0) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(result.current.some((e) => e.kind === 'match_undo' && e.team === 1)).toBe(true),
    );
  });

  it('synthesizes the forward chip and emits the struck-clock when an undo is non-adjacent', async () => {
    // Operator sequence: point(0→1), [popped timeout(t1: 0→1)],
    // point(1→2), undo timeout(t1: 1→0).
    // After pop_last_forward the audit response is the baseline
    // point + the in-between point (still showing the bumped
    // timeout count) + the undo. The classifier synthesizes the
    // missing forward chip right before the in-between record and
    // emits the struck chip at the undo.
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 3,
      records: [
        // Baseline record — anchors prevTimeouts at t1=0.
        rec(1, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 1, sets: 0, timeouts: 0 },
          team_2: { score: 0, sets: 0, timeouts: 0 },
        }),
        // In-between record — observed the bumped count, so
        // synthesis fires here.
        rec(2, 'add_point', { team: 1 }, {
          score_set: 1,
          team_1: { score: 2, sets: 0, timeouts: 1 },
          team_2: { score: 0, sets: 0, timeouts: 0 },
        }),
        // Undo brings the count back down.
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
    await waitFor(() => expect(result.current).toHaveLength(4));
    expect(result.current[0]).toMatchObject({ team: 1, kind: 'point_add' });
    expect(result.current[1]).toMatchObject({ team: 1, kind: 'timeout' });
    expect(result.current[2]).toMatchObject({ team: 1, kind: 'point_add' });
    expect(result.current[3]).toMatchObject({ team: 1, kind: 'timeout_undo' });
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
        // Match-winning point: sets++ AND match_finished flips true.
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
      // First record anchors the prevSets baseline; second record bumps
      // team_1.sets so the diff fires. The explicit add_set itself
      // produces no action chip — only the trophy from the diff.
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
        // Set-winning add_point — backend logs add_point, NOT add_set.
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

  it('drops sticky events when match_started_at changes (new match boundary)', async () => {
    // First fetch: a forward point lives in the audit and surfaces a
    // chip, populating the stickiness buffer.
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
    // ``match_started_at``. The sticky chip from the previous match
    // must not bleed into the new one.
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

  it('anchors set_undo ts to the latest merged event, not Date.now', async () => {
    // First fetch: set-winning point at ts=10. After classification,
    // ``priorEvents`` holds the [point_add, set_won] pair both at
    // ts=10 (the audit ts).
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
    // Second fetch: forward popped, undo at ts=11.
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
    await waitFor(() =>
      expect(result.current.some((e) => e.kind === 'set_undo')).toBe(true),
    );
    const setUndo = result.current.find((e) => e.kind === 'set_undo');
    // Ts must be derived from the latest merged audit ts (11), with
    // a small bump — *not* a Date.now() value (which would be on the
    // order of 1.7e9, an order of magnitude apart).
    expect(setUndo!.ts).toBeGreaterThan(11);
    expect(setUndo!.ts).toBeLessThan(12);
  });

  it('does not collapse two distinct manual chips with the same ts but different values', async () => {
    // Two manual corrections that happen to share a ts (e.g.
    // low-resolution server clock). They differ in ``value`` and
    // must not dedupe each other when stickiness merges them.
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 2,
      records: [
        rec(10, 'set_score', { team: 1, set_number: 1, value: 5 }, {
          score_set: 1,
          team_1: { score: 5, sets: 0 },
          team_2: { score: 0, sets: 0 },
        }),
        rec(10, 'set_score', { team: 1, set_number: 1, value: 7 }, {
          score_set: 1,
          team_1: { score: 7, sets: 0 },
          team_2: { score: 0, sets: 0 },
        }),
      ],
    });
    // Same payload on refetch — sticky merge must surface both.
    getAuditSpy.mockResolvedValueOnce({
      oid: 'oid',
      count: 2,
      records: [
        rec(10, 'set_score', { team: 1, set_number: 1, value: 5 }, {
          score_set: 1,
          team_1: { score: 5, sets: 0 },
          team_2: { score: 0, sets: 0 },
        }),
        rec(10, 'set_score', { team: 1, set_number: 1, value: 7 }, {
          score_set: 1,
          team_1: { score: 7, sets: 0 },
          team_2: { score: 0, sets: 0 },
        }),
      ],
    });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentEvents('oid', true, s, 8),
      { initialProps: { s: makeState(7, 0) } },
    );
    await waitFor(() => expect(result.current).toHaveLength(2));
    // Trigger a refetch — same records, sticky merge must not
    // collapse the two manual chips into one.
    rerender({ s: makeState(7, 1) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current).toHaveLength(2));
    const values = result.current.map((e) => e.value).sort();
    expect(values).toEqual([5, 7]);
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
