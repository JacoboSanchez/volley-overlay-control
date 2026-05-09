import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { ReactNode } from 'react';
import { useMatchAlertHaptics } from '../hooks/useMatchAlertHaptics';
import { HAPTIC_PATTERNS } from '../hooks/useHaptics';
import { I18nProvider } from '../i18n';
import { SettingsProvider } from '../hooks/useSettings';
import type { GameState } from '../api/client';
import { mockGameState } from './helpers';

function wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nProvider>
      <SettingsProvider>{children}</SettingsProvider>
    </I18nProvider>
  );
}

function withSetPoint(team: 1 | 2): GameState {
  return {
    ...mockGameState,
    match_point_info: {
      team_1_set_point: team === 1,
      team_2_set_point: team === 2,
      team_1_match_point: false,
      team_2_match_point: false,
    },
  };
}

function withMatchPoint(team: 1 | 2): GameState {
  return {
    ...mockGameState,
    match_point_info: {
      team_1_set_point: team === 1,
      team_2_set_point: team === 2,
      team_1_match_point: team === 1,
      team_2_match_point: team === 2,
    },
  };
}

describe('useMatchAlertHaptics', () => {
  let vibrateMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    localStorage.clear();
    vibrateMock = vi.fn().mockReturnValue(true);
    Object.defineProperty(navigator, 'vibrate', {
      configurable: true,
      writable: true,
      value: vibrateMock,
    });
  });

  afterEach(() => {
    Object.defineProperty(navigator, 'vibrate', {
      configurable: true,
      writable: true,
      value: undefined,
    });
  });

  it('does not vibrate on idle state', () => {
    renderHook(() => useMatchAlertHaptics(mockGameState), { wrapper });
    expect(vibrateMock).not.toHaveBeenCalled();
  });

  it('vibrates with the alert pattern on transition into set point', () => {
    const { rerender } = renderHook(
      ({ s }) => useMatchAlertHaptics(s),
      { wrapper, initialProps: { s: mockGameState as GameState } },
    );
    expect(vibrateMock).not.toHaveBeenCalled();
    rerender({ s: withSetPoint(1) });
    expect(vibrateMock).toHaveBeenCalledTimes(1);
    expect(vibrateMock).toHaveBeenLastCalledWith(Array.from(HAPTIC_PATTERNS.alert));
  });

  it('does not re-fire while the same alert persists', () => {
    const { rerender } = renderHook(
      ({ s }) => useMatchAlertHaptics(s),
      { wrapper, initialProps: { s: withSetPoint(1) } },
    );
    expect(vibrateMock).toHaveBeenCalledTimes(1);
    // Same alert resent (e.g. WS rebroadcast on unrelated state change):
    rerender({ s: withSetPoint(1) });
    expect(vibrateMock).toHaveBeenCalledTimes(1);
  });

  it('escalates from set point to match point when the alert sharpens', async () => {
    const { rerender } = renderHook(
      ({ s }) => useMatchAlertHaptics(s),
      { wrapper, initialProps: { s: withSetPoint(2) } },
    );
    // Wait past the 50 ms throttle window so the next pulse isn't dropped.
    await new Promise((r) => setTimeout(r, 80));
    rerender({ s: withMatchPoint(2) });
    expect(vibrateMock).toHaveBeenCalledTimes(2);
    expect(vibrateMock).toHaveBeenLastCalledWith(Array.from(HAPTIC_PATTERNS.matchPoint));
  });

  it('fires the finished pattern when the match ends', async () => {
    const { rerender } = renderHook(
      ({ s }) => useMatchAlertHaptics(s),
      { wrapper, initialProps: { s: mockGameState as GameState } },
    );
    await new Promise((r) => setTimeout(r, 80));
    rerender({ s: { ...mockGameState, match_finished: true } });
    expect(vibrateMock).toHaveBeenCalledTimes(1);
    expect(vibrateMock).toHaveBeenLastCalledWith(Array.from(HAPTIC_PATTERNS.finished));
  });
});
