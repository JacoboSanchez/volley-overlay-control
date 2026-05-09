import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useScreenWakeLock } from '../hooks/useScreenWakeLock';

interface FakeSentinel {
  released: boolean;
  release: ReturnType<typeof vi.fn>;
  addEventListener: ReturnType<typeof vi.fn>;
  removeEventListener: ReturnType<typeof vi.fn>;
  /** Hand-fire the platform-driven release event the API emits when
   *  the page becomes hidden. */
  fireRelease: () => void;
}

function makeSentinel(): FakeSentinel {
  const listeners: Array<() => void> = [];
  const sentinel: FakeSentinel = {
    released: false,
    release: vi.fn(async () => {
      sentinel.released = true;
    }),
    addEventListener: vi.fn((_event: string, cb: () => void) => {
      listeners.push(cb);
    }),
    removeEventListener: vi.fn(),
    fireRelease: () => {
      sentinel.released = true;
      listeners.forEach((cb) => cb());
    },
  };
  return sentinel;
}

describe('useScreenWakeLock', () => {
  let sentinels: FakeSentinel[];
  let request: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    sentinels = [];
    request = vi.fn(async () => {
      const s = makeSentinel();
      sentinels.push(s);
      return s;
    });
    Object.defineProperty(navigator, 'wakeLock', {
      configurable: true,
      writable: true,
      value: { request },
    });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      writable: true,
      value: 'visible',
    });
  });

  afterEach(() => {
    Object.defineProperty(navigator, 'wakeLock', {
      configurable: true,
      writable: true,
      value: undefined,
    });
  });

  it('does not acquire while disabled', async () => {
    renderHook(() => useScreenWakeLock(false));
    await Promise.resolve();
    expect(request).not.toHaveBeenCalled();
  });

  it('acquires the screen sentinel when enabled', async () => {
    renderHook(() => useScreenWakeLock(true));
    await waitFor(() => expect(request).toHaveBeenCalledWith('screen'));
    expect(sentinels).toHaveLength(1);
  });

  it('releases the sentinel when disabled', async () => {
    const { rerender } = renderHook(
      ({ on }: { on: boolean }) => useScreenWakeLock(on),
      { initialProps: { on: true } },
    );
    await waitFor(() => expect(sentinels).toHaveLength(1));
    rerender({ on: false });
    await waitFor(() => expect(sentinels[0]!.release).toHaveBeenCalled());
  });

  it('releases the sentinel on unmount', async () => {
    const { unmount } = renderHook(() => useScreenWakeLock(true));
    await waitFor(() => expect(sentinels).toHaveLength(1));
    unmount();
    await waitFor(() => expect(sentinels[0]!.release).toHaveBeenCalled());
  });

  it('re-acquires after the platform releases on visibilitychange', async () => {
    renderHook(() => useScreenWakeLock(true));
    await waitFor(() => expect(sentinels).toHaveLength(1));
    // Simulate the browser hiding the page and releasing the lock.
    sentinels[0]!.fireRelease();
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      writable: true,
      value: 'hidden',
    });
    document.dispatchEvent(new Event('visibilitychange'));
    // Page comes back — we should reacquire.
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      writable: true,
      value: 'visible',
    });
    document.dispatchEvent(new Event('visibilitychange'));
    await waitFor(() => expect(sentinels.length).toBeGreaterThanOrEqual(2));
  });

  it('no-ops when the API is unsupported', async () => {
    Object.defineProperty(navigator, 'wakeLock', {
      configurable: true,
      writable: true,
      value: undefined,
    });
    expect(() => {
      renderHook(() => useScreenWakeLock(true));
    }).not.toThrow();
  });

  it('swallows request rejections (permission policy / no gesture)', async () => {
    request.mockRejectedValueOnce(new Error('not allowed'));
    expect(() => {
      renderHook(() => useScreenWakeLock(true));
    }).not.toThrow();
  });

  it('does not request while the page is already hidden', async () => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      writable: true,
      value: 'hidden',
    });
    renderHook(() => useScreenWakeLock(true));
    await Promise.resolve();
    expect(request).not.toHaveBeenCalled();
  });
});
