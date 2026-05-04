import ScoreButton from './ScoreButton';
import type { ScoreButtonFontStyle } from './ScoreButton';
import ScoreTable from './ScoreTable';
import OverlayPreview from './OverlayPreview';
import PointsHistoryStrip from './PointsHistoryStrip';
import SideSwitchIndicator from './SideSwitchIndicator';
import MatchAlertIndicator from './MatchAlertIndicator';
import type { GameState } from '../api/client';
import type { ConfigModel } from './TeamCard';
import type { RecentPoint } from '../hooks/useRecentPoints';
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
   * Last few points scored in chronological order (oldest first).
   * Rendered as a chip strip in the slot the preview would occupy
   * whenever the preview is hidden.
   */
  recentPoints: RecentPoint[];
  /** Score-button colours, reused for the points-history chips so the
   * strip honours followTeamColors / custom team colour overrides. */
  btnColorA: string;
  btnTextA: string;
  btnColorB: string;
  btnTextB: string;
  fontStyle?: ScoreButtonFontStyle;
  onAddSet: (teamId: 1 | 2) => void;
  onLongPressSet: (teamId: 1 | 2) => void;
}

const PREVIEW_CARD_WIDTH = 300;
const PREVIEW_CARD_WIDTH_COMPACT = 200;

export default function CenterPanel({
  state,
  customization,
  currentSet,
  setsLimit,
  isPortrait,
  compactLandscape = false,
  previewData,
  recentPoints,
  btnColorA,
  btnTextA,
  btnColorB,
  btnTextB,
  fontStyle,
  onAddSet,
  onLongPressSet,
}: CenterPanelProps) {
  // Hooks must run before any early return — the hook itself handles
  // a null/undefined state by returning ``false``.
  const indoorMidpointPending = useIndoorMidpointAlert(state, currentSet, setsLimit);

  if (!state) return null;

  const t1Sets = state.team_1.sets;
  const t2Sets = state.team_2.sets;

  const logo1 = asString(customization?.['Team 1 Logo']);
  const logo2 = asString(customization?.['Team 2 Logo']);

  return (
    <div className={`center-panel${compactLandscape ? ' center-panel-compact' : ''}`}>
      <div className="sets-row">
        <ScoreButton
          text={String(t1Sets)}
          color="#424242"
          textColor="#fff"
          className="set-button"
          size={48}
          fontStyle={fontStyle}
          onClick={() => onAddSet(1)}
          onLongPress={() => onLongPressSet(1)}
          data-testid="team-1-sets"
        />

        {!isPortrait && (
          <div className="logos-scores-section">
            <div className="team-score-column">
              {logo1 && (
                <img src={logo1} alt="Team 1" className="team-logo" data-testid="team-1-logo" />
              )}
              <ScoreTable
                state={state}
                setsLimit={setsLimit}
                currentSet={currentSet}
                teamId={1}
              />
            </div>
            <div className="current-set-indicator" data-testid="current-set-indicator">
              {currentSet}
            </div>
            <div className="team-score-column">
              {logo2 && (
                <img src={logo2} alt="Team 2" className="team-logo" data-testid="team-2-logo" />
              )}
              <ScoreTable
                state={state}
                setsLimit={setsLimit}
                currentSet={currentSet}
                teamId={2}
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
          text={String(t2Sets)}
          color="#424242"
          textColor="#fff"
          className="set-button"
          size={48}
          fontStyle={fontStyle}
          onClick={() => onAddSet(2)}
          onLongPress={() => onLongPressSet(2)}
          data-testid="team-2-sets"
        />
      </div>

      <div className="match-alerts-row" data-testid="match-alerts-row">
        <MatchAlertIndicator state={state} isPortrait={isPortrait} />
        {!state.match_finished && (
          <SideSwitchIndicator
            info={state.beach_side_switch}
            forcePending={indoorMidpointPending}
          />
        )}
      </div>

      {previewData ? (
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
          points={recentPoints}
          team1Color={btnColorA}
          team1TextColor={btnTextA}
          team2Color={btnColorB}
          team2TextColor={btnTextB}
        />
      )}
    </div>
  );
}
