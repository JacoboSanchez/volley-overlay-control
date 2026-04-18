import React from 'react';
import { useI18n } from '../i18n';
import TeamPanel from './TeamPanel';
import CenterPanel from './CenterPanel';
import ControlButtons from './ControlButtons';
import {
  TEAM_A_SERVE_ACTIVE,
  TEAM_B_SERVE_ACTIVE,
  TEAM_A_LIGHT,
  TEAM_B_LIGHT,
} from '../theme';

export default function ScoreboardView({
  state,
  customization,
  currentSet,
  setsLimit,
  isPortrait,
  buttonSize,
  previewData,
  showPreview,
  showControls,
  setShowControls,
  undoMode,
  simpleMode,
  matchFinished,
  isFullscreen,
  darkMode,
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
  onLongPressScore,
  onLongPressSet,
  onSetChange,
  onToggleVisibility,
  onToggleSimpleMode,
  onToggleUndo,
  onToggleDarkMode,
  onToggleFullscreen,
  onTogglePreview,
  onOpenConfig,
}) {
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
          onLongPressScore={onLongPressScore}
        />

        <CenterPanel
          state={state}
          customization={customization}
          currentSet={currentSet}
          setsLimit={setsLimit}
          isPortrait={isPortrait}
          previewData={showPreview ? previewData : null}
          onAddSet={onAddSet}
          onLongPressSet={onLongPressSet}
          onSetChange={onSetChange}
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
          <span className="material-icons">more_vert</span>
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
            undoMode={undoMode}
            darkMode={darkMode}
            isFullscreen={isFullscreen}
            matchFinished={matchFinished}
            showPreview={showPreview}
            onToggleVisibility={onToggleVisibility}
            onToggleSimpleMode={onToggleSimpleMode}
            onToggleUndo={onToggleUndo}
            onToggleDarkMode={onToggleDarkMode}
            onToggleFullscreen={onToggleFullscreen}
            onTogglePreview={onTogglePreview}
          />
        </div>
      </div>
    </>
  );
}
