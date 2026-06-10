import { useState, useCallback } from 'react';
import * as api from '../api/client';
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

  // Score a point (optionally tagged). Shared by the direct tap path
  // and the point-type picker so the auto-simple side-effect stays in
  // one place.
  const commitPoint = useCallback(
    (team: Team, pointType?: api.PointType, errorType?: api.ErrorType) => {
      actions.addPoint(team, false, pointType, errorType);
      if (settings.autoSimple && !simpleMode) {
        actions.setSimpleMode(true);
      }
    },
    [actions, settings.autoSimple, simpleMode],
  );

  const handleAddPoint = useCallback(
    (team: Team) => {
      if (matchFinished) return;
      // Opt-in classification: defer scoring to the picker so the
      // operator can tag how the point was won. Off by default — the
      // tap scores immediately, unchanged.
      if (settings.trackPointTypes) {
        setPointPickerTeam(team);
        return;
      }
      commitPoint(team);
    },
    [matchFinished, settings.trackPointTypes, commitPoint],
  );

  const handleAddSet = useCallback(
    (team: Team) => {
      if (matchFinished) return;
      actions.addSet(team, false);
    },
    [actions, matchFinished],
  );

  const handleAddTimeout = useCallback(
    (team: Team) => {
      if (matchFinished) return;
      actions.addTimeout(team, false);
      if (settings.autoSimple && settings.autoSimpleOnTimeout && simpleMode) {
        actions.setSimpleMode(false);
      }
    },
    [actions, matchFinished, settings.autoSimple, settings.autoSimpleOnTimeout, simpleMode],
  );

  const handleChangeServe = useCallback(
    (team: Team) => {
      actions.changeServe(team);
    },
    [actions],
  );

  // Per-team double-tap undoes the most recent forward of the
  // same (action, team). The server-side per-type undo path
  // pops the matching forward from the audit log on its own, so
  // no client-side bookkeeping is required.
  const handleDoubleTapScore = useCallback(
    (team: Team) => {
      pulse('confirm');
      actions.addPoint(team, true);
    },
    [actions, pulse],
  );

  const handleDoubleTapTimeout = useCallback(
    (team: Team) => {
      pulse('confirm');
      actions.addTimeout(team, true);
    },
    [actions, pulse],
  );

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
