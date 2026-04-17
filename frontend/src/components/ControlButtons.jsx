import React from 'react';
import { useI18n } from '../i18n';
import {
  VISIBLE_ON_COLOR,
  VISIBLE_OFF_COLOR,
  FULL_SCOREBOARD_COLOR,
  SIMPLE_SCOREBOARD_COLOR,
  UNDO_COLOR,
  DO_COLOR,
  PREVIEW_ON_COLOR,
  PREVIEW_OFF_COLOR,
} from '../theme';

/**
 * Bottom control bar with visibility, simple mode, undo, and config navigation.
 * Mirrors the NiceGUI ControlButtons component.
 */
export default function ControlButtons({
  visible,
  simpleMode,
  undoMode,
  darkMode,
  isFullscreen,
  matchFinished,
  onToggleVisibility,
  onToggleSimpleMode,
  onToggleUndo,
  onToggleDarkMode,
  onToggleFullscreen,
  showPreview,
  onTogglePreview,
}) {
  const { t } = useI18n();

  return (
    <div className="control-buttons">
      <button
        className="control-btn"
        style={{
          borderColor: visible ? VISIBLE_ON_COLOR : VISIBLE_OFF_COLOR,
          color: visible ? VISIBLE_ON_COLOR : VISIBLE_OFF_COLOR,
        }}
        onClick={onToggleVisibility}
        title={visible ? t('ctrl.hideOverlay') : t('ctrl.showOverlay')}
        data-testid="visibility-button"
      >
        <span className="material-icons">
          {visible ? 'visibility' : 'visibility_off'}
        </span>
      </button>

      <button
        className="control-btn"
        style={{
          borderColor: showPreview ? PREVIEW_ON_COLOR : PREVIEW_OFF_COLOR,
          color: showPreview ? PREVIEW_ON_COLOR : PREVIEW_OFF_COLOR,
        }}
        onClick={onTogglePreview}
        title={showPreview ? t('ctrl.hidePreview') : t('ctrl.showPreview')}
        data-testid="preview-button"
      >
        <span className="material-icons">
          {showPreview ? 'tv' : 'tv_off'}
        </span>
      </button>

      <button
        className="control-btn"
        style={{
          borderColor: simpleMode ? SIMPLE_SCOREBOARD_COLOR : FULL_SCOREBOARD_COLOR,
          color: simpleMode ? SIMPLE_SCOREBOARD_COLOR : FULL_SCOREBOARD_COLOR,
        }}
        onClick={onToggleSimpleMode}
        title={simpleMode ? t('ctrl.fullScoreboard') : t('ctrl.simpleScoreboard')}
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
        title={undoMode ? t('ctrl.undoOn') : t('ctrl.undoOff')}
        data-testid="undo-button"
      >
        <span className="material-icons">
          {undoMode ? 'redo' : 'undo'}
        </span>
      </button>

      <div className="spacer" />

      <button
        className="control-btn control-btn-fullscreen"
        onClick={onToggleFullscreen}
        title={isFullscreen ? t('ctrl.exitFullscreen') : t('ctrl.fullscreen')}
        data-testid="fullscreen-button"
      >
        <span className="material-icons">
          {isFullscreen ? 'fullscreen_exit' : 'fullscreen'}
        </span>
      </button>

      <button
        className="control-btn control-btn-theme"
        onClick={onToggleDarkMode}
        title={darkMode ? t('ctrl.lightMode') : t('ctrl.darkMode')}
        data-testid="dark-mode-button"
      >
        <span className="material-icons">
          {darkMode ? 'light_mode' : 'dark_mode'}
        </span>
      </button>
    </div>
  );
}
