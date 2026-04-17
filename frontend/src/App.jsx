import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useI18n } from './i18n';
import { useGameState } from './hooks/useGameState';
import { useSettings } from './hooks/useSettings';
import { useOrientation } from './hooks/useOrientation';
import { usePreview } from './hooks/usePreview';
import * as api from './api/client';
import TeamPanel from './components/TeamPanel';
import CenterPanel from './components/CenterPanel';
import ControlButtons from './components/ControlButtons';
import ConfigPanel from './components/ConfigPanel';
import SetValueDialog from './components/SetValueDialog';
import {
  TEAM_A_COLOR,
  TEAM_B_COLOR,
  TEAM_A_SERVE_ACTIVE,
  TEAM_B_SERVE_ACTIVE,
  TEAM_A_LIGHT,
  TEAM_B_LIGHT,
  FONT_SCALES,
} from './theme';

function getInitialOid() {
  const params = new URLSearchParams(window.location.search);
  const urlOid = params.get('oid');
  if (urlOid) return urlOid;
  try {
    return localStorage.getItem('volley_oid') || '';
  } catch { return ''; }
}

export default function App() {
  const { t } = useI18n();
  const { settings, setSetting } = useSettings();
  const { isPortrait, buttonSize } = useOrientation();

  const [oid, setOid] = useState(getInitialOid);
  const [oidInput, setOidInput] = useState(oid);
  const [undoMode, setUndoMode] = useState(false);
  const [activeTab, setActiveTab] = useState('scoreboard');
  const [isFullscreen, setIsFullscreen] = useState(!!document.fullscreenElement);
  const [showControls, setShowControls] = useState(true);
  const hideTimerRef = useRef(null);

  const resetHideTimer = useCallback(() => {
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    hideTimerRef.current = setTimeout(() => setShowControls(false), 10000);
  }, [setShowControls]);

  const previewData = usePreview(oid, settings.showPreview);

  // Dialog state
  const [dialog, setDialog] = useState({
    open: false,
    title: '',
    initialValue: 0,
    maxValue: 99,
    team: null,
    isSet: false,
  });

  const { state, customization, connected, error, initialize, actions, refreshCustomization, setCustomization } = useGameState(oid);

  useEffect(() => {
    if (showControls && activeTab === 'scoreboard' && state) {
      resetHideTimer();
      window.addEventListener('pointerdown', resetHideTimer, { passive: true });
    }
    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
      window.removeEventListener('pointerdown', resetHideTimer);
    };
  }, [showControls, activeTab, !!state, resetHideTimer]);

  // Compute current set from state
  const setsLimit = state?.config?.sets_limit ?? 5;
  const pointsLimit = state?.config?.points_limit ?? 25;
  const matchFinished = state?.match_finished ?? false;
  const simpleMode = state?.simple_mode ?? false;

  const computeCurrentSet = useCallback(() => {
    if (!state) return 1;
    const t1 = state.team_1.sets;
    const t2 = state.team_2.sets;
    let cs = t1 + t2;
    if (!matchFinished) cs += 1;
    return Math.max(1, Math.min(cs, setsLimit));
  }, [state, matchFinished, setsLimit]);

  const [currentSet, setCurrentSet] = useState(1);

  useEffect(() => {
    if (state) {
      setCurrentSet(computeCurrentSet());
    }
  }, [state, computeCurrentSet]);

  // Initialize session
  const handleInit = useCallback(
    (e) => {
      e?.preventDefault();
      if (oidInput.trim()) {
        setOid(oidInput.trim());
      }
    },
    [oidInput]
  );

  // Persist OID to localStorage when OID changes
  useEffect(() => {
    if (oid) {
      try { localStorage.setItem('volley_oid', oid); } catch (e) { console.warn('Failed to save OID:', e); }
      initialize();
    }
  }, [oid, initialize]);

  // Actions
  const handleAddPoint = useCallback(
    (team) => {
      if (!undoMode && matchFinished) return;
      actions.addPoint(team, undoMode);
      if (undoMode) setUndoMode(false);
      if (settings.autoSimple && !simpleMode && !undoMode) {
        actions.setSimpleMode(true);
      }
    },
    [actions, undoMode, matchFinished, settings.autoSimple, simpleMode]
  );

  const handleAddSet = useCallback(
    (team) => {
      if (!undoMode && matchFinished) return;
      actions.addSet(team, undoMode);
      if (undoMode) setUndoMode(false);
    },
    [actions, undoMode, matchFinished]
  );

  const handleAddTimeout = useCallback(
    (team) => {
      if (!undoMode && matchFinished) return;
      actions.addTimeout(team, undoMode);
      if (undoMode) setUndoMode(false);
      if (settings.autoSimple && settings.autoSimpleOnTimeout && simpleMode && !undoMode) {
        actions.setSimpleMode(false);
      }
    },
    [actions, undoMode, matchFinished, settings.autoSimple, settings.autoSimpleOnTimeout, simpleMode]
  );

  const handleChangeServe = useCallback(
    (team) => {
      actions.changeServe(team);
    },
    [actions]
  );

  const handleToggleVisibility = useCallback(() => {
    if (state) {
      actions.setVisibility(!state.visible);
    }
  }, [actions, state]);

  const handleToggleSimpleMode = useCallback(() => {
    actions.setSimpleMode(!simpleMode);
  }, [actions, simpleMode]);

  const handleToggleUndo = useCallback(() => {
    setUndoMode((u) => !u);
  }, []);

  const handleToggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
      setIsFullscreen(false);
    } else {
      document.documentElement.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => setIsFullscreen(false));
    }
  }, []);

  const handleTogglePreview = useCallback(() => {
    setSetting('showPreview', !settings.showPreview);
  }, [setSetting, settings.showPreview]);

  const handleReset = useCallback(() => {
    if (window.confirm(t('config.resetConfirm'))) {
      actions.reset();
      setUndoMode(false);
    }
  }, [actions, t]);

  const handleLogout = useCallback(() => {
    try { localStorage.removeItem('volley_oid'); } catch (e) { console.warn('Failed to remove OID:', e); }
    setOid('');
    setOidInput('');
    setUndoMode(false);
    setActiveTab('scoreboard');
  }, []);

  const handleSetChange = useCallback(
    (set) => {
      const clamped = Math.max(1, Math.min(set, setsLimit));
      setCurrentSet(clamped);
    },
    [setsLimit]
  );

  // Double-tap handler — undo last point
  const handleDoubleTapScore = useCallback(
    (team) => {
      actions.addPoint(team, true);
    },
    [actions]
  );

  // Long-press handlers for custom value dialog
  const handleLongPressScore = useCallback(
    (team) => {
      if (!state) return;
      const teamState = team === 1 ? state.team_1 : state.team_2;
      const currentScore = teamState.scores[`set_${currentSet}`] ?? 0;
      setDialog({
        open: true,
        title: t('dialog.setScore', { team }),
        initialValue: currentScore,
        maxValue: 99,
        team,
        isSet: false,
      });
    },
    [state, currentSet]
  );

  const handleLongPressSet = useCallback(
    (team) => {
      if (!state) return;
      const teamState = team === 1 ? state.team_1 : state.team_2;
      setDialog({
        open: true,
        title: t('dialog.setSets', { team }),
        initialValue: teamState.sets,
        maxValue: Math.ceil(setsLimit / 2),
        team,
        isSet: true,
      });
    },
    [state, setsLimit]
  );

  const handleDialogSubmit = useCallback(
    (value) => {
      if (dialog.isSet) {
        actions.setSets(dialog.team, value);
      } else {
        actions.setScore(dialog.team, currentSet, value);
      }
      setDialog((d) => ({ ...d, open: false }));
    },
    [dialog, actions, currentSet]
  );

  // Compute button colors from settings
  const btnColorA = settings.followTeamColors
    ? (customization?.['Team 1 Color'] ?? TEAM_A_COLOR)
    : (settings.team1BtnColor ?? TEAM_A_COLOR);
  const btnTextA = settings.followTeamColors
    ? (customization?.['Team 1 Text Color'] ?? '#ffffff')
    : (settings.team1BtnText ?? '#ffffff');
  const btnColorB = settings.followTeamColors
    ? (customization?.['Team 2 Color'] ?? TEAM_B_COLOR)
    : (settings.team2BtnColor ?? TEAM_B_COLOR);
  const btnTextB = settings.followTeamColors
    ? (customization?.['Team 2 Text Color'] ?? '#ffffff')
    : (settings.team2BtnText ?? '#ffffff');

  const iconLogoA = settings.showIcon ? (customization?.['Team 1 Logo'] ?? null) : null;
  const iconLogoB = settings.showIcon ? (customization?.['Team 2 Logo'] ?? null) : null;

  // Font style for score buttons
  const fontProps = FONT_SCALES[settings.selectedFont] || FONT_SCALES.Default;
  const fontStyle = settings.selectedFont && settings.selectedFont !== 'Default'
    ? { fontFamily: `'${settings.selectedFont}'`, fontScale: fontProps.scale, fontOffsetY: fontProps.offset_y }
    : { fontFamily: undefined, fontScale: 1.0, fontOffsetY: 0.0 };

  // Predefined overlays for selection on init screen
  const [predefinedOverlays, setPredefinedOverlays] = useState([]);
  useEffect(() => {
    api.getOverlays().then((data) => {
      let overlays = [];
      if (Array.isArray(data)) {
        overlays = data
          .map((item) => {
            if (item && typeof item === 'object' && item.oid) {
              return { oid: item.oid, name: item.name || item.oid };
            }
            if (typeof item === 'string' && item) {
              return { oid: item, name: item };
            }
            return null;
          })
          .filter(Boolean);
      } else if (data && typeof data === 'object') {
        overlays = Object.entries(data).map(([name, oid]) => ({ oid, name }));
      }
      setPredefinedOverlays(overlays);
    }).catch((error) => {
      console.warn('Failed to fetch predefined overlays:', error);
    });
  }, []);

  const handleOverlaySelect = useCallback((e) => {
    setOidInput(e.target.value);
    if (e.target.value) {
      setOid(e.target.value);
    }
  }, []);

  // OID entry screen
  if (!oid || !state) {
    return (
      <div className="init-screen">
        <h1 className="init-title">{t('app.title')}</h1>
        {predefinedOverlays.length > 0 && (
          <div className="init-overlay-selector">
            <label className="init-label">{t('app.selectOverlay')}</label>
            <select
              className="init-select"
              defaultValue=""
              onChange={handleOverlaySelect}
            >
              <option value="">{t('app.selectOverlayPlaceholder')}</option>
              {predefinedOverlays.map((o) => (
                <option key={o.oid} value={o.oid}>{o.name}</option>
              ))}
            </select>
            <div className="init-divider"><span>{t('app.orManualOid')}</span></div>
          </div>
        )}
        <form onSubmit={handleInit} className="init-form">
          <label className="init-label">{t('app.oidLabel')}</label>
          <input
            className="init-input"
            type="text"
            value={oidInput}
            onChange={(e) => setOidInput(e.target.value)}
            placeholder={t('app.oidPlaceholder')}
            autoFocus={predefinedOverlays.length === 0}
          />
          <button className="init-button" type="submit" disabled={!oidInput.trim()}>
            {t('app.connect')}
          </button>
          {error && <p className="init-error">{error}</p>}
        </form>
      </div>
    );
  }

  return (
    <div className="app-container">

      {/* Main scoreboard layout */}
      {activeTab === 'scoreboard' && (
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
          iconOpacity={settings.iconOpacity}
          fontStyle={fontStyle}
          state={state}
          setsLimit={setsLimit}
          customization={customization}
          onAddPoint={handleAddPoint}
          onAddTimeout={handleAddTimeout}
          onChangeServe={handleChangeServe}
          onDoubleTapScore={handleDoubleTapScore}
          onLongPressScore={handleLongPressScore}
        />

        <CenterPanel
          state={state}
          customization={customization}
          currentSet={currentSet}
          setsLimit={setsLimit}
          isPortrait={isPortrait}
          previewData={settings.showPreview ? previewData : null}
          onAddSet={handleAddSet}
          onLongPressSet={handleLongPressSet}
          onSetChange={handleSetChange}
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
          iconOpacity={settings.iconOpacity}
          fontStyle={fontStyle}
          state={state}
          setsLimit={setsLimit}
          customization={customization}
          onAddPoint={handleAddPoint}
          onAddTimeout={handleAddTimeout}
          onChangeServe={handleChangeServe}
          onDoubleTapScore={handleDoubleTapScore}
          onLongPressScore={handleLongPressScore}
        />
      </div>
      )}

      {/* HUD Controls */}
      {activeTab === 'scoreboard' && (
        <>
          <div className={`hud-controls ${!showControls ? 'ui-hidden' : ''}`}>
            <button
              className="top-right-config-btn"
              onClick={() => setActiveTab('config')}
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
                darkMode={settings.darkMode}
                isFullscreen={isFullscreen}
                matchFinished={matchFinished}
                showPreview={settings.showPreview}
                onToggleVisibility={handleToggleVisibility}
                onToggleSimpleMode={handleToggleSimpleMode}
                onToggleUndo={handleToggleUndo}
                onToggleDarkMode={() => setSetting('darkMode', !settings.darkMode)}
                onToggleFullscreen={handleToggleFullscreen}
                onTogglePreview={handleTogglePreview}
              />
            </div>
          </div>
        </>
      )}

      {/* Configuration panel (replaces scoreboard when active) */}
      {activeTab === 'config' && (
        <ConfigPanel
          oid={oid}
          customization={customization}
          actions={actions}
          onBack={() => setActiveTab('scoreboard')}
          onReset={handleReset}
          onLogout={handleLogout}
          onCustomizationSaved={refreshCustomization}
          onCustomizationRefreshed={setCustomization}
        />
      )}

      {/* Custom value dialog */}
      <SetValueDialog
        open={dialog.open}
        title={dialog.title}
        initialValue={dialog.initialValue}
        maxValue={dialog.maxValue}
        onSubmit={handleDialogSubmit}
        onClose={() => setDialog((d) => ({ ...d, open: false }))}
      />
    </div>
  );
}
