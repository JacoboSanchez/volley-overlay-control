import { useCallback, useEffect, useLayoutEffect, useRef } from 'react';
import { useConfirm } from '../ConfirmProvider';
import { useI18n } from '../../i18n';

/**
 * Guards every way out of the config panel — the back button, a swipe-back
 * gesture, the dashboard link, switching overlay — behind one unsaved-changes
 * prompt, and owns the history entry that makes swipe-back land here instead
 * of leaving the board.
 *
 * Returns `guard(action)`: runs `action` straight away on a clean panel, and
 * otherwise only after the operator confirms.
 */
export function useUnsavedChangesGuard(isDirty: boolean, onExit: () => void) {
  const { t } = useI18n();
  const confirm = useConfirm();

  // Synced in a *layout* effect, deliberately. The popstate listener reads this
  // ref synchronously, and a passive `useEffect` runs after the commit — that
  // gap let the panel render clean (Save disabled) while the ref still said
  // dirty, so a user who saved and immediately pressed Back got a spurious
  // "unsaved changes" prompt. `useLayoutEffect` closes it by running
  // synchronously at commit time.
  //
  // Not assigned during render either: the app mounts under createRoot +
  // StrictMode, where a render can be interrupted or thrown away, and a
  // render-phase write would leave this shared ref reflecting a render that
  // never committed.
  const isDirtyRef = useRef(isDirty);
  useLayoutEffect(() => {
    isDirtyRef.current = isDirty;
  }, [isDirty]);

  const confirmExit = useCallback(
    () =>
      confirm({
        title: t('config.unsavedChangesTitle'),
        message: t('config.unsavedChangesConfirm'),
        confirmLabel: t('config.unsavedChangesLeave'),
        cancelLabel: t('config.unsavedChangesStay'),
        danger: true,
      }),
    [confirm, t],
  );
  const confirmExitRef = useRef(confirmExit);
  useEffect(() => {
    confirmExitRef.current = confirmExit;
  }, [confirmExit]);

  const onExitRef = useRef(onExit);
  useEffect(() => {
    onExitRef.current = onExit;
  }, [onExit]);

  const guard = useCallback((action: () => void) => {
    // A clean panel leaves synchronously: nothing to ask about, and deferring
    // it a microtask would make Back feel laggy.
    if (!isDirtyRef.current) {
      action();
      return;
    }
    void confirmExitRef.current().then((ok) => {
      if (ok) action();
    });
  }, []);

  const ignoreNextPopRef = useRef(false);

  useEffect(() => {
    window.history.pushState({ configOpen: true }, '');
    const handlePopState = () => {
      if (ignoreNextPopRef.current) {
        ignoreNextPopRef.current = false;
        return;
      }
      if (!isDirtyRef.current) {
        onExitRef.current();
        return;
      }
      // The entry is already popped by the time we hear about it. The panel
      // stays mounted while the prompt is open (both entries are the same
      // board URL, so nothing visibly navigates); on cancel we push the
      // configOpen entry back by going forward rather than pushing a new one,
      // so repeated cancels don't grow the history stack.
      void confirmExitRef.current().then((ok) => {
        if (ok) {
          onExitRef.current();
          return;
        }
        ignoreNextPopRef.current = true;
        window.history.go(1);
      });
    };
    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  return guard;
}
