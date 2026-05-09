import { useCallback, useEffect, useRef, useState } from 'react';
import { useI18n } from '../i18n';

export interface GestureCoachmarkProps {
  /**
   * Open state. The host (typically App) flips this on the first
   * frame of state availability and back off when the operator
   * dismisses or finishes the tour.
   */
  open: boolean;
  /**
   * Called once on dismiss (Skip / ESC / final Done). The host is
   * expected to persist a "tour seen" flag so the coachmark won't
   * re-arm on the next session. The same callback is used for all
   * three exit paths so the host's persistence path is reused.
   */
  onDismiss: () => void;
}

interface Step {
  /** i18n key for the step heading. */
  titleKey: string;
  /** i18n key for the step body copy. */
  bodyKey: string;
  /** Material icon shown next to the heading. */
  icon: string;
}

const STEPS: Step[] = [
  { icon: 'touch_app', titleKey: 'tour.tap.title', bodyKey: 'tour.tap.body' },
  { icon: 'undo', titleKey: 'tour.doubletap.title', bodyKey: 'tour.doubletap.body' },
  { icon: 'edit', titleKey: 'tour.longpress.title', bodyKey: 'tour.longpress.body' },
  { icon: 'settings', titleKey: 'tour.config.title', bodyKey: 'tour.config.body' },
];

/**
 * First-run coachmark that walks a new operator through the four
 * non-obvious gestures (tap to score, double-tap to undo, long-
 * press to edit, swipe / gear icon for config). Lives at the end of
 * App's render tree so the focus trap doesn't fight the scoreboard
 * controls underneath.
 *
 * Intentionally lightweight — a single fixed card, no spotlight or
 * positional pointer. The operator already sees the team panels and
 * HUD behind it; the tour just labels what they do.
 */
export default function GestureCoachmark({ open, onDismiss }: GestureCoachmarkProps) {
  const { t } = useI18n();
  const [stepIndex, setStepIndex] = useState(0);
  const cardRef = useRef<HTMLDivElement>(null);

  // Reset to the first step every time the coachmark re-opens, so a
  // "Replay tour" trigger after a previous dismiss starts at the
  // top.
  useEffect(() => {
    if (open) setStepIndex(0);
  }, [open]);

  // Keyboard shortcuts on top of the focusable buttons. ESC
  // dismisses, ArrowLeft / ArrowRight step. Enter is **deliberately
  // not** intercepted here — letting the document listener swallow
  // it would block the Skip / Back buttons' native click activation
  // and force every keyboard user into "advance only" mode. The
  // focused button handles Enter by itself.
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!open) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      onDismiss();
      return;
    }
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      setStepIndex((i) => {
        if (i >= STEPS.length - 1) {
          onDismiss();
          return i;
        }
        return i + 1;
      });
      return;
    }
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      setStepIndex((i) => Math.max(0, i - 1));
    }
  }, [open, onDismiss]);

  useEffect(() => {
    if (!open) return undefined;
    document.addEventListener('keydown', handleKeyDown);
    cardRef.current?.focus();
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, handleKeyDown]);

  if (!open) return null;
  const step = STEPS[stepIndex]!;
  const isLast = stepIndex === STEPS.length - 1;
  const stepCount = STEPS.length;

  return (
    <div
      className="gesture-coachmark"
      role="dialog"
      aria-modal="true"
      aria-labelledby="gesture-coachmark-title"
      data-testid="gesture-coachmark"
    >
      <div
        ref={cardRef}
        className="gesture-coachmark-card"
        tabIndex={-1}
      >
        <div className="gesture-coachmark-icon" aria-hidden="true">
          <span className="material-icons">{step.icon}</span>
        </div>
        <h3 className="gesture-coachmark-title" id="gesture-coachmark-title">
          {t(step.titleKey)}
        </h3>
        <p className="gesture-coachmark-body">{t(step.bodyKey)}</p>
        <div
          className="gesture-coachmark-progress"
          aria-label={t('tour.progress', { step: stepIndex + 1, total: stepCount })}
        >
          {STEPS.map((_, i) => (
            <span
              key={i}
              className={
                'gesture-coachmark-dot'
                + (i === stepIndex ? ' gesture-coachmark-dot-active' : '')
              }
              aria-hidden="true"
            />
          ))}
        </div>
        <div className="gesture-coachmark-actions">
          <button
            type="button"
            className="gesture-coachmark-btn gesture-coachmark-btn-skip"
            onClick={onDismiss}
            data-testid="gesture-coachmark-skip"
          >
            {t('tour.skip')}
          </button>
          {stepIndex > 0 && (
            <button
              type="button"
              className="gesture-coachmark-btn gesture-coachmark-btn-prev"
              onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
              data-testid="gesture-coachmark-prev"
            >
              <span className="material-icons">chevron_left</span>
              {t('tour.prev')}
            </button>
          )}
          <button
            type="button"
            className="gesture-coachmark-btn gesture-coachmark-btn-next"
            onClick={() => {
              if (isLast) {
                onDismiss();
                return;
              }
              setStepIndex((i) => i + 1);
            }}
            data-testid="gesture-coachmark-next"
          >
            {isLast ? t('tour.done') : t('tour.next')}
            {!isLast && <span className="material-icons">chevron_right</span>}
          </button>
        </div>
      </div>
    </div>
  );
}
