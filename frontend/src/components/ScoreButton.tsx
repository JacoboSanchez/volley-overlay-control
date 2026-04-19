import { memo, useRef, useCallback, useEffect, CSSProperties, MouseEvent, TouchEvent } from 'react';

const LONG_PRESS_MS = 1000;
// Window used to distinguish a single tap from a double tap. A shorter window
// makes every single-tap score feel snappier because we wait less before
// committing the point, while still leaving comfortable headroom above a
// human double-tap (~150ms typical).
const DOUBLE_TAP_MS = 280;

export interface ScoreButtonFontStyle {
  fontScale?: number;
  fontOffsetY?: number;
  fontFamily?: string;
}

export interface ScoreButtonProps {
  text: string;
  color: string;
  textColor?: string;
  size?: number;
  fontStyle?: ScoreButtonFontStyle;
  onClick?: () => void;
  onDoubleTap?: () => void;
  onLongPress?: () => void;
  className?: string;
  style?: CSSProperties;
  'data-testid'?: string;
}

type PressEvent = MouseEvent<HTMLButtonElement> | TouchEvent<HTMLButtonElement>;

/**
 * Score button with tap (add point), double-tap (undo) and long-press
 * (open custom value dialog) detection.
 * Gesture priority: long-press > double-tap > single-tap.
 *
 * Double-tap is detected at press-start (touchstart / mousedown) because
 * that event fires immediately and reliably on mobile, whereas touchend
 * timing varies with how long the user keeps their finger down.
 */
function ScoreButton({
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
}: ScoreButtonProps) {
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
    if (onDoubleTap && gap > 0 && gap < DOUBLE_TAP_MS) {
      doubleTapPending.current = true;
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
      }, DOUBLE_TAP_MS);
    } else {
      onClick?.();
    }
  }, [onClick, onDoubleTap]);

  const cancelPress = useCallback((e: PressEvent) => {
    if (e?.type === 'touchmove') touchActive.current = false;
    if (pressTimer.current) {
      clearTimeout(pressTimer.current);
      pressTimer.current = null;
    }
    doubleTapPending.current = false;
  }, []);

  const scale = fontStyle?.fontScale ?? 1.0;
  const offsetY = fontStyle?.fontOffsetY ?? 0.0;
  const baseFontSize = size ? size / 2 : 56;
  const scaledFontSize = baseFontSize * scale;
  const offsetPx = size ? size * offsetY * 2.0 : 0;

  const btnStyle: CSSProperties = {
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

export default memo(ScoreButton);
