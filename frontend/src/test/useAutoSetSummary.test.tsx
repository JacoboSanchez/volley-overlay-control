import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useAutoSetSummary } from '../hooks/useAutoSetSummary';
import type { GameState } from '../api/client';

function makeState(opts: {
  t1Sets?: number;
  t2Sets?: number;
  t1Score?: number;
  t2Score?: number;
  currentSet?: number;
  matchFinished?: boolean;
} = {}): GameState {
  const {
    t1Sets = 0,
    t2Sets = 0,
    t1Score = 0,
    t2Score = 0,
    currentSet = 1,
    matchFinished = false,
  } = opts;
  return {
    team_1: {
      sets: t1Sets,
      timeouts: 0,
      serving: true,
      scores: { [`set_${currentSet}`]: t1Score },
    },
    team_2: {
      sets: t2Sets,
      timeouts: 0,
      serving: false,
      scores: { [`set_${currentSet}`]: t2Score },
    },
    visible: true,
    simple_mode: false,
    match_finished: matchFinished,
    current_set: currentSet,
    serve: 'A',
    config: { mode: 'indoor', sets_limit: 5, points_limit: 25, points_limit_last_set: 15 },
    can_undo: false,
  } as unknown as GameState;
}

describe('useAutoSetSummary', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the recap after the configured delay on a set transition', () => {
    const setSetSummary = vi.fn();
    const initial = makeState({ t1Sets: 0, t2Sets: 0 });
    const { rerender } = renderHook(
      ({ s }: { s: GameState }) =>
        useAutoSetSummary({
          state: s,
          enabled: true,
          delaySec: 5,
          durationSec: 15,
          setSetSummary,
        }),
      { initialProps: { s: initial } },
    );
    // Set-winning point lands: total sets jumps 0 → 1.
    rerender({ s: makeState({ t1Sets: 1, t2Sets: 0, currentSet: 2 }) });
    // The delay timer hasn't fired yet.
    expect(setSetSummary).not.toHaveBeenCalled();
    // Advance just shy of the delay — still nothing.
    vi.advanceTimersByTime(4999);
    expect(setSetSummary).not.toHaveBeenCalled();
    // Crossing the threshold posts ``enabled=true``.
    vi.advanceTimersByTime(1);
    expect(setSetSummary).toHaveBeenCalledWith(true);
  });

  it('dismisses the recap after the configured duration', () => {
    const setSetSummary = vi.fn();
    const initial = makeState({ t1Sets: 0, t2Sets: 0 });
    const { rerender } = renderHook(
      ({ s }: { s: GameState }) =>
        useAutoSetSummary({
          state: s,
          enabled: true,
          delaySec: 5,
          durationSec: 15,
          setSetSummary,
        }),
      { initialProps: { s: initial } },
    );
    rerender({ s: makeState({ t1Sets: 1, t2Sets: 0, currentSet: 2 }) });
    vi.advanceTimersByTime(5000); // delay → show
    expect(setSetSummary).toHaveBeenLastCalledWith(true);
    vi.advanceTimersByTime(15000); // duration → hide
    expect(setSetSummary).toHaveBeenLastCalledWith(false);
    expect(setSetSummary).toHaveBeenCalledTimes(2);
  });

  it('suppresses the show entirely when a point lands during the delay', () => {
    const setSetSummary = vi.fn();
    const initial = makeState({ t1Sets: 0, t2Sets: 0 });
    const { rerender } = renderHook(
      ({ s }: { s: GameState }) =>
        useAutoSetSummary({
          state: s,
          enabled: true,
          delaySec: 5,
          durationSec: 15,
          setSetSummary,
        }),
      { initialProps: { s: initial } },
    );
    // Set 1 ends.
    rerender({ s: makeState({ t1Sets: 1, t2Sets: 0, currentSet: 2 }) });
    // Operator scores a quick point in set 2 before the camera window closes.
    vi.advanceTimersByTime(2000);
    rerender({
      s: makeState({ t1Sets: 1, t2Sets: 0, currentSet: 2, t1Score: 1 }),
    });
    // Run the rest of what would have been the delay — show must not fire.
    vi.advanceTimersByTime(10000);
    expect(setSetSummary).not.toHaveBeenCalled();
  });

  it('dismisses immediately when a point lands during the recap display', () => {
    const setSetSummary = vi.fn();
    const initial = makeState({ t1Sets: 0, t2Sets: 0 });
    const { rerender } = renderHook(
      ({ s }: { s: GameState }) =>
        useAutoSetSummary({
          state: s,
          enabled: true,
          delaySec: 5,
          durationSec: 15,
          setSetSummary,
        }),
      { initialProps: { s: initial } },
    );
    rerender({ s: makeState({ t1Sets: 1, t2Sets: 0, currentSet: 2 }) });
    vi.advanceTimersByTime(5000); // show fires
    expect(setSetSummary).toHaveBeenLastCalledWith(true);
    // Player resumes — score lands in set 2.
    rerender({
      s: makeState({ t1Sets: 1, t2Sets: 0, currentSet: 2, t1Score: 1 }),
    });
    // Hide should be posted instantly, well before the 15s duration.
    expect(setSetSummary).toHaveBeenLastCalledWith(false);
    expect(setSetSummary).toHaveBeenCalledTimes(2);
  });

  it('cancels timers and posts hide when the set-winning point is undone', () => {
    const setSetSummary = vi.fn();
    const initial = makeState({ t1Sets: 0, t2Sets: 0 });
    const { rerender } = renderHook(
      ({ s }: { s: GameState }) =>
        useAutoSetSummary({
          state: s,
          enabled: true,
          delaySec: 5,
          durationSec: 15,
          setSetSummary,
        }),
      { initialProps: { s: initial } },
    );
    rerender({ s: makeState({ t1Sets: 1, t2Sets: 0, currentSet: 2 }) });
    vi.advanceTimersByTime(2000);
    // Operator undoes — total sets goes back to 0.
    rerender({ s: makeState({ t1Sets: 0, t2Sets: 0, currentSet: 1, t1Score: 24 }) });
    expect(setSetSummary).toHaveBeenLastCalledWith(false);
    // Pending delay timer must not still fire after the undo.
    vi.advanceTimersByTime(10000);
    // Still only the single ``false`` call from the undo path.
    expect(setSetSummary).toHaveBeenCalledTimes(1);
  });

  it('skips auto-dismiss when the set transition closes the match', () => {
    const setSetSummary = vi.fn();
    const initial = makeState({ t1Sets: 2, t2Sets: 0 });
    const { rerender } = renderHook(
      ({ s }: { s: GameState }) =>
        useAutoSetSummary({
          state: s,
          enabled: true,
          delaySec: 5,
          durationSec: 15,
          setSetSummary,
        }),
      { initialProps: { s: initial } },
    );
    // Match-winning set. ``match_finished`` is true at the moment we observe it.
    rerender({
      s: makeState({ t1Sets: 3, t2Sets: 0, matchFinished: true, currentSet: 3 }),
    });
    vi.advanceTimersByTime(5000);
    expect(setSetSummary).toHaveBeenLastCalledWith(true);
    // Long after the would-be dismiss window, the recap must stay up.
    vi.advanceTimersByTime(60000);
    expect(setSetSummary).toHaveBeenCalledTimes(1);
  });

  it('shows the recap on the same tick when delaySec is 0', () => {
    const setSetSummary = vi.fn();
    const initial = makeState({ t1Sets: 0, t2Sets: 0 });
    const { rerender } = renderHook(
      ({ s }: { s: GameState }) =>
        useAutoSetSummary({
          state: s,
          enabled: true,
          delaySec: 0,
          durationSec: 15,
          setSetSummary,
        }),
      { initialProps: { s: initial } },
    );
    rerender({ s: makeState({ t1Sets: 1, t2Sets: 0, currentSet: 2 }) });
    // Show fires synchronously — no setTimeout needed.
    expect(setSetSummary).toHaveBeenCalledWith(true);
  });

  it('drops a pending timer when the operator flips the toggle off mid-pending', () => {
    const setSetSummary = vi.fn();
    const initial = makeState({ t1Sets: 0, t2Sets: 0 });
    const { rerender } = renderHook(
      ({ s, enabled }: { s: GameState; enabled: boolean }) =>
        useAutoSetSummary({
          state: s,
          enabled,
          delaySec: 5,
          durationSec: 15,
          setSetSummary,
        }),
      { initialProps: { s: initial, enabled: true } },
    );
    // Set ends — delay timer is now armed.
    rerender({ s: makeState({ t1Sets: 1, t2Sets: 0, currentSet: 2 }), enabled: true });
    vi.advanceTimersByTime(2000);
    // Operator turns the feature off mid-delay.
    rerender({ s: makeState({ t1Sets: 1, t2Sets: 0, currentSet: 2 }), enabled: false });
    // The remainder of the delay must not fire.
    vi.advanceTimersByTime(60000);
    expect(setSetSummary).not.toHaveBeenCalled();
  });

  it('does nothing when the master toggle is off', () => {
    const setSetSummary = vi.fn();
    const initial = makeState({ t1Sets: 0, t2Sets: 0 });
    const { rerender } = renderHook(
      ({ s }: { s: GameState }) =>
        useAutoSetSummary({
          state: s,
          enabled: false,
          delaySec: 5,
          durationSec: 15,
          setSetSummary,
        }),
      { initialProps: { s: initial } },
    );
    rerender({ s: makeState({ t1Sets: 1, t2Sets: 0, currentSet: 2 }) });
    vi.advanceTimersByTime(60000);
    expect(setSetSummary).not.toHaveBeenCalled();
  });
});
