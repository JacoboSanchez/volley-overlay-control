import { useCallback, useRef } from 'react';
import { useSettings } from './useSettings';

/**
 * Pre-defined vibration patterns. Numbers are milliseconds; arrays
 * alternate vibrate/pause. Kept short and on the muscle-memory side
 * — anything longer than ~80 ms feels like a notification rather
 * than a control acknowledgement.
 */
export const HAPTIC_PATTERNS = {
  /** Single-tap acknowledgement (button press). */
  tap: 10,
  /** Double-tap or other deliberate gesture confirmation. */
  confirm: [10, 30, 10] as const,
  /** Set point — two-pulse cue. */
  alert: [15, 35, 15] as const,
  /** Match point — heavier alert. */
  matchPoint: [20, 40, 20, 40, 20] as const,
  /** Match finished. */
  finished: [40, 60, 40] as const,
} as const;

export type HapticPatternKey = keyof typeof HAPTIC_PATTERNS;
export type HapticPattern = number | readonly number[];

export interface UseHapticsResult {
  /**
   * Fires the named pattern through ``navigator.vibrate`` if the
   * device supports it and the operator has not opted out via
   * ``settings.haptics``. Throttled internally so a runaway
   * re-render loop can't replay the same pattern repeatedly.
   */
  pulse: (pattern: HapticPatternKey | HapticPattern) => void;
  /** ``true`` when the runtime advertises ``navigator.vibrate``. */
  supported: boolean;
}

const MIN_INTERVAL_MS = 50;

function readPattern(p: HapticPatternKey | HapticPattern): number | number[] {
  if (typeof p === 'string') {
    const preset = HAPTIC_PATTERNS[p];
    return typeof preset === 'number' ? preset : Array.from(preset);
  }
  if (typeof p === 'number') return p;
  return Array.from(p);
}

/**
 * Thin wrapper around the Vibration API that respects the
 * ``haptics`` user setting and silently no-ops on unsupported
 * runtimes (desktop browsers, iOS Safari prior to 18.4, JSDOM, …).
 * Centralised so the call site never has to repeat the feature
 * detect or the user-setting check.
 */
export function useHaptics(): UseHapticsResult {
  const { settings } = useSettings();
  const lastFire = useRef(0);

  const supported = typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function';

  const pulse = useCallback(
    (pattern: HapticPatternKey | HapticPattern) => {
      if (!settings.haptics || !supported) return;
      const now = Date.now();
      if (now - lastFire.current < MIN_INTERVAL_MS) return;
      lastFire.current = now;
      try {
        navigator.vibrate(readPattern(pattern));
      } catch {
        // Some runtimes throw on long patterns or permission policy
        // violations; treat them as no-op rather than escalate.
      }
    },
    [settings.haptics, supported],
  );

  return { pulse, supported };
}
