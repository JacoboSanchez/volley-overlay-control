import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ACTION_HISTORY_LIMIT } from '../constants';

export type Team = 1 | 2;

export type ActionEntry = {
  type: 'point' | 'set' | 'timeout';
  team: Team;
};

export interface UseActionHistory {
  history: readonly ActionEntry[];
  canUndo: boolean;
  /** Append a forward action to the stack, evicting the oldest entry if the
   *  cap is reached. */
  push: (entry: ActionEntry) => void;
  /** Pop the most recent entry. Returns the popped entry so the caller can
   *  dispatch the matching API undo, or `null` if the stack is empty.
   *  Side effects must run *after* this returns — never inside a state
   *  updater (React contract; StrictMode double-invokes updaters in dev). */
  undoLast: () => ActionEntry | null;
  /** Remove the most recent entry whose `type` and `team` match (used by
   *  the double-tap gestures, which are themselves an undo and so consume
   *  one entry). No-op when no match is found. */
  popMatching: (type: ActionEntry['type'], team: Team) => void;
  /** Drop everything (e.g. on session reset / logout). */
  clear: () => void;
}

/**
 * Bounded client-side history of the user's forward actions, used to drive
 * the undo button and reconcile double-tap gestures.
 *
 * State is mirrored into a ref so action functions can read the latest
 * value synchronously even between React batches — important when a user
 * fires the undo button repeatedly faster than React can re-render.
 */
export function useActionHistory(): UseActionHistory {
  const [history, setHistory] = useState<readonly ActionEntry[]>([]);
  const historyRef = useRef<readonly ActionEntry[]>(history);

  useEffect(() => {
    historyRef.current = history;
  }, [history]);

  const push = useCallback((entry: ActionEntry) => {
    const next = historyRef.current.length >= ACTION_HISTORY_LIMIT
      ? historyRef.current.slice(-(ACTION_HISTORY_LIMIT - 1))
      : historyRef.current;
    historyRef.current = [...next, entry];
    setHistory(historyRef.current);
  }, []);

  const undoLast = useCallback((): ActionEntry | null => {
    const h = historyRef.current;
    if (h.length === 0) return null;
    const popped = h[h.length - 1];
    historyRef.current = h.slice(0, -1);
    setHistory(historyRef.current);
    return popped;
  }, []);

  const popMatching = useCallback((type: ActionEntry['type'], team: Team) => {
    const h = historyRef.current;
    for (let i = h.length - 1; i >= 0; i--) {
      if (h[i].type === type && h[i].team === team) {
        historyRef.current = [...h.slice(0, i), ...h.slice(i + 1)];
        setHistory(historyRef.current);
        return;
      }
    }
  }, []);

  const clear = useCallback(() => {
    historyRef.current = [];
    setHistory([]);
  }, []);

  // Memoise the returned object so consumers that depend on the whole
  // hook value (rather than individual functions) only see a new
  // identity when `history` actually changes — the action callbacks
  // themselves are already stable via useCallback([]).
  return useMemo(
    () => ({
      history,
      canUndo: history.length > 0,
      push,
      undoLast,
      popMatching,
      clear,
    }),
    [history, push, undoLast, popMatching, clear],
  );
}
