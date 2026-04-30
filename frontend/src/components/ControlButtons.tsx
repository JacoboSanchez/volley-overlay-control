import { useI18n } from '../i18n';
import { ThemePreference } from '../hooks/useSettings';
import {
  VISIBLE_ON_COLOR,
  VISIBLE_OFF_COLOR,
  FULL_SCOREBOARD_COLOR,
  SIMPLE_SCOREBOARD_COLOR,
  UNDO_COLOR,
  PREVIEW_ON_COLOR,
  PREVIEW_OFF_COLOR,
} from '../theme';

export interface ControlButtonsProps {
  visible: boolean;
  simpleMode: boolean;
  canUndo: boolean;
  /**
   * Theme preference. ``'auto'`` follows the OS, ``true`` forces dark,
   * ``false`` forces light. Click cycles auto → dark → light → auto.
   */
  darkMode: ThemePreference;
  isFullscreen: boolean;
  onToggleVisibility: () => void;
  onToggleSimpleMode: () => void;
  onUndoLast: () => void;
  onToggleDarkMode: () => void;
  onToggleFullscreen: () => void;
  showPreview: boolean;
  onTogglePreview: () => void;
}

function themeIcon(pref: ThemePreference): string {
  if (pref === 'auto') return 'brightness_auto';
  // pref boolean: icon represents the *next* state (matches existing UX).
  return pref ? 'light_mode' : 'dark_mode';
}

function themeTitle(pref: ThemePreference, t: (k: string) => string): string {
  if (pref === 'auto') return t('ctrl.themeAuto');
  return pref ? t('ctrl.lightMode') : t('ctrl.darkMode');
}

/**
 * Bottom HUD control bar: visibility, preview, simple-mode, undo,
 * fullscreen, and dark-mode toggles.
 */
export default function ControlButtons({
  visible,
  simpleMode,
  canUndo,
  darkMode,
  isFullscreen,
  onToggleVisibility,
  onToggleSimpleMode,
  onUndoLast,
  onToggleDarkMode,
  onToggleFullscreen,
  showPreview,
  onTogglePreview,
}: ControlButtonsProps) {
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
          borderColor: UNDO_COLOR,
          color: UNDO_COLOR,
          opacity: canUndo ? 1 : 0.4,
        }}
        onClick={onUndoLast}
        disabled={!canUndo}
        title={t('ctrl.undoLast')}
        data-testid="undo-button"
      >
        <span className="material-icons">undo</span>
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
        title={themeTitle(darkMode, t)}
        data-testid="dark-mode-button"
      >
        <span className="material-icons">{themeIcon(darkMode)}</span>
      </button>
    </div>
  );
}
