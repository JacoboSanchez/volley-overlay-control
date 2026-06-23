import { useState, useEffect, useCallback, useMemo } from 'react';
import { setControlToken, setPublicUser } from './api/client';
import { useI18n } from './i18n';
import { useAppConfig } from './hooks/useAppConfig';
import { useGameState } from './hooks/useGameState';
import { useRecentEvents } from './hooks/useRecentEvents';
import { useSettings } from './hooks/useSettings';
import { useOrientation } from './hooks/useOrientation';
import { usePreview } from './hooks/usePreview';
import { useSwipeNavigation } from './hooks/useSwipeNavigation';
import { useHaptics } from './hooks/useHaptics';
import { useMatchAlertHaptics } from './hooks/useMatchAlertHaptics';
import { useScreenWakeLock } from './hooks/useScreenWakeLock';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { useAutoSetSummary } from './hooks/useAutoSetSummary';
import { useOidSession } from './hooks/useOidSession';
import { useHudVisibility } from './hooks/useHudVisibility';
import { useStaleSetPrompt } from './hooks/useStaleSetPrompt';
import { useShareLinks } from './hooks/useShareLinks';
import { useCoachmark } from './hooks/useCoachmark';
import { useOverlayLocaleSync } from './hooks/useOverlayLocaleSync';
import { useScoreActions } from './hooks/useScoreActions';
import { useSetValueDialog } from './hooks/useSetValueDialog';
import { useButtonTheme } from './hooks/useButtonTheme';
import InitScreen from './components/InitScreen';
import ScoreboardView from './components/ScoreboardView';
import ScoreboardSkeleton from './components/ScoreboardSkeleton';
import ConfigPanel from './components/ConfigPanel';
import ConnectionStatus from './components/ConnectionStatus';
import AppDialogs from './components/AppDialogs';
import PointTypePicker from './components/PointTypePicker';
import ErrorBoundary from './components/ErrorBoundary';
import { asString } from './utils/coerce';

