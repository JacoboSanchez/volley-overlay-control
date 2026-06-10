import { useState, useEffect, useCallback, useRef, Dispatch, SetStateAction } from 'react';
import type { GameState } from '../api/client';
import { HUD_AUTO_HIDE_MS } from '../constants';

export interface UseHudVisibilityResult {
  showControls: boolean;
  setShowControls: Dispatch<SetStateAction<boolean>>;
}

/**
 * HUD control-bar visibility: the inactivity auto-hide timer plus the
 * reveal rules (viewport gains room, match flips back to pending, the
 * set-summary recap goes live).
 */
export function useHudVisibility({
  hasRoomForPersistentControls,
  activeTab,
  state,
}: {
  hasRoomForPersistentControls: boolean;
  activeTab: 'scoreboard' | 'config';
  state: GameState | null;
}): UseHudVisibilityResult {
  const [showControls, setShowControls] = useState(true);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const resetHideTimer = useCallback(() => {
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    hideTimerRef.current = setTimeout(() => setShowControls(false), HUD_AUTO_HIDE_MS);
  }, []);

  // Reveal the bar when the viewport gains room for it (e.g. phone→tablet
  // resize). Kept in its own effect so the manual hide toggle still works
  // on tablets — the auto-hide effect below would otherwise re-show it on
  // every showControls change.
  useEffect(() => {
    if (hasRoomForPersistentControls) {
      setShowControls(true);
    }
  }, [hasRoomForPersistentControls]);

  // Reveal the bar whenever the match flips back to the pending state
  // (initial load or post-reset) so the operator can see the Start button.
  const matchStartedAt = state?.match_started_at ?? null;
  useEffect(() => {
    if (matchStartedAt == null) {
      setShowControls(true);
    }
  }, [matchStartedAt, setShowControls]);

  // Depend on the two state fields the effect actually reads, not the
  // ``state`` object itself — its identity changes on every WebSocket
  // push and would re-arm the effect on every scored point. Operator
  // taps still reset the countdown via the pointerdown listener.
  const setSummaryActive = state?.set_summary ?? false;
  useEffect(() => {
    // On tablets/desktops the control bar fits without covering scoreboard
    // elements, so skip the inactivity timer entirely.
    if (hasRoomForPersistentControls) return;
    // Keep the bar visible while the match is pending — only arm the
    // inactivity timer once ``match_started_at`` is stamped. Also covers
    // the pre-init case where ``state`` itself is still null.
    if (matchStartedAt == null) return;
    // When the set-summary recap is live, the operator must be able to
    // turn it off in one tap — never auto-hide the HUD.
    if (setSummaryActive) {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
      setShowControls(true);
      return;
    }
    if (showControls && activeTab === 'scoreboard') {
      resetHideTimer();
      window.addEventListener('pointerdown', resetHideTimer, { passive: true });
    }
    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
      window.removeEventListener('pointerdown', resetHideTimer);
    };
  }, [
    showControls,
    activeTab,
    matchStartedAt,
    setSummaryActive,
    resetHideTimer,
    hasRoomForPersistentControls,
  ]);

  return { showControls, setShowControls };
}
