import { Dispatch, SetStateAction } from 'react';
import { useI18n } from '../i18n';
import TeamPanel from './TeamPanel';
import CenterPanel from './CenterPanel';
import ControlButtons from './ControlButtons';
import type { GameState } from '../api/client';
import type { ConfigModel } from './TeamCard';
import type { PreviewData } from './CenterPanel';
import type { ScoreButtonFontStyle } from './ScoreButton';
import type { RecentEvent } from '../hooks/useRecentEvents';
import { TEAM_A_SERVE_ACTIVE, TEAM_B_SERVE_ACTIVE, TEAM_A_LIGHT, TEAM_B_LIGHT } from '../theme';

export interface ScoreboardViewProps {
  state: GameState;
  customization: ConfigModel | null | undefined;
  currentSet: number;
  setsLimit: number;
  isPortrait: boolean;
  buttonSize?: number;
  previewData: PreviewData | null | undefined;
  showPreview: boolean;
  recentEvents: RecentEvent[];
  /**
   * True on landscape phones (no room for persistent controls). The
   * centre column then uses a tighter layout and a smaller preview so
   * the alert pills don't get pushed off the bottom of the viewport.
   */
  compactLandscape?: boolean;
  showControls: boolean;
  setShowControls: Dispatch<SetStateAction<boolean>>;
  canUndo: boolean;
  simpleMode: boolean;
  btnColorA: string;
  btnTextA: string;
  btnColorB: string;
  btnTextB: string;
  iconLogoA: string | null;
  iconLogoB: string | null;
  iconOpacity?: number;
  fontStyle?: ScoreButtonFontStyle;
  onAddPoint: (teamId: 1 | 2) => void;
  onAddSet: (teamId: 1 | 2) => void;
  onAddTimeout: (teamId: 1 | 2) => void;
  onChangeServe: (teamId: 1 | 2) => void;
  onDoubleTapScore: (teamId: 1 | 2) => void;
  onDoubleTapTimeout: (teamId: 1 | 2) => void;
  onLongPressScore: (teamId: 1 | 2) => void;
  onLongPressSet: (teamId: 1 | 2) => void;
  onToggleVisibility: () => void;
  onToggleSimpleMode: () => void;
  onUndoLast: () => void;
  onTogglePreview: () => void;
  onStartMatch: () => void;
  onReset: () => void;
  onOpenConfig: () => void;
  onOpenShare: () => void;
  onOpenHistory: () => void;
  /** Set summary overlay — feature flag + live state + handlers. */
  setSummaryEnabled?: boolean;
  setSummaryActive?: boolean;
  setSummarySetNum?: number | null;
  setSummaryStyle?: import('../api/client').SetSummaryStyle;
  onToggleSetSummary?: () => void;
  onChangeSetSummaryStyle?: (style: import('../api/client').SetSummaryStyle) => void;
}

