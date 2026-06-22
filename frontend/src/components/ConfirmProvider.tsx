import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';
import Dialog from './Dialog';

export interface ConfirmOptions {
  /** Body text of the confirmation prompt. */
  message: string;
  /** Optional heading. */
  title?: string;
  /** Label for the confirming action (default "Confirm"). */
  confirmLabel?: string;
  /** Label for the dismissing action (default "Cancel"). */
  cancelLabel?: string;
  /** Render the confirm button in the destructive (red) style. */
  danger?: boolean;
}

type ConfirmFn = (opts: ConfirmOptions) => Promise<boolean>;

const ConfirmCtx = createContext<ConfirmFn | null>(null);

interface PendingConfirm extends ConfirmOptions {
  resolve: (ok: boolean) => void;
}

/** Promise-based confirmation dialog for the account pages, built on the
 *  i18n-free {@link Dialog} primitive so it works outside the I18nProvider. */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<PendingConfirm | null>(null);

  const confirm = useCallback<ConfirmFn>((opts) => {
    return new Promise<boolean>((resolve) => {
      setPending({ ...opts, resolve });
    });
  }, []);

  const settle = useCallback(
    (ok: boolean) => {
      setPending((cur) => {
        cur?.resolve(ok);
        return null;
      });
    },
    [],
  );

  return (
    <ConfirmCtx.Provider value={confirm}>
      {children}
      <Dialog
        open={pending !== null}
        onClose={() => settle(false)}
        ariaLabel={pending?.title ?? 'Confirm'}
      >
        {pending?.title ? <p className="dialog-title">{pending.title}</p> : null}
        <p className="dialog-message">{pending?.message}</p>
        <div className="dialog-actions">
          <button type="button" className="dialog-btn dialog-btn-cancel" onClick={() => settle(false)}>
            {pending?.cancelLabel ?? 'Cancel'}
          </button>
          <button
            type="button"
            className={`dialog-btn ${pending?.danger ? 'dialog-btn-danger' : 'dialog-btn-ok'}`}
            onClick={() => settle(true)}
          >
            {pending?.confirmLabel ?? 'Confirm'}
          </button>
        </div>
      </Dialog>
    </ConfirmCtx.Provider>
  );
}

/** Returns an async ``confirm`` function. Falls back to ``window.confirm``
 *  when rendered outside a provider (e.g. isolated component tests). */
export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmCtx);
  const fallback = useRef<ConfirmFn>((opts) =>
    Promise.resolve(typeof window !== 'undefined' && window.confirm(opts.message)),
  );
  return ctx ?? fallback.current;
}
