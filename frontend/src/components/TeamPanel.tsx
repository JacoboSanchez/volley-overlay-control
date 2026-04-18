import { CSSProperties, ReactElement } from 'react';
import ScoreButton, { ScoreButtonFontStyle } from './ScoreButton';
import ScoreTable from './ScoreTable';
import type { GameState } from '../api/client';
import type { components } from '../api/schema';
import type { ConfigModel } from './TeamCard';
import { toNumber, asString } from '../utils/coerce';

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
  onLongPressScore,
}: TeamPanelProps) {
  const score = toNumber(teamState?.scores?.[`set_${currentSet}`]);
  const timeouts = teamState?.timeouts ?? 0;
  const isServing = teamState?.serving ?? false;

  const scoreText = String(score).padStart(2, '0');

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

  return (
    <div className={`team-panel ${isPortrait ? 'team-panel-portrait' : 'team-panel-landscape'}`}>
      <div className={isPortrait ? 'team-panel-row' : 'team-panel-col'}>
        {isPortrait && state && (
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
        )}
        <ScoreButton
          text={scoreText}
          color={buttonColor}
          textColor={buttonTextColor}
          size={buttonSize}
          fontStyle={fontStyle}
          style={iconStyle}
          onClick={() => onAddPoint(teamId)}
          onDoubleTap={() => onDoubleTapScore(teamId)}
          onLongPress={() => onLongPressScore(teamId)}
          data-testid={`team-${teamId}-score`}
        />
        <div className={isPortrait ? 'team-side-col' : 'team-side-row'}>
          <div className={isPortrait ? 'team-side-group-col' : 'team-side-group-row'}>
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
