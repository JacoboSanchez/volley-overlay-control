import { Dispatch, SetStateAction } from 'react';
import { useI18n } from '../i18n';
import TeamPanel from './TeamPanel';
import CenterPanel from './CenterPanel';
import ControlButtons from './ControlButtons';
import type { GameState } from '../api/client';
import type { ConfigModel } from './TeamCard';
import type { PreviewData } from './CenterPanel';
import type { ScoreButtonFontStyle } from './ScoreButton';
import type { RecentPoint } from '../hooks/useRecentPoints';
import {
  TEAM_A_SERVE_ACTIVE,
  TEAM_B_SERVE_ACTIVE,
  TEAM_A_LIGHT,
  TEAM_B_LIGHT,
} from '../theme';

export interface ScoreboardViewProps {
  state: GameState;
  customization: ConfigModel | null | undefined;
  currentSet: number;
  setsLimit: number;
  isPortrait: boolean;
  buttonSize?: number;
  previewData: PreviewData | null | undefined;
  showPreview: boolean;
  recentPoints: RecentPoint[];
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
  recentPoints,
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
}: ScoreboardViewProps) {
  const { t } = useI18n();

  return (
    <>
      <div className={`main-layout ${isPortrait ? 'main-layout-portrait' : 'main-layout-landscape'}`}>
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
          recentPoints={recentPoints}
          btnColorA={btnColorA}
          btnTextA={btnTextA}
          btnColorB={btnColorB}
          btnTextB={btnTextB}
          fontStyle={fontStyle}
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
        <button
          className="top-right-config-btn"
          onClick={onOpenConfig}
          title={t('ctrl.config')}
          data-testid="config-tab-button"
        >
          <span className="material-icons">settings</span>
        </button>

        <div className="control-buttons-wrapper">
          <div
            className="wakeup-handle"
            onClick={() => setShowControls(!showControls)}
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
            matchFinished={state.match_finished}
            onToggleVisibility={onToggleVisibility}
            onToggleSimpleMode={onToggleSimpleMode}
            onUndoLast={onUndoLast}
            onTogglePreview={onTogglePreview}
            onStartMatch={onStartMatch}
            onReset={onReset}
          />
        </div>
      </div>
    </>
  );
}
