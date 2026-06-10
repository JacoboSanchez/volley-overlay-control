import { useState, useEffect, useCallback } from 'react';
import type { GameState } from '../api/client';
import type { SetSetting } from './useSettings';

export interface UseCoachmarkResult {
  coachmarkOpen: boolean;
  handleCoachmarkDismiss: () => void;
}

/**
 * First-use gesture tour. Fires once the first authoritative state
 * lands and the operator hasn't dismissed the tour yet. The dismissal
 * flips ``settings.gestureTourSeen`` to ``true`` and persists across
 * sessions; the Behavior section exposes a "Replay tour" affordance
 * that flips it back to ``false`` to re-open this on demand without a
 * page refresh.
 */
export function useCoachmark({
  state,
  gestureTourSeen,
  setSetting,
}: {
  state: GameState | null;
  gestureTourSeen: boolean;
  setSetting: SetSetting;
}): UseCoachmarkResult {
  const [coachmarkOpen, setCoachmarkOpen] = useState(false);

  // Open the coachmark whenever the operator has unseen-tour state
  // and authoritative game state is available. The condition stops
  // re-firing once dismissal flips ``gestureTourSeen`` to ``true``
  // — on the next dep change the effect runs, the guard fails, and
  // the open state stays as the operator left it.
  useEffect(() => {
    if (state && !gestureTourSeen) {
      setCoachmarkOpen(true);
    }
  }, [state, gestureTourSeen]);

  const handleCoachmarkDismiss = useCallback(() => {
    setCoachmarkOpen(false);
    setSetting('gestureTourSeen', true);
  }, [setSetting]);

  return { coachmarkOpen, handleCoachmarkDismiss };
}
