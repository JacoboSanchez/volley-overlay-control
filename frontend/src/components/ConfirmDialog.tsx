import { useI18n } from '../i18n';
import Dialog from './Dialog';

export interface ConfirmDialogProps {
  open: boolean;
  /** Optional heading; defaults to a localized "Are you sure?" prompt. */
  title?: string;
  /** Body copy explaining what the operator is about to do. */
  message: string;
  /** Label for the confirming action; defaults to a localized "Confirm". */
  confirmLabel?: string;
  /** Label for the cancelling action; defaults to a localized "Cancel". */
  cancelLabel?: string;
  /**
   * Marks the action as destructive — paints the OK button in the
   * danger colour (red) instead of the neutral confirm green. Used
   * for resets and logouts so the operator can't fire them on
   * autopilot.
   */
  danger?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

/**
 * Stylised replacement for ``window.confirm`` that reuses the focus-trapped
 * ``Dialog`` primitive. Centralises the OK/Cancel layout so reset, logout
 * and similar destructive prompts share the same look, focus management
 * and i18n footprint.
 */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  danger = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const { t } = useI18n();
  const heading = title ?? t('confirm.title');
  const ok = confirmLabel ?? t('confirm.confirm');
  const cancel = cancelLabel ?? t('confirm.cancel');

  return (
    <Dialog open={open} onClose={onClose} ariaLabelledBy="confirm-dialog-title">
      <h3 className="dialog-title" id="confirm-dialog-title">{heading}</h3>
      <p className="dialog-message">{message}</p>
      <div className="dialog-actions">
        <button
          type="button"
          className={`dialog-btn ${danger ? 'dialog-btn-danger' : 'dialog-btn-ok'}`}
          onClick={() => { onConfirm(); onClose(); }}
          data-testid="confirm-dialog-ok"
        >
          <span className="material-icons">{danger ? 'warning' : 'done'}</span>
          {ok}
        </button>
        <button
          type="button"
          className="dialog-btn dialog-btn-cancel"
          onClick={onClose}
          data-testid="confirm-dialog-cancel"
        >
          <span className="material-icons">close</span>
          {cancel}
        </button>
      </div>
    </Dialog>
  );
}
