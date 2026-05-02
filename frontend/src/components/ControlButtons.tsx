import { useI18n } from '../i18n';
import MatchTimer from './MatchTimer';
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
  showPreview: boolean;
  /**
   * Match start timestamp (Unix seconds), or ``null`` when the match
   * is unarmed. Drives the Start-match / Reset toggle and the live
   * timer in the spacer.
   */
  matchStartedAt: number | null | undefined;
  onToggleVisibility: () => void;
  onToggleSimpleMode: () => void;
  onUndoLast: () => void;
  onTogglePreview: () => void;
  onStartMatch: () => void;
  onReset: () => void;
}

/**
 * Bottom HUD control bar: visibility, preview, simple-mode, undo,
 * a live match timer (when armed), and a start-match / reset toggle
 * on the right edge. Theme + fullscreen toggles live in the config
 * panel — they're once-per-session decisions, so they don't earn
 * a permanent slot in the in-game HUD.
 */
export default function ControlButtons({
  visible,
  simpleMode,
  canUndo,
  showPreview,
  matchStartedAt,
  onToggleVisibility,
  onToggleSimpleMode,
  onUndoLast,
  onTogglePreview,
  onStartMatch,
  onReset,
}: ControlButtonsProps) {
  const { t } = useI18n();
  const isArmed = matchStartedAt != null;

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

      <div className="spacer">
        <MatchTimer startedAt={matchStartedAt} />
      </div>

      {isArmed ? (
        <button
          className="control-btn control-btn-reset"
          onClick={onReset}
          title={t('ctrl.reset')}
          data-testid="reset-button"
        >
          <span className="material-icons">restart_alt</span>
        </button>
      ) : (
        <button
          className="control-btn control-btn-start"
          onClick={onStartMatch}
          title={t('ctrl.startMatch')}
          data-testid="start-match-button"
        >
          <span className="material-icons">play_arrow</span>
        </button>
      )}
    </div>
  );
}
