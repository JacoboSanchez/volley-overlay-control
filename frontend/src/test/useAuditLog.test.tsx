import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useAuditLog } from '../hooks/useAuditLog';
import * as api from '../api/client';
import type { AuditRecord, GameState } from '../api/client';
import { mockGameState } from './helpers';

vi.mock('../api/client', () => ({
  getAudit: vi.fn(),
}));

function record(ts: number, action: string, params: Record<string, unknown> = {}): AuditRecord {
  return {
    ts,
    action,
    params: params as AuditRecord['params'],
    result: { team_1: { score: 1 }, team_2: { score: 0 } },
  };
}

function withScore(t1: number, t2: number): GameState {
  return {
    ...mockGameState,
    team_1: { ...mockGameState.team_1, scores: { set_1: t1 } },
    team_2: { ...mockGameState.team_2, scores: { set_1: t2 } },
  };
}

describe('useAuditLog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getAudit).mockResolvedValue({
      oid: 'x',
      count: 0,
      records: [],
    });
  });

  it('does not fetch while disabled', async () => {
    renderHook(() => useAuditLog('test-oid', false, { trigger: mockGameState }));
    // Microtask flush — no fetch should have happened.
    await Promise.resolve();
    expect(api.getAudit).not.toHaveBeenCalled();
  });

  it('fetches when enabled and surfaces the page', async () => {
    vi.mocked(api.getAudit).mockResolvedValue({
      oid: 'test-oid',
      count: 2,
      records: [record(1, 'add_point', { team: 1 }), record(2, 'add_point', { team: 2 })],
    });
    const { result } = renderHook(() =>
      useAuditLog('test-oid', true, { trigger: mockGameState, limit: 10 }),
    );
    await waitFor(() => {
      expect(result.current.records).toHaveLength(2);
    });
    expect(api.getAudit).toHaveBeenCalledWith('test-oid', 10, expect.any(AbortSignal));
    // Newest-first ordering: descending by ts.
    expect(result.current.records[0]!.ts).toBe(2);
    expect(result.current.records[1]!.ts).toBe(1);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('refetches when the trigger key changes', async () => {
    const { rerender, result } = renderHook(
      ({ s }: { s: GameState }) => useAuditLog('test-oid', true, { trigger: s }),
      { initialProps: { s: withScore(0, 0) } },
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.getAudit).toHaveBeenCalledTimes(1);

    rerender({ s: withScore(1, 0) });
    await waitFor(() => expect(api.getAudit).toHaveBeenCalledTimes(2));
  });

  it('does not refetch when the trigger key is unchanged', async () => {
    const { rerender, result } = renderHook(
      ({ s }: { s: GameState }) => useAuditLog('test-oid', true, { trigger: s }),
      { initialProps: { s: withScore(0, 0) } },
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.getAudit).toHaveBeenCalledTimes(1);

    // New object identity, identical scoring shape — same key.
    rerender({ s: { ...withScore(0, 0) } });
    await Promise.resolve();
    expect(api.getAudit).toHaveBeenCalledTimes(1);
  });

  it('records error message on fetch failure', async () => {
    vi.mocked(api.getAudit).mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useAuditLog('test-oid', true, { trigger: mockGameState }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('boom');
    expect(result.current.records).toEqual([]);
  });

  it('manual refresh re-issues the fetch', async () => {
    const { result } = renderHook(() => useAuditLog('test-oid', true, { trigger: mockGameState }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.getAudit).toHaveBeenCalledTimes(1);
    result.current.refresh();
    await waitFor(() => expect(api.getAudit).toHaveBeenCalledTimes(2));
  });

  it('clears records and stops fetching when oid becomes null', async () => {
    // Seed the mock *before* the initial renderHook so the first
    // fetch the hook fires lands on a populated payload — otherwise
    // the records assertion races the default empty mock.
    vi.mocked(api.getAudit).mockResolvedValue({
      oid: 'test-oid',
      count: 1,
      records: [record(1, 'add_point', { team: 1 })],
    });
    const { rerender, result } = renderHook(
      ({ id }: { id: string | null }) => useAuditLog(id, true, { trigger: mockGameState }),
      { initialProps: { id: 'test-oid' as string | null } },
    );
    await waitFor(() => expect(result.current.records.length).toBeGreaterThan(0));
    rerender({ id: null });
    await waitFor(() => expect(result.current.records).toEqual([]));
  });
});
