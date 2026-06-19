import { describe, it, expect, vi, beforeEach, afterEach, Mock } from 'vitest';
import {
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
      }),
    );
  });

  it('getState sends GET with encoded oid', async () => {
    mockFetchOk({ team_1: {} });
    await getState('my oid');
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/state?oid=my%20oid',
      expect.objectContaining({ method: 'GET' }),
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
      }),
    );
  });

  it('addPoint omits classification tags when not provided', async () => {
    mockFetchOk({ success: true });
    await addPoint('oid', 1);
    const body = JSON.parse(fetchMock().mock.calls[0]![1].body);
    expect(body).toEqual({ team: 1, undo: false });
    expect(body).not.toHaveProperty('point_type');
    expect(body).not.toHaveProperty('error_type');
  });

  it('addPoint includes point_type and error_type when provided', async () => {
    mockFetchOk({ success: true });
    await addPoint('oid', 2, false, 'opp_error', 'serve_error');
    const body = JSON.parse(fetchMock().mock.calls[0]![1].body);
    expect(body).toEqual({
      team: 2,
      undo: false,
      point_type: 'opp_error',
      error_type: 'serve_error',
    });
  });

  it('throws on non-ok response', async () => {
    mockFetchError(500, 'Server error');
    await expect(getState('oid')).rejects.toThrow('API GET /state?oid=oid failed (500)');
  });

  it('sends requests with credentials so the session cookie is included', async () => {
    mockFetchOk({});
    await getTeams();
    const firstCall = fetchMock().mock.calls[0]!;
    expect(firstCall[1].credentials).toBe('include');
  });

  it('setVisibility sends visible flag', async () => {
    mockFetchOk({ success: true });
    await setVisibility('oid', false);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/display/visibility?oid=oid',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ visible: false }),
      }),
    );
  });

  it('resetGame sends POST', async () => {
    mockFetchOk({ success: true });
    await resetGame('oid');
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/game/reset?oid=oid',
      expect.objectContaining({ method: 'POST' }),
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
      }),
    );
  });
});
