import { useState, useEffect, useCallback, useMemo, useRef, FormEvent } from 'react';
import { useI18n } from './i18n';
import { useAppConfig } from './hooks/useAppConfig';
import { useGameState } from './hooks/useGameState';
import { useSettings } from './hooks/useSettings';
import { useOrientation } from './hooks/useOrientation';
import { usePreview } from './hooks/usePreview';
import { useSwipeNavigation } from './hooks/useSwipeNavigation';
import InitScreen from './components/InitScreen';
import ScoreboardView from './components/ScoreboardView';
import ConfigPanel from './components/ConfigPanel';
import SetValueDialog from './components/SetValueDialog';
import ErrorBoundary from './components/ErrorBoundary';
import type { GameState } from './api/client';
import type { ConfigModel } from './components/TeamCard';
import type { ScoreButtonFontStyle } from './components/ScoreButton';
import {
  TEAM_A_COLOR,
  TEAM_B_COLOR,
  FONT_SCALES,
} from './theme';
import { HUD_AUTO_HIDE_MS } from './constants';

type Team = 1 | 2;

interface DialogState {
  open: boolean;
  title: string;
  initialValue: number;
  maxValue: number;
  team: Team | null;
  isSet: boolean;
}

interface FontScale {
  scale: number;
  offset_y: number;
}

function getInitialOid(): string {
  const params = new URLSearchParams(window.location.search);
  const urlOid = params.get('oid') || params.get('control');
  if (urlOid) return urlOid;
  try {
    return localStorage.getItem('volley_oid') || '';
  } catch {
    return '';
  }
}

