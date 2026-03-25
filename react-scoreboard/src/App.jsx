import React, { useState, useEffect, useCallback } from 'react';
import { useGameState } from './hooks/useGameState';
import * as api from './api/client';
import TeamPanel from './components/TeamPanel';
import CenterPanel from './components/CenterPanel';
import ControlButtons from './components/ControlButtons';
import ConfigPanel from './components/ConfigPanel';
import SetValueDialog from './components/SetValueDialog';
import {
  TEAM_A_COLOR,
  TEAM_B_COLOR,
  TEAM_A_LIGHT,
  TEAM_B_LIGHT,
  TEAM_A_SERVE_ACTIVE,
  TEAM_B_SERVE_ACTIVE,
} from './theme';

function getInitialOid() {
  // Priority: URL param > localStorage (matches NiceGUI's priority system)
  const params = new URLSearchParams(window.location.search);
  const urlOid = params.get('oid');
  if (urlOid) return urlOid;
  try {
    return localStorage.getItem('volley_oid') || '';
  } catch { return ''; }
}

export default function App() {
  const [oid, setOid] = useState(getInitialOid);
  const [oidInput, setOidInput] = useState(oid);
  const [undoMode, setUndoMode] = useState(false);
  const [simpleMode, setSimpleMode] = useState(false);
  const [isPortrait, setIsPortrait] = useState(false);
  const [buttonSize, setButtonSize] = useState(null);
  const [activeTab, setActiveTab] = useState('scoreboard');

  // Local visual settings (persisted in localStorage by ConfigPanel)
  const readLocalSetting = (key, fallback) => {
    try {
      const v = localStorage.getItem('volley_' + key);
      return v !== null ? JSON.parse(v) : fallback;
    } catch { return fallback; }
  };
  const followTeamColors = readLocalSetting('followTeamColors', true);
  const showIcon = readLocalSetting('showIcon', false);
  const iconOpacity = readLocalSetting('iconOpacity', 50);
  const autoSimple = readLocalSetting('autoSimple', false);
  const autoSimpleOnTimeout = readLocalSetting('autoSimpleOnTimeout', false);
  const showPreview = readLocalSetting('showPreview', false);

  // Preview data (overlay URL + geometry for cropping)
  const [previewData, setPreviewData] = useState(null);
  useEffect(() => {
    if (oid && showPreview) {
      api.getLinks(oid).then((links) => {
        if (links?.overlay && links?.preview) {
          // Parse geometry from the preview query string
          const params = new URLSearchParams(links.preview.split('?')[1] || '');
          setPreviewData({
            overlayUrl: links.overlay,
            x: parseFloat(params.get('x')) || 0,
            y: parseFloat(params.get('y')) || 0,
            width: parseFloat(params.get('width')) || 30,
            height: parseFloat(params.get('height')) || 10,
            layoutId: params.get('layout_id') || '',
          });
        } else {
          setPreviewData(null);
        }
      }).catch(() => setPreviewData(null));
    } else {
      setPreviewData(null);
    }
  }, [oid, showPreview]);

  // Dialog state
  const [dialog, setDialog] = useState({
    open: false,
    title: '',
    initialValue: 0,
    maxValue: 99,
    team: null,
    isSet: false,
  });

  const { state, customization, connected, error, initialize, actions, refreshCustomization } = useGameState(oid);

  // Compute current set from state
  const setsLimit = state?.config?.sets_limit ?? 5;
  const pointsLimit = state?.config?.points_limit ?? 25;
  const matchFinished = state?.match_finished ?? false;

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
      setSimpleMode(state.simple_mode);
    }
  }, [state, computeCurrentSet]);

  // Responsive layout
  useEffect(() => {
    function handleResize() {
      const w = window.innerWidth;
      const h = window.innerHeight;
      const portrait = h > 1.2 * w && w <= 800;
      setIsPortrait(portrait);
      if (!portrait) {
        setButtonSize(Math.min(w / 3.5, 360));
      } else {
        setButtonSize(Math.min(h / 4, 360));
      }
    }
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

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

  // Persist OID to localStorage and clear stale preview when OID changes
  useEffect(() => {
    if (oid) {
      try { localStorage.setItem('volley_oid', oid); } catch {}
      setPreviewData(null);  // clear stale preview from previous OID
      initialize();
    }
  }, [oid, initialize]);

  // Actions
  const handleAddPoint = useCallback(
    (team) => {
      if (!undoMode && matchFinished) return;
      actions.addPoint(team, undoMode);
      if (undoMode) setUndoMode(false);
      // Auto simple mode: switch to simple after scoring
      if (autoSimple && !simpleMode && !undoMode) {
        actions.setSimpleMode(true);
        setSimpleMode(true);
      }
    },
    [actions, undoMode, matchFinished, autoSimple, simpleMode]
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
      actions.addTimeout(team, undoMode);
      if (undoMode) setUndoMode(false);
      // Auto simple on timeout: switch back to full mode when timeout is called
      if (autoSimple && autoSimpleOnTimeout && simpleMode && !undoMode) {
        actions.setSimpleMode(false);
        setSimpleMode(false);
      }
    },
    [actions, undoMode, autoSimple, autoSimpleOnTimeout, simpleMode]
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
    setSimpleMode((s) => !s);
  }, [actions, simpleMode]);

  const handleToggleUndo = useCallback(() => {
    setUndoMode((u) => !u);
  }, []);

  const handleReset = useCallback(() => {
    if (window.confirm('Reset the match?')) {
      actions.reset();
      setUndoMode(false);
      setSimpleMode(false);
    }
  }, [actions]);

  const handleLogout = useCallback(() => {
    try { localStorage.removeItem('volley_oid'); } catch {}
    setOid('');
    setOidInput('');
    setPreviewData(null);
    setUndoMode(false);
    setSimpleMode(false);
    setActiveTab('scoreboard');
  }, []);

  const handleSetChange = useCallback(
    (set) => {
      const clamped = Math.max(1, Math.min(set, setsLimit));
      setCurrentSet(clamped);
    },
    [setsLimit]
  );

  // Long-press handlers for custom value dialog
  const handleLongPressScore = useCallback(
    (team) => {
      if (!state) return;
      const teamState = team === 1 ? state.team_1 : state.team_2;
      const currentScore = teamState.scores[`set_${currentSet}`] ?? 0;
      setDialog({
        open: true,
        title: `Set score — Team ${team}`,
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
        title: `Set sets won — Team ${team}`,
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
  const btnColorA = followTeamColors
    ? (customization?.['Team 1 Color'] ?? TEAM_A_COLOR)
    : readLocalSetting('team1BtnColor', TEAM_A_COLOR);
  const btnTextA = followTeamColors
    ? (customization?.['Team 1 Text Color'] ?? '#ffffff')
    : readLocalSetting('team1BtnText', '#ffffff');
  const btnColorB = followTeamColors
    ? (customization?.['Team 2 Color'] ?? TEAM_B_COLOR)
    : readLocalSetting('team2BtnColor', TEAM_B_COLOR);
  const btnTextB = followTeamColors
    ? (customization?.['Team 2 Text Color'] ?? '#ffffff')
    : readLocalSetting('team2BtnText', '#ffffff');

  const iconLogoA = showIcon ? (customization?.['Team 1 Logo'] ?? null) : null;
  const iconLogoB = showIcon ? (customization?.['Team 2 Logo'] ?? null) : null;

  // OID entry screen
  if (!oid || !state) {
    return (
      <div className="init-screen">
        <h1 className="init-title">Volley Scoreboard</h1>
        <form onSubmit={handleInit} className="init-form">
          <label className="init-label">Overlay Control ID (OID)</label>
          <input
            className="init-input"
            type="text"
            value={oidInput}
            onChange={(e) => setOidInput(e.target.value)}
            placeholder="C-my-overlay"
            autoFocus
          />
          <button className="init-button" type="submit" disabled={!oidInput.trim()}>
            Connect
          </button>
          {error && <p className="init-error">{error}</p>}
        </form>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Connection status */}
      <div className={`status-bar ${connected ? 'status-connected' : 'status-disconnected'}`}>
        {connected ? 'Connected' : 'Disconnected — reconnecting...'}
      </div>

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
          iconOpacity={iconOpacity}
          onAddPoint={handleAddPoint}
          onAddTimeout={handleAddTimeout}
          onChangeServe={handleChangeServe}
          onLongPressScore={handleLongPressScore}
        />

        <CenterPanel
          state={state}
          customization={customization}
          currentSet={currentSet}
          setsLimit={setsLimit}
          previewData={showPreview ? previewData : null}
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
          iconOpacity={iconOpacity}
          onAddPoint={handleAddPoint}
          onAddTimeout={handleAddTimeout}
          onChangeServe={handleChangeServe}
          onLongPressScore={handleLongPressScore}
        />
      </div>
      )}

      {/* Control buttons */}
      {activeTab === 'scoreboard' && (
        <ControlButtons
          visible={state.visible}
          simpleMode={simpleMode}
          undoMode={undoMode}
          matchFinished={matchFinished}
          onToggleVisibility={handleToggleVisibility}
          onToggleSimpleMode={handleToggleSimpleMode}
          onToggleUndo={handleToggleUndo}
          onGoToConfig={() => setActiveTab('config')}
        />
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
