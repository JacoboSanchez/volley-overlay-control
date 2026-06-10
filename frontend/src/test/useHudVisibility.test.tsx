import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useHudVisibility } from '../hooks/useHudVisibility';
import { HUD_AUTO_HIDE_MS } from '../constants';
import type { GameState } from '../api/client';
import { mockGameState } from './helpers';

function makeState(
  overrides: Partial<Pick<GameState, 'match_started_at' | 'set_summary'>> = {},
): GameState {
  return {
    ...mockGameState,
    match_started_at: 1_000_000,
    set_summary: false,
    ...overrides,
  };
}

interface Props {
  hasRoomForPersistentControls: boolean;
  activeTab: 'scoreboard' | 'config';
  state: GameState | null;
}

function setup(initial: Partial<Props> = {}) {
  return renderHook((props: Props) => useHudVisibility(props), {
    initialProps: {
      hasRoomForPersistentControls: false,
      activeTab: 'scoreboard' as const,
      state: makeState(),
      ...initial,
    },
  });
}

describe('useHudVisibility', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('auto-hides the HUD after the inactivity window on a started match', () => {
    const { result } = setup();
    expect(result.current.showControls).toBe(true);
    act(() => {
      vi.advanceTimersByTime(HUD_AUTO_HIDE_MS - 1);
    });
    expect(result.current.showControls).toBe(true);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current.showControls).toBe(false);
  });

  it('does not arm the timer while the match is pending', () => {
    const { result } = setup({ state: makeState({ match_started_at: null }) });
    act(() => {
      vi.advanceTimersByTime(HUD_AUTO_HIDE_MS * 3);
    });
    expect(result.current.showControls).toBe(true);
  });

  it('does not arm the timer before state arrives', () => {
    const { result } = setup({ state: null });
    act(() => {
      vi.advanceTimersByTime(HUD_AUTO_HIDE_MS * 3);
    });
    expect(result.current.showControls).toBe(true);
  });

  it('skips auto-hide entirely when there is room for persistent controls', () => {
    const { result } = setup({ hasRoomForPersistentControls: true });
    act(() => {
      vi.advanceTimersByTime(HUD_AUTO_HIDE_MS * 3);
    });
    expect(result.current.showControls).toBe(true);
  });

  it('does not arm the timer on the config tab', () => {
    const { result } = setup({ activeTab: 'config' });
    act(() => {
      vi.advanceTimersByTime(HUD_AUTO_HIDE_MS * 3);
    });
    expect(result.current.showControls).toBe(true);
  });

  it('pointer activity restarts the inactivity window', () => {
    const { result } = setup();
    act(() => {
      vi.advanceTimersByTime(HUD_AUTO_HIDE_MS - 1000);
      window.dispatchEvent(new Event('pointerdown'));
      vi.advanceTimersByTime(HUD_AUTO_HIDE_MS - 1);
    });
    // Only HUD_AUTO_HIDE_MS - 1 ms since the last activity — still visible.
    expect(result.current.showControls).toBe(true);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current.showControls).toBe(false);
  });

  it('reveals the HUD when the viewport gains room for persistent controls', () => {
    const { result, rerender } = setup();
    act(() => {
      vi.advanceTimersByTime(HUD_AUTO_HIDE_MS);
    });
    expect(result.current.showControls).toBe(false);
    rerender({
      hasRoomForPersistentControls: true,
      activeTab: 'scoreboard',
      state: makeState(),
    });
    expect(result.current.showControls).toBe(true);
  });

  it('reveals and pins the HUD while the set-summary recap is live', () => {
    const { result, rerender } = setup();
    act(() => {
      vi.advanceTimersByTime(HUD_AUTO_HIDE_MS);
    });
    expect(result.current.showControls).toBe(false);
    rerender({
      hasRoomForPersistentControls: false,
      activeTab: 'scoreboard' as const,
      state: makeState({ set_summary: true }),
    });
    expect(result.current.showControls).toBe(true);
    // Pinned: the inactivity timer must not fire while the recap is up.
    act(() => {
      vi.advanceTimersByTime(HUD_AUTO_HIDE_MS * 3);
    });
    expect(result.current.showControls).toBe(true);
  });

  it('reveals the HUD when the match flips back to pending (reset)', () => {
    const { result, rerender } = setup();
    act(() => {
      vi.advanceTimersByTime(HUD_AUTO_HIDE_MS);
    });
    expect(result.current.showControls).toBe(false);
    rerender({
      hasRoomForPersistentControls: false,
      activeTab: 'scoreboard' as const,
      state: makeState({ match_started_at: null }),
    });
    expect(result.current.showControls).toBe(true);
  });

  it('exposes a manual toggle through setShowControls', () => {
    const { result } = setup({ hasRoomForPersistentControls: true });
    act(() => {
      result.current.setShowControls(false);
    });
    expect(result.current.showControls).toBe(false);
    act(() => {
      result.current.setShowControls(true);
    });
    expect(result.current.showControls).toBe(true);
  });
});
