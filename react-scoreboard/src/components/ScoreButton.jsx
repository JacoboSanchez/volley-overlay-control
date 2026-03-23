import React, { useRef, useCallback } from 'react';

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
  onClick,
  onLongPress,
  className = '',
  style = {},
  'data-testid': testId,
}) {
  const pressTimer = useRef(null);
  const isLongPress = useRef(false);

  const startPress = useCallback(() => {
    isLongPress.current = false;
    pressTimer.current = setTimeout(() => {
      isLongPress.current = true;
      onLongPress?.();
    }, LONG_PRESS_MS);
  }, [onLongPress]);

  const endPress = useCallback(() => {
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

  const btnStyle = {
    backgroundColor: color,
    color: textColor,
    width: size ? `${size}px` : undefined,
    height: size ? `${size}px` : undefined,
    fontSize: size ? `${size / 2}px` : '3.5rem',
    lineHeight: 1,
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
