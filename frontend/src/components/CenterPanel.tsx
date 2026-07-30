import { memo } from 'react';
import { useI18n } from '../i18n';
import ScoreButton from './ScoreButton';
import ScoreTable from './ScoreTable';
import OverlayPreview from './OverlayPreview';
import PointsHistoryStrip from './PointsHistoryStrip';
import SetSummaryActiveNotice from './SetSummaryActiveNotice';
import SideSwitchIndicator from './SideSwitchIndicator';
import ServeSwitchIndicator from './ServeSwitchIndicator';
import MatchAlertIndicator from './MatchAlertIndicator';
import { useIndoorMidpointAlert } from '../hooks/useIndoorMidpointAlert';
import { asString } from '../utils/coerce';
import {
  useBoardActions,
  useBoardLayout,
  useBoardState,
  useBoardTheme,
} from '../board/BoardContexts';

export interface PreviewData {
  overlayUrl: string;
  x: number;
  y: number;
  width: number;
  height: number;
  layoutId?: string;
}

const PREVIEW_CARD_WIDTH = 300;
const PREVIEW_CARD_WIDTH_COMPACT = 200;

/** Centre score, alerts, and preview column. */
function CenterPanel() {
  const { t } = useI18n();
  const {
    state,
    customization,
    currentSet,
    setsLimit,
    sidesSwapped,
    previewData,
    showPreview,
    recentEvents,
  } = useBoardState();
  const { isPortrait, compactLandscape } = useBoardLayout();
  const { btnColorA, btnTextA, btnColorB, btnTextB, iconLogoA, iconLogoB, fontStyle } =
    useBoardTheme();
  const { onAddSet, onLongPressSet, onSwapSides, onToggleSetSummary, onChangeSetSummaryStyle } =
    useBoardActions();
  const indoorMidpointPending = useIndoorMidpointAlert(state, currentSet, setsLimit);

  // Display-side swap: presentation only — the buttons stay bound to
  // their real team ids, the columns just trade places.
  const leftId: 1 | 2 = sidesSwapped ? 2 : 1;
  const rightId: 1 | 2 = sidesSwapped ? 1 : 2;
  const setsById = { 1: state.team_1.sets, 2: state.team_2.sets } as const;
  // Already gated by the "show logos" toggle upstream — null when off.
  const logosById = { 1: iconLogoA, 2: iconLogoB } as const;
  const teamNamesById = {
    1:
      asString(customization?.['Team 1 Name']) ||
      asString(customization?.['Team 1 Text Name']) ||
      t('scoreboard.team', { team: 1 }),
    2:
      asString(customization?.['Team 2 Name']) ||
      asString(customization?.['Team 2 Text Name']) ||
      t('scoreboard.team', { team: 2 }),
  } as const;
  const setSummaryActive = state.set_summary ?? false;
  const setSummarySetNum = state.set_summary_set_num ?? null;
  const setSummaryStyle = (state.set_summary_style ??
    'brand_ledger') as import('../api/client').SetSummaryStyle;

  return (
    <div className={`center-panel${compactLandscape ? ' center-panel-compact' : ''}`}>
      <div className="sets-row">
        <ScoreButton
          key={`sets-${leftId}`}
          text={String(setsById[leftId])}
          color="#424242"
          textColor="#fff"
          className="set-button"
          size={48}
          fontStyle={fontStyle}
          onClick={() => onAddSet(leftId)}
          onLongPress={() => onLongPressSet(leftId)}
          data-testid={`team-${leftId}-sets`}
        />

        {!isPortrait && (
          <div className="logos-scores-section">
            <div className="team-score-column" key={`col-${leftId}`}>
              {logosById[leftId] && (
                <img
                  src={logosById[leftId]}
                  alt={teamNamesById[leftId]}
                  className="team-logo"
                  data-testid={`team-${leftId}-logo`}
                />
              )}
              <ScoreTable
                state={state}
                setsLimit={setsLimit}
                currentSet={currentSet}
                teamId={leftId}
              />
            </div>
            <div className="current-set-indicator" data-testid="current-set-indicator">
              {currentSet}
            </div>
            <div className="team-score-column" key={`col-${rightId}`}>
              {logosById[rightId] && (
                <img
                  src={logosById[rightId]}
                  alt={teamNamesById[rightId]}
                  className="team-logo"
                  data-testid={`team-${rightId}-logo`}
                />
              )}
              <ScoreTable
                state={state}
                setsLimit={setsLimit}
                currentSet={currentSet}
                teamId={rightId}
              />
            </div>
          </div>
        )}

        {isPortrait && (
          <div className="current-set-indicator" data-testid="current-set-indicator">
            {currentSet}
          </div>
        )}

        <ScoreButton
          key={`sets-${rightId}`}
          text={String(setsById[rightId])}
          color="#424242"
          textColor="#fff"
          className="set-button"
          size={48}
          fontStyle={fontStyle}
          onClick={() => onAddSet(rightId)}
          onLongPress={() => onLongPressSet(rightId)}
          data-testid={`team-${rightId}-sets`}
        />
      </div>

      <div className="match-alerts-row" data-testid="match-alerts-row">
        <button
          type="button"
          className="swap-sides-button"
          onClick={onSwapSides}
          title={t('scoreboard.swapSides')}
          aria-label={t('scoreboard.swapSides')}
          aria-pressed={sidesSwapped}
          data-testid="swap-sides-button"
        >
          <span className="material-icons" aria-hidden="true">
            swap_horiz
          </span>
        </button>
        <MatchAlertIndicator state={state} isPortrait={isPortrait} sidesSwapped={sidesSwapped} />
        {!state.match_finished && (
          <SideSwitchIndicator
            info={state.beach_side_switch}
            forcePending={indoorMidpointPending}
          />
        )}
        {!state.match_finished && <ServeSwitchIndicator info={state.serve_switch} />}
      </div>

      {setSummaryActive ? (
        <SetSummaryActiveNotice
          setNum={setSummarySetNum}
          style={setSummaryStyle}
          onDeactivate={onToggleSetSummary}
          onChangeStyle={onChangeSetSummaryStyle}
        />
      ) : showPreview && previewData ? (
        <OverlayPreview
          overlayUrl={previewData.overlayUrl}
          x={previewData.x}
          y={previewData.y}
          width={previewData.width}
          height={previewData.height}
          layoutId={previewData.layoutId}
          cardWidth={compactLandscape ? PREVIEW_CARD_WIDTH_COMPACT : PREVIEW_CARD_WIDTH}
        />
      ) : (
        <PointsHistoryStrip
          events={recentEvents}
          swapped={sidesSwapped}
          team1Color={btnColorA}
          team1TextColor={btnTextA}
          team1Logo={logosById[1] || null}
          team1Name={teamNamesById[1]}
          team2Color={btnColorB}
          team2TextColor={btnTextB}
          team2Logo={logosById[2] || null}
          team2Name={teamNamesById[2]}
        />
      )}
    </div>
  );
}

export default memo(CenterPanel);
