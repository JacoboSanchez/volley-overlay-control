import { describe, it, expect, vi, beforeEach, afterEach, Mock } from 'vitest';
import {
  setApiKey,
  initSession,
  getState,
  addPoint,
  getTeams,
  setVisibility,
  resetGame,
  updateCustomization,
} from '../api/client';

describe('api/client', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn() as unknown as typeof globalThis.fetch;
    setApiKey(null);
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  function fetchMock(): Mock {
    return globalThis.fetch as unknown as Mock;
  }

  function mockFetchOk(data: unknown) {
    fetchMock().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(data),
    });
  }

  function mockFetchError(status: number, text: string) {
    fetchMock().mockResolvedValue({
      ok: false,
      status,
      text: () => Promise.resolve(text),
    });
  }

  it('initSession sends POST with oid', async () => {
    mockFetchOk({ success: true });
    await initSession('test-oid');
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/session/init',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ oid: 'test-oid' }),
      })
    );
  });

  it('getState sends GET with encoded oid', async () => {
    mockFetchOk({ team_1: {} });
    await getState('my oid');
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/state?oid=my%20oid',
      expect.objectContaining({ method: 'GET' })
    );
  });

  it('addPoint sends team and undo flag', async () => {
    mockFetchOk({ success: true });
    await addPoint('oid', 1, true);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/game/add-point?oid=oid',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ team: 1, undo: true }),
      })
    );
  });

  it('throws on non-ok response', async () => {
    mockFetchError(500, 'Server error');
    await expect(getState('oid')).rejects.toThrow('API GET /state?oid=oid failed (500)');
  });

  it('includes Authorization header when apiKey is set', async () => {
    mockFetchOk({});
    setApiKey('secret');
    await getTeams();
    const callHeaders = fetchMock().mock.calls[0][1].headers;
    expect(callHeaders.Authorization).toBe('Bearer secret');
    setApiKey(null);
  });

  it('setVisibility sends visible flag', async () => {
    mockFetchOk({ success: true });
    await setVisibility('oid', false);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/display/visibility?oid=oid',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ visible: false }),
      })
    );
  });

  it('resetGame sends POST', async () => {
    mockFetchOk({ success: true });
    await resetGame('oid');
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/game/reset?oid=oid',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('updateCustomization sends PUT', async () => {
    mockFetchOk({});
    await updateCustomization('oid', { Height: 10 });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/customization?oid=oid',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ Height: 10 }),
      })
    );
  });
});
