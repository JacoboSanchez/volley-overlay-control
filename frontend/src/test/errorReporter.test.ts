import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  installErrorReporter,
  reportClientError,
  _resetForTests,
} from '../utils/errorReporter';

describe('errorReporter', () => {
  let originalSendBeacon: typeof navigator.sendBeacon | undefined;
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    _resetForTests();
    originalSendBeacon = navigator.sendBeacon;
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    if (originalSendBeacon !== undefined) {
      Object.defineProperty(navigator, 'sendBeacon', {
        value: originalSendBeacon,
        configurable: true,
      });
    }
    globalThis.fetch = originalFetch;
    _resetForTests();
  });

  it('uses sendBeacon when available and includes href + UA', () => {
    const beacon = vi.fn().mockReturnValue(true);
    Object.defineProperty(navigator, 'sendBeacon', {
      value: beacon, configurable: true,
    });
    reportClientError({ level: 'error', message: 'kapow', stack: 'at foo' });
    expect(beacon).toHaveBeenCalledTimes(1);
    const [endpoint, blob] = beacon.mock.calls[0];
    expect(endpoint).toBe('/api/v1/_log');
    return (blob as Blob).text().then((body) => {
      const parsed = JSON.parse(body);
      expect(parsed.level).toBe('error');
      expect(parsed.message).toBe('kapow');
      expect(parsed.stack).toBe('at foo');
      expect(parsed.href).toBe(window.location.href);
      expect(parsed.user_agent).toBe(navigator.userAgent);
    });
  });

  it('falls back to fetch with keepalive when sendBeacon is missing', () => {
    Object.defineProperty(navigator, 'sendBeacon', {
      value: undefined, configurable: true,
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch;
    reportClientError({ level: 'warn', message: 'soft' });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/_log',
      expect.objectContaining({ method: 'POST', keepalive: true }),
    );
  });

  it('dedupes identical messages within the dedupe window', () => {
    const beacon = vi.fn().mockReturnValue(true);
    Object.defineProperty(navigator, 'sendBeacon', {
      value: beacon, configurable: true,
    });
    reportClientError({ level: 'error', message: 'same' });
    reportClientError({ level: 'error', message: 'same' });
    reportClientError({ level: 'error', message: 'different' });
    expect(beacon).toHaveBeenCalledTimes(2);
  });

  it('install() is idempotent', () => {
    const addEventListener = vi.spyOn(window, 'addEventListener');
    installErrorReporter();
    installErrorReporter();
    const errorListenerCalls = addEventListener.mock.calls.filter(
      (c) => c[0] === 'error',
    );
    expect(errorListenerCalls).toHaveLength(1);
    addEventListener.mockRestore();
  });

  it('does not throw when reporting fails internally', () => {
    Object.defineProperty(navigator, 'sendBeacon', {
      value: () => { throw new Error('blocked'); },
      configurable: true,
    });
    globalThis.fetch = (() => { throw new Error('blocked'); }) as unknown as typeof globalThis.fetch;
    expect(() => reportClientError({ level: 'error', message: 'safe' })).not.toThrow();
  });
});