export default function App(
  { controlToken, publicUser }: { controlToken?: string; publicUser?: string } = {},
) {
  // Register the board capability (operator token or public username) before any
  // request fires (the session-init effect below runs after this render).
  // ``useMemo`` sets them synchronously during render; owner mode clears both.
  const unauthenticated = !!controlToken || !!publicUser;
  useMemo(() => {
    setControlToken(controlToken ?? null);
    setPublicUser(publicUser ?? null);
  }, [controlToken, publicUser]);

  const { t, lang } = useI18n();
  const appConfig = useAppConfig();
  const { settings, setSetting } = useSettings();
  const { isPortrait, buttonSize, hasRoomForPersistentControls } = useOrientation();

  const [activeTab, setActiveTab] = useState<'scoreboard' | 'config'>('scoreboard');
  const { oid, setOid, oidInput, setOidInput, handleInit, handleLogout } = useOidSession({
    onLogout: useCallback(() => setActiveTab('scoreboard'), []),
    initialOid: controlToken,
  });
  const swipeHandlers = useSwipeNavigation({
    onSwipeLeft: activeTab === 'scoreboard' ? () => setActiveTab('config') : undefined,
    // Route through history.back() so ConfigPanel's popstate listener can
    // run the unsaved-changes confirmation before tearing down.
    onSwipeRight: activeTab === 'config' ? () => window.history.back() : undefined,
  });
  const [isFullscreen, setIsFullscreen] = useState<boolean>(!!document.fullscreenElement);

  const {
    state,
    confirmedState,
    customization,
    connected,
    error,
    initialize,
    actions,
    refreshCustomization,
  } = useGameState(oid);

  // Persist the chosen OID and (re)create the backend session. Lives
  // here rather than in useOidSession because ``initialize`` comes
  // from ``useGameState(oid)``, which needs the hook's ``oid`` first.
  useEffect(() => {
    if (oid) {
      // Don't persist a capability handle to localStorage in an unauthenticated
      // board mode — it's a shared-device credential and a stale value would
      // hijack a later owner visit to /board.
      if (!unauthenticated) {
        try {
          localStorage.setItem('volley_oid', oid);
        } catch (e) {
          console.warn('Failed to save OID:', e);
        }
      }
      initialize();
    }
  }, [oid, initialize, unauthenticated]);

  useOverlayLocaleSync({ oid, lang, customization, refreshCustomization });

  const { pulse } = useHaptics();
  // Set / match / finished transitions vibrate via the shared
  // useHaptics throttle so the operator gets a confirmed signal
  // even when the HUD has auto-hidden behind the play.
  useMatchAlertHaptics(state);

  // Hold a Screen Wake Lock for the operator's device while a
  // match is actively in progress, so the phone doesn't dim or
  // lock between rallies. Released on match end, on reset, and
  // when the page is hidden — re-acquired automatically when the
  // operator returns to the tab. No-op on unsupported runtimes
  // (desktop browsers, pre-iOS-16.4 Safari).
  const matchInProgress = !!state && state.match_started_at != null && !state.match_finished;
  useScreenWakeLock(matchInProgress);

  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);

  const { stalePromptOpen, setStalePromptOpen } = useStaleSetPrompt({
    state,
    thresholdMinutes: appConfig.stale_set_threshold_minutes,
  });

  // Auto-trigger the set-summary recap on each set transition (operator
  // opt-in via the Behavior section). The recap waits ``delaySec`` so
  // the broadcast camera has time to linger on the players' reaction
  // before the overlay covers them, then dismisses after ``durationSec``.
  useAutoSetSummary({
    state: confirmedState,
    enabled: settings.setSummaryEnabled && settings.autoShowSetSummary,
    delaySec: settings.autoShowSetSummaryDelay,
    durationSec: settings.autoShowSetSummaryDuration,
    setSetSummary: (v) => actions.setSetSummary(v),
  });

  const { coachmarkOpen, handleCoachmarkDismiss } = useCoachmark({
    state,
    gestureTourSeen: settings.gestureTourSeen,
    setSetting,
  });

  const { shareOpen, setShareOpen, shareLinks, handleOpenShare } = useShareLinks(oid);

  // Recent-audit drawer: a non-modal slide-in panel that surfaces
  // the per-OID action log so the operator can verify what just
  // happened without leaving the scoreboard. Lazy-fetched on open
  // by ``useAuditLog`` inside the component itself.
  const [historyOpen, setHistoryOpen] = useState(false);

  // Keyboard shortcuts help modal — opened with `?`, listed in the
  // Behavior section as a "Show shortcuts" entry.
  const [shortcutsHelpOpen, setShortcutsHelpOpen] = useState(false);

  // Gate preview fetch on session readiness — /api/v1/links returns 404 until
  // initSession has created the session.
  const previewData = usePreview(oid, settings.showPreview, !!state);

  // Landscape phones run with a narrower centre slot; truncate the
  // history strip accordingly so it doesn't overflow.
  const compactLandscape = !isPortrait && !hasRoomForPersistentControls;

  // Filled only while the preview is hidden, so the centre column shows
  // a momentum strip in place of the empty preview gap.
  // Uses ``confirmedState`` (not ``state``) so the audit refetch is triggered
  // only after the server has acknowledged a change. Depending on the
  // optimistically-updated ``state`` would race the audit GET against the
  // in-flight POST and silently drop the chip for the action that just
  // happened — it would only surface together with the next confirmed event.
  const recentEvents = useRecentEvents(
    oid,
    !settings.showPreview,
    confirmedState,
    compactLandscape ? 5 : 8,
  );

  const { showControls, setShowControls } = useHudVisibility({
    hasRoomForPersistentControls,
    activeTab,
    state,
  });

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

  const {
    commitPoint,
    handleAddPoint,
    handleAddSet,
    handleAddTimeout,
    handleChangeServe,
    handleDoubleTapScore,
    handleDoubleTapTimeout,
    pointPickerTeam,
    setPointPickerTeam,
  } = useScoreActions({ actions, settings, simpleMode, matchFinished, pulse });

  const handleToggleVisibility = useCallback(() => {
    if (state) actions.setVisibility(!state.visible);
  }, [actions, state]);

  const handleToggleSimpleMode = useCallback(() => {
    actions.setSimpleMode(!simpleMode);
  }, [actions, simpleMode]);

  const sidesSwapped = state?.sides_swapped ?? false;
  const handleSwapSides = useCallback(() => {
    actions.setSwapSides(!sidesSwapped);
  }, [actions, sidesSwapped]);

  const setSummaryActive = state?.set_summary ?? false;
  const setSummarySetNum = state?.set_summary_set_num ?? null;
  const setSummaryStyle = (state?.set_summary_style ??
    'brand_ledger') as import('./api/client').SetSummaryStyle;

  const handleToggleSetSummary = useCallback(() => {
    if (!settings.setSummaryEnabled) return;
    actions.setSetSummary(!setSummaryActive);
  }, [actions, setSummaryActive, settings.setSummaryEnabled]);

  const handleChangeSetSummaryStyle = useCallback(
    (style: import('./api/client').SetSummaryStyle) => {
      actions.setSetSummaryStyle(style);
    },
    [actions],
  );

  // Server-side LIFO: ``actions.undoLast()`` posts to /game/undo,
  // which pops from the audit log and reverses the action via the
  // existing per-type ``add_*(undo=True)`` path. The two undo
  // entry points (this and the per-team double-tap) share
  // the same stack on the server and cannot drift.
  const handleUndoLast = useCallback(() => {
    pulse('confirm');
    actions.undoLast();
  }, [actions, pulse]);

  const handleToggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
      setIsFullscreen(false);
    } else {
      document.documentElement
        .requestFullscreen()
        .then(() => setIsFullscreen(true))
        .catch(() => setIsFullscreen(false));
    }
  }, []);

  const handleTogglePreview = useCallback(() => {
    setSetting('showPreview', !settings.showPreview);
  }, [setSetting, settings.showPreview]);

  const handleReset = useCallback(() => {
    setResetConfirmOpen(true);
  }, []);

  const confirmReset = useCallback(() => {
    actions.reset();
  }, [actions]);

  const handleStartMatch = useCallback(() => {
    actions.startMatch();
  }, [actions]);

  const { dialog, handleLongPressScore, handleLongPressSet, handleDialogSubmit, closeDialog } =
    useSetValueDialog({ state, currentSet, setsLimit, actions, t });

  // Keyboard shortcuts. Disabled while any dialog/coachmark is open
  // (those own focus and ESC handling) or on touch-only devices where
  // the operator opted out via ``settings.keyboardShortcuts``.
  const anyModalOpen =
    dialog.open ||
    resetConfirmOpen ||
    stalePromptOpen ||
    coachmarkOpen ||
    shareOpen ||
    shortcutsHelpOpen;
  useKeyboardShortcuts({
    enabled: settings.keyboardShortcuts && !anyModalOpen && !!state && activeTab === 'scoreboard',
    onAddPoint: handleAddPoint,
    onUndoLast: state?.can_undo ? handleUndoLast : undefined,
    onChangeServe: handleChangeServe,
    onAddTimeout: handleAddTimeout,
    onStartMatch: state?.match_started_at == null ? handleStartMatch : undefined,
    onToggleVisibility: handleToggleVisibility,
    onToggleSimpleMode: handleToggleSimpleMode,
    onOpenHelp: () => setShortcutsHelpOpen(true),
  });

  const { btnColorA, btnTextA, btnColorB, btnTextB, iconLogoA, iconLogoB, fontStyle } =
    useButtonTheme({ settings, customization });

  if (!oid || (error && !state)) {
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
  // OID is set, no error, but the first authoritative state hasn't
  // arrived yet — show a structurally-matched skeleton instead of the
  // InitScreen so the next render swap doesn't flash unrelated UI.
  if (!state) {
    return (
      <div className="app-container">
        <ConnectionStatus connected={connected} />
        <ScoreboardSkeleton isPortrait={isPortrait} />
      </div>
    );
  }

  return (
    <div className="app-container" {...swipeHandlers}>
      <ConnectionStatus connected={connected} />
      {activeTab === 'scoreboard' && (
        <ErrorBoundary>
          <ScoreboardView
            state={state}
            customization={customization}
            sidesSwapped={sidesSwapped}
            onSwapSides={handleSwapSides}
            currentSet={currentSet}
            setsLimit={setsLimit}
            isPortrait={isPortrait}
            buttonSize={buttonSize}
            previewData={previewData}
            showPreview={settings.showPreview}
            recentEvents={recentEvents}
            // Landscape phones (no room for persistent controls) need the
            // preview shrunk so the alert pills below it don't get pushed
            // off the bottom of the viewport.
            compactLandscape={compactLandscape}
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
            onToggleVisibility={handleToggleVisibility}
            onToggleSimpleMode={handleToggleSimpleMode}
            onUndoLast={handleUndoLast}
            onTogglePreview={handleTogglePreview}
            onStartMatch={handleStartMatch}
            onReset={handleReset}
            onOpenConfig={() => setActiveTab('config')}
            onOpenShare={handleOpenShare}
            onOpenHistory={() => setHistoryOpen(true)}
            setSummaryEnabled={settings.setSummaryEnabled}
            setSummaryActive={setSummaryActive}
            setSummarySetNum={setSummarySetNum}
            setSummaryStyle={setSummaryStyle}
            onToggleSetSummary={handleToggleSetSummary}
            onChangeSetSummaryStyle={handleChangeSetSummaryStyle}
            obsClients={state?.obs_clients ?? 0}
            showOnAir={settings.showOnAir}
            lastMatchId={state?.last_match_id ?? null}
            showReportLink={settings.showReportLink}
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
            autoSwapSides={state?.auto_swap_sides ?? null}
            onBack={() => setActiveTab('scoreboard')}
            onLogout={handleLogout}
            operator={unauthenticated}
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
            onShowShortcuts={() => setShortcutsHelpOpen(true)}
            setSummaryStyle={setSummaryStyle}
            onChangeSetSummaryStyle={handleChangeSetSummaryStyle}
          />
        </ErrorBoundary>
      )}

      <AppDialogs
        dialog={dialog}
        onDialogSubmit={handleDialogSubmit}
        onDialogClose={closeDialog}
        resetConfirmOpen={resetConfirmOpen}
        onResetConfirm={() => {
          confirmReset();
          setResetConfirmOpen(false);
        }}
        onResetConfirmClose={() => setResetConfirmOpen(false)}
        stalePromptOpen={stalePromptOpen}
        onStaleReset={() => {
          confirmReset();
          setStalePromptOpen(false);
        }}
        onStaleClose={() => setStalePromptOpen(false)}
        shareOpen={shareOpen}
        shareLinks={shareLinks}
        reportsUrl={
          // Only the signed-in owner (cookie session — never an operator
          // token or public bookmark) gets the full reports page, deep-linked
          // to this board's overlay. Spectators fall back to the read-only
          // public report links the backend includes in ``shareLinks``.
          unauthenticated || !oid ? null : `/reports?oid=${encodeURIComponent(oid)}`
        }
        onShareClose={() => setShareOpen(false)}
        oid={oid}
        historyOpen={historyOpen}
        confirmedState={confirmedState}
        onHistoryClose={() => setHistoryOpen(false)}
        coachmarkOpen={coachmarkOpen}
        onCoachmarkDismiss={handleCoachmarkDismiss}
        shortcutsHelpOpen={shortcutsHelpOpen}
        onShortcutsHelpClose={() => setShortcutsHelpOpen(false)}
      />

      {pointPickerTeam !== null && (
        <PointTypePicker
          team={pointPickerTeam}
          teamName={
            pointPickerTeam === 1
              ? asString(customization?.['Team 1 Name']) || 'Team 1'
              : asString(customization?.['Team 2 Name']) || 'Team 2'
          }
          color={pointPickerTeam === 1 ? btnColorA : btnColorB}
          textColor={pointPickerTeam === 1 ? btnTextA : btnTextB}
          extendedErrors={settings.extendedErrorTracking}
          onPick={(pt, et) => {
            commitPoint(pointPickerTeam, pt, et);
            setPointPickerTeam(null);
          }}
          onClose={() => setPointPickerTeam(null)}
        />
      )}
    </div>
  );
}
