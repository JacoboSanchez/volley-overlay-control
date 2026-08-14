/**
 * ``POST /matches/bulk-delete`` rejects more than 100 ids with a 422, while
 * the reports page deliberately keeps selections across pages — so a
 * 101-report selection must not fail as a whole. These tests pin that the
 * client splits the request and reports the summed totals.
 */
import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';
import { BULK_DELETE_CHUNK, deleteMatches } from '../api/reports';

describe('deleteMatches chunking', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn() as unknown as typeof globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  function fetchMock(): Mock {
    return globalThis.fetch as unknown as Mock;
  }

  /** Echoes the chunk size back, like the real endpoint does. */
  function respondOk() {
    fetchMock().mockImplementation((_url: string, init: RequestInit) => {
      const sent = JSON.parse(String(init.body)).match_ids as string[];
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: { get: () => null },
        json: () => Promise.resolve({ requested: sent.length, deleted: sent.length }),
      });
    });
  }

  function sentBatches(): string[][] {
    return fetchMock().mock.calls.map(
      (call) => JSON.parse(String((call[1] as RequestInit).body)).match_ids,
    );
  }

  it('sends one request when the selection fits the server cap', async () => {
    respondOk();
    const ids = Array.from({ length: BULK_DELETE_CHUNK }, (_, i) => `m${i}`);

    const result = await deleteMatches(ids);

    expect(fetchMock()).toHaveBeenCalledTimes(1);
    expect(result).toEqual({ requested: BULK_DELETE_CHUNK, deleted: BULK_DELETE_CHUNK });
  });

  it('splits a selection above the cap and sums the totals', async () => {
    respondOk();
    const ids = Array.from({ length: BULK_DELETE_CHUNK * 2 + 1 }, (_, i) => `m${i}`);

    const result = await deleteMatches(ids);

    const batches = sentBatches();
    expect(batches.map((batch) => batch.length)).toEqual([BULK_DELETE_CHUNK, BULK_DELETE_CHUNK, 1]);
    // Every id is sent exactly once, in order.
    expect(batches.flat()).toEqual(ids);
    expect(result).toEqual({ requested: ids.length, deleted: ids.length });
  });
});
