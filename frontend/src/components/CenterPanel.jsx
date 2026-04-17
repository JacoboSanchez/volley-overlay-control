import React from 'react';
import ScoreButton from './ScoreButton';
import ScoreTable from './ScoreTable';
import OverlayPreview from './OverlayPreview';

/**
 * Center panel with set buttons, team logos, score history, and set pagination.
 * Mirrors the NiceGUI CenterPanel component layout:
 * logos on top, score columns directly below (no set indicator in between).
 */
export default function CenterPanel({
  state,
  customization,
  currentSet,
  setsLimit,
  isPortrait,
  previewData,
  onAddSet,
  onLongPressSet,
  onSetChange,
}) {
  if (!state) return null;

  const t1Sets = state.team_1.sets;
  const t2Sets = state.team_2.sets;

  const logo1 = customization?.['Team 1 Logo'] || null;
  const logo2 = customization?.['Team 2 Logo'] || null;

  return (
    <div className="center-panel">
      <div className="sets-row">
        <ScoreButton
          text={String(t1Sets)}
          color="#424242"
          textColor="#fff"
          className="set-button"
          onClick={() => onAddSet(1)}
          onLongPress={() => onLongPressSet(1)}
          data-testid="team-1-sets"
        />

        {/* In landscape, show score history here; in portrait it moves to TeamPanels */}
        {!isPortrait && (
          <div className="logos-scores-section">
            <div className="team-score-column">
              {logo1 && (
                <img
                  src={logo1}
                  alt="Team 1"
                  className="team-logo"
                  data-testid="team-1-logo"
                />
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
                <img
                  src={logo2}
                  alt="Team 2"
                  className="team-logo"
                  data-testid="team-2-logo"
                />
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
