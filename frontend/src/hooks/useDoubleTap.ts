import { useCallback, useEffect, useRef, MouseEvent, TouchEvent } from 'react';
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
}

/**
 * Press-gesture detector with single-tap, double-tap and (optional) long-press.
 *
 * Gesture priority: long-press > double-tap > single-tap.
 *
 * Double-tap is detected at press-start (touchstart / mousedown) because that
 * event fires immediately and reliably on mobile, whereas touchend timing
 * varies with how long the user keeps their finger down.
 *
 * If `onDoubleTap` is not provided, `onClick` fires immediately on press-end
 * (no single-tap delay).
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

  const startPress = useCallback((e: PressEvent) => {
    if (e?.type === 'mousedown' && touchActive.current) return;
    if (e?.type === 'touchstart') touchActive.current = true;

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

  const endPress = useCallback((e: PressEvent) => {
    if (e?.type === 'touchend') {
      e.preventDefault();
      setTimeout(() => { touchActive.current = false; }, 50);
    }
    if (e?.type === 'mouseup' && touchActive.current) return;

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

  const cancelPress = useCallback((e: PressEvent) => {
    if (e?.type === 'touchmove') touchActive.current = false;
    if (pressTimer.current) {
      clearTimeout(pressTimer.current);
      pressTimer.current = null;
    }
    doubleTapPending.current = false;
  }, []);

  return {
    onMouseDown: startPress,
    onMouseUp: endPress,
    onMouseLeave: cancelPress,
    onTouchStart: startPress,
    onTouchEnd: endPress,
    onTouchMove: cancelPress,
    onTouchCancel: cancelPress,
  };
}
