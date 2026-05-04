import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useRecentPoints } from '../hooks/useRecentPoints';
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

describe('useRecentPoints', () => {
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
      useRecentPoints('oid', false, makeState(5, 3)),
    );
    expect(result.current).toEqual([]);
    expect(getAuditSpy).not.toHaveBeenCalled();
  });

  it('returns empty and does not fetch when oid is null', () => {
    getAuditSpy.mockResolvedValue({ oid: 'x', count: 0, records: [] });
    const { result } = renderHook(() =>
      useRecentPoints(null, true, makeState(5, 3)),
    );
    expect(result.current).toEqual([]);
    expect(getAuditSpy).not.toHaveBeenCalled();
  });

  it('fetches and exposes only add_point records, mapped and trimmed', async () => {
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 7,
      records: [
        { ts: 1, action: 'add_point', params: { team: 1 } },
        { ts: 2, action: 'add_set',   params: { team: 1 } },
        { ts: 3, action: 'add_point', params: { team: 2 } },
        { ts: 4, action: 'add_timeout', params: { team: 1 } },
        { ts: 5, action: 'add_point', params: { team: 1 } },
        { ts: 6, action: 'add_point', params: { team: 2 } },
        { ts: 7, action: 'add_point', params: { team: 1 } },
      ],
    });
    const { result } = renderHook(() =>
      useRecentPoints('oid', true, makeState(5, 3), 3),
    );
    await waitFor(() => expect(result.current).toHaveLength(3));
    expect(result.current).toEqual([
      { team: 1, ts: 5 },
      { team: 2, ts: 6 },
      { team: 1, ts: 7 },
    ]);
  });

  it('drops records with params.undo truthy', async () => {
    getAuditSpy.mockResolvedValue({
      oid: 'oid',
      count: 3,
      records: [
        { ts: 1, action: 'add_point', params: { team: 1 } },
        { ts: 2, action: 'add_point', params: { team: 2, undo: true } },
        { ts: 3, action: 'add_point', params: { team: 1 } },
      ],
    });
    const { result } = renderHook(() =>
      useRecentPoints('oid', true, makeState(2, 0), 5),
    );
    await waitFor(() =>
      expect(result.current).toEqual([
        { team: 1, ts: 1 },
        { team: 1, ts: 3 },
      ]),
    );
  });

  it('refetches when scoring key changes', async () => {
    getAuditSpy.mockResolvedValue({ oid: 'oid', count: 0, records: [] });
    const { rerender } = renderHook(
      ({ s }: { s: GameState }) => useRecentPoints('oid', true, s, 5),
      { initialProps: { s: makeState(5, 3) } },
    );
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(1));
    // Same scoring key (no point change) → no extra fetch.
    rerender({ s: makeState(5, 3) });
    expect(getAuditSpy).toHaveBeenCalledTimes(1);
    // Score advances → refetch.
    rerender({ s: makeState(6, 3) });
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalledTimes(2));
  });

  it('swallows fetch errors and keeps points empty', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    getAuditSpy.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() =>
      useRecentPoints('oid', true, makeState(1, 0), 5),
    );
    await waitFor(() => expect(getAuditSpy).toHaveBeenCalled());
    expect(result.current).toEqual([]);
    warn.mockRestore();
  });
});
