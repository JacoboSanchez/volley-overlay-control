import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { ReactNode } from 'react';
import { useHaptics, HAPTIC_PATTERNS } from '../hooks/useHaptics';
import { I18nProvider } from '../i18n';
import { SettingsProvider } from '../hooks/useSettings';

function wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nProvider>
      <SettingsProvider>{children}</SettingsProvider>
    </I18nProvider>
  );
}

describe('useHaptics', () => {
  let vibrateMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    localStorage.clear();
    // Haptics defaults to ``false`` in production so a fresh
    // install doesn't surprise the operator with vibration on
    // the first scoring tap. Tests in this suite exercise the
    // active path, so flip the flag on explicitly. The "no-ops
    // when disabled" case overrides it back to ``false``.
    localStorage.setItem('volley_haptics', 'true');
    vibrateMock = vi.fn().mockReturnValue(true);
    Object.defineProperty(navigator, 'vibrate', {
      configurable: true,
      writable: true,
      value: vibrateMock,
    });
  });

  afterEach(() => {
    // Clean up the global override so other tests don't see it.
    Object.defineProperty(navigator, 'vibrate', {
      configurable: true,
      writable: true,
      value: undefined,
    });
  });

  it('reports support when navigator.vibrate is callable', () => {
    const { result } = renderHook(() => useHaptics(), { wrapper });
    expect(result.current.supported).toBe(true);
  });

  it('fires the named pattern through navigator.vibrate', () => {
    const { result } = renderHook(() => useHaptics(), { wrapper });
    act(() => {
      result.current.pulse('tap');
    });
    expect(vibrateMock).toHaveBeenCalledWith(HAPTIC_PATTERNS.tap);
  });

  it('expands array patterns into a fresh mutable array for the API', () => {
    const { result } = renderHook(() => useHaptics(), { wrapper });
    act(() => {
      result.current.pulse('confirm');
    });
    expect(vibrateMock).toHaveBeenCalledTimes(1);
    const arg = vibrateMock.mock.calls[0]![0];
    expect(Array.isArray(arg)).toBe(true);
    expect(arg).toEqual(Array.from(HAPTIC_PATTERNS.confirm));
  });

  it('throttles repeated pulses inside the minimum interval', () => {
    const { result } = renderHook(() => useHaptics(), { wrapper });
    act(() => {
      result.current.pulse('tap');
      result.current.pulse('tap');
      result.current.pulse('tap');
    });
    expect(vibrateMock).toHaveBeenCalledTimes(1);
  });

  it('no-ops when haptics is disabled in settings', () => {
    localStorage.setItem('volley_haptics', 'false');
    const { result } = renderHook(() => useHaptics(), { wrapper });
    act(() => {
      result.current.pulse('tap');
    });
    expect(vibrateMock).not.toHaveBeenCalled();
  });

  it('swallows runtime errors raised by navigator.vibrate', () => {
    vibrateMock.mockImplementation(() => {
      throw new Error('not allowed');
    });
    const { result } = renderHook(() => useHaptics(), { wrapper });
    expect(() => {
      act(() => {
        result.current.pulse('alert');
      });
    }).not.toThrow();
  });

  it('reports unsupported when navigator.vibrate is missing', () => {
    Object.defineProperty(navigator, 'vibrate', {
      configurable: true,
      writable: true,
      value: undefined,
    });
    const { result } = renderHook(() => useHaptics(), { wrapper });
    expect(result.current.supported).toBe(false);
    act(() => {
      result.current.pulse('tap');
    });
    expect(vibrateMock).not.toHaveBeenCalled();
  });
});
