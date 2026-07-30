import type { CSSProperties } from 'react';
import { useI18n } from '../i18n';
import { useBoardActions, useBoardState } from '../board/BoardContexts';
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

const UNDO_STYLE_ENABLED: CSSProperties = {
  borderColor: UNDO_COLOR,
  color: UNDO_COLOR,
  opacity: 1,
};
const UNDO_STYLE_DISABLED: CSSProperties = {
  borderColor: UNDO_COLOR,
  color: UNDO_COLOR,
  opacity: 0.4,
};
const SIMPLE_MODE_STYLE: CSSProperties = {
  borderColor: SIMPLE_SCOREBOARD_COLOR,
  color: SIMPLE_SCOREBOARD_COLOR,
};
const FULL_MODE_STYLE: CSSProperties = {
  borderColor: FULL_SCOREBOARD_COLOR,
  color: FULL_SCOREBOARD_COLOR,
};
const PREVIEW_ON_STYLE: CSSProperties = {
  borderColor: PREVIEW_ON_COLOR,
  color: PREVIEW_ON_COLOR,
};
const PREVIEW_OFF_STYLE: CSSProperties = {
  borderColor: PREVIEW_OFF_COLOR,
  color: PREVIEW_OFF_COLOR,
};
const SET_SUMMARY_ACTIVE_STYLE: CSSProperties = {
  borderColor: FULL_SCOREBOARD_COLOR,
  color: FULL_SCOREBOARD_COLOR,
};
const SET_SUMMARY_INACTIVE_STYLE: CSSProperties = PREVIEW_OFF_STYLE;
const VISIBLE_STYLE: CSSProperties = {
  borderColor: VISIBLE_ON_COLOR,
  color: VISIBLE_ON_COLOR,
};
const HIDDEN_STYLE: CSSProperties = {
  borderColor: VISIBLE_OFF_COLOR,
  color: VISIBLE_OFF_COLOR,
};

/**
 * Bottom HUD control bar. Its live display fields and operator actions are
 * context slices, so it stays independent of ScoreboardView's composition.
 */
export default function ControlButtons() {
  const { t } = useI18n();
  const { state, simpleMode, showPreview, setSummaryEnabled, showOnAir, showReportLink } =
    useBoardState();
  const {
    onToggleVisibility,
    onToggleSimpleMode,
    onUndoLast,
    onTogglePreview,
    onStartMatch,
    onReset,
    onToggleSetSummary,
  } = useBoardActions();
  const {
    visible,
    can_undo: canUndo,
    match_started_at: matchStartedAt,
    match_finished_at: matchFinishedAt,
    match_finished: matchFinished,
    set_summary: setSummaryActive,
    obs_clients: obsClients = 0,
    last_match_id: lastMatchId,
  } = state;

  // The Reset face stays up while the match is in progress, and while a
  // finished match is still being shown — only an explicit Reset returns the
  // operator to the pre-match idle state where Start match is armable again.
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
          <span className="material-icons" aria-hidden="true">
            restart_alt
          </span>
          <span>{t('ctrl.reset')}</span>
        </button>
      ) : (
        <button
          className="control-btn control-btn-text control-btn-start"
          onClick={onStartMatch}
          title={t('ctrl.startMatch')}
          data-testid="start-match-button"
        >
          <span className="material-icons" aria-hidden="true">
            play_arrow
          </span>
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
          <span className="material-icons" aria-hidden="true">
            description
          </span>
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
          <span className="material-icons" aria-hidden="true">
            podcasts
          </span>
          <span className="control-onair-count">{obsClients}</span>
        </span>
      )}

      <button
        className="control-btn"
        style={canUndo ? UNDO_STYLE_ENABLED : UNDO_STYLE_DISABLED}
        onClick={onUndoLast}
        disabled={!canUndo}
        title={t('ctrl.undoLast')}
        aria-label={t('ctrl.undoLast')}
        data-testid="undo-button"
      >
        <span className="material-icons" aria-hidden="true">
          undo
        </span>
      </button>

      <button
        className="control-btn"
        style={simpleMode ? SIMPLE_MODE_STYLE : FULL_MODE_STYLE}
        onClick={onToggleSimpleMode}
        title={simpleMode ? t('ctrl.fullScoreboard') : t('ctrl.simpleScoreboard')}
        aria-label={t('ctrl.simpleScoreboard')}
        aria-pressed={simpleMode}
        data-testid="simple-mode-button"
      >
        <span className="material-icons" aria-hidden="true">
          {simpleMode ? 'window' : 'grid_on'}
        </span>
      </button>

      <button
        className="control-btn"
        style={showPreview ? PREVIEW_ON_STYLE : PREVIEW_OFF_STYLE}
        onClick={onTogglePreview}
        title={showPreview ? t('ctrl.hidePreview') : t('ctrl.showPreview')}
        aria-label={t('links.preview')}
        aria-pressed={showPreview}
        data-testid="preview-button"
      >
        <span className="material-icons" aria-hidden="true">
          {showPreview ? 'tv' : 'tv_off'}
        </span>
      </button>

      {setSummaryEnabled && (
        <button
          className="control-btn"
          style={setSummaryActive ? SET_SUMMARY_ACTIVE_STYLE : SET_SUMMARY_INACTIVE_STYLE}
          onClick={onToggleSetSummary}
          title={t('setSummary.toggle')}
          aria-label={t('setSummary.toggle')}
          aria-pressed={!!setSummaryActive}
          data-testid="set-summary-button"
        >
          <span className="material-icons" aria-hidden="true">
            summarize
          </span>
        </button>
      )}

      <button
        className="control-btn"
        style={visible ? VISIBLE_STYLE : HIDDEN_STYLE}
        onClick={onToggleVisibility}
        title={visible ? t('ctrl.hideOverlay') : t('ctrl.showOverlay')}
        aria-label={t('ctrl.overlayVisibility')}
        aria-pressed={visible}
        data-testid="visibility-button"
      >
        <span className="material-icons" aria-hidden="true">
          {visible ? 'visibility' : 'visibility_off'}
        </span>
      </button>
    </div>
  );
}
