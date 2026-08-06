import { useState, useCallback, useRef } from 'react';
import type * as api from '../api/client';
import type { GameActions } from './useGameState';
import type { Settings } from './useSettings';
import type { useHaptics } from './useHaptics';

type Team = 1 | 2;
type Pulse = ReturnType<typeof useHaptics>['pulse'];

export interface UseScoreActionsResult {
  commitPoint: (team: Team, pointType?: api.PointType, errorType?: api.ErrorType) => void;
  handleAddPoint: (team: Team) => void;
  handleAddSet: (team: Team) => void;
  handleAddTimeout: (team: Team) => void;
  handleChangeServe: (team: Team) => void;
  handleDoubleTapScore: (team: Team) => void;
  handleDoubleTapTimeout: (team: Team) => void;
  pointPickerTeam: Team | null;
  setPointPickerTeam: (team: Team | null) => void;
}

interface ScoreActionInputs {
  actions: GameActions;
  settings: Settings;
  simpleMode: boolean;
  matchFinished: boolean;
  pulse: Pulse;
}

/**
 * Scoring gesture handlers: tap-to-score (optionally routed through
 * the point-type picker), set/timeout/serve taps, and the per-team
 * double-tap undo pair. Owns the picker's open state so the
 * auto-simple side-effect stays in one place (``commitPoint``).
 */
export function useScoreActions({
  actions,
  settings,
  simpleMode,
  matchFinished,
  pulse,
}: {
  actions: GameActions;
  settings: Settings;
  simpleMode: boolean;
  matchFinished: boolean;
  pulse: Pulse;
}): UseScoreActionsResult {
  // Per-point classification picker. Holds the team whose score tap is
  // awaiting a point-type choice, or ``null`` when closed. Only used
  // when ``settings.trackPointTypes`` is on.
  const [pointPickerTeam, setPointPickerTeam] = useState<Team | null>(null);
  // Keep gesture callbacks stable across live state pushes. The scoreboard
  // exposes them through BoardActionsContext, whose memoized value must not
  // change simply because a WebSocket message updated a score.
  const inputsRef = useRef<ScoreActionInputs>({
    actions,
    settings,
    simpleMode,
    matchFinished,
    pulse,
  });
  inputsRef.current = { actions, settings, simpleMode, matchFinished, pulse };

  // Score a point (optionally tagged). Shared by the direct tap path
  // and the point-type picker so the auto-simple side-effect stays in
  // one place.
  const commitPoint = useCallback(
    (team: Team, pointType?: api.PointType, errorType?: api.ErrorType) => {
      const {
        actions: currentActions,
        settings: currentSettings,
        simpleMode: currentSimpleMode,
      } = inputsRef.current;
      currentActions.addPoint(team, false, pointType, errorType);
      if (currentSettings.autoSimple && !currentSimpleMode) {
        currentActions.setSimpleMode(true);
      }
    },
    [],
  );

  const handleAddPoint = useCallback(
    (team: Team) => {
      const { matchFinished: currentMatchFinished, settings: currentSettings } = inputsRef.current;
      if (currentMatchFinished) return;
      // Opt-in classification: defer scoring to the picker so the
      // operator can tag how the point was won. Off by default — the
      // tap scores immediately, unchanged.
      if (currentSettings.trackPointTypes) {
        setPointPickerTeam(team);
        return;
      }
      commitPoint(team);
    },
    [commitPoint],
  );

  const handleAddSet = useCallback((team: Team) => {
    const { actions: currentActions, matchFinished: currentMatchFinished } = inputsRef.current;
    if (currentMatchFinished) return;
    currentActions.addSet(team, false);
  }, []);

  const handleAddTimeout = useCallback((team: Team) => {
    const {
      actions: currentActions,
      settings: currentSettings,
      simpleMode: currentSimpleMode,
      matchFinished: currentMatchFinished,
    } = inputsRef.current;
    if (currentMatchFinished) return;
    currentActions.addTimeout(team, false);
    if (currentSettings.autoSimple && currentSettings.autoSimpleOnTimeout && currentSimpleMode) {
      currentActions.setSimpleMode(false);
    }
  }, []);

  const handleChangeServe = useCallback((team: Team) => {
    inputsRef.current.actions.changeServe(team);
  }, []);

  // Per-team double-tap undoes the most recent forward of the
  // same (action, team). The server-side per-type undo path
  // pops the matching forward from the audit log on its own, so
  // no client-side bookkeeping is required.
  const handleDoubleTapScore = useCallback((team: Team) => {
    const { actions: currentActions, pulse: currentPulse } = inputsRef.current;
    currentPulse('confirm');
    currentActions.addPoint(team, true);
  }, []);

  const handleDoubleTapTimeout = useCallback((team: Team) => {
    const { actions: currentActions, pulse: currentPulse } = inputsRef.current;
    currentPulse('confirm');
    currentActions.addTimeout(team, true);
  }, []);

  return {
    commitPoint,
    handleAddPoint,
    handleAddSet,
    handleAddTimeout,
    handleChangeServe,
    handleDoubleTapScore,
    handleDoubleTapTimeout,
    pointPickerTeam,
    setPointPickerTeam,
  };
}
