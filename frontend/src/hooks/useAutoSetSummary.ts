import { useEffect, useRef } from 'react';
import type { GameState } from '../api/client';

export interface UseAutoSetSummaryOptions {
  /**
   * The live game state. Pass ``confirmedState`` (not ``state``) so the
   * detector ignores optimistic predictions — the set transition has
   * to be authoritative before we cover the broadcast with a recap.
   */
  state: GameState | null;
  /**
   * Master enable. The hook is a no-op when ``false`` — combine the
   * operator's ``setSummaryEnabled`` + ``autoShowSetSummary`` toggles
   * at the call site.
   */
  enabled: boolean;
  /**
   * Seconds to wait between the set-winning point and the recap
   * appearing. ``0`` shows the recap on the same tick.
   */
  delaySec: number;
  /**
   * Seconds the recap stays visible before auto-dismiss. The
   * dismiss is skipped on match end (final set transition) so the
   * end-of-match recap stays up until the operator clears it.
   */
  durationSec: number;
  /**
   * Toggle the server-side set-summary flag (delegate to
   * ``actions.setSetSummary`` from ``useGameState``). Errors are
   * intentionally swallowed inside the hook — the recap is best-
   * effort polish and a transient API hiccup shouldn't crash the
   * scoreboard.
   */
  setSetSummary: (v: boolean) => Promise<unknown> | void;
}

function totalSets(state: GameState | null): number | null {
  if (!state) return null;
  return (state.team_1?.sets ?? 0) + (state.team_2?.sets ?? 0);
}

function currentSetScore(state: GameState | null): number | null {
  if (!state) return null;
  const setNum = state.current_set || (state.team_1?.sets ?? 0) + (state.team_2?.sets ?? 0) + 1;
  const key = `set_${setNum}`;
  const t1 = state.team_1?.scores as Record<string, unknown> | undefined;
  const t2 = state.team_2?.scores as Record<string, unknown> | undefined;
  const t1Score = typeof t1?.[key] === 'number' ? (t1[key] as number) : 0;
  const t2Score = typeof t2?.[key] === 'number' ? (t2[key] as number) : 0;
  return t1Score + t2Score;
}

/**
 * Auto-trigger the set-summary recap overlay on each set transition.
 *
 * Wires two timers around the set-winning point:
 *
 *   final point ──[ delaySec ]──▶ recap shown ──[ durationSec ]──▶ recap hidden
 *
 * Both timers are cancellable:
 * - Score advances during the delay → show is suppressed.
 * - Score advances during the recap → recap is dismissed immediately.
 * - Operator undoes the set-winning point → timers clear, hide is posted.
 * - Final set transition wins the match → recap shows but auto-dismiss
 *   is skipped so the operator dismisses the end-of-match recap on
 *   their own.
 */
export function useAutoSetSummary(opts: UseAutoSetSummaryOptions): void {
  const { state, enabled, delaySec, durationSec, setSetSummary } = opts;

  const delayTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevTotalSets = useRef<number | null>(null);
  const prevCurrentScore = useRef<number | null>(null);
  const setSetSummaryRef = useRef(setSetSummary);

  // Keep the latest callback in a ref so timer fires use the current
  // closure (not the one captured when the timer was scheduled).
  useEffect(() => {
    setSetSummaryRef.current = setSetSummary;
  }, [setSetSummary]);

  const clearAll = () => {
    if (delayTimer.current !== null) {
      clearTimeout(delayTimer.current);
      delayTimer.current = null;
    }
    if (dismissTimer.current !== null) {
      clearTimeout(dismissTimer.current);
      dismissTimer.current = null;
    }
  };

  useEffect(() => {
    if (!state) return;
    const ts = totalSets(state);
    const cs = currentSetScore(state);
    const prevTs = prevTotalSets.current;
    const prevCs = prevCurrentScore.current;
    prevTotalSets.current = ts;
    prevCurrentScore.current = cs;

    if (!enabled) {
      // Master toggle off: drop any pending timers so a delayed show
      // can't fire after the operator opted out. We keep tracking the
      // prev refs above so flipping the toggle back on mid-match
      // doesn't re-fire from a stale baseline. The currently visible
      // recap (if any) is left alone — the operator can dismiss it
      // manually via the existing toggle.
      clearAll();
      return;
    }

    if (prevTs === null || prevCs === null) {
      // First authoritative state seen — baseline the refs but do not
      // fire (a mid-match page refresh shouldn't slam the recap up).
      return;
    }

    // Operator undid the set-winning point. Total sets dropped — clear
    // any pending timers and force-hide so a stale show timer can't
    // appear half a second after the undo.
    if (ts !== null && ts < prevTs) {
      clearAll();
      try {
        setSetSummaryRef.current(false);
      } catch {
        /* best-effort */
      }
      return;
    }

    // Set-transition edge.
    if (ts !== null && ts > prevTs) {
      clearAll();
      const isMatchEnd = !!state.match_finished;
      const show = () => {
        delayTimer.current = null;
        try {
          setSetSummaryRef.current(true);
        } catch {
          /* best-effort */
        }
        if (!isMatchEnd && durationSec > 0) {
          dismissTimer.current = setTimeout(() => {
            dismissTimer.current = null;
            try {
              setSetSummaryRef.current(false);
            } catch {
              /* best-effort */
            }
          }, durationSec * 1000);
        }
      };
      if (delaySec > 0) {
        delayTimer.current = setTimeout(show, delaySec * 1000);
      } else {
        show();
      }
      return;
    }

    // Resumed-play edge: a new point landed in the current set while
    // a timer was pending. If the show hasn't fired yet, suppress it
    // entirely; if the recap is already up, dismiss it immediately.
    if (cs !== null && prevCs !== null && cs > prevCs) {
      if (delayTimer.current !== null) {
        clearTimeout(delayTimer.current);
        delayTimer.current = null;
        return;
      }
      if (dismissTimer.current !== null) {
        clearTimeout(dismissTimer.current);
        dismissTimer.current = null;
        try {
          setSetSummaryRef.current(false);
        } catch {
          /* best-effort */
        }
      }
    }
  }, [state, enabled, delaySec, durationSec]);

  // Cleanup on unmount.
  useEffect(() => {
    return () => clearAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
