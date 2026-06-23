import { memo } from 'react';
import { useI18n } from '../i18n';
import ScoreButton from './ScoreButton';
import type { ScoreButtonFontStyle } from './ScoreButton';
import ScoreTable from './ScoreTable';
import OverlayPreview from './OverlayPreview';
import PointsHistoryStrip from './PointsHistoryStrip';
import SetSummaryActiveNotice from './SetSummaryActiveNotice';
import type { SetSummaryStyle } from '../api/client';
import SideSwitchIndicator from './SideSwitchIndicator';
import MatchAlertIndicator from './MatchAlertIndicator';
import type { GameState } from '../api/client';
import type { ConfigModel } from './TeamCard';
import type { RecentEvent } from '../hooks/useRecentEvents';
import { useIndoorMidpointAlert } from '../hooks/useIndoorMidpointAlert';
import { asString } from '../utils/coerce';

export interface PreviewData {
  overlayUrl: string;
  x: number;
  y: number;
  width: number;
  height: number;
  layoutId?: string;
}

export interface CenterPanelProps {
  state: GameState | null | undefined;
  /** Display-side swap: true mirrors the centre columns too. */
  sidesSwapped?: boolean;
  onSwapSides?: () => void;
  customization: ConfigModel | null | undefined;
  currentSet: number;
  setsLimit: number;
  isPortrait: boolean;
  /**
   * Landscape phones can't fit a 300px-wide preview AND the alert pills
   * (set/match point, side switch) without spilling off the viewport.
   * When true the centre column tightens its spacing and the preview
   * renders at a reduced width so its derived height shrinks too.
   */
  compactLandscape?: boolean;
  previewData: PreviewData | null | undefined;
  /**
   * Recent audit events in chronological order (oldest first).
   * Rendered as a two-row table (one per team) in the slot the
   * preview would occupy whenever the preview is hidden.
   */
  recentEvents: RecentEvent[];
  /** Score-button colours, reused for the points-history chips so the
   * strip honours followTeamColors / custom team colour overrides. */
  btnColorA: string;
  btnTextA: string;
  btnColorB: string;
  btnTextB: string;
  /**
   * Team logos, already resolved against the operator's "show logos"
   * (``showIcon``) setting — ``null`` when logos are turned off. Passing
   * the resolved value (rather than re-reading the customization here)
   * keeps the set-score columns and points-history strip in lockstep
   * with the score buttons, which hide their logos from the same toggle.
   */
  team1Logo: string | null;
  team2Logo: string | null;
  fontStyle?: ScoreButtonFontStyle;
  /**
   * Set summary overlay: when the operator has the recap active, the
   * centre column swaps the preview / history strip for a notice so
   * they can't lose track of it being on air. Defaults to off.
   */
  setSummaryActive?: boolean;
  setSummarySetNum?: number | null;
  setSummaryStyle?: SetSummaryStyle;
  onDeactivateSetSummary?: () => void;
  onChangeSetSummaryStyle?: (style: SetSummaryStyle) => void;
  onAddSet: (teamId: 1 | 2) => void;
  onLongPressSet: (teamId: 1 | 2) => void;
}

const PREVIEW_CARD_WIDTH = 300;
const PREVIEW_CARD_WIDTH_COMPACT = 200;

function CenterPanel({
  state,
  sidesSwapped = false,
  onSwapSides,
  customization,
  currentSet,
  setsLimit,
  isPortrait,
  compactLandscape = false,
  previewData,
  recentEvents,
  btnColorA,
  btnTextA,
  btnColorB,
  btnTextB,
  team1Logo,
  team2Logo,
  fontStyle,
  setSummaryActive,
  setSummarySetNum,
  setSummaryStyle,
  onDeactivateSetSummary,
  onChangeSetSummaryStyle,
  onAddSet,
  onLongPressSet,
}: CenterPanelProps) {
  const { t } = useI18n();
  // Hooks must run before any early return — the hook itself handles
  // a null/undefined state by returning ``false``.
  const indoorMidpointPending = useIndoorMidpointAlert(state, currentSet, setsLimit);

  if (!state) return null;

  // Display-side swap: presentation only — the buttons stay bound to
  // their real team ids, the columns just trade places.
  const leftId: 1 | 2 = sidesSwapped ? 2 : 1;
  const rightId: 1 | 2 = sidesSwapped ? 1 : 2;
  const setsById = { 1: state.team_1.sets, 2: state.team_2.sets } as const;
  // Already gated by the "show logos" toggle upstream — null when off.
  const logosById = { 1: team1Logo, 2: team2Logo } as const;

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
                  alt={`Team ${leftId}`}
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
                  alt={`Team ${rightId}`}
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
        {onSwapSides && (
          <button
            type="button"
            className="swap-sides-button"
            onClick={onSwapSides}
            title={t('scoreboard.swapSides')}
            aria-label={t('scoreboard.swapSides')}
            aria-pressed={sidesSwapped}
            data-testid="swap-sides-button"
          >
            <span className="material-icons">swap_horiz</span>
          </button>
        )}
        <MatchAlertIndicator state={state} isPortrait={isPortrait} sidesSwapped={sidesSwapped} />
        {!state.match_finished && (
          <SideSwitchIndicator
            info={state.beach_side_switch}
            forcePending={indoorMidpointPending}
          />
        )}
      </div>

      {setSummaryActive && onDeactivateSetSummary && onChangeSetSummaryStyle ? (
        <SetSummaryActiveNotice
          setNum={setSummarySetNum ?? null}
          style={setSummaryStyle ?? 'brand_ledger'}
          onDeactivate={onDeactivateSetSummary}
          onChangeStyle={onChangeSetSummaryStyle}
        />
      ) : previewData ? (
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
          team1Name={asString(customization?.['Team 1 Name']) || 'Team 1'}
          team2Color={btnColorB}
          team2TextColor={btnTextB}
          team2Logo={logosById[2] || null}
          team2Name={asString(customization?.['Team 2 Name']) || 'Team 2'}
        />
      )}
    </div>
  );
}

export default memo(CenterPanel);
