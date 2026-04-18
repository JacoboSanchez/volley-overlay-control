import { describe, it, expect, vi, beforeEach, afterEach, Mock } from 'vitest';
import { createWebSocket } from '../api/websocket';

class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  static _instance: MockWebSocket | null = null;

  url: string;
  readyState: number;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: ((event: { type: string }) => void) | null = null;
  sent: string[] = [];
  close: Mock = vi.fn();

  constructor(url: string) {
    this.url = url;
    this.readyState = MockWebSocket.OPEN;
    MockWebSocket._instance = this;
  }

  send(data: string) {
    this.sent.push(data);
  }
}

let originalWebSocket: typeof globalThis.WebSocket;

beforeEach(() => {
  originalWebSocket = globalThis.WebSocket;
  globalThis.WebSocket = MockWebSocket as unknown as typeof globalThis.WebSocket;
  Object.defineProperty(window, 'location', {
    value: { protocol: 'https:', host: 'example.com', search: '' },
    writable: true,
  });
});

afterEach(() => {
  globalThis.WebSocket = originalWebSocket;
  vi.restoreAllMocks();
});

function currentInstance(): MockWebSocket {
  const instance = MockWebSocket._instance;
  if (!instance) throw new Error('no MockWebSocket instance');
  return instance;
}

describe('createWebSocket', () => {
  it('creates WebSocket with correct wss URL for https', () => {
    createWebSocket('abc123', {});
    expect(currentInstance().url).toBe('wss://example.com/api/v1/ws?oid=abc123');
  });

  it('creates WebSocket with correct ws URL for http', () => {
    (window.location as unknown as { protocol: string }).protocol = 'http:';
    createWebSocket('abc123', {});
    expect(currentInstance().url).toBe('ws://example.com/api/v1/ws?oid=abc123');
  });

  it('encodes oid in URL', () => {
    createWebSocket('has space&special', {});
    expect(currentInstance().url).toContain('oid=has%20space%26special');
  });

  it('calls onOpen callback when connection opens', () => {
    const onOpen = vi.fn();
    createWebSocket('oid1', { onOpen });
    currentInstance().onopen!();
    expect(onOpen).toHaveBeenCalledOnce();
  });

  it('starts ping interval on open', () => {
    vi.useFakeTimers();
    createWebSocket('oid1', {});
    const ws = currentInstance();
    ws.onopen!();

    vi.advanceTimersByTime(25000);
    expect(ws.sent).toContain('ping');

    vi.advanceTimersByTime(25000);
    expect(ws.sent.filter((m) => m === 'ping')).toHaveLength(2);
    vi.useRealTimers();
  });

  it('does not send ping if readyState is not OPEN', () => {
    vi.useFakeTimers();
    createWebSocket('oid1', {});
    const ws = currentInstance();
    ws.onopen!();
    ws.readyState = MockWebSocket.CLOSED;

    vi.advanceTimersByTime(25000);
    expect(ws.sent).not.toContain('ping');
    vi.useRealTimers();
  });

  it('ignores pong messages', () => {
    const onStateUpdate = vi.fn();
    createWebSocket('oid1', { onStateUpdate });
    currentInstance().onmessage!({ data: 'pong' });
    expect(onStateUpdate).not.toHaveBeenCalled();
  });

  it('calls onStateUpdate for state_update messages', () => {
    const onStateUpdate = vi.fn();
    createWebSocket('oid1', { onStateUpdate });
    const payload = { team_1: { sets: 1 } };
    currentInstance().onmessage!({
      data: JSON.stringify({ type: 'state_update', data: payload }),
    });
    expect(onStateUpdate).toHaveBeenCalledWith(payload);
  });

  it('calls onCustomizationUpdate for customization_update messages', () => {
    const onCustomizationUpdate = vi.fn();
    createWebSocket('oid1', { onCustomizationUpdate });
    const payload = { 'Team 1 Name': 'Eagles' };
    currentInstance().onmessage!({
      data: JSON.stringify({ type: 'customization_update', data: payload }),
    });
    expect(onCustomizationUpdate).toHaveBeenCalledWith(payload);
  });

  it('ignores non-JSON messages silently', () => {
    const onStateUpdate = vi.fn();
    createWebSocket('oid1', { onStateUpdate });
    currentInstance().onmessage!({ data: 'not json' });
    expect(onStateUpdate).not.toHaveBeenCalled();
  });

  it('calls onClose and clears ping interval', () => {
    vi.useFakeTimers();
    const onClose = vi.fn();
    createWebSocket('oid1', { onClose });
    const ws = currentInstance();
    ws.onopen!();

    const closeEvent = { code: 1000 };
    ws.onclose!(closeEvent);
    expect(onClose).toHaveBeenCalledWith(closeEvent);

    ws.sent = [];
    vi.advanceTimersByTime(25000);
    expect(ws.sent).toHaveLength(0);
    vi.useRealTimers();
  });

  it('calls onError callback', () => {
    const onError = vi.fn();
    createWebSocket('oid1', { onError });
    const errorEvent = { type: 'error' };
    currentInstance().onerror!(errorEvent);
    expect(onError).toHaveBeenCalledWith(errorEvent);
  });

  it('returns the WebSocket instance', () => {
    const ws = createWebSocket('oid1', {});
    expect(ws).toBe(currentInstance());
  });
});
