import { memo } from 'react';
import { useI18n } from '../i18n';
import { useBoardActions, useBoardLayout } from '../board/BoardContexts';
import TeamPanel from './TeamPanel';
import CenterPanel from './CenterPanel';
import ControlButtons from './ControlButtons';

/**
 * Board composition. The team, centre, and HUD components consume the state
 * slices they need directly, so this layer never has to mirror App's board
 * state through a pass-through prop interface.
 */
function ScoreboardView() {
  const { t } = useI18n();
  const { isPortrait, showControls } = useBoardLayout();
  const { onOpenConfig, onOpenShare, onOpenHistory, onToggleControls } = useBoardActions();

  return (
    <>
      <div
        className={`main-layout ${isPortrait ? 'main-layout-portrait' : 'main-layout-landscape'}`}
      >
        {/**
         * The three children stay in this fixed DOM order across display-side
         * swaps. TeamPanel changes its flex order from board state, keeping
         * CentrePanel's preview iframe mounted and free from visible reloads.
         */}
        <TeamPanel teamId={1} />
        <CenterPanel />
        <TeamPanel teamId={2} />
      </div>

      <div className={`hud-controls ${!showControls ? 'ui-hidden' : ''}`}>
        <div className="top-corner-stack top-right-stack">
          <button
            className="top-corner-icon-btn"
            onClick={onOpenConfig}
            title={t('ctrl.configHint')}
            aria-label={t('ctrl.config')}
            data-testid="config-tab-button"
          >
            <span className="material-icons" aria-hidden="true">
              settings
            </span>
          </button>
          <button
            className="top-corner-icon-btn"
            onClick={onOpenShare}
            title={t('share.title')}
            aria-label={t('share.title')}
            data-testid="share-button"
          >
            <span className="material-icons" aria-hidden="true">
              share
            </span>
          </button>
          <button
            className="top-corner-icon-btn"
            onClick={onOpenHistory}
            title={t('history.title')}
            aria-label={t('history.title')}
            data-testid="history-button"
          >
            <span className="material-icons" aria-hidden="true">
              history
            </span>
          </button>
        </div>

        <div className="control-buttons-wrapper">
          <button
            type="button"
            className="wakeup-handle"
            aria-expanded={showControls}
            aria-label={showControls ? t('ctrl.hideControls') : t('ctrl.showControls')}
            onClick={onToggleControls}
            title={showControls ? t('ctrl.hideControls') : t('ctrl.showControls')}
          >
            <span className="material-icons" aria-hidden="true">
              {showControls ? 'expand_more' : 'expand_less'}
            </span>
          </button>
          <ControlButtons />
        </div>
      </div>
    </>
  );
}

export default memo(ScoreboardView);
