import { useMemo, useRef, TouchEvent as ReactTouchEvent } from 'react';

export interface SwipeHandlers {
  onTouchStart: (e: ReactTouchEvent<HTMLElement>) => void;
  onTouchMove: (e: ReactTouchEvent<HTMLElement>) => void;
  onTouchEnd: (e: ReactTouchEvent<HTMLElement>) => void;
  onTouchCancel: (e: ReactTouchEvent<HTMLElement>) => void;
}

export interface UseSwipeNavigationOptions {
  onSwipeLeft?: () => void;
  onSwipeRight?: () => void;
  /** Minimum horizontal distance in pixels to register a swipe. */
  threshold?: number;
  /**
   * Maximum allowed |dy|/|dx| ratio. Above this, the gesture is treated as a
   * vertical scroll and ignored.
   */
  maxVerticalRatio?: number;
  /**
   * CSS selector matched against the touchstart target (and its ancestors).
   * If it matches, the gesture is skipped so interactive elements such as
   * buttons, inputs, and sliders keep their default behavior.
   */
  ignoreSelector?: string;
}

export const DEFAULT_IGNORE_SELECTORS = [
  'button',
  'input',
  'select',
  'textarea',
  'a',
  'label',
  '[role="button"]',
  '[role="slider"]',
  '[role="checkbox"]',
  '[role="switch"]',
  '[role="tab"]',
  '[role="menuitem"]',
  '[contenteditable="true"]',
];

const DEFAULT_IGNORE_SELECTOR = DEFAULT_IGNORE_SELECTORS.join(',');

interface SwipeStart {
  x: number;
  y: number;
  ignored: boolean;
}

interface ResolvedOptions {
  onSwipeLeft?: () => void;
  onSwipeRight?: () => void;
  threshold: number;
  maxVerticalRatio: number;
  ignoreSelector: string;
}

export function useSwipeNavigation({
  onSwipeLeft,
  onSwipeRight,
  threshold = 80,
  maxVerticalRatio = 0.5,
  ignoreSelector = DEFAULT_IGNORE_SELECTOR,
}: UseSwipeNavigationOptions): SwipeHandlers {
  const startRef = useRef<SwipeStart | null>(null);
  // "Latest ref" pattern: handlers read from optionsRef.current so the
  // returned SwipeHandlers object can stay identity-stable across renders.
  const optionsRef = useRef<ResolvedOptions>({ onSwipeLeft, onSwipeRight, threshold, maxVerticalRatio, ignoreSelector });
  optionsRef.current = { onSwipeLeft, onSwipeRight, threshold, maxVerticalRatio, ignoreSelector };

  return useMemo<SwipeHandlers>(() => ({
    onTouchStart: (e) => {
      if (e.touches.length !== 1) {
        startRef.current = null;
        return;
      }
      const touch = e.touches[0];
      const target = e.target as Node | null;
      const element = target instanceof Element ? target : target?.parentElement ?? null;
      const { ignoreSelector: sel } = optionsRef.current;
      const ignored = !!(element && typeof element.closest === 'function' && element.closest(sel));
      startRef.current = { x: touch.clientX, y: touch.clientY, ignored };
    },
    onTouchMove: (e) => {
      if (e.touches.length > 1) startRef.current = null;
    },
    onTouchEnd: (e) => {
      const start = startRef.current;
      startRef.current = null;
      if (!start || start.ignored) return;
      const touch = e.changedTouches[0];
      if (!touch) return;
      const { threshold: th, maxVerticalRatio: ratio, onSwipeLeft: left, onSwipeRight: right } = optionsRef.current;
      const dx = touch.clientX - start.x;
      const dy = touch.clientY - start.y;
      if (Math.abs(dx) < th) return;
      if (Math.abs(dy) > Math.abs(dx) * ratio) return;
      if (dx < 0) left?.();
      else right?.();
    },
    onTouchCancel: () => {
      startRef.current = null;
    },
  }), []);
}
