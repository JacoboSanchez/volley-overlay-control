import { useRef, TouchEvent as ReactTouchEvent } from 'react';

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

export function useSwipeNavigation({
  onSwipeLeft,
  onSwipeRight,
  threshold = 80,
  maxVerticalRatio = 0.5,
  ignoreSelector = DEFAULT_IGNORE_SELECTOR,
}: UseSwipeNavigationOptions): SwipeHandlers {
  const startRef = useRef<SwipeStart | null>(null);

  const onTouchStart = (e: ReactTouchEvent<HTMLElement>) => {
    if (e.touches.length !== 1) {
      startRef.current = null;
      return;
    }
    const touch = e.touches[0];
    const target = e.target as Element | null;
    const ignored = !!(target && typeof target.closest === 'function' && target.closest(ignoreSelector));
    startRef.current = { x: touch.clientX, y: touch.clientY, ignored };
  };

  const onTouchMove = (e: ReactTouchEvent<HTMLElement>) => {
    if (e.touches.length > 1) startRef.current = null;
  };

  const onTouchEnd = (e: ReactTouchEvent<HTMLElement>) => {
    const start = startRef.current;
    startRef.current = null;
    if (!start || start.ignored) return;
    const touch = e.changedTouches[0];
    if (!touch) return;
    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    if (Math.abs(dx) < threshold) return;
    if (Math.abs(dy) > Math.abs(dx) * maxVerticalRatio) return;
    if (dx < 0) onSwipeLeft?.();
    else onSwipeRight?.();
  };

  const onTouchCancel = () => {
    startRef.current = null;
  };

  return { onTouchStart, onTouchMove, onTouchEnd, onTouchCancel };
}
