import { useState, useCallback } from 'react';
import type { GameState } from '../api/client';
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
    [state, currentSet, t],
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
    [state, setsLimit, t],
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
    [dialog, actions, currentSet],
  );

  const closeDialog = useCallback(() => {
    setDialog((d) => ({ ...d, open: false }));
  }, []);

  return { dialog, handleLongPressScore, handleLongPressSet, handleDialogSubmit, closeDialog };
}