export default function ScoreboardView({
  state,
  customization,
  currentSet,
  setsLimit,
  isPortrait,
  buttonSize,
  previewData,
  showPreview,
  recentEvents,
  compactLandscape = false,
  showControls,
  setShowControls,
  canUndo,
  simpleMode,
  btnColorA,
  btnTextA,
  btnColorB,
  btnTextB,
  iconLogoA,
  iconLogoB,
  iconOpacity,
  fontStyle,
  onAddPoint,
  onAddSet,
  onAddTimeout,
  onChangeServe,
  onDoubleTapScore,
  onDoubleTapTimeout,
  onLongPressScore,
  onLongPressSet,
  onToggleVisibility,
  onToggleSimpleMode,
  onUndoLast,
  onTogglePreview,
  onStartMatch,
  onReset,
  onOpenConfig,
  onOpenShare,
  onOpenHistory,
  setSummaryEnabled,
  setSummaryActive,
  setSummarySetNum,
  setSummaryStyle,
  onToggleSetSummary,
  onChangeSetSummaryStyle,
}: ScoreboardViewProps) {
  const { t } = useI18n();

  return (
    <>
      <div
        className={`main-layout ${isPortrait ? 'main-layout-portrait' : 'main-layout-landscape'}`}
      >
        <TeamPanel
          teamId={1}
          teamState={state.team_1}
          currentSet={currentSet}
          buttonColor={btnColorA}
          buttonTextColor={btnTextA}
          serveColor={TEAM_A_SERVE_ACTIVE}
          timeoutColor={TEAM_A_LIGHT}
          buttonSize={buttonSize}
          isPortrait={isPortrait}
          iconLogo={iconLogoA}
          iconOpacity={iconOpacity}
          fontStyle={fontStyle}
          state={state}
          setsLimit={setsLimit}
          customization={customization}
          onAddPoint={onAddPoint}
          onAddTimeout={onAddTimeout}
          onChangeServe={onChangeServe}
          onDoubleTapScore={onDoubleTapScore}
          onDoubleTapTimeout={onDoubleTapTimeout}
          onLongPressScore={onLongPressScore}
        />

        <CenterPanel
          state={state}
          customization={customization}
          currentSet={currentSet}
          setsLimit={setsLimit}
          isPortrait={isPortrait}
          compactLandscape={compactLandscape}
          previewData={showPreview ? previewData : null}
          recentEvents={recentEvents}
          btnColorA={btnColorA}
          btnTextA={btnTextA}
          btnColorB={btnColorB}
          btnTextB={btnTextB}
          fontStyle={fontStyle}
          setSummaryActive={setSummaryActive}
          setSummarySetNum={setSummarySetNum}
          setSummaryStyle={setSummaryStyle}
          onDeactivateSetSummary={onToggleSetSummary}
          onChangeSetSummaryStyle={onChangeSetSummaryStyle}
          onAddSet={onAddSet}
          onLongPressSet={onLongPressSet}
        />

        <TeamPanel
          teamId={2}
          teamState={state.team_2}
          currentSet={currentSet}
          buttonColor={btnColorB}
          buttonTextColor={btnTextB}
          serveColor={TEAM_B_SERVE_ACTIVE}
          timeoutColor={TEAM_B_LIGHT}
          buttonSize={buttonSize}
          isPortrait={isPortrait}
          iconLogo={iconLogoB}
          iconOpacity={iconOpacity}
          fontStyle={fontStyle}
          state={state}
          setsLimit={setsLimit}
          customization={customization}
          onAddPoint={onAddPoint}
          onAddTimeout={onAddTimeout}
          onChangeServe={onChangeServe}
          onDoubleTapScore={onDoubleTapScore}
          onDoubleTapTimeout={onDoubleTapTimeout}
          onLongPressScore={onLongPressScore}
        />
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
          <div
            className="wakeup-handle"
            role="button"
            tabIndex={0}
            aria-label={showControls ? t('ctrl.hideControls') : t('ctrl.showControls')}
            onClick={() => setShowControls(!showControls)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setShowControls(!showControls);
              }
            }}
            title={showControls ? t('ctrl.hideControls') : t('ctrl.showControls')}
          >
            <span className="material-icons">{showControls ? 'expand_more' : 'expand_less'}</span>
          </div>
          <ControlButtons
            visible={state.visible}
            simpleMode={simpleMode}
            canUndo={canUndo}
            showPreview={showPreview}
            matchStartedAt={state.match_started_at}
            matchFinishedAt={state.match_finished_at}
            matchFinished={state.match_finished}
            setSummaryEnabled={setSummaryEnabled}
            setSummaryActive={setSummaryActive}
            onToggleVisibility={onToggleVisibility}
            onToggleSimpleMode={onToggleSimpleMode}
            onUndoLast={onUndoLast}
            onTogglePreview={onTogglePreview}
            onStartMatch={onStartMatch}
            onReset={onReset}
            onToggleSetSummary={onToggleSetSummary}
          />
        </div>
      </div>
    </>
  );
}
