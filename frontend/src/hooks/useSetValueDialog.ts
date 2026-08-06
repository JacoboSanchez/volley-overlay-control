import { useState, useCallback, useRef } from 'react';
import type { GameState } from '../api/board';
import type { Translate } from '../i18n';
import type { GameActions } from './useGameState';
import type { DialogState } from '../components/AppDialogs';

type Team = 1 | 2;

export interface UseSetValueDialogResult {
  dialog: DialogState;
  handleLongPressScore: (team: Team) => void;
  handleLongPressSet: (team: Team) => void;
  handleDialogSubmit: (value: number) => void;
  closeDialog: () => void;
}

/**
 * Long-press "set exact value" dialog for scores and sets-won. Owns
 * the dialog state and submits through ``actions.setScore`` /
 * ``actions.setSets`` against the current set.
 */
export function useSetValueDialog({
  state,
  currentSet,
  setsLimit,
  actions,
  t,
}: {
  state: GameState | null;
  currentSet: number;
  setsLimit: number;
  actions: GameActions;
  t: Translate;
}): UseSetValueDialogResult {
  const [dialog, setDialog] = useState<DialogState>({
    open: false,
    title: '',
    initialValue: 0,
    maxValue: 99,
    team: null,
    isSet: false,
  });

  // Scoreboard handlers live in the stable BoardActionsContext. Read the
  // latest live score / set values from refs instead of recreating the
  // long-press callbacks after every WebSocket state update.
  const inputsRef = useRef({ state, currentSet, setsLimit, actions, t });
  const dialogRef = useRef(dialog);
  inputsRef.current = { state, currentSet, setsLimit, actions, t };
  dialogRef.current = dialog;

  const handleLongPressScore = useCallback((team: Team) => {
    const current = inputsRef.current;
    if (!current.state) return;
    const teamState = team === 1 ? current.state.team_1 : current.state.team_2;
    const rawScore = teamState.scores?.[`set_${current.currentSet}`];
    const currentScore = typeof rawScore === 'number' ? rawScore : 0;
    setDialog({
      open: true,
      title: current.t('dialog.setScore', { team }),
      initialValue: currentScore,
      maxValue: 99,
      team,
      isSet: false,
    });
  }, []);

  const handleLongPressSet = useCallback((team: Team) => {
    const current = inputsRef.current;
    if (!current.state) return;
    const teamState = team === 1 ? current.state.team_1 : current.state.team_2;
    setDialog({
      open: true,
      title: current.t('dialog.setSets', { team }),
      initialValue: teamState.sets,
      maxValue: Math.ceil(current.setsLimit / 2),
      team,
      isSet: true,
    });
  }, []);

  const handleDialogSubmit = useCallback((value: number) => {
    const currentDialog = dialogRef.current;
    const current = inputsRef.current;
    if (currentDialog.team === null) return;
    if (currentDialog.isSet) {
      current.actions.setSets(currentDialog.team, value);
    } else {
      current.actions.setScore(currentDialog.team, current.currentSet, value);
    }
    setDialog((d) => ({ ...d, open: false }));
  }, []);

  const closeDialog = useCallback(() => {
    setDialog((d) => ({ ...d, open: false }));
  }, []);

  return { dialog, handleLongPressScore, handleLongPressSet, handleDialogSubmit, closeDialog };
}
