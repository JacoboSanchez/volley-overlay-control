import ScoreButton from './ScoreButton';
import type { ScoreButtonFontStyle } from './ScoreButton';
import ScoreTable from './ScoreTable';
import OverlayPreview from './OverlayPreview';
import type { GameState } from '../api/client';
import type { ConfigModel } from './TeamCard';
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
  previewData: PreviewData | null | undefined;
  fontStyle?: ScoreButtonFontStyle;
  onAddSet: (teamId: 1 | 2) => void;
  onLongPressSet: (teamId: 1 | 2) => void;
  onSetChange: (set: number) => void;
}

export default function CenterPanel({
  state,
  customization,
  currentSet,
  setsLimit,
  isPortrait,
  previewData,
  fontStyle,
  onAddSet,
  onLongPressSet,
  onSetChange,
}: CenterPanelProps) {
  if (!state) return null;

  const t1Sets = state.team_1.sets;
  const t2Sets = state.team_2.sets;

  const logo1 = asString(customization?.['Team 1 Logo']);
  const logo2 = asString(customization?.['Team 2 Logo']);

  return (
    <div className="center-panel">
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

      <div className="set-pagination" data-testid="set-selector">
        <button
          className="pagination-arrow"
          disabled={currentSet <= 1}
          onClick={() => onSetChange(currentSet - 1)}
        >
          <span className="material-icons">chevron_left</span>
        </button>
        {Array.from({ length: setsLimit }, (_, i) => i + 1).map((num) => (
          <button
            key={num}
            className={`pagination-page ${num === currentSet ? 'pagination-page-active' : ''}`}
            onClick={() => onSetChange(num)}
          >
            {num}
          </button>
        ))}
        <button
          className="pagination-arrow"
          disabled={currentSet >= setsLimit}
          onClick={() => onSetChange(currentSet + 1)}
        >
          <span className="material-icons">chevron_right</span>
        </button>
      </div>

      {previewData && (
        <OverlayPreview
          overlayUrl={previewData.overlayUrl}
          x={previewData.x}
          y={previewData.y}
          width={previewData.width}
          height={previewData.height}
          layoutId={previewData.layoutId}
          cardWidth={300}
        />
      )}
    </div>
  );
}
