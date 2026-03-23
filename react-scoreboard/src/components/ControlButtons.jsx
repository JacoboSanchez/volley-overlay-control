import React from 'react';
import {
  VISIBLE_ON_COLOR,
  VISIBLE_OFF_COLOR,
  FULL_SCOREBOARD_COLOR,
  SIMPLE_SCOREBOARD_COLOR,
  UNDO_COLOR,
  DO_COLOR,
} from '../theme';

/**
 * Bottom control bar with visibility, simple mode, undo, and reset buttons.
 * Mirrors the NiceGUI ControlButtons component.
 */
export default function ControlButtons({
  visible,
  simpleMode,
  undoMode,
  matchFinished,
  onToggleVisibility,
  onToggleSimpleMode,
  onToggleUndo,
  onReset,
}) {
  return (
    <div className="control-buttons">
      <button
        className="control-btn"
        style={{
          borderColor: visible ? VISIBLE_ON_COLOR : VISIBLE_OFF_COLOR,
          color: visible ? VISIBLE_ON_COLOR : VISIBLE_OFF_COLOR,
        }}
        onClick={onToggleVisibility}
        title={visible ? 'Hide overlay' : 'Show overlay'}
        data-testid="visibility-button"
      >
        <span className="material-icons">
          {visible ? 'visibility' : 'visibility_off'}
        </span>
      </button>

      <button
        className="control-btn"
        style={{
          borderColor: simpleMode ? SIMPLE_SCOREBOARD_COLOR : FULL_SCOREBOARD_COLOR,
          color: simpleMode ? SIMPLE_SCOREBOARD_COLOR : FULL_SCOREBOARD_COLOR,
        }}
        onClick={onToggleSimpleMode}
        title={simpleMode ? 'Full scoreboard' : 'Simple scoreboard'}
        data-testid="simple-mode-button"
      >
        <span className="material-icons">
          {simpleMode ? 'window' : 'grid_on'}
        </span>
      </button>

      <button
        className="control-btn"
        style={{
          borderColor: undoMode ? DO_COLOR : UNDO_COLOR,
          color: undoMode ? DO_COLOR : UNDO_COLOR,
        }}
        onClick={onToggleUndo}
        title={undoMode ? 'Undo mode ON' : 'Undo mode OFF'}
        data-testid="undo-button"
      >
        <span className="material-icons">
          {undoMode ? 'redo' : 'undo'}
        </span>
      </button>

      <div className="spacer" />

      <button
        className="control-btn control-btn-reset"
        onClick={onReset}
        title="Reset match"
        data-testid="reset-button"
      >
        <span className="material-icons">restart_alt</span>
      </button>
    </div>
  );
}
