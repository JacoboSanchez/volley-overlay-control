import { memo, CSSProperties } from 'react';
import { useDoubleTap } from '../hooks/useDoubleTap';

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
  'aria-label'?: string;
  'aria-describedby'?: string;
  'data-testid'?: string;
}

/**
 * Score button with tap (add point), double-tap (undo) and long-press
 * (open custom value dialog) detection.
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
  'aria-label': ariaLabel,
  'aria-describedby': ariaDescribedBy,
  'data-testid': testId,
}: ScoreButtonProps) {
  const handlers = useDoubleTap({ onClick, onDoubleTap, onLongPress });

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
      {...handlers}
      aria-label={ariaLabel}
      aria-live={ariaLabel ? 'polite' : undefined}
      aria-describedby={ariaDescribedBy}
      data-testid={testId}
    >
      {text}
    </button>
  );
}

export default memo(ScoreButton);
