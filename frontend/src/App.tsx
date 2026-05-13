import { useState, useEffect, useCallback, useMemo, useRef, FormEvent } from 'react';
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
import InitScreen from './components/InitScreen';
import ShortcutsHelp from './components/ShortcutsHelp';
import ScoreboardView from './components/ScoreboardView';
import ScoreboardSkeleton from './components/ScoreboardSkeleton';
import ConfigPanel from './components/ConfigPanel';
import SetValueDialog from './components/SetValueDialog';
import ConfirmDialog from './components/ConfirmDialog';
import ConnectionStatus from './components/ConnectionStatus';
import GestureCoachmark from './components/GestureCoachmark';
import LinksDialog from './components/LinksDialog';
import RecentAuditDrawer from './components/RecentAuditDrawer';
import * as api from './api/client';
import ErrorBoundary from './components/ErrorBoundary';
import type { ScoreButtonFontStyle } from './components/ScoreButton';
import {
  TEAM_A_COLOR,
  TEAM_B_COLOR,
  FONT_SCALES,
  DEFAULT_FONT_SCALE,
} from './theme';
import { HUD_AUTO_HIDE_MS } from './constants';
import { asColor, asString } from './utils/coerce';

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
    confirmedState,
    customization,
    connected,
    error,
    initialize,
    actions,
    refreshCustomization,
  } = useGameState(oid);

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
  const matchInProgress = !!state
    && state.match_started_at != null
    && !state.match_finished;
  useScreenWakeLock(matchInProgress);

  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  // Coachmark fires once the first authoritative state lands and the
  // operator hasn't dismissed the tour yet. The dismissal flips
  // ``settings.gestureTourSeen`` to ``true`` and persists across
  // sessions; the Behavior section exposes a "Replay tour"
  // affordance that flips it back to ``false`` to re-open this on
  // demand without a page refresh.
  const [coachmarkOpen, setCoachmarkOpen] = useState(false);

  // Share dialog: lazy-fetched links, opened from the HUD's share
  // button. Kept in App so the dialog renders on top of both the
  // scoreboard and config tabs (useful when the operator opens it
  // from either surface).
  const [shareOpen, setShareOpen] = useState(false);
  const [shareLinks, setShareLinks] = useState<{
    control?: string; overlay?: string; preview?: string; follow?: string;
  } | null>(null);

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
    // When the set-summary recap is live, the operator must be able to
    // turn it off in one tap — never auto-hide the HUD.
    if (state?.set_summary) {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
      setShowControls(true);
      return;
    }
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

  const setSummaryActive = state?.set_summary ?? false;
  const setSummarySetNum = state?.set_summary_set_num ?? null;
  const setSummaryStyle = (state?.set_summary_style ?? 'brand_ledger') as
    import('./api/client').SetSummaryStyle;

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

  // Defensive cleanup: if the operator disables the feature while the
  // overlay panel is still active in the backend, push the off state
  // so OBS doesn't keep showing the recap.
  useEffect(() => {
    if (!settings.setSummaryEnabled && setSummaryActive) {
      actions.setSetSummary(false);
    }
  }, [actions, settings.setSummaryEnabled, setSummaryActive]);

  // Server-side LIFO: ``actions.undoLast()`` posts to /game/undo,
  // which pops from the audit log and reverses the action via the
  // existing per-type ``add_*(undo=True)`` path. The two undo
  // entry points (this and the per-team double-tap below) share
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
      document.documentElement.requestFullscreen()
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

  // Open the coachmark whenever the operator has unseen-tour state
  // and authoritative game state is available. The condition stops
  // re-firing once dismissal flips ``gestureTourSeen`` to ``true``
  // — on the next dep change the effect runs, the guard fails, and
  // the open state stays as the operator left it. "Replay tour"
  // flips ``gestureTourSeen`` back to ``false`` and the effect
  // re-opens immediately without a page refresh.
  useEffect(() => {
    if (state && !settings.gestureTourSeen) {
      setCoachmarkOpen(true);
    }
  }, [state, settings.gestureTourSeen]);

  const handleCoachmarkDismiss = useCallback(() => {
    setCoachmarkOpen(false);
    setSetting('gestureTourSeen', true);
  }, [setSetting]);

  const handleOpenShare = useCallback(async () => {
    if (!oid) return;
    setShareOpen(true);
    if (!shareLinks) {
      try {
        const links = await api.getLinks(oid);
        setShareLinks({
          control: typeof links?.control === 'string' ? links.control : '',
          overlay: typeof links?.overlay === 'string' ? links.overlay : '',
          preview: typeof links?.preview === 'string' ? links.preview : '',
          follow: typeof links?.follow === 'string' ? links.follow : '',
        });
      } catch {
        // Empty links surface as the "No links available" fallback
        // already rendered by LinksDialog — no extra error UI needed.
        setShareLinks({});
      }
    }
  }, [oid, shareLinks]);

  const handleStartMatch = useCallback(() => {
    actions.startMatch();
  }, [actions]);

  const handleLogout = useCallback(() => {
    try { localStorage.removeItem('volley_oid'); } catch (e) { console.warn('Failed to remove OID:', e); }
    setOid('');
    setOidInput('');
    setActiveTab('scoreboard');
  }, []);

  // Per-team double-tap undoes the most recent forward of the
  // same (action, team). The server-side per-type undo path now
  // pops the matching forward from the audit log on its own, so
  // no client-side bookkeeping is required.
  // Keyboard shortcuts. Disabled while any dialog/coachmark is open
  // (those own focus and ESC handling) or on touch-only devices where
  // the operator opted out via ``settings.keyboardShortcuts``.
  const anyModalOpen = dialog.open
    || resetConfirmOpen
    || coachmarkOpen
    || shareOpen
    || shortcutsHelpOpen;
  useKeyboardShortcuts({
    enabled: settings.keyboardShortcuts
      && !anyModalOpen
      && !!state
      && activeTab === 'scoreboard',
    onAddPoint: handleAddPoint,
    onUndoLast: state?.can_undo ? handleUndoLast : undefined,
    onChangeServe: handleChangeServe,
    onAddTimeout: handleAddTimeout,
    onStartMatch: state?.match_started_at == null ? handleStartMatch : undefined,
    onToggleVisibility: handleToggleVisibility,
    onToggleSimpleMode: handleToggleSimpleMode,
    onOpenHelp: () => setShortcutsHelpOpen(true),
  });

  const handleDoubleTapScore = useCallback(
    (team: Team) => {
      pulse('confirm');
      actions.addPoint(team, true);
    },
    [actions, pulse]
  );

  const handleDoubleTapTimeout = useCallback(
    (team: Team) => {
      pulse('confirm');
      actions.addTimeout(team, true);
    },
    [actions, pulse]
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

  // Memoize the four button colours together so the strings keep
  // referential identity across re-renders that didn't change any
  // colour input. Without this, every WebSocket state push would
  // hand fresh string instances to TeamPanel/CenterPanel and defeat
  // the React.memo wrappers that guard those subtrees.
  const { btnColorA, btnTextA, btnColorB, btnTextB } = useMemo(() => ({
    btnColorA: settings.followTeamColors
      ? asColor(customization?.['Team 1 Color'], TEAM_A_COLOR)
      : (settings.team1BtnColor ?? TEAM_A_COLOR),
    btnTextA: settings.followTeamColors
      ? asColor(customization?.['Team 1 Text Color'], '#ffffff')
      : (settings.team1BtnText ?? '#ffffff'),
    btnColorB: settings.followTeamColors
      ? asColor(customization?.['Team 2 Color'], TEAM_B_COLOR)
      : (settings.team2BtnColor ?? TEAM_B_COLOR),
    btnTextB: settings.followTeamColors
      ? asColor(customization?.['Team 2 Text Color'], '#ffffff')
      : (settings.team2BtnText ?? '#ffffff'),
  }), [
    settings.followTeamColors,
    settings.team1BtnColor,
    settings.team1BtnText,
    settings.team2BtnColor,
    settings.team2BtnText,
    customization,
  ]);

  const iconLogoA = settings.showIcon ? asString(customization?.['Team 1 Logo']) : null;
  const iconLogoB = settings.showIcon ? asString(customization?.['Team 2 Logo']) : null;

  const fontStyle = useMemo<ScoreButtonFontStyle>(() => {
    const fontProps: FontScale =
      FONT_SCALES[settings.selectedFont] ?? DEFAULT_FONT_SCALE;
    return settings.selectedFont && settings.selectedFont !== 'Default'
      ? { fontFamily: `'${settings.selectedFont}'`, fontScale: fontProps.scale, fontOffsetY: fontProps.offset_y }
      : { fontFamily: undefined, fontScale: 1.0, fontOffsetY: 0.0 };
  }, [settings.selectedFont]);

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
            onShowShortcuts={() => setShortcutsHelpOpen(true)}
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

      <ConfirmDialog
        open={resetConfirmOpen}
        message={t('config.resetConfirm')}
        confirmLabel={t('config.resetMatch')}
        danger
        onConfirm={() => {
          confirmReset();
          setResetConfirmOpen(false);
        }}
        onClose={() => setResetConfirmOpen(false)}
      />

      {shareOpen && (
        <LinksDialog
          links={shareLinks ?? {}}
          onClose={() => setShareOpen(false)}
        />
      )}

      <RecentAuditDrawer
        oid={oid}
        open={historyOpen}
        confirmedState={confirmedState}
        onClose={() => setHistoryOpen(false)}
      />

      <GestureCoachmark
        open={coachmarkOpen}
        onDismiss={handleCoachmarkDismiss}
      />

      <ShortcutsHelp
        open={shortcutsHelpOpen}
        onClose={() => setShortcutsHelpOpen(false)}
      />
    </div>
  );
}
