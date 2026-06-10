import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useStaleSetPrompt } from '../hooks/useStaleSetPrompt';
import type { GameState } from '../api/client';
import { mockGameState } from './helpers';

const NOW_SEC = 1_750_000_000;

function makeState(
  overrides: Partial<
    Pick<GameState, 'current_set_started_at' | 'server_time' | 'match_finished'>
  > = {},
): GameState {
  return {
    ...mockGameState,
    server_time: NOW_SEC,
    current_set_started_at: NOW_SEC - 90 * 60, // 90 minutes ago
    ...overrides,
  };
}

interface Props {
  state: GameState | null;
  thresholdMinutes: number | undefined;
}

function setup(initial: Partial<Props> = {}) {
  return renderHook((props: Props) => useStaleSetPrompt(props), {
    initialProps: { state: makeState(), thresholdMinutes: 60, ...initial },
  });
}

describe('useStaleSetPrompt', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('opens the prompt when the set has been live past the threshold', () => {
    const { result } = setup();
    expect(result.current.stalePromptOpen).toBe(true);
  });

  it('stays closed while elapsed time is under the threshold', () => {
    const { result } = setup({
      state: makeState({ current_set_started_at: NOW_SEC - 30 * 60 }),
    });
    expect(result.current.stalePromptOpen).toBe(false);
  });

  it('defaults to a 60-minute threshold when none is configured', () => {
    const { result } = setup({ thresholdMinutes: undefined });
    expect(result.current.stalePromptOpen).toBe(true);
    const { result: fresh } = setup({
      thresholdMinutes: undefined,
      state: makeState({ current_set_started_at: NOW_SEC - 59 * 60 }),
    });
    expect(fresh.current.stalePromptOpen).toBe(false);
  });

  it('threshold 0 disables the prompt entirely', () => {
    const { result } = setup({ thresholdMinutes: 0 });
    expect(result.current.stalePromptOpen).toBe(false);
  });

  it('never fires for a finished match', () => {
    const { result } = setup({ state: makeState({ match_finished: true }) });
    expect(result.current.stalePromptOpen).toBe(false);
  });

  it('never fires without a set-start anchor or without state', () => {
    const { result } = setup({ state: makeState({ current_set_started_at: null }) });
    expect(result.current.stalePromptOpen).toBe(false);
    const { result: noState } = setup({ state: null });
    expect(noState.current.stalePromptOpen).toBe(false);
  });

  it('prefers server_time over the client clock', () => {
    // Client clock is hours ahead, but the server says only 5 minutes passed.
    vi.spyOn(Date, 'now').mockReturnValue((NOW_SEC + 6 * 3600) * 1000);
    const { result } = setup({
      state: makeState({ current_set_started_at: NOW_SEC - 5 * 60 }),
    });
    expect(result.current.stalePromptOpen).toBe(false);
  });

  it('falls back to Date.now when server_time is missing', () => {
    vi.spyOn(Date, 'now').mockReturnValue(NOW_SEC * 1000);
    const { result } = setup({
      state: makeState({ server_time: null, current_set_started_at: NOW_SEC - 90 * 60 }),
    });
    expect(result.current.stalePromptOpen).toBe(true);
  });

  it('fires only once: a dismissed prompt is not re-opened by later updates', () => {
    const { result, rerender } = setup();
    expect(result.current.stalePromptOpen).toBe(true);
    act(() => {
      result.current.setStalePromptOpen(false);
    });
    expect(result.current.stalePromptOpen).toBe(false);
    // The WS keeps streaming the same stale state — must not re-ask.
    rerender({ state: makeState({ server_time: NOW_SEC + 30 }), thresholdMinutes: 60 });
    expect(result.current.stalePromptOpen).toBe(false);
  });
});
