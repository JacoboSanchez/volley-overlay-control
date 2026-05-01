import { useEffect, useRef, useState } from 'react';
import type { GameState } from '../api/client';

/**
 * Indoor mode side-switch alert for the deciding-set midpoint
 * (FIVB rule: switch when the leading team first reaches 8 of 15).
 *
 * The trigger is *transient* — it fires the moment the leader crosses
 * the midpoint and clears the next time the score changes — so we
 * compute it from the diff between consecutive game states rather than
 * from the current snapshot alone. Each tab tracks its own ``prev``
 * state, which means a page refresh exactly at the trigger score
 * silently misses the alert; that's acceptable since the operator
 * would have already switched in that scenario.
 *
 * Returns ``false`` outside indoor mode, outside the deciding set, or
 * when the match has already finished.
 */
export function useIndoorMidpointAlert(
  state: GameState | null | undefined,
  currentSet: number,
  setsLimit: number,
): boolean {
  const prevScoreRef = useRef<{ t1: number; t2: number; set: number } | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const mode = state?.config?.mode as string | undefined;
    const lastSetTarget = state?.config?.points_limit_last_set as number | undefined;
    const isLastSet = setsLimit > 0 && currentSet === setsLimit;
    const eligible =
      !!state
      && !state.match_finished
      && mode === 'indoor'
      && isLastSet
      && typeof lastSetTarget === 'number'
      && lastSetTarget > 0;

    if (!eligible) {
      // Reset so a later eligible window (entering the deciding set)
      // starts fresh — otherwise a stale ``prev`` from set 4 would
      // skew the diff in set 5.
      setPending(false);
      prevScoreRef.current = null;
      return;
    }

    const t1 = (state.team_1.scores[`set_${currentSet}`] as number | undefined) ?? 0;
    const t2 = (state.team_2.scores[`set_${currentSet}`] as number | undefined) ?? 0;
    const midpoint = Math.ceil(lastSetTarget / 2);
    const prev = prevScoreRef.current;

    // First eligible state (or a set transition): anchor ``prev``
    // without firing. Refreshing the page exactly at 8-X would
    // otherwise look like a fresh trigger even though no point was
    // actually scored in this session.
    if (!prev || prev.set !== currentSet) {
      prevScoreRef.current = { t1, t2, set: currentSet };
      setPending(false);
      return;
    }

    const scoreChanged = prev.t1 !== t1 || prev.t2 !== t2;
    if (!scoreChanged) {
      // Unrelated state churn (visibility toggle, etc.) — leave the
      // current ``pending`` value untouched so the alert keeps showing
      // until the next actual point is scored.
      return;
    }

    // Trigger: leader just crossed the midpoint. On every other score
    // change the alert clears, so it is genuinely transient.
    const currMax = Math.max(t1, t2);
    const prevMax = Math.max(prev.t1, prev.t2);
    setPending(currMax === midpoint && prevMax < midpoint);
    prevScoreRef.current = { t1, t2, set: currentSet };
  }, [state, currentSet, setsLimit]);

  return pending;
}
