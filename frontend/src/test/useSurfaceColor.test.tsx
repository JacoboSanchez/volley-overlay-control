import { describe, it, expect, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useCssVariableColor, useSurfaceColor } from '../hooks/useSurfaceColor';

afterEach(() => {
  document.documentElement.style.removeProperty('--surface');
  document.documentElement.style.removeProperty('--test-var');
  document.documentElement.className = '';
});

describe('useCssVariableColor', () => {
  it('returns the fallback when the variable is unset', () => {
    const { result } = renderHook(() => useCssVariableColor('--test-var', '#abcdef'));
    expect(result.current).toBe('#abcdef');
  });

  it('reads the current value of the variable from :root', () => {
    document.documentElement.style.setProperty('--test-var', '#112233');
    const { result } = renderHook(() => useCssVariableColor('--test-var', '#ffffff'));
    expect(result.current).toBe('#112233');
  });

  it('updates when the documentElement class changes (theme toggle)', async () => {
    document.documentElement.style.setProperty('--test-var', '#111111');
    const { result } = renderHook(() => useCssVariableColor('--test-var', '#000000'));
    expect(result.current).toBe('#111111');

    act(() => {
      document.documentElement.style.setProperty('--test-var', '#eeeeee');
      // Trigger the mutation observer with a class change.
      document.documentElement.classList.add('light');
    });

    await waitFor(() => {
      expect(result.current).toBe('#eeeeee');
    });
  });
});

describe('useSurfaceColor', () => {
  it('reads --surface from the root element', () => {
    document.documentElement.style.setProperty('--surface', '#16213e');
    const { result } = renderHook(() => useSurfaceColor());
    expect(result.current).toBe('#16213e');
  });

  it('falls back when --surface is missing', () => {
    const { result } = renderHook(() => useSurfaceColor());
    expect(result.current).toBe('#16213e');
  });
});
