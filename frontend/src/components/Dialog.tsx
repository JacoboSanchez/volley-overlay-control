import { useEffect, useRef, ReactNode } from 'react';

export interface DialogProps {
  /** Whether the dialog is currently visible. */
  open: boolean;
  /** Called when the user requests close (ESC key or backdrop click). */
  onClose: () => void;
  /** Accessible name for the dialog as a whole. */
  ariaLabel?: string;
  /** Optional ID of an existing element that labels the dialog. */
  ariaLabelledBy?: string;
  /** Dialog body. */
  children: ReactNode;
}

/**
 * Reusable modal dialog primitive.
 *
 * Adds the a11y bits we used to be missing on the bespoke overlay/card
 * pairs: ``role="dialog"``, ``aria-modal="true"``, an ESC handler, and a
 * keyboard-reachable backdrop button. Visual styling stays in
 * ``App.css`` (``dialog-overlay`` / ``dialog-card``) so existing CSS
 * keeps working.
 */
export default function Dialog({
  open,
  onClose,
  ariaLabel,
  ariaLabelledBy,
  children,
}: DialogProps) {
  const cardRef = useRef<HTMLDivElement>(null);

  // Focus the card on the open transition only. Splitting this from the
  // keydown effect below matters: parents often pass an inline ``onClose``
  // arrow, so re-running on every ``onClose`` identity change would steal
  // focus back to the card on every parent render — losing in-flight
  // input as the App re-renders on every WebSocket update.
  useEffect(() => {
    if (open) {
      cardRef.current?.focus();
    }
  }, [open]);

  // ESC-to-dismiss + a basic focus trap on Tab/Shift+Tab. The trap keeps
  // keyboard users from leaking out of the modal into the background page
  // (``aria-modal="true"`` only signals the modal state to assistive tech
  // — browsers don't enforce it).
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
      const card = cardRef.current;
      if (!card) return;
      const focusable = card.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea:not([disabled]), '
          + 'input:not([disabled]), select:not([disabled]), '
          + '[tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) {
        e.preventDefault();
        card.focus();
        return;
      }
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      const active = document.activeElement;
      if (e.shiftKey && (active === first || active === card)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="dialog-overlay">
      {/*
        Backdrop is a real <button> so we can have a click-target for
        "click outside to dismiss" without an onClick on a <div> (which
        the linter rightly rejects). It is intentionally outside the tab
        order (``tabIndex={-1}``): keyboard users dismiss the dialog with
        ESC or the explicit Cancel button rather than tabbing to an
        invisible region. The button still carries an aria-label so
        assistive tech announces a meaningful close target.
      */}
      <button
        type="button"
        className="dialog-backdrop"
        onClick={onClose}
        aria-label="Close dialog"
        tabIndex={-1}
      />
      <div
        ref={cardRef}
        className="dialog-card"
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledBy}
        tabIndex={-1}
      >
        {children}
      </div>
    </div>
  );
}
