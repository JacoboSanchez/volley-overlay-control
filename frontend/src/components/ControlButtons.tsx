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
   * Match end timestamp (Unix seconds), or ``null`` while the match
   * is still in progress. Forwarded to ``MatchTimer`` so the live
   * counter freezes at the actual end-of-match value once the
   * match transitions to finished.
   */
  matchFinishedAt?: number | null | undefined;
  /**
   * ``true`` once the match transitions to finished. Drives one half
   * of the Start-match / Reset toggle so the operator's next step is
   * Reset, not Start. ``matchStartedAt`` stays in place after match
   * end (so the timer can render the final duration); Reset is the
   * only path that clears it back to ``null``.
   */
  matchFinished: boolean;
  /**
   * Set summary overlay — operator toggle that swaps the scoreboard
   * for a recap panel. The button slot only renders when the
   * feature is enabled in settings (``setSummaryEnabled``); the live
   * state of the toggle is in ``setSummaryActive``.
   */
  setSummaryEnabled?: boolean;
  setSummaryActive?: boolean;
  /**
   * Live output clients (OBS browser sources + spectators) connected to
   * this overlay. With ``showOnAir`` on, a >0 count lights an "on-air"
   * badge so the operator can confirm the scoreboard is reaching OBS.
   */
  obsClients?: number;
  showOnAir?: boolean;
  /**
   * ``match_id`` of the just-finished match. With ``showReportLink`` on,
   * a "Match report" button appears next to Reset at match end.
   */
  lastMatchId?: string | null;
  showReportLink?: boolean;
  onToggleVisibility: () => void;
  onToggleSimpleMode: () => void;
  onUndoLast: () => void;
  onTogglePreview: () => void;
  onStartMatch: () => void;
  onReset: () => void;
  onToggleSetSummary?: () => void;
}

/**
 * Bottom HUD control bar. Layout, left → right:
 *   * Start-match / Reset toggle (with text label) — primary
 *     operator action, parked on the dominant side.
 *   * Live match timer (when armed).
 *   * Undo, simple-mode, preview, visibility — secondary toggles
 *     pushed to the right edge so they don't crowd the primary
 *     action. Undo sits closest to the timer because it's the
 *     most reached-for during play.
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
  matchFinishedAt,
  matchFinished,
  setSummaryEnabled,
  setSummaryActive,
  obsClients = 0,
  showOnAir = true,
  lastMatchId,
  showReportLink = true,
  onToggleVisibility,
  onToggleSimpleMode,
  onUndoLast,
  onTogglePreview,
  onStartMatch,
  onReset,
  onToggleSetSummary,
}: ControlButtonsProps) {
  const { t } = useI18n();
  // The Reset face stays up while the match is in progress, and
  // while a finished match is still being shown — only an explicit
  // Reset returns the operator to the pre-match idle state where
  // Start match is armable again.
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

      {matchFinished && lastMatchId && showReportLink && (
        <a
          className="control-btn control-btn-text control-btn-report"
          href={`/match/${encodeURIComponent(lastMatchId)}/report`}
          target="_blank"
          rel="noopener noreferrer"
          title={t('ctrl.viewReport')}
          data-testid="view-report-button"
        >
          <span className="material-icons">description</span>
          <span>{t('ctrl.viewReport')}</span>
        </a>
      )}

      <div className="spacer">
        <MatchTimer startedAt={matchStartedAt} finishedAt={matchFinishedAt} />
      </div>

      {showOnAir && obsClients > 0 && (
        <span
          className="control-onair"
          title={t('ctrl.onAir')}
          aria-label={t('ctrl.onAir')}
          data-testid="onair-indicator"
        >
          <span className="control-onair-dot" />
          <span className="material-icons">podcasts</span>
          <span className="control-onair-count">{obsClients}</span>
        </span>
      )}

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
        <span className="material-icons">{simpleMode ? 'window' : 'grid_on'}</span>
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
        <span className="material-icons">{showPreview ? 'tv' : 'tv_off'}</span>
      </button>

      {setSummaryEnabled && onToggleSetSummary && (
        <button
          className="control-btn"
          style={{
            // Gated by the feature flag — when enabled and active,
            // tint the icon orange to match the SIMPLE / FULL scoreboard
            // family so it visually groups with the other display
            // toggles.
            borderColor: setSummaryActive ? FULL_SCOREBOARD_COLOR : PREVIEW_OFF_COLOR,
            color: setSummaryActive ? FULL_SCOREBOARD_COLOR : PREVIEW_OFF_COLOR,
          }}
          onClick={onToggleSetSummary}
          title={t('setSummary.toggle')}
          aria-pressed={!!setSummaryActive}
          data-testid="set-summary-button"
        >
          <span className="material-icons">summarize</span>
        </button>
      )}

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
        <span className="material-icons">{visible ? 'visibility' : 'visibility_off'}</span>
      </button>
    </div>
  );
}
