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
   * is unarmed. Drives the live timer in the spacer and one half of
   * the Start-match / Reset toggle.
   */
  matchStartedAt: number | null | undefined;
  /**
   * ``true`` once the match transitions to finished. Combined with
   * ``matchStartedAt`` to decide which side of the Start/Reset
   * toggle to render: the archive path clears
   * ``matchStartedAt`` to prep the next match, but the operator
   * still sees the just-played scoreboard and needs to hit Reset
   * before the next start can be armed — so a finished match
   * forces the Reset face regardless of the timer field.
   */
  matchFinished: boolean;
  onToggleVisibility: () => void;
  onToggleSimpleMode: () => void;
  onUndoLast: () => void;
  onTogglePreview: () => void;
  onStartMatch: () => void;
  onReset: () => void;
}

/**
 * Bottom HUD control bar. Layout, left → right:
 *   * Start-match / Reset toggle (with text label) — primary
 *     operator action, parked on the dominant side.
 *   * Live match timer (when armed).
 *   * Visibility, preview, simple-mode, undo — secondary toggles
 *     pushed to the right edge so they don't crowd the primary
 *     action.
 *
 * Theme + fullscreen toggles live in the config panel; they're
 * once-per-session decisions and don't earn a permanent slot here.
 */
export default function ControlButtons({
  visible,
  simpleMode,
  canUndo,
  showPreview,
  matchStartedAt,
  matchFinished,
  onToggleVisibility,
  onToggleSimpleMode,
  onUndoLast,
  onTogglePreview,
  onStartMatch,
  onReset,
}: ControlButtonsProps) {
  const { t } = useI18n();
  // ``matchFinished`` keeps the Reset face up after a match ends —
  // ``_archive_if_finished`` zeroes ``matchStartedAt`` to prep the
  // next match but the operator still sees the just-played
  // scoreboard, so the next required action is Reset, not Start.
  const showReset = matchStartedAt != null || matchFinished;

  return (
    <div className="control-buttons">
      {showReset ? (
        <button
          className="control-btn control-btn-text control-btn-reset"
          onClick={onReset}
          title={t('ctrl.reset')}
          data-testid="reset-button"
        >
          <span className="material-icons">restart_alt</span>
          <span>{t('ctrl.reset')}</span>
        </button>
      ) : (
        <button
          className="control-btn control-btn-text control-btn-start"
          onClick={onStartMatch}
          title={t('ctrl.startMatch')}
          data-testid="start-match-button"
        >
          <span className="material-icons">play_arrow</span>
          <span>{t('ctrl.startMatch')}</span>
        </button>
      )}

      <div className="spacer">
        <MatchTimer startedAt={matchStartedAt} />
      </div>

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
    </div>
  );
}
