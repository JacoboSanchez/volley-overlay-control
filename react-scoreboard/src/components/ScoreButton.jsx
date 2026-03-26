import React, { useRef, useCallback, useEffect } from 'react';

const LONG_PRESS_MS = 1000;

/**
 * Score button with tap (add point) and long-press (open custom value dialog) detection.
 * Mirrors the NiceGUI ScoreButton + ButtonInteraction behavior.
 */
export default function ScoreButton({
  text,
  color,
  textColor = '#fff',
  size,
  fontStyle,
  onClick,
  onLongPress,
  className = '',
  style = {},
  'data-testid': testId,
}) {
  const pressTimer = useRef(null);
  const isLongPress = useRef(false);

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (pressTimer.current) {
        clearTimeout(pressTimer.current);
        pressTimer.current = null;
      }
    };
  }, []);

  const startPress = useCallback(() => {
    isLongPress.current = false;
    pressTimer.current = setTimeout(() => {
      isLongPress.current = true;
      onLongPress?.();
    }, LONG_PRESS_MS);
  }, [onLongPress]);

  const endPress = useCallback((e) => {
    // Prevent mouse events from firing after touch events
    if (e?.type === 'touchend') {
      e.preventDefault();
    }
    if (pressTimer.current) {
      clearTimeout(pressTimer.current);
      pressTimer.current = null;
    }
    if (!isLongPress.current) {
      onClick?.();
    }
  }, [onClick]);

  const cancelPress = useCallback(() => {
    if (pressTimer.current) {
      clearTimeout(pressTimer.current);
      pressTimer.current = null;
    }
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
      data-testid={testId}
    >
      {text}
    </button>
  );
}
