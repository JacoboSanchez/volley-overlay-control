import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createWebSocket } from '../api/websocket';

// Mock WebSocket
class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;

  constructor(url) {
    this.url = url;
    this.readyState = MockWebSocket.OPEN;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    this.sent = [];
    this.close = vi.fn();
    MockWebSocket._instance = this;
  }

  send(data) {
    this.sent.push(data);
  }
}

let originalWebSocket;

beforeEach(() => {
  originalWebSocket = global.WebSocket;
  global.WebSocket = MockWebSocket;
  // Set location for URL building
  Object.defineProperty(window, 'location', {
    value: { protocol: 'https:', host: 'example.com', search: '' },
    writable: true,
  });
});

afterEach(() => {
  global.WebSocket = originalWebSocket;
  vi.restoreAllMocks();
});

describe('createWebSocket', () => {
  it('creates WebSocket with correct wss URL for https', () => {
    createWebSocket('abc123', {});
    expect(MockWebSocket._instance.url).toBe('wss://example.com/api/v1/ws?oid=abc123');
  });

  it('creates WebSocket with correct ws URL for http', () => {
    window.location.protocol = 'http:';
    createWebSocket('abc123', {});
    expect(MockWebSocket._instance.url).toBe('ws://example.com/api/v1/ws?oid=abc123');
  });

  it('encodes oid in URL', () => {
    createWebSocket('has space&special', {});
    expect(MockWebSocket._instance.url).toContain('oid=has%20space%26special');
  });

  it('calls onOpen callback when connection opens', () => {
    const onOpen = vi.fn();
    createWebSocket('oid1', { onOpen });
    MockWebSocket._instance.onopen();
    expect(onOpen).toHaveBeenCalledOnce();
  });

  it('starts ping interval on open', () => {
    vi.useFakeTimers();
    createWebSocket('oid1', {});
    const ws = MockWebSocket._instance;
    ws.onopen();

    vi.advanceTimersByTime(25000);
    expect(ws.sent).toContain('ping');

    vi.advanceTimersByTime(25000);
    expect(ws.sent.filter((m) => m === 'ping')).toHaveLength(2);
    vi.useRealTimers();
  });

  it('does not send ping if readyState is not OPEN', () => {
    vi.useFakeTimers();
    createWebSocket('oid1', {});
    const ws = MockWebSocket._instance;
    ws.onopen();
    ws.readyState = MockWebSocket.CLOSED;

    vi.advanceTimersByTime(25000);
    expect(ws.sent).not.toContain('ping');
    vi.useRealTimers();
  });

  it('ignores pong messages', () => {
    const onStateUpdate = vi.fn();
    createWebSocket('oid1', { onStateUpdate });
    MockWebSocket._instance.onmessage({ data: 'pong' });
    expect(onStateUpdate).not.toHaveBeenCalled();
  });

  it('calls onStateUpdate for state_update messages', () => {
    const onStateUpdate = vi.fn();
    createWebSocket('oid1', { onStateUpdate });
    const payload = { team_1: { sets: 1 } };
    MockWebSocket._instance.onmessage({
      data: JSON.stringify({ type: 'state_update', data: payload }),
    });
    expect(onStateUpdate).toHaveBeenCalledWith(payload);
  });

  it('calls onCustomizationUpdate for customization_update messages', () => {
    const onCustomizationUpdate = vi.fn();
    createWebSocket('oid1', { onCustomizationUpdate });
    const payload = { 'Team 1 Name': 'Eagles' };
    MockWebSocket._instance.onmessage({
      data: JSON.stringify({ type: 'customization_update', data: payload }),
    });
    expect(onCustomizationUpdate).toHaveBeenCalledWith(payload);
  });

  it('ignores non-JSON messages silently', () => {
    const onStateUpdate = vi.fn();
    createWebSocket('oid1', { onStateUpdate });
    // Should not throw
    MockWebSocket._instance.onmessage({ data: 'not json' });
    expect(onStateUpdate).not.toHaveBeenCalled();
  });

  it('calls onClose and clears ping interval', () => {
    vi.useFakeTimers();
    const onClose = vi.fn();
    createWebSocket('oid1', { onClose });
    const ws = MockWebSocket._instance;
    ws.onopen();

    const closeEvent = { code: 1000 };
    ws.onclose(closeEvent);
    expect(onClose).toHaveBeenCalledWith(closeEvent);

    // Ping should no longer fire
    ws.sent = [];
    vi.advanceTimersByTime(25000);
    expect(ws.sent).toHaveLength(0);
    vi.useRealTimers();
  });

  it('calls onError callback', () => {
    const onError = vi.fn();
    createWebSocket('oid1', { onError });
    const errorEvent = { type: 'error' };
    MockWebSocket._instance.onerror(errorEvent);
    expect(onError).toHaveBeenCalledWith(errorEvent);
  });

  it('returns the WebSocket instance', () => {
    const ws = createWebSocket('oid1', {});
    expect(ws).toBe(MockWebSocket._instance);
  });
});
