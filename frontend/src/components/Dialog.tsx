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

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey);
    // Focus the dialog card so screen readers announce it and tab order
    // starts inside the dialog rather than on the page below.
    cardRef.current?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="dialog-overlay">
      {/*
        A real <button> behind the card lets keyboard users close the
        dialog with Enter/Space, satisfies jsx-a11y, and gives us a
        click-target for "click outside to dismiss" without abusing a
        <div onClick>.
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
