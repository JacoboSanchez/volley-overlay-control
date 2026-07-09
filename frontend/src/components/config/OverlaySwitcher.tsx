import { useState, useRef, useEffect, useCallback } from 'react';
import { useI18n } from '../../i18n';
import { useOverlays } from '../../hooks/useOverlays';

export interface OverlaySwitcherProps {
  /** The oid of the board currently being controlled. */
  currentOid: string;
  /** Called with the chosen oid (never the current one). */
  onSwitch: (oid: string) => void;
}

/**
 * Config top-bar control that names the board being controlled and, on tap,
 * lists the owner's other overlays so they can switch in place — without a
 * round-trip through the Overlays management page. Owner (cookie) mode only:
 * capability/public-bookmark credentials resolve exactly one overlay and
 * cannot enumerate the rest, so ConfigPanel never renders this for them.
 */
export default function OverlaySwitcher({ currentOid, onSwitch }: OverlaySwitcherProps) {
  const { t } = useI18n();
  const { overlays } = useOverlays();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Close on outside interaction or Escape — the menu is a lightweight
  // popover, not a modal, so it must never trap focus or block the panel.
  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const handlePick = useCallback(
    (oid: string) => {
      setOpen(false);
      if (oid !== currentOid) onSwitch(oid);
    },
    [currentOid, onSwitch],
  );

  // While the list is loading (or failed) there is nothing to switch to, but
  // the control still has its first job: naming the current board.
  const canOpen = overlays.length > 0;

  return (
    <div className="overlay-switcher" ref={rootRef}>
      <button
        type="button"
        className={`overlay-switcher-trigger${open ? ' is-open' : ''}`}
        onClick={() => setOpen((v) => !v)}
        disabled={!canOpen}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={t('config.switcher.open')}
        data-testid="overlay-switcher-trigger"
      >
        <span className="overlay-switcher-text">
          <span className="overlay-switcher-eyebrow">{t('config.switcher.eyebrow')}</span>
          <span className="overlay-switcher-oid">{currentOid}</span>
        </span>
        {canOpen && (
          <span className="material-icons overlay-switcher-caret" aria-hidden="true">
            {open ? 'expand_less' : 'expand_more'}
          </span>
        )}
      </button>
      {open && (
        <div
          className="overlay-switcher-menu"
          role="listbox"
          aria-label={t('config.switcher.listTitle')}
          data-testid="overlay-switcher-menu"
        >
          <div className="overlay-switcher-menu-head">{t('config.switcher.listTitle')}</div>
          {overlays.map((o) => {
            const current = o.oid === currentOid;
            return (
              <button
                key={o.oid}
                type="button"
                role="option"
                aria-selected={current}
                className={`overlay-switcher-option${current ? ' is-current' : ''}`}
                onClick={() => handlePick(o.oid)}
              >
                <span className="material-icons overlay-switcher-check" aria-hidden="true">
                  {current ? 'check' : ''}
                </span>
                <span className="overlay-switcher-option-labels">
                  <span className="overlay-switcher-option-oid">{o.oid}</span>
                  {o.description && (
                    <span className="overlay-switcher-option-desc">{o.description}</span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
