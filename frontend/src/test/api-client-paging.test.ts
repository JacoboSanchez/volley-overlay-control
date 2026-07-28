/**
 * The list endpoints cap any single response (LIST_DEFAULT_LIMIT) and report
 * the full size in `X-Total-Count`. These tests pin that the client walks
 * every page, so a deployment whose catalog exceeds one page does not
 * silently lose rows from the overlays / teams / groups / icons / presets
 * screens.
 */
import { describe, it, expect, vi, beforeEach, afterEach, Mock } from 'vitest';
import { getTeamCatalog, getMyGroups, getOverlays, listIcons, listPresets } from '../api/client';

describe('api/client pagination', () => {
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

  /** A page whose `X-Total-Count` advertises `total` rows in scope. */
  function page(data: unknown, total: number | null) {
    return {
      ok: true,
      status: 200,
      headers: { get: (name: string) => (name === 'X-Total-Count' ? total : null) },
      json: () => Promise.resolve(data),
    };
  }

  function urls(): string[] {
    return fetchMock().mock.calls.map(([url]) => url as string);
  }

  function team(id: number) {
    return { id, name: `T${id}`, is_global: true };
  }

  it('walks every page of a bare-array listing and concatenates the rows', async () => {
    const first = Array.from({ length: 200 }, (_, i) => team(i));
    const second = Array.from({ length: 50 }, (_, i) => team(200 + i));
    fetchMock().mockResolvedValueOnce(page(first, 250)).mockResolvedValueOnce(page(second, 250));

    const rows = await getTeamCatalog();

    expect(rows).toHaveLength(250);
    expect(rows.map((t) => t.id)).toEqual(Array.from({ length: 250 }, (_, i) => i));
    expect(urls()).toEqual([
      '/api/v1/teams/catalog?limit=200&offset=0',
      '/api/v1/teams/catalog?limit=200&offset=200',
    ]);
  });

  it('stops after one request when the first page already holds everything', async () => {
    fetchMock().mockResolvedValueOnce(page([team(1), team(2)], 2));
    await expect(getTeamCatalog()).resolves.toHaveLength(2);
    expect(fetchMock()).toHaveBeenCalledTimes(1);
  });

  it('stops on a short page even if the total is larger', async () => {
    // Rows deleted between two requests: the second page comes back short, so
    // the walk ends instead of spinning until it reaches a stale total.
    fetchMock()
      .mockResolvedValueOnce(
        page(
          Array.from({ length: 200 }, (_, i) => team(i)),
          900,
        ),
      )
      .mockResolvedValueOnce(page([team(200)], 900));
    await expect(getTeamCatalog()).resolves.toHaveLength(201);
    expect(fetchMock()).toHaveBeenCalledTimes(2);
  });

  it('treats a missing X-Total-Count as a single complete page', async () => {
    // An older server, or any response without the header — must not loop.
    fetchMock().mockResolvedValue(page([team(1)], null));
    await expect(getTeamCatalog()).resolves.toHaveLength(1);
    expect(fetchMock()).toHaveBeenCalledTimes(1);
  });

  it('returns what it has when a page body is not the expected array', async () => {
    // An error envelope or a shape change must not surface as an opaque
    // "spread requires an iterable" TypeError from inside the walk.
    fetchMock().mockResolvedValue(page({}, 5));
    await expect(getTeamCatalog()).resolves.toEqual([]);
    expect(fetchMock()).toHaveBeenCalledTimes(1);
  });

  it('pages /my/groups, where the synthetic "All" group is row 0', async () => {
    const all = { id: null, name: 'All teams', kind: 'all', is_private: false, teams: [] };
    const first = [all, ...Array.from({ length: 199 }, (_, i) => ({ id: i, name: `G${i}` }))];
    fetchMock()
      .mockResolvedValueOnce(page(first, 201))
      .mockResolvedValueOnce(page([{ id: 199, name: 'G199' }], 201));

    const groups = await getMyGroups();
    expect(groups).toHaveLength(201);
    expect(groups[0]?.kind).toBe('all');
    expect(urls()[1]).toBe('/api/v1/my/groups?limit=200&offset=200');
  });

  it('pages the overlays listing and still maps the name alias', async () => {
    fetchMock().mockResolvedValueOnce(page([{ oid: 'cup', public_token: 't' }], 1));
    const rows = await getOverlays();
    expect(rows[0]?.name).toBe('cup');
    expect(rows[0]?.oid).toBe('cup');
  });

  it('pages an envelope listing by its items array', async () => {
    const items = (n: number, from: number) =>
      Array.from({ length: n }, (_, i) => ({ slug: `p${from + i}`, name: `P${from + i}` }));
    fetchMock()
      .mockResolvedValueOnce(page({ items: items(200, 0) }, 210))
      .mockResolvedValueOnce(page({ items: items(10, 200) }, 210));

    const { items: all } = await listPresets();
    expect(all).toHaveLength(210);
    expect(all[209]?.slug).toBe('p209');
  });

  it('pages only the uncapped globals half of the icon library', async () => {
    const icon = (id: number) => ({ id, name: `i${id}`, url: `/media/icons/${id}.webp` });
    const mine = [icon(900)];
    const quota = { used: 1, limit: 50 };
    fetchMock()
      .mockResolvedValueOnce(
        page({ globals: Array.from({ length: 200 }, (_, i) => icon(i)), mine, quota }, 205),
      )
      .mockResolvedValueOnce(
        page({ globals: Array.from({ length: 5 }, (_, i) => icon(200 + i)), mine, quota }, 205),
      );

    const library = await listIcons();
    expect(library.globals).toHaveLength(205);
    // `mine` and `quota` are taken from the first page, not concatenated.
    expect(library.mine).toHaveLength(1);
    expect(library.quota).toEqual(quota);
  });
});
