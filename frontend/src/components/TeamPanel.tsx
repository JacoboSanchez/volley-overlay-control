import { type CSSProperties, type ReactElement, memo, useCallback, useMemo } from 'react';
import ScoreButton from './ScoreButton';
import ScoreTable from './ScoreTable';
import { toNumber, asString } from '../utils/coerce';
import { getReadableOnSurface } from '../utils/contrast';
import { useDoubleTap } from '../hooks/useDoubleTap';
import { useSurfaceColor } from '../hooks/useSurfaceColor';
import { useI18n } from '../i18n';
import {
  useBoardActions,
  useBoardLayout,
  useBoardState,
  useBoardTheme,
} from '../board/BoardContexts';
import { TEAM_A_LIGHT, TEAM_A_SERVE_ACTIVE, TEAM_B_LIGHT, TEAM_B_SERVE_ACTIVE } from '../theme';

export interface TeamPanelProps {
  teamId: 1 | 2;
}

const SERVE_ICON_BASE_STYLE: CSSProperties = {
  cursor: 'pointer',
  border: 'none',
  background: 'transparent',
  padding: 0,
};
const SERVE_ICON_SIZE_STYLE: CSSProperties = { fontSize: '2rem' };

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
 * Its board data and handlers are intentionally read from narrow contexts so
 * ScoreboardView does not need to relay them through another component level.
 */
