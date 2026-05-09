import { useEffect, useRef } from 'react';
import type { GameState } from '../api/client';
import { pickAlert, type AlertSpec } from '../components/MatchAlertIndicator';
import { useHaptics, type HapticPatternKey } from './useHaptics';

const PATTERN_FOR: Record<AlertSpec['kind'], HapticPatternKey> = {
  finished: 'finished',
  'match-point': 'matchPoint',
  'set-point': 'alert',
};

function alertId(alert: AlertSpec | null): string {
  if (!alert) return '';
  return `${alert.kind}:${alert.team ?? ''}`;
}

/**
 * Fires a haptic pulse whenever ``state`` transitions into a new
 * match-alert (set point, match point, finished). Re-entries into
 * the same alert (e.g. the WebSocket re-broadcasting an unchanged
 * state) are suppressed by comparing the resolved alert identity
 * against the previous render.
 *
 * Centralised here rather than inlined in App.tsx so the same
 * trigger surface can later drive sound cues / coachmarks without
 * duplicating the transition-detection logic.
 */
export function useMatchAlertHaptics(state: GameState | null | undefined): void {
  const { pulse } = useHaptics();
  const lastAlert = useRef<string>('');

  useEffect(() => {
    const alert = pickAlert(state ?? null);
    const id = alertId(alert);
    if (id === lastAlert.current) return;
    lastAlert.current = id;
    if (!alert) return;
    pulse(PATTERN_FOR[alert.kind]);
  }, [state, pulse]);
}
