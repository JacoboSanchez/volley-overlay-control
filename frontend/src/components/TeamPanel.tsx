import { CSSProperties, ReactElement, useCallback } from 'react';
import ScoreButton, { ScoreButtonFontStyle } from './ScoreButton';
import ScoreTable from './ScoreTable';
import type { GameState } from '../api/client';
import type { components } from '../api/schema';
import type { ConfigModel } from './TeamCard';
import { toNumber, asString } from '../utils/coerce';
import { useDoubleTap } from '../hooks/useDoubleTap';

type TeamState = components['schemas']['TeamState'];

export interface TeamPanelProps {
  teamId: 1 | 2;
  teamState: TeamState | null | undefined;
  currentSet: number;
  buttonColor: string;
  buttonTextColor?: string;
  serveColor: string;
  timeoutColor: string;
  buttonSize?: number;
  isPortrait: boolean;
  /**
   * In landscape, when true, render the per-team score history next to
   * the score button instead of relying on CenterPanel to host it. The
   * history sits on the side closest to the centre — right of the
   * button for team 1, left for team 2.
   */
  inlineScoreHistory?: boolean;
  iconLogo?: string | null;
  iconOpacity?: number;
  fontStyle?: ScoreButtonFontStyle;
  state: GameState | null | undefined;
  setsLimit: number;
  customization?: ConfigModel | null;
  onAddPoint: (teamId: 1 | 2) => void;
  onAddTimeout: (teamId: 1 | 2) => void;
  onChangeServe: (teamId: 1 | 2) => void;
  onDoubleTapScore: (teamId: 1 | 2) => void;
  onDoubleTapTimeout: (teamId: 1 | 2) => void;
  onLongPressScore: (teamId: 1 | 2) => void;
}

function isSafeUrl(url: string | null | undefined): url is string {
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
  inlineScoreHistory = false,
  iconLogo,
  iconOpacity = 50,
  fontStyle,
  state,
  setsLimit,
  customization,
  onAddPoint,
  onAddTimeout,
  onChangeServe,
  onDoubleTapScore,
  onDoubleTapTimeout,
  onLongPressScore,
}: TeamPanelProps) {
  const score = toNumber(teamState?.scores?.[`set_${currentSet}`]);
  const timeouts = teamState?.timeouts ?? 0;
  const isServing = teamState?.serving ?? false;

  const handleAddPoint = useCallback(() => onAddPoint(teamId), [onAddPoint, teamId]);
  const handleAddTimeout = useCallback(() => onAddTimeout(teamId), [onAddTimeout, teamId]);
  const handleChangeServe = useCallback(() => onChangeServe(teamId), [onChangeServe, teamId]);
  const handleDoubleTap = useCallback(() => onDoubleTapScore(teamId), [onDoubleTapScore, teamId]);
  const handleDoubleTapTimeoutCb = useCallback(
    () => onDoubleTapTimeout(teamId),
    [onDoubleTapTimeout, teamId]
  );
  const handleLongPress = useCallback(() => onLongPressScore(teamId), [onLongPressScore, teamId]);

  const timeoutHandlers = useDoubleTap({
    onClick: handleAddTimeout,
    onDoubleTap: handleDoubleTapTimeoutCb,
  });

  const scoreText = String(score).padStart(2, '0');

  // A concise live-region label: only the team name + current score are
  // announced on every update. The long-form instructions live in a
  // separate description node referenced via aria-describedby so they are
  // read once on focus rather than every time the score changes.
  const teamNameLabel =
    asString(customization?.[`Team ${teamId} Name`]) ||
    asString(customization?.[`Team ${teamId} Text Name`]) ||
    `Team ${teamId === 1 ? 'A' : 'B'}`;
  const scoreAriaLabel = `${teamNameLabel} score ${score}`;
  const scoreDescId = `team-${teamId}-score-help`;

  const timeoutDots: ReactElement[] = [];
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

  const iconStyle: CSSProperties = {};
  const safeIconLogo = isSafeUrl(iconLogo) ? iconLogo : null;
  if (safeIconLogo) {
    const alpha = 1.0 - iconOpacity / 100;
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

  const teamLogo = asString(customization?.[`Team ${teamId} Logo`]);

  const historyBlock = state ? (
    <div className="team-history-col">
      {teamLogo && (
        <img
          src={teamLogo}
          alt={`Team ${teamId}`}
          className="team-logo"
          data-testid={`team-${teamId}-logo`}
        />
      )}
      <ScoreTable
        state={state}
        setsLimit={setsLimit}
        currentSet={currentSet}
        teamId={teamId}
      />
    </div>
  ) : null;

  const scoreButton = (
    <ScoreButton
      text={scoreText}
      color={buttonColor}
      textColor={buttonTextColor}
      size={buttonSize}
      fontStyle={fontStyle}
      style={iconStyle}
      onClick={handleAddPoint}
      onDoubleTap={handleDoubleTap}
      onLongPress={handleLongPress}
      aria-label={scoreAriaLabel}
      aria-describedby={scoreDescId}
      data-testid={`team-${teamId}-score`}
    />
  );

  // In landscape compact mode, the history rides next to the button on
  // the side closest to the centre — right of team 1, left of team 2.
  const renderInlineLandscapeHistory = !isPortrait && inlineScoreHistory && historyBlock;

  return (
    <div className={`team-panel ${isPortrait ? 'team-panel-portrait' : 'team-panel-landscape'}`}>
      <div className={isPortrait ? 'team-panel-row' : 'team-panel-col'}>
        {isPortrait && historyBlock}
        {renderInlineLandscapeHistory ? (
          <div
            className={`team-score-row team-score-row-team-${teamId}`}
            data-testid={`team-${teamId}-score-row`}
          >
            {teamId === 2 && historyBlock}
            {scoreButton}
            {teamId === 1 && historyBlock}
          </div>
        ) : (
          scoreButton
        )}
        <span id={scoreDescId} className="visually-hidden">
          Tap to add point, double-tap to undo, long-press to set value.
        </span>
        <div className={isPortrait ? 'team-side-col' : 'team-side-row'}>
          <div className={isPortrait ? 'team-side-group-col' : 'team-side-group-row'}>
            <button
              className="timeout-button"
              style={{ borderColor: timeoutColor, color: timeoutColor }}
              {...timeoutHandlers}
              aria-label={`Team ${teamId} timeout`}
              aria-describedby={`team-${teamId}-timeout-help`}
              data-testid={`team-${teamId}-timeout`}
            >
              <span className="material-icons">timer</span>
            </button>
            <span id={`team-${teamId}-timeout-help`} className="visually-hidden">
              Tap to add timeout, double-tap to undo.
            </span>
            <div className={`timeout-dots ${isPortrait ? 'timeout-dots-col' : 'timeout-dots-row'}`}
                 data-testid={`team-${teamId}-timeouts-display`}>
              {timeoutDots}
            </div>
          </div>
          {!isPortrait && <div className="spacer" />}
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
