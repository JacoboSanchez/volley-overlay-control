import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useRecentEvents } from '../hooks/useRecentEvents';
import type { GameState } from '../api/client';
import * as apiClient from '../api/client';

function makeState(t1Points = 0, t2Points = 0, t1Sets = 0, t2Sets = 0): GameState {
  return {
    team_1: {
      sets: t1Sets,
      timeouts: 0,
      serving: true,
      scores: { set_1: t1Points },
    },
    team_2: {
      sets: t2Sets,
      timeouts: 0,
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

  it('classifies add_timeout forward and undo into timeout / timeout_undo', async () => {
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 2,
      records: [
        rec(1, 'add_timeout', { team: 2 }),
        rec(2, 'add_timeout', { team: 2, undo: true }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(0, 0), 8),
    );
    await waitFor(() => expect(result.current).toHaveLength(2));
    expect(result.current[0]).toMatchObject({ team: 2, kind: 'timeout' });
    expect(result.current[1]).toMatchObject({ team: 2, kind: 'timeout_undo' });
  });

  it('emits set_won only for forward add_set', async () => {
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 2,
      records: [
        rec(1, 'add_set', { team: 1 }),
        rec(2, 'add_set', { team: 1, undo: true }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(0, 0, 1, 0), 8),
    );
    await waitFor(() => expect(result.current).toHaveLength(1));
    expect(result.current[0]).toMatchObject({ team: 1, kind: 'set_won' });
  });

  it('emits manual chips with the signed delta computed against prior state', async () => {
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 4,
      records: [
        // Bring score to 5-0 via add_points so the running cache reflects it.
        rec(1, 'add_point', { team: 1 }, {
          score_set: 1, team_1: { score: 1 }, team_2: { score: 0 },
        }),
        rec(2, 'add_point', { team: 1 }, {
          score_set: 1, team_1: { score: 2 }, team_2: { score: 0 },
        }),
        // Operator types 5 → delta = 5 - 2 = +3.
        rec(3, 'set_score', { team: 1, set_number: 1, value: 5 }, {
          score_set: 1, team_1: { score: 5 }, team_2: { score: 0 },
        }),
        // Operator corrects down to 4 → delta = 4 - 5 = -1.
        rec(4, 'set_score', { team: 1, set_number: 1, value: 4 }, {
          score_set: 1, team_1: { score: 4 }, team_2: { score: 0 },
        }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(4, 0), 8),
    );
    await waitFor(() => expect(result.current).toHaveLength(4));
    expect(result.current[2]).toMatchObject({ team: 1, kind: 'manual', delta: 3 });
    expect(result.current[3]).toMatchObject({ team: 1, kind: 'manual', delta: -1 });
  });

  it('drops manual records whose delta is zero (no-op corrections)', async () => {
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 1,
      records: [
        rec(1, 'set_score', { team: 1, set_number: 1, value: 0 }, {
          score_set: 1, team_1: { score: 0 }, team_2: { score: 0 },
        }),
      ],
    });
    const { result } = renderHook(() =>
      useRecentEvents('oid', true, makeState(0, 0), 8),
    );
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalled());
    expect(result.current).toEqual([]);
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
