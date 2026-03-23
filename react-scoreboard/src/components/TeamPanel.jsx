import React from 'react';
import ScoreButton from './ScoreButton';

/**
 * Team panel with score button, timeout button + indicators, and serve icon.
 * Mirrors the NiceGUI TeamPanel component.
 */
export default function TeamPanel({
  teamId,
  teamState,
  currentSet,
  buttonColor,
  serveColor,
  timeoutColor,
  buttonSize,
  isPortrait,
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

  return (
    <div className={`team-panel ${isPortrait ? 'team-panel-portrait' : 'team-panel-landscape'}`}>
      <div className={isPortrait ? 'team-panel-row' : 'team-panel-col'}>
        <ScoreButton
          text={scoreText}
          color={buttonColor}
          size={buttonSize}
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
