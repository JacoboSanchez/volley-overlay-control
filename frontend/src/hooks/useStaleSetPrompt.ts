import { useState, useEffect, useRef } from 'react';
import type { GameState } from '../api/client';

export interface UseStaleSetPromptResult {
  stalePromptOpen: boolean;
  setStalePromptOpen: (open: boolean) => void;
}

/**
 * Stale-set prompt: if the operator opens the control UI on a
 * session whose current set has been live for more than an hour
 * the marker was probably abandoned (the operator forgot to reset
 * it). Surface a one-shot dialog asking whether to reset or keep
 * going. The ``firedRef`` guard makes sure we only ever fire once
 * per page load so a refusal isn't re-asked while the WS keeps
 * streaming the same stale state.
 */
export function useStaleSetPrompt({
  state,
  thresholdMinutes,
}: {
  state: GameState | null;
  thresholdMinutes: number | undefined;
}): UseStaleSetPromptResult {
  const [stalePromptOpen, setStalePromptOpen] = useState(false);
  const stalePromptFiredRef = useRef(false);
  useEffect(() => {
    if (stalePromptFiredRef.current) return;
    if (!state) return;
    if (state.match_finished) return;
    // Threshold is configured server-side via the
    // ``STALE_SET_THRESHOLD_MINUTES`` env var and arrives on the
    // ``/api/v1/app-config`` response. ``0`` disables the prompt.
    const thresholdSec = (thresholdMinutes ?? 60) * 60;
    if (thresholdSec <= 0) return;
    const startedAt = state.current_set_started_at;
    if (typeof startedAt !== 'number' || startedAt <= 0) return;
    // Prefer the server's wall clock when the payload includes it
    // (every fresh state response carries ``server_time``), so the
    // stale-set threshold isn't tripped by a client whose system
    // clock is hours off. Fall back to ``Date.now()`` on the rare
    // legacy payload that omits the field.
    const nowSec =
      typeof state.server_time === 'number' && state.server_time > 0
        ? state.server_time
        : Date.now() / 1000;
    const elapsed = nowSec - startedAt;
    if (elapsed > thresholdSec) {
      stalePromptFiredRef.current = true;
      setStalePromptOpen(true);
    }
  }, [state, thresholdMinutes]);

  return { stalePromptOpen, setStalePromptOpen };
}
