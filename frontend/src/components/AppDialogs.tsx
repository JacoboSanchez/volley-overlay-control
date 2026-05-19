import { useI18n } from '../i18n';
import SetValueDialog from './SetValueDialog';
import ConfirmDialog from './ConfirmDialog';
import LinksDialog from './LinksDialog';
import RecentAuditDrawer from './RecentAuditDrawer';
import GestureCoachmark from './GestureCoachmark';
import ShortcutsHelp from './ShortcutsHelp';
import type { GameState } from '../api/client';

export interface DialogState {
  open: boolean;
  title: string;
  initialValue: number;
  maxValue: number;
  team: 1 | 2 | null;
  isSet: boolean;
}

export interface AppDialogsProps {
  dialog: DialogState;
  onDialogSubmit: (value: number) => void;
  onDialogClose: () => void;
  resetConfirmOpen: boolean;
  onResetConfirm: () => void;
  onResetConfirmClose: () => void;
  stalePromptOpen: boolean;
  onStaleReset: () => void;
  onStaleClose: () => void;
  shareOpen: boolean;
  shareLinks: {
    control?: string;
    overlay?: string;
    preview?: string;
    follow?: string;
  } | null;
  onShareClose: () => void;
  oid: string;
  historyOpen: boolean;
  confirmedState: GameState | null;
  onHistoryClose: () => void;
  coachmarkOpen: boolean;
  onCoachmarkDismiss: () => void;
  shortcutsHelpOpen: boolean;
  onShortcutsHelpClose: () => void;
}

export default function AppDialogs({
  dialog,
  onDialogSubmit,
  onDialogClose,
  resetConfirmOpen,
  onResetConfirm,
  onResetConfirmClose,
  stalePromptOpen,
  onStaleReset,
  onStaleClose,
  shareOpen,
  shareLinks,
  onShareClose,
  oid,
  historyOpen,
  confirmedState,
  onHistoryClose,
  coachmarkOpen,
  onCoachmarkDismiss,
  shortcutsHelpOpen,
  onShortcutsHelpClose,
}: AppDialogsProps) {
  const { t } = useI18n();

  return (
    <>
      <SetValueDialog
        open={dialog.open}
        title={dialog.title}
        initialValue={dialog.initialValue}
        maxValue={dialog.maxValue}
        onSubmit={onDialogSubmit}
        onClose={onDialogClose}
      />

      <ConfirmDialog
        open={resetConfirmOpen}
        message={t('config.resetConfirm')}
        confirmLabel={t('config.resetMatch')}
        danger
        onConfirm={onResetConfirm}
        onClose={onResetConfirmClose}
      />

      <ConfirmDialog
        open={stalePromptOpen}
        title={t('staleSet.title')}
        message={t('staleSet.message')}
        confirmLabel={t('staleSet.reset')}
        cancelLabel={t('staleSet.continue')}
        danger
        onConfirm={onStaleReset}
        onClose={onStaleClose}
      />

      {shareOpen && <LinksDialog links={shareLinks ?? {}} onClose={onShareClose} />}

      <RecentAuditDrawer
        oid={oid}
        open={historyOpen}
        confirmedState={confirmedState}
        onClose={onHistoryClose}
      />

      <GestureCoachmark open={coachmarkOpen} onDismiss={onCoachmarkDismiss} />

      <ShortcutsHelp open={shortcutsHelpOpen} onClose={onShortcutsHelpClose} />
    </>
  );
}
