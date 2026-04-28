import {
  useCallback,
  useEffect,
  useRef,
  KeyboardEvent,
  MouseEvent,
  TouchEvent,
} from 'react';
import { DOUBLE_TAP_MS, LONG_PRESS_MS } from '../constants';

export interface UseDoubleTapOptions {
  onClick?: () => void;
  onDoubleTap?: () => void;
  onLongPress?: () => void;
  longPressMs?: number;
  doubleTapMs?: number;
}

export type PressEvent =
  | MouseEvent<HTMLElement>
  | TouchEvent<HTMLElement>;

export interface PressHandlers {
  onMouseDown: (e: MouseEvent<HTMLElement>) => void;
  onMouseUp: (e: MouseEvent<HTMLElement>) => void;
  onMouseLeave: (e: MouseEvent<HTMLElement>) => void;
  onTouchStart: (e: TouchEvent<HTMLElement>) => void;
  onTouchEnd: (e: TouchEvent<HTMLElement>) => void;
  onTouchMove: (e: TouchEvent<HTMLElement>) => void;
  onTouchCancel: (e: TouchEvent<HTMLElement>) => void;
  onKeyDown: (e: KeyboardEvent<HTMLElement>) => void;
  onKeyUp: (e: KeyboardEvent<HTMLElement>) => void;
}

/**
 * Press-gesture detector with single-tap, double-tap and (optional)
 * long-press. Activated by mouse, touch, or keyboard (Enter / Space).
 *
 * Gesture priority: long-press > double-tap > single-tap.
 *
 * Double-tap is detected at press-start (touchstart / mousedown / keydown)
 * because that event fires immediately and reliably, whereas the
 * corresponding "release" timing varies with how long the user holds the
 * input.
 *
 * If `onDoubleTap` is not provided, `onClick` fires immediately on
 * press-end (no single-tap delay).
 */
export function useDoubleTap({
  onClick,
  onDoubleTap,
  onLongPress,
  longPressMs = LONG_PRESS_MS,
  doubleTapMs = DOUBLE_TAP_MS,
}: UseDoubleTapOptions): PressHandlers {
  const pressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isLongPress = useRef(false);
  const lastTapTime = useRef(0);
  const singleTapTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const doubleTapPending = useRef(false);
  const touchActive = useRef(false);
  const keyActive = useRef(false);

  useEffect(() => {
    return () => {
      if (pressTimer.current) {
        clearTimeout(pressTimer.current);
        pressTimer.current = null;
      }
      if (singleTapTimer.current) {
        clearTimeout(singleTapTimer.current);
        singleTapTimer.current = null;
      }
    };
  }, []);

  // Core press-start logic, shared by mouse / touch / keyboard.
  const beginPress = useCallback(() => {
    isLongPress.current = false;

    const now = Date.now();
    const gap = now - lastTapTime.current;
    if (onDoubleTap && gap > 0 && gap < doubleTapMs) {
      doubleTapPending.current = true;
      if (singleTapTimer.current) {
        clearTimeout(singleTapTimer.current);
        singleTapTimer.current = null;
      }
    } else {
      doubleTapPending.current = false;
    }
    lastTapTime.current = now;

    if (onLongPress) {
      pressTimer.current = setTimeout(() => {
        isLongPress.current = true;
        doubleTapPending.current = false;
        if (singleTapTimer.current) {
          clearTimeout(singleTapTimer.current);
          singleTapTimer.current = null;
        }
        lastTapTime.current = 0;
        onLongPress();
      }, longPressMs);
    }
  }, [onDoubleTap, onLongPress, doubleTapMs, longPressMs]);

  // Core press-end logic, shared by mouse / touch / keyboard.
  const finishPress = useCallback(() => {
    if (pressTimer.current) {
      clearTimeout(pressTimer.current);
      pressTimer.current = null;
    }
    if (isLongPress.current) return;

    if (doubleTapPending.current) {
      doubleTapPending.current = false;
      lastTapTime.current = 0;
      onDoubleTap?.();
    } else if (onDoubleTap) {
      singleTapTimer.current = setTimeout(() => {
        singleTapTimer.current = null;
        onClick?.();
      }, doubleTapMs);
    } else {
      onClick?.();
    }
  }, [onClick, onDoubleTap, doubleTapMs]);

  const startPress = useCallback((e: PressEvent) => {
    if (e?.type === 'mousedown' && touchActive.current) return;
    if (e?.type === 'touchstart') touchActive.current = true;
    beginPress();
  }, [beginPress]);

  const endPress = useCallback((e: PressEvent) => {
    if (e?.type === 'touchend') {
      e.preventDefault();
      setTimeout(() => { touchActive.current = false; }, 50);
    }
    if (e?.type === 'mouseup' && touchActive.current) return;
    finishPress();
  }, [finishPress]);

  const cancelPress = useCallback((e: PressEvent) => {
    if (e?.type === 'touchmove') touchActive.current = false;
    if (pressTimer.current) {
      clearTimeout(pressTimer.current);
      pressTimer.current = null;
    }
    doubleTapPending.current = false;
  }, []);

  const onKeyDown = useCallback((e: KeyboardEvent<HTMLElement>) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    // Hold-down browsers fire keydown repeatedly; only the first edge counts
    // so the long-press timer isn't reset every frame.
    if (e.repeat) return;
    // Suppress the browser default that would scroll the page on Space and
    // synthesise a click on Enter (we manage activation ourselves).
    e.preventDefault();
    keyActive.current = true;
    beginPress();
  }, [beginPress]);

  const onKeyUp = useCallback((e: KeyboardEvent<HTMLElement>) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    if (!keyActive.current) return;
    keyActive.current = false;
    e.preventDefault();
    finishPress();
  }, [finishPress]);

  return {
    onMouseDown: startPress,
    onMouseUp: endPress,
    onMouseLeave: cancelPress,
    onTouchStart: startPress,
    onTouchEnd: endPress,
    onTouchMove: cancelPress,
    onTouchCancel: cancelPress,
    onKeyDown,
    onKeyUp,
  };
}
