import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useIndoorMidpointAlert } from '../hooks/useIndoorMidpointAlert';
import type { GameState } from '../api/client';

function makeState(overrides: Partial<GameState> & {
  t1?: number;
  t2?: number;
  set?: number;
  mode?: 'indoor' | 'beach';
  pointsLimitLastSet?: number;
  matchFinished?: boolean;
}): GameState {
  const {
    t1 = 0, t2 = 0, set = 5,
    mode = 'indoor', pointsLimitLastSet = 15,
    matchFinished = false,
  } = overrides;
  return {
    team_1: { sets: 0, timeouts: 0, serving: true, scores: { [`set_${set}`]: t1 } },
    team_2: { sets: 0, timeouts: 0, serving: false, scores: { [`set_${set}`]: t2 } },
    visible: true,
    simple_mode: false,
    match_finished: matchFinished,
    current_set: set,
    serve: '1',
    config: {
      mode,
      sets_limit: 5,
      points_limit: 25,
      points_limit_last_set: pointsLimitLastSet,
    },
    can_undo: false,
  } as unknown as GameState;
}

describe('useIndoorMidpointAlert', () => {
  it('returns false on the first observed state (no prior to diff against)', () => {
    const { result } = renderHook(() =>
      useIndoorMidpointAlert(makeState({ t1: 8, t2: 0, set: 5 }), 5, 5),
    );
    expect(result.current).toBe(false);
  });

  it('returns false outside the deciding set', () => {
    const initial = makeState({ t1: 7, t2: 0, set: 4 });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useIndoorMidpointAlert(s, 4, 5),
      { initialProps: { s: initial } },
    );
    rerender({ s: makeState({ t1: 8, t2: 0, set: 4 }) });
    expect(result.current).toBe(false);
  });

  it('returns false in beach mode (frontend rule is indoor-only)', () => {
    const initial = makeState({ t1: 7, t2: 0, set: 5, mode: 'beach' });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useIndoorMidpointAlert(s, 5, 5),
      { initialProps: { s: initial } },
    );
    rerender({ s: makeState({ t1: 8, t2: 0, set: 5, mode: 'beach' }) });
    expect(result.current).toBe(false);
  });

  it('fires when leader transitions across the midpoint', () => {
    const initial = makeState({ t1: 7, t2: 0, set: 5 });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useIndoorMidpointAlert(s, 5, 5),
      { initialProps: { s: initial } },
    );
    expect(result.current).toBe(false); // first observation anchors prev
    rerender({ s: makeState({ t1: 8, t2: 0, set: 5 }) });
    expect(result.current).toBe(true);
  });

  it('clears on the next score change (8-0 → 8-1)', () => {
    const initial = makeState({ t1: 7, t2: 0, set: 5 });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useIndoorMidpointAlert(s, 5, 5),
      { initialProps: { s: initial } },
    );
    rerender({ s: makeState({ t1: 8, t2: 0, set: 5 }) });
    expect(result.current).toBe(true);
    rerender({ s: makeState({ t1: 8, t2: 1, set: 5 }) });
    expect(result.current).toBe(false);
  });

  it('clears when leader scores past the midpoint (8-0 → 9-0)', () => {
    const initial = makeState({ t1: 7, t2: 0, set: 5 });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useIndoorMidpointAlert(s, 5, 5),
      { initialProps: { s: initial } },
    );
    rerender({ s: makeState({ t1: 8, t2: 0, set: 5 }) });
    expect(result.current).toBe(true);
    rerender({ s: makeState({ t1: 9, t2: 0, set: 5 }) });
    expect(result.current).toBe(false);
  });

  it('does not fire when entering the deciding set already past the midpoint', () => {
    // Operator opens the app mid-set 5 at 8-3 (page refresh, late join…).
    // Without a prior in-session ``prev`` we don't synthesise the trigger.
    const { result } = renderHook(() =>
      useIndoorMidpointAlert(makeState({ t1: 8, t2: 3, set: 5 }), 5, 5),
    );
    expect(result.current).toBe(false);
  });

  it('rounds the midpoint up for odd targets (13 → 7)', () => {
    const initial = makeState({ t1: 6, t2: 0, set: 5, pointsLimitLastSet: 13 });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useIndoorMidpointAlert(s, 5, 5),
      { initialProps: { s: initial } },
    );
    rerender({ s: makeState({ t1: 7, t2: 0, set: 5, pointsLimitLastSet: 13 }) });
    expect(result.current).toBe(true);
  });

  it('survives unrelated state churn between point changes', () => {
    // Visibility toggle and the like push a new state object without
    // changing the score — the alert must keep showing until the next
    // actual point.
    const initial = makeState({ t1: 7, t2: 0, set: 5 });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useIndoorMidpointAlert(s, 5, 5),
      { initialProps: { s: initial } },
    );
    rerender({ s: makeState({ t1: 8, t2: 0, set: 5 }) });
    expect(result.current).toBe(true);
    // Same scores, different state object identity (e.g. visibility flag).
    rerender({ s: { ...makeState({ t1: 8, t2: 0, set: 5 }), visible: false } });
    expect(result.current).toBe(true);
  });

  it('clears once the match has finished', () => {
    const initial = makeState({ t1: 7, t2: 0, set: 5 });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useIndoorMidpointAlert(s, 5, 5),
      { initialProps: { s: initial } },
    );
    rerender({ s: makeState({ t1: 8, t2: 0, set: 5 }) });
    expect(result.current).toBe(true);
    rerender({ s: makeState({ t1: 15, t2: 7, set: 5, matchFinished: true }) });
    expect(result.current).toBe(false);
  });

  it('does not refire after a non-trigger change at the same score', () => {
    // After 8-0 → 8-1 the alert clears. Re-emitting 8-1 (e.g. a
    // ``get_state`` poll) must not turn it back on.
    const initial = makeState({ t1: 7, t2: 0, set: 5 });
    const { result, rerender } = renderHook(
      ({ s }: { s: GameState }) => useIndoorMidpointAlert(s, 5, 5),
      { initialProps: { s: initial } },
    );
    rerender({ s: makeState({ t1: 8, t2: 0, set: 5 }) });
    rerender({ s: makeState({ t1: 8, t2: 1, set: 5 }) });
    rerender({ s: makeState({ t1: 8, t2: 1, set: 5 }) });
    expect(result.current).toBe(false);
  });

  it('handles the null-state case without throwing', () => {
    const { result } = renderHook(() =>
      useIndoorMidpointAlert(null, 5, 5),
    );
    expect(result.current).toBe(false);
  });
});

// ``act`` is exported for parity with other hook tests; explicit usage
// isn't needed here because ``rerender`` already wraps state updates.
void act;
