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

  // Traversals this hook performs itself. Counted rather than flagged: a
  // restore and an exit can both be in flight before either popstate lands,
  // and a boolean would let the second one be handled as if the operator had
  // pressed Back.
  const selfTraversalsRef = useRef(0);
  const traverse = useCallback((delta: number) => {
    selfTraversalsRef.current += 1;
    window.history.go(delta);
  }, []);

  // Only one prompt at a time: further exit attempts while it is open are
  // answered by the dialog already on screen.
  const promptOpenRef = useRef(false);
  const ask = useCallback((action: () => void) => {
    if (promptOpenRef.current) return;
    promptOpenRef.current = true;
    void confirmExitRef.current().then((ok) => {
      promptOpenRef.current = false;
      if (ok) action();
    });
  }, []);

  const guard = useCallback(
    (action: () => void) => {
      // A clean panel leaves synchronously: nothing to ask about, and deferring
      // it a microtask would make Back feel laggy.
      if (!isDirtyRef.current) {
        action();
        return;
      }
      ask(action);
    },
    [ask],
  );

  useEffect(() => {
    window.history.pushState({ configOpen: true }, '');
    const handlePopState = () => {
      if (selfTraversalsRef.current > 0) {
        selfTraversalsRef.current -= 1;
        return;
      }
      if (!isDirtyRef.current) {
        onExitRef.current();
        return;
      }
      // The entry is already popped by the time we hear about it, and the
      // prompt below is asynchronous — unlike the `window.confirm` this
      // replaced, it does not block the main thread. So put the entry back
      // *first*: until the operator answers, a second Back press has to land
      // on the guard entry again rather than traversing past the board and
      // unmounting it with the edits unsaved. Going forward (rather than
      // pushing a fresh entry) keeps repeated attempts from growing the stack.
      traverse(1);
      ask(() => {
        // Confirmed: consume the entry we just restored, so leaving the panel
        // doesn't strand a stale configOpen entry the next Back press would
        // have to walk through.
        traverse(-1);
        onExitRef.current();
      });
    };
    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, [ask, traverse]);

  return guard;
}
