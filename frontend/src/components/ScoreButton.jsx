import React, { useRef, useCallback, useEffect } from 'react';

const LONG_PRESS_MS = 1000;
const DOUBLE_TAP_MS = 400;

/**
 * Score button with tap (add point), double-tap (undo) and long-press
 * (open custom value dialog) detection.
 * Gesture priority: long-press > double-tap > single-tap.
 *
 * Double-tap is detected at press-start (touchstart / mousedown) because
 * that event fires immediately and reliably on mobile, whereas touchend
 * timing varies with how long the user keeps their finger down.
 */
export default function ScoreButton({
  text,
  color,
  textColor = '#fff',
  size,
  fontStyle,
  onClick,
  onDoubleTap,
  onLongPress,
  className = '',
  style = {},
  'data-testid': testId,
}) {
  const pressTimer = useRef(null);
  const isLongPress = useRef(false);
  const lastTapTime = useRef(0);
  const singleTapTimer = useRef(null);
  const doubleTapPending = useRef(false);
  const touchActive = useRef(false);

  // Clean up timers on unmount
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

  const startPress = useCallback((e) => {
    // Ignore mouse events that follow a touch (prevents double-firing)
    if (e?.type === 'mousedown' && touchActive.current) return;
    if (e?.type === 'touchstart') touchActive.current = true;

    isLongPress.current = false;

    // Detect double-tap at press-start for reliable mobile timing
    const now = Date.now();
    const gap = now - lastTapTime.current;
    if (onDoubleTap && gap > 0 && gap < DOUBLE_TAP_MS) {
      doubleTapPending.current = true;
      // Cancel the pending single-tap action from the first tap
      if (singleTapTimer.current) {
        clearTimeout(singleTapTimer.current);
        singleTapTimer.current = null;
      }
    } else {
      doubleTapPending.current = false;
    }
    lastTapTime.current = now;

    pressTimer.current = setTimeout(() => {
      isLongPress.current = true;
      doubleTapPending.current = false;
      if (singleTapTimer.current) {
        clearTimeout(singleTapTimer.current);
        singleTapTimer.current = null;
      }
      lastTapTime.current = 0;
      onLongPress?.();
    }, LONG_PRESS_MS);
  }, [onLongPress, onDoubleTap]);

  const endPress = useCallback((e) => {
    if (e?.type === 'touchend') {
      e.preventDefault();
      // Allow mousedown again after a short delay (covers edge cases)
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
      // First tap — defer action to allow time for a second tap
      singleTapTimer.current = setTimeout(() => {
        singleTapTimer.current = null;
        onClick?.();
      }, DOUBLE_TAP_MS);
    } else {
      onClick?.();
    }
  }, [onClick, onDoubleTap]);

  const cancelPress = useCallback((e) => {
    if (e?.type === 'touchmove') touchActive.current = false;
    if (pressTimer.current) {
      clearTimeout(pressTimer.current);
      pressTimer.current = null;
    }
    doubleTapPending.current = false;
  }, []);

  const scale = fontStyle?.fontScale ?? 1.0;
  const offsetY = fontStyle?.fontOffsetY ?? 0.0;
  const baseFontSize = size ? size / 2 : 56; // 3.5rem ≈ 56px
  const scaledFontSize = baseFontSize * scale;
  const offsetPx = size ? size * offsetY * 2.0 : 0;

  const btnStyle = {
    backgroundColor: color,
    color: textColor,
    width: size ? `${size}px` : undefined,
    height: size ? `${size}px` : undefined,
    fontSize: `${scaledFontSize}px`,
    lineHeight: 1,
    fontFamily: fontStyle?.fontFamily,
    paddingTop: offsetPx > 0 ? `${offsetPx}px` : undefined,
    paddingBottom: offsetPx < 0 ? `${-offsetPx}px` : undefined,
    ...style,
  };

  return (
    <button
      className={`score-button ${className}`}
      style={btnStyle}
      onMouseDown={startPress}
      onMouseUp={endPress}
      onMouseLeave={cancelPress}
      onTouchStart={startPress}
      onTouchEnd={endPress}
      onTouchMove={cancelPress}
      onTouchCancel={cancelPress}
      data-testid={testId}
    >
      {text}
    </button>
  );
}
