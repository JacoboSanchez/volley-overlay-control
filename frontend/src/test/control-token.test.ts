import { afterEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/client';
import { createWebSocket } from '../api/websocket';

describe('control-token (operator) mode', () => {
  afterEach(() => {
    api.setControlToken(null);
    api.setPublicUser(null);
    vi.restoreAllMocks();
  });

  it('addresses board requests by ?u=&oid= in public bookmark mode', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ team_1: {} }), { status: 200 }),
    );

    api.setPublicUser('alice');
    await api.getState('liga');

    const url = fetchMock.mock.calls[0]![0] as string;
    expect(url).toContain('/state?u=alice&oid=liga');
    expect(url).not.toContain('?c=');
  });

  it('addresses board requests by ?c=<token> instead of ?oid=', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ team_1: {} }), { status: 200 }),
    );

    api.setControlToken('TOK-123');
    await api.getState('ignored-oid');

    const url = fetchMock.mock.calls[0]![0] as string;
    expect(url).toContain('/state?c=TOK-123');
    expect(url).not.toContain('oid=');
  });

  it('falls back to ?oid= in owner (no token) mode', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ team_1: {} }), { status: 200 }),
    );

    api.setControlToken(null);
    await api.getState('liga');

    const url = fetchMock.mock.calls[0]![0] as string;
    expect(url).toContain('/state?oid=liga');
    expect(url).not.toContain('c=');
  });

  it('posts session init with the token query in operator mode', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ success: true }), { status: 200 }),
    );

    api.setControlToken('TOK-9');
    await api.initSession('liga');

    const url = fetchMock.mock.calls[0]![0] as string;
    expect(url).toContain('/session/init?c=TOK-9');
  });

  it('opens the control WebSocket by token when in operator mode', () => {
    const created: string[] = [];
    vi.stubGlobal(
      'WebSocket',
      class {
        constructor(url: string) {
          created.push(url);
        }
        close() {}
      } as unknown as typeof WebSocket,
    );

    api.setControlToken('WS-TOK');
    createWebSocket('ignored-oid', {});
    expect(created[0]).toContain('/api/v1/ws?c=WS-TOK');
    expect(created[0]).not.toContain('oid=');

    vi.unstubAllGlobals();
  });
});