function TeamPanel({ teamId }: TeamPanelProps) {
  const { t } = useI18n();
  const { state, customization, currentSet, setsLimit, sidesSwapped } = useBoardState();
  const { btnColorA, btnTextA, btnColorB, btnTextB, iconLogoA, iconLogoB, iconOpacity, fontStyle } =
    useBoardTheme();
  const { buttonSize, isPortrait } = useBoardLayout();
  const {
    onAddPoint,
    onAddTimeout,
    onChangeServe,
    onDoubleTapScore,
    onDoubleTapTimeout,
    onLongPressScore,
  } = useBoardActions();

  const teamState = teamId === 1 ? state.team_1 : state.team_2;
  const buttonColor = teamId === 1 ? btnColorA : btnColorB;
  const buttonTextColor = teamId === 1 ? btnTextA : btnTextB;
  const iconLogo = teamId === 1 ? iconLogoA : iconLogoB;
  const serveColor = teamId === 1 ? TEAM_A_SERVE_ACTIVE : TEAM_B_SERVE_ACTIVE;
  const timeoutColor = teamId === 1 ? TEAM_A_LIGHT : TEAM_B_LIGHT;
  const order = teamId === 1 ? (sidesSwapped ? 1 : -1) : sidesSwapped ? -1 : 1;
  const score = toNumber(teamState?.scores?.[`set_${currentSet}`]);
  const timeouts = teamState?.timeouts ?? 0;
  const isServing = teamState?.serving ?? false;

  // Lift the lightness of foreground colours that fail WCAG AA against
  // the current panel surface so dark team colours stay legible without
  // losing their hue.
  const surface = useSurfaceColor();
  const readableTimeoutColor = getReadableOnSurface(timeoutColor, surface);
  const readableServeColor = getReadableOnSurface(serveColor, surface);

  const handleAddPoint = useCallback(() => onAddPoint(teamId), [onAddPoint, teamId]);
  const handleAddTimeout = useCallback(() => onAddTimeout(teamId), [onAddTimeout, teamId]);
  const handleDoubleTap = useCallback(() => onDoubleTapScore(teamId), [onDoubleTapScore, teamId]);
  const handleDoubleTapTimeoutCb = useCallback(
    () => onDoubleTapTimeout(teamId),
    [onDoubleTapTimeout, teamId],
  );
  const handleLongPress = useCallback(() => onLongPressScore(teamId), [onLongPressScore, teamId]);
  const handleChangeServe = useCallback(() => onChangeServe(teamId), [onChangeServe, teamId]);

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
    t('scoreboard.team', { team: teamId });
  const scoreAriaLabel = t('scoreboard.score', { team: teamNameLabel, score });
  const scoreDescId = `team-${teamId}-score-help`;
  const timeoutDotStyle = useMemo<CSSProperties>(
    () => ({ color: readableTimeoutColor, fontSize: '12px' }),
    [readableTimeoutColor],
  );

  const timeoutDots: ReactElement[] = [];
  for (let i = 0; i < timeouts; i++) {
    timeoutDots.push(
      <span
        key={i}
        className="material-icons timeout-dot"
        style={timeoutDotStyle}
        data-testid={`timeout-${teamId}-number-${i}`}
      >
        radio_button_unchecked
      </span>,
    );
  }

  const safeIconLogo = isSafeUrl(iconLogo) ? iconLogo : null;
  const iconStyle = useMemo<CSSProperties>(() => {
    if (!safeIconLogo) return {};
    const alpha = 1.0 - (iconOpacity ?? 50) / 100;
    let r = 0;
    let g = 0;
    let b = 0;
    const hex = buttonColor.replace('#', '');
    if (hex.length === 6) {
      r = parseInt(hex.substring(0, 2), 16);
      g = parseInt(hex.substring(2, 4), 16);
      b = parseInt(hex.substring(4, 6), 16);
    }
    return {
      backgroundImage: `linear-gradient(rgba(${r},${g},${b},${alpha}), rgba(${r},${g},${b},${alpha})), url(${safeIconLogo})`,
      backgroundSize: 'contain',
      backgroundRepeat: 'no-repeat',
      backgroundPosition: 'center',
    };
  }, [buttonColor, iconOpacity, safeIconLogo]);
  const panelStyle = useMemo<CSSProperties>(() => ({ order }), [order]);
  const timeoutButtonStyle = useMemo<CSSProperties>(
    () => ({ borderColor: readableTimeoutColor, color: readableTimeoutColor }),
    [readableTimeoutColor],
  );
  const serveIconStyle = useMemo<CSSProperties>(
    () => ({ ...SERVE_ICON_BASE_STYLE, color: readableServeColor, opacity: isServing ? 1 : 0.4 }),
    [isServing, readableServeColor],
  );

  return (
    <div
      className={`team-panel ${isPortrait ? 'team-panel-portrait' : 'team-panel-landscape'}`}
      style={panelStyle}
    >
      <div className={isPortrait ? 'team-panel-row' : 'team-panel-col'}>
        {isPortrait && (
          <div className="team-history-col">
            {safeIconLogo && (
              <img
                src={safeIconLogo}
                alt={teamNameLabel}
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
          onClick={handleAddPoint}
          onDoubleTap={handleDoubleTap}
          onLongPress={handleLongPress}
          aria-label={scoreAriaLabel}
          aria-describedby={scoreDescId}
          data-testid={`team-${teamId}-score`}
        />
        <span id={scoreDescId} className="visually-hidden">
          {t('scoreboard.scoreHelp')}
        </span>
        <div className={isPortrait ? 'team-side-col' : 'team-side-row'}>
          <div className={isPortrait ? 'team-side-group-col' : 'team-side-group-row'}>
            <button
              className="timeout-button"
              style={timeoutButtonStyle}
              {...timeoutHandlers}
              aria-label={t('scoreboard.timeout', { team: teamNameLabel })}
              aria-describedby={`team-${teamId}-timeout-help`}
              data-testid={`team-${teamId}-timeout`}
            >
              <span className="material-icons" aria-hidden="true">
                timer
              </span>
            </button>
            <span id={`team-${teamId}-timeout-help`} className="visually-hidden">
              {t('scoreboard.timeoutHelp')}
            </span>
            <div
              className={`timeout-dots ${isPortrait ? 'timeout-dots-col' : 'timeout-dots-row'}`}
              data-testid={`team-${teamId}-timeouts-display`}
            >
              {timeoutDots}
            </div>
          </div>
          {!isPortrait && <div className="spacer" />}
          <button
            type="button"
            className="serve-icon"
            aria-label={t('scoreboard.serve', { team: teamNameLabel })}
            aria-pressed={isServing}
            style={serveIconStyle}
            onClick={handleChangeServe}
            data-testid={`team-${teamId}-serve`}
          >
            <span className="material-icons" aria-hidden="true" style={SERVE_ICON_SIZE_STYLE}>
              sports_volleyball
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}

export default memo(TeamPanel);
