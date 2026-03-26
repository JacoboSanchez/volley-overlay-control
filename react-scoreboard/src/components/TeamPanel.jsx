import React from 'react';
import ScoreButton from './ScoreButton';

/**
 * Validate that a URL uses http or https protocol.
 */
function isSafeUrl(url) {
  if (!url) return false;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

/**
 * Team panel with score button, timeout button + indicators, and serve icon.
 * Supports custom button colors, team icon overlay, and icon opacity.
 * Mirrors the NiceGUI TeamPanel + ButtonStyle component.
 */
export default function TeamPanel({
  teamId,
  teamState,
  currentSet,
  buttonColor,
  buttonTextColor = '#fff',
  serveColor,
  timeoutColor,
  buttonSize,
  isPortrait,
  iconLogo,
  iconOpacity = 50,
  fontStyle,
  onAddPoint,
  onAddTimeout,
  onChangeServe,
  onLongPressScore,
}) {
  const score = teamState?.scores?.[`set_${currentSet}`] ?? 0;
  const timeouts = teamState?.timeouts ?? 0;
  const isServing = teamState?.serving ?? false;

  const scoreText = String(score).padStart(2, '0');

  const timeoutDots = [];
  for (let i = 0; i < timeouts; i++) {
    timeoutDots.push(
      <span
        key={i}
        className="material-icons timeout-dot"
        style={{ color: timeoutColor, fontSize: '12px' }}
        data-testid={`timeout-${teamId}-number-${i}`}
      >
        radio_button_unchecked
      </span>
    );
  }

  // Build icon overlay style if iconLogo is set and URL is safe
  const iconStyle = {};
  const safeIconLogo = isSafeUrl(iconLogo) ? iconLogo : null;
  if (safeIconLogo) {
    const alpha = 1.0 - iconOpacity / 100;
    // Parse hex color to rgba for overlay
    let r = 0, g = 0, b = 0;
    const hex = buttonColor.replace('#', '');
    if (hex.length === 6) {
      r = parseInt(hex.substring(0, 2), 16);
      g = parseInt(hex.substring(2, 4), 16);
      b = parseInt(hex.substring(4, 6), 16);
    }
    iconStyle.backgroundImage = `linear-gradient(rgba(${r},${g},${b},${alpha}), rgba(${r},${g},${b},${alpha})), url(${safeIconLogo})`;
    iconStyle.backgroundSize = 'contain';
    iconStyle.backgroundRepeat = 'no-repeat';
    iconStyle.backgroundPosition = 'center';
  }

  return (
    <div className={`team-panel ${isPortrait ? 'team-panel-portrait' : 'team-panel-landscape'}`}>
      <div className={isPortrait ? 'team-panel-row' : 'team-panel-col'}>
        <ScoreButton
          text={scoreText}
          color={buttonColor}
          textColor={buttonTextColor}
          size={buttonSize}
          fontStyle={fontStyle}
          style={iconStyle}
          onClick={() => onAddPoint(teamId)}
          onLongPress={() => onLongPressScore(teamId)}
          data-testid={`team-${teamId}-score`}
        />
        <div className={isPortrait ? 'team-side-col' : 'team-side-row'}>
          <button
            className="timeout-button"
            style={{ borderColor: timeoutColor, color: timeoutColor }}
            onClick={() => onAddTimeout(teamId)}
            data-testid={`team-${teamId}-timeout`}
          >
            <span className="material-icons">timer</span>
          </button>
          <div className={`timeout-dots ${isPortrait ? 'timeout-dots-col' : 'timeout-dots-row'}`}
               data-testid={`team-${teamId}-timeouts-display`}>
            {timeoutDots}
          </div>
          <div className="spacer" />
          <span
            className="material-icons serve-icon"
            style={{
              color: serveColor,
              opacity: isServing ? 1 : 0.4,
              cursor: 'pointer',
              fontSize: '2rem',
            }}
            onClick={() => onChangeServe(teamId)}
            data-testid={`team-${teamId}-serve`}
          >
            sports_volleyball
          </span>
        </div>
      </div>
    </div>
  );
}