export default function App() {
  const { t } = useI18n();
  const appConfig = useAppConfig();
  const { settings, setSetting } = useSettings();
  const { isPortrait, buttonSize, hasRoomForPersistentControls } = useOrientation();

  const [oid, setOid] = useState<string>(getInitialOid);
  const [oidInput, setOidInput] = useState<string>(oid);
  const [activeTab, setActiveTab] = useState<'scoreboard' | 'config'>('scoreboard');
  const swipeHandlers = useSwipeNavigation({
    onSwipeLeft: activeTab === 'scoreboard' ? () => setActiveTab('config') : undefined,
    // Route through history.back() so ConfigPanel's popstate listener can
    // run the unsaved-changes confirmation before tearing down.
    onSwipeRight: activeTab === 'config' ? () => window.history.back() : undefined,
  });
  const [isFullscreen, setIsFullscreen] = useState<boolean>(!!document.fullscreenElement);
  const [showControls, setShowControls] = useState(true);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const resetHideTimer = useCallback(() => {
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    hideTimerRef.current = setTimeout(() => setShowControls(false), HUD_AUTO_HIDE_MS);
  }, []);

  const [dialog, setDialog] = useState<DialogState>({
    open: false,
    title: '',
    initialValue: 0,
    maxValue: 99,
    team: null,
    isSet: false,
  });

  const {
    state,
    customization,
    error,
    initialize,
    actions,
    refreshCustomization,
    setCustomization,
  } = useGameState(oid);

  // Gate preview fetch on session readiness — /api/v1/links returns 404 until
  // initSession has created the session.
  const previewData = usePreview(oid, settings.showPreview, !!state);

  // Reveal the bar when the viewport gains room for it (e.g. phone→tablet
  // resize). Kept in its own effect so the manual hide toggle still works
  // on tablets — the auto-hide effect below would otherwise re-show it on
  // every showControls change.
  useEffect(() => {
    if (hasRoomForPersistentControls) {
      setShowControls(true);
    }
  }, [hasRoomForPersistentControls]);

  // Reveal the bar whenever the match flips back to the pending state
  // (initial load or post-reset) so the operator can see the Start button.
  const matchStartedAt = state?.match_started_at ?? null;
  useEffect(() => {
    if (matchStartedAt == null) {
      setShowControls(true);
    }
  }, [matchStartedAt, setShowControls]);

  useEffect(() => {
    // On tablets/desktops the control bar fits without covering scoreboard
    // elements, so skip the inactivity timer entirely.
    if (hasRoomForPersistentControls) return;
    // Keep the bar visible while the match is pending — only arm the
    // inactivity timer once ``match_started_at`` is stamped. Also covers
    // the pre-init case where ``state`` itself is still null.
    if (state?.match_started_at == null) return;
    if (showControls && activeTab === 'scoreboard') {
      resetHideTimer();
      window.addEventListener('pointerdown', resetHideTimer, { passive: true });
    }
    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
      window.removeEventListener('pointerdown', resetHideTimer);
    };
  }, [showControls, activeTab, state, resetHideTimer, hasRoomForPersistentControls]);

  const setsLimit = (state?.config?.sets_limit as number | undefined) ?? 5;
  const matchFinished = state?.match_finished ?? false;
  const simpleMode = state?.simple_mode ?? false;

  const computeCurrentSet = useCallback((): number => {
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

  const handleInit = useCallback(
    (e?: FormEvent<HTMLFormElement>) => {
      e?.preventDefault();
      if (oidInput.trim()) {
        setOid(oidInput.trim());
      }
    },
    [oidInput]
  );

  useEffect(() => {
    if (oid) {
      try { localStorage.setItem('volley_oid', oid); } catch (e) { console.warn('Failed to save OID:', e); }
      initialize();
    }
  }, [oid, initialize]);

  const handleAddPoint = useCallback(
    (team: Team) => {
      if (matchFinished) return;
      actions.addPoint(team, false);
      if (settings.autoSimple && !simpleMode) {
        actions.setSimpleMode(true);
      }
    },
    [actions, matchFinished, settings.autoSimple, simpleMode]
  );

  const handleAddSet = useCallback(
    (team: Team) => {
      if (matchFinished) return;
      actions.addSet(team, false);
    },
    [actions, matchFinished]
  );

  const handleAddTimeout = useCallback(
    (team: Team) => {
      if (matchFinished) return;
      actions.addTimeout(team, false);
      if (settings.autoSimple && settings.autoSimpleOnTimeout && simpleMode) {
        actions.setSimpleMode(false);
      }
    },
    [actions, matchFinished, settings.autoSimple, settings.autoSimpleOnTimeout, simpleMode]
  );

  const handleChangeServe = useCallback(
    (team: Team) => { actions.changeServe(team); },
    [actions]
  );

  const handleToggleVisibility = useCallback(() => {
    if (state) actions.setVisibility(!state.visible);
  }, [actions, state]);

  const handleToggleSimpleMode = useCallback(() => {
    actions.setSimpleMode(!simpleMode);
  }, [actions, simpleMode]);

  // Server-side LIFO: ``actions.undoLast()`` posts to /game/undo,
  // which pops from the audit log and reverses the action via the
  // existing per-type ``add_*(undo=True)`` path. The two undo
  // entry points (this and the per-team double-tap below) share
  // the same stack on the server and cannot drift.
  const handleUndoLast = useCallback(() => {
    actions.undoLast();
  }, [actions]);

  const handleToggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
      setIsFullscreen(false);
    } else {
      document.documentElement.requestFullscreen()
        .then(() => setIsFullscreen(true))
        .catch(() => setIsFullscreen(false));
    }
  }, []);

  const handleTogglePreview = useCallback(() => {
    setSetting('showPreview', !settings.showPreview);
  }, [setSetting, settings.showPreview]);

  const handleReset = useCallback(() => {
    if (window.confirm(t('config.resetConfirm'))) {
      actions.reset();
    }
  }, [actions, t]);

  const handleStartMatch = useCallback(() => {
    actions.startMatch();
  }, [actions]);

  const handleLogout = useCallback(() => {
    try { localStorage.removeItem('volley_oid'); } catch (e) { console.warn('Failed to remove OID:', e); }
    setOid('');
    setOidInput('');
    setActiveTab('scoreboard');
  }, []);

  const handleSetChange = useCallback(
    (set: number) => {
      const clamped = Math.max(1, Math.min(set, setsLimit));
      setCurrentSet(clamped);
    },
    [setsLimit]
  );

  // Per-team double-tap undoes the most recent forward of the
  // same (action, team). The server-side per-type undo path now
  // pops the matching forward from the audit log on its own, so
  // no client-side bookkeeping is required.
  const handleDoubleTapScore = useCallback(
    (team: Team) => {
      actions.addPoint(team, true);
    },
    [actions]
  );

  const handleDoubleTapTimeout = useCallback(
    (team: Team) => {
      actions.addTimeout(team, true);
    },
    [actions]
  );

  const handleLongPressScore = useCallback(
    (team: Team) => {
      if (!state) return;
      const teamState = team === 1 ? state.team_1 : state.team_2;
      const rawScore = teamState.scores?.[`set_${currentSet}`];
      const currentScore = typeof rawScore === 'number' ? rawScore : 0;
      setDialog({
        open: true,
        title: t('dialog.setScore', { team }),
        initialValue: currentScore,
        maxValue: 99,
        team,
        isSet: false,
      });
    },
    [state, currentSet, t]
  );

  const handleLongPressSet = useCallback(
    (team: Team) => {
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
    [state, setsLimit, t]
  );

  const handleDialogSubmit = useCallback(
    (value: number) => {
      if (dialog.team === null) return;
      if (dialog.isSet) {
        actions.setSets(dialog.team, value);
      } else {
        actions.setScore(dialog.team, currentSet, value);
      }
      setDialog((d) => ({ ...d, open: false }));
    },
    [dialog, actions, currentSet]
  );

  const asColor = (v: unknown, fallback: string): string =>
    typeof v === 'string' && v ? v : fallback;
  const asLogo = (v: unknown): string | null =>
    typeof v === 'string' && v ? v : null;

  const btnColorA = settings.followTeamColors
    ? asColor(customization?.['Team 1 Color'], TEAM_A_COLOR)
    : (settings.team1BtnColor ?? TEAM_A_COLOR);
  const btnTextA = settings.followTeamColors
    ? asColor(customization?.['Team 1 Text Color'], '#ffffff')
    : (settings.team1BtnText ?? '#ffffff');
  const btnColorB = settings.followTeamColors
    ? asColor(customization?.['Team 2 Color'], TEAM_B_COLOR)
    : (settings.team2BtnColor ?? TEAM_B_COLOR);
  const btnTextB = settings.followTeamColors
    ? asColor(customization?.['Team 2 Text Color'], '#ffffff')
    : (settings.team2BtnText ?? '#ffffff');

  const iconLogoA = settings.showIcon ? asLogo(customization?.['Team 1 Logo']) : null;
  const iconLogoB = settings.showIcon ? asLogo(customization?.['Team 2 Logo']) : null;

  const fontStyle = useMemo<ScoreButtonFontStyle>(() => {
    const fontScales = FONT_SCALES as Record<string, FontScale>;
    const fontProps: FontScale = fontScales[settings.selectedFont] ?? fontScales.Default;
    return settings.selectedFont && settings.selectedFont !== 'Default'
      ? { fontFamily: `'${settings.selectedFont}'`, fontScale: fontProps.scale, fontOffsetY: fontProps.offset_y }
      : { fontFamily: undefined, fontScale: 1.0, fontOffsetY: 0.0 };
  }, [settings.selectedFont]);

  if (!oid || !state) {
    return (
      <InitScreen
        oidInput={oidInput}
        setOidInput={setOidInput}
        onSubmit={handleInit}
        onSelect={setOid}
        error={error}
        title={appConfig.title}
      />
    );
  }

  return (
    <div className="app-container" {...swipeHandlers}>
      {activeTab === 'scoreboard' && (
        <ErrorBoundary>
        <ScoreboardView
          state={state}
          customization={customization}
          currentSet={currentSet}
          setsLimit={setsLimit}
          isPortrait={isPortrait}
          buttonSize={buttonSize}
          previewData={previewData}
          showPreview={settings.showPreview}
          // Landscape phones (no room for persistent controls) need the
          // preview shrunk so the alert pills below it don't get pushed
          // off the bottom of the viewport.
          compactLandscape={!isPortrait && !hasRoomForPersistentControls}
          showControls={showControls}
          setShowControls={setShowControls}
          canUndo={state?.can_undo ?? false}
          simpleMode={simpleMode}
          btnColorA={btnColorA}
          btnTextA={btnTextA}
          btnColorB={btnColorB}
          btnTextB={btnTextB}
          iconLogoA={iconLogoA}
          iconLogoB={iconLogoB}
          iconOpacity={settings.iconOpacity}
          fontStyle={fontStyle}
          onAddPoint={handleAddPoint}
          onAddSet={handleAddSet}
          onAddTimeout={handleAddTimeout}
          onChangeServe={handleChangeServe}
          onDoubleTapScore={handleDoubleTapScore}
          onDoubleTapTimeout={handleDoubleTapTimeout}
          onLongPressScore={handleLongPressScore}
          onLongPressSet={handleLongPressSet}
          onSetChange={handleSetChange}
          onToggleVisibility={handleToggleVisibility}
          onToggleSimpleMode={handleToggleSimpleMode}
          onUndoLast={handleUndoLast}
          onTogglePreview={handleTogglePreview}
          onStartMatch={handleStartMatch}
          onReset={handleReset}
          onOpenConfig={() => setActiveTab('config')}
        />
        </ErrorBoundary>
      )}

      {activeTab === 'config' && (
        <ErrorBoundary>
          <ConfigPanel
            oid={oid}
            customization={customization}
            actions={actions}
            gameConfig={state?.config ?? null}
            onBack={() => setActiveTab('scoreboard')}
            onLogout={handleLogout}
            onCustomizationSaved={refreshCustomization}
            darkMode={settings.darkMode}
            isFullscreen={isFullscreen}
            onToggleDarkMode={() => {
              // Cycle: auto → dark → light → auto
              const current = settings.darkMode;
              const next = current === 'auto' ? true : current === true ? false : 'auto';
              setSetting('darkMode', next);
            }}
            onToggleFullscreen={handleToggleFullscreen}
          />
        </ErrorBoundary>
      )}

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
