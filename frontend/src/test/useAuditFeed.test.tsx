import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { AUDIT_FEED_LIMIT, useAuditFeed } from '../hooks/useAuditFeed';
import * as apiClient from '../api/board';
import type { AuditRecord } from '../api/board';

function rec(ts: number, action = 'add_point'): AuditRecord {
  return { ts, action, params: { team: 1 } } as unknown as AuditRecord;
}

function page(records: AuditRecord[], version: number) {
  return { oid: 'oid', count: records.length, records, version };
}

describe('useAuditFeed', () => {
  let getAudit: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    getAudit = vi.spyOn(apiClient, 'getAudit');
  });

  afterEach(() => {
    getAudit.mockRestore();
  });

  it('does not fetch while disabled', () => {
    getAudit.mockResolvedValue(page([], 1));
    const { result } = renderHook(() => useAuditFeed('oid', false));
    expect(result.current.records).toEqual([]);
    expect(getAudit).not.toHaveBeenCalled();
  });

  it('does not fetch without an oid', () => {
    getAudit.mockResolvedValue(page([], 1));
    const { result } = renderHook(() => useAuditFeed(null, true));
    expect(result.current.records).toEqual([]);
    expect(getAudit).not.toHaveBeenCalled();
  });

  it('reads one window when armed', async () => {
    getAudit.mockResolvedValue(page([rec(1)], 5));
    const { result } = renderHook(() => useAuditFeed('oid', true));

    await waitFor(() => expect(result.current.records).toHaveLength(1));
    expect(getAudit).toHaveBeenCalledTimes(1);
    expect(getAudit).toHaveBeenCalledWith('oid', AUDIT_FEED_LIMIT, expect.anything());
  });

  it('applies a contiguous append without refetching', async () => {
    getAudit.mockResolvedValue(page([rec(1)], 5));
    const { result } = renderHook(() => useAuditFeed('oid', true));
    await waitFor(() => expect(result.current.records).toHaveLength(1));

    act(() => result.current.onAppend(6, rec(2)));

    expect(result.current.records.map((r) => r.ts)).toEqual([1, 2]);
    // The whole point: a pushed row costs no round trip.
    expect(getAudit).toHaveBeenCalledTimes(1);
  });

  it('applies a run of contiguous appends', async () => {
    getAudit.mockResolvedValue(page([], 0));
    const { result } = renderHook(() => useAuditFeed('oid', true));
    await waitFor(() => expect(getAudit).toHaveBeenCalledTimes(1));

    act(() => {
      result.current.onAppend(1, rec(1));
    });
    act(() => {
      result.current.onAppend(2, rec(2));
    });
    act(() => {
      result.current.onAppend(3, rec(3));
    });

    expect(result.current.records.map((r) => r.ts)).toEqual([1, 2, 3]);
    expect(getAudit).toHaveBeenCalledTimes(1);
  });

  it('refetches instead of applying when the version skips ahead', async () => {
    getAudit.mockResolvedValue(page([rec(1)], 5));
    const { result } = renderHook(() => useAuditFeed('oid', true));
    await waitFor(() => expect(result.current.records).toHaveLength(1));
    getAudit.mockResolvedValue(page([rec(1), rec(2), rec(3)], 7));

    // 7 while holding 5 — a message went missing, so the record is not
    // applied blind; the log is re-read instead.
    act(() => result.current.onAppend(7, rec(3)));

    await waitFor(() => expect(getAudit).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.records.map((r) => r.ts)).toEqual([1, 2, 3]));
  });

  it('refetches on a replayed (stale) version', async () => {
    getAudit.mockResolvedValue(page([rec(1)], 5));
    const { result } = renderHook(() => useAuditFeed('oid', true));
    await waitFor(() => expect(result.current.records).toHaveLength(1));

    act(() => result.current.onAppend(5, rec(1)));

    await waitFor(() => expect(getAudit).toHaveBeenCalledTimes(2));
    // The duplicate must not land twice in the list.
    await waitFor(() => expect(result.current.records).toHaveLength(1));
  });

  it('refetches on invalidate', async () => {
    getAudit.mockResolvedValue(page([rec(1), rec(2)], 5));
    const { result } = renderHook(() => useAuditFeed('oid', true));
    await waitFor(() => expect(result.current.records).toHaveLength(2));
    // An undo tombstoned the second row, so the server now returns one.
    getAudit.mockResolvedValue(page([rec(1)], 6));

    act(() => result.current.onInvalidate(6));

    await waitFor(() => expect(result.current.records.map((r) => r.ts)).toEqual([1]));
  });

  it('refetches on resync after a reconnect', async () => {
    getAudit.mockResolvedValue(page([rec(1)], 5));
    const { result } = renderHook(() => useAuditFeed('oid', true));
    await waitFor(() => expect(getAudit).toHaveBeenCalledTimes(1));

    act(() => result.current.onResync());

    await waitFor(() => expect(getAudit).toHaveBeenCalledTimes(2));
  });

  it('treats an append arriving before the first read as a miss', async () => {
    // Nothing trustworthy is held yet, so the push cannot be applied on
    // top of an unknown baseline.
    let resolveFirst: ((v: unknown) => void) | undefined;
    // Only the *first* call hangs, so the re-read below gets a real page.
    getAudit.mockReturnValueOnce(
      new Promise((res) => {
        resolveFirst = res;
      }),
    );
    const { result } = renderHook(() => useAuditFeed('oid', true));
    await waitFor(() => expect(getAudit).toHaveBeenCalledTimes(1));

    getAudit.mockResolvedValue(page([rec(1)], 1));
    act(() => result.current.onAppend(1, rec(1)));

    await waitFor(() => expect(getAudit).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.records.map((r) => r.ts)).toEqual([1]));

    // The abandoned first read must not overwrite what the re-read set.
    await act(async () => {
      resolveFirst?.(page([], 0));
    });
    expect(result.current.records.map((r) => r.ts)).toEqual([1]);
  });

  it('bounds the record list as appends accumulate', async () => {
    const initial = Array.from({ length: AUDIT_FEED_LIMIT }, (_, i) => rec(i + 1));
    getAudit.mockResolvedValue(page(initial, 100));
    const { result } = renderHook(() => useAuditFeed('oid', true));
    await waitFor(() => expect(result.current.records).toHaveLength(AUDIT_FEED_LIMIT));

    act(() => result.current.onAppend(101, rec(9999)));

    expect(result.current.records).toHaveLength(AUDIT_FEED_LIMIT);
    // Oldest dropped, newest kept.
    expect(result.current.records[0]!.ts).toBe(2);
    expect(result.current.records.at(-1)!.ts).toBe(9999);
  });

  it('clears records and surfaces the error when the read fails', async () => {
    getAudit.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useAuditFeed('oid', true));

    await waitFor(() => expect(result.current.error).toBe('boom'));
    // A strip that silently stops tracking play is worse than an empty
    // one, so the stale rows go.
    expect(result.current.records).toEqual([]);
  });

  it('does not apply pushes after a failed read', async () => {
    getAudit.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useAuditFeed('oid', true));
    await waitFor(() => expect(result.current.error).toBe('boom'));
    getAudit.mockResolvedValue(page([rec(1)], 9));

    act(() => result.current.onAppend(9, rec(1)));

    // The version is unknown after a failure, so this re-reads rather
    // than guessing where the record belongs.
    await waitFor(() => expect(getAudit).toHaveBeenCalledTimes(2));
  });

  it('drops records when the board changes', async () => {
    getAudit.mockResolvedValue(page([rec(1)], 5));
    const { result, rerender } = renderHook(
      ({ id }: { id: string | null }) => useAuditFeed(id, true),
      { initialProps: { id: 'oid-a' as string | null } },
    );
    await waitFor(() => expect(result.current.records).toHaveLength(1));

    rerender({ id: null });

    // Another board's rows must never linger after a switch.
    expect(result.current.records).toEqual([]);
  });

  it('drops the previous board rows the moment the board changes', async () => {
    // Not when the new board's read lands: until then the strip would be
    // rendering another board's history under this board's name.
    getAudit.mockResolvedValue(page([rec(1), rec(2)], 5));
    const { result, rerender } = renderHook(({ id }: { id: string }) => useAuditFeed(id, true), {
      initialProps: { id: 'oid-a' },
    });
    await waitFor(() => expect(result.current.records).toHaveLength(2));

    let resolveSecond: ((v: unknown) => void) | undefined;
    getAudit.mockReturnValueOnce(
      new Promise((res) => {
        resolveSecond = res;
      }),
    );
    rerender({ id: 'oid-b' });

    // Read for oid-b is still in flight.
    expect(result.current.records).toEqual([]);

    await act(async () => {
      resolveSecond?.(page([rec(9)], 1));
    });
    await waitFor(() => expect(result.current.records.map((r) => r.ts)).toEqual([9]));
  });

  it('will not apply a stale frame contiguous with the new board version', async () => {
    // The cross-board case: per-board counters all start at 0, so the old
    // board's version N+1 can line up with the new board's N. Clearing
    // the held version on a switch means a frame arriving before the new
    // read lands can never be mistaken for contiguous.
    getAudit.mockResolvedValue(page([rec(1)], 5));
    const { result, rerender } = renderHook(({ id }: { id: string }) => useAuditFeed(id, true), {
      initialProps: { id: 'oid-a' },
    });
    await waitFor(() => expect(result.current.records).toHaveLength(1));

    getAudit.mockResolvedValue(page([], 0));
    rerender({ id: 'oid-b' });
    await waitFor(() => expect(result.current.records).toEqual([]));

    // A frame the old board would have made contiguous (5 + 1).
    act(() => result.current.onAppend(6, rec(999)));

    expect(result.current.records.some((r) => r.ts === 999)).toBe(false);
  });

  it('re-reads when it is armed mid-session', async () => {
    getAudit.mockResolvedValue(page([rec(1)], 5));
    const { result, rerender } = renderHook(({ on }: { on: boolean }) => useAuditFeed('oid', on), {
      initialProps: { on: false },
    });
    expect(getAudit).not.toHaveBeenCalled();

    rerender({ on: true });

    await waitFor(() => expect(result.current.records).toHaveLength(1));
  });
});
