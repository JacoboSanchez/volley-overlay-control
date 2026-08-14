/**
 * The per-tab id feeds presence dedup and audit attribution, so two live
 * tabs must never share one. Browsers copy sessionStorage into a duplicated
 * (or same-origin-opened) tab, which is exactly the case a plain
 * "read it back from sessionStorage" scheme gets wrong.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

const ID_KEY = 'volley_client_id';
const CLAIM_KEY = 'volley_client_id_live';

/** Load a fresh copy of the module — one module instance is one page load,
 *  since the id is memoised per load. */
async function newPageLoad() {
  vi.resetModules();
  return import('../api/clientIdentity');
}

/** What a browser hands a duplicated tab: a copy of the opener's storage,
 *  claim flag included, because the opener never unloaded. */
function duplicateTab(): void {
  // sessionStorage is shared across module instances in jsdom, so the copy
  // is implicit — the claim simply stays set.
}

/** A reload of the same tab: ``pagehide`` fires first, releasing the claim. */
function reloadTab(): void {
  window.dispatchEvent(new Event('pagehide'));
}

describe('client identity', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.resetModules();
  });

  it('keeps the same id across a reload of the same tab', async () => {
    const first = (await newPageLoad()).getClientId();
    expect(sessionStorage.getItem(ID_KEY)).toBe(first);
    expect(sessionStorage.getItem(CLAIM_KEY)).toBe('1');

    reloadTab();
    const second = (await newPageLoad()).getClientId();

    expect(second).toBe(first);
  });

  it('mints a new id for a tab duplicated from a live one', async () => {
    const original = (await newPageLoad()).getClientId();

    duplicateTab();
    const copy = (await newPageLoad()).getClientId();

    expect(copy).not.toBe(original);
    expect(copy).toMatch(/^tab-/);
  });

  it('is stable within one page load', async () => {
    const mod = await newPageLoad();
    expect(mod.getClientId()).toBe(mod.getClientId());
  });

  it('survives a sessionStorage that throws', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    try {
      const mod = await newPageLoad();
      const id = mod.getClientId();
      expect(id).toMatch(/^tab-/);
      // Still stable for this load, from memory alone.
      expect(mod.getClientId()).toBe(id);
    } finally {
      getItem.mockRestore();
      setItem.mockRestore();
    }
  });
});
