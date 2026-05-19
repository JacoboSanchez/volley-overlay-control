import { useEffect, useRef } from 'react';

/**
 * Minimal type surface for the Screen Wake Lock API. Browsers
 * without support don't expose ``navigator.wakeLock``; the hook
 * feature-detects before touching it so unsupported runtimes
 * (older Safari, JSDOM) silently no-op.
 */
interface WakeLockSentinelLike {
  released: boolean;
  release: () => Promise<void>;
  addEventListener: (event: 'release', cb: () => void) => void;
  removeEventListener: (event: 'release', cb: () => void) => void;
}

interface WakeLockNavigator {
  wakeLock?: {
    request: (type: 'screen') => Promise<WakeLockSentinelLike>;
  };
}

interface Handlers {
  acquire: () => Promise<void>;
  release: () => Promise<void>;
}

/**
 * Holds a screen wake lock while ``enabled`` is ``true`` so the
 * device doesn't dim or lock during a live match.
 *
 * The platform releases the lock automatically whenever the page
 * becomes hidden (tab switch, lock screen, multitasking on iOS).
 * We listen for ``visibilitychange`` and re-acquire on return so a
 * brief excursion to another app doesn't strand the operator with
 * a dark screen until the next gesture. Released deliberately when
 * ``enabled`` flips back to ``false`` (e.g. ``match_finished``,
 * post-reset) and on unmount.
 *
 * Silent no-op on unsupported runtimes — desktop browsers and the
 * ~2% of iOS still on <16.4 simply don't get the lock and the rest
 * of the app keeps working.
 *
 * Implementation notes:
 *
 * * The visibility listener is bound once on mount via a stable
 *   ``[]`` effect — toggling ``enabled`` does **not** re-bind it.
 *   Latest ``enabled`` value reaches the handler through
 *   ``enabledRef`` so a stale closure can't leak past a flip.
 * * ``isRequestingRef`` blocks concurrent ``acquire()`` calls so
 *   simultaneous mount-time + visibility-change triggers can't
 *   race the async ``request('screen')`` and leak a sentinel
 *   that no one releases.
 */
export function useScreenWakeLock(enabled: boolean): void {
  const sentinelRef = useRef<WakeLockSentinelLike | null>(null);
  const enabledRef = useRef(enabled);
  const isRequestingRef = useRef(false);
  const handlersRef = useRef<Handlers | null>(null);

  // Mirror ``enabled`` on a ref so the visibility handler reads
  // the latest value without forcing a re-bind.
  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  // Bind the visibility handler once and keep it bound for the
  // lifetime of the consumer. The acquire/release toggle lives in
  // a separate effect below.
  useEffect(() => {
    // ``navigator`` is undefined under Node-side SSR / static
    // pre-render. Guard the access the same way the
    // ``document`` checks below do, so the hook can be imported
    // without blowing up before hydration. After hydration the
    // browser globals are populated and the effect re-runs.
    const nav =
      typeof navigator !== 'undefined'
        ? (navigator as WakeLockNavigator)
        : ({} as WakeLockNavigator);
    if (!nav.wakeLock || typeof nav.wakeLock.request !== 'function') {
      return undefined;
    }

    const release = async () => {
      const sentinel = sentinelRef.current;
      sentinelRef.current = null;
      if (!sentinel || sentinel.released) return;
      try {
        await sentinel.release();
      } catch {
        // The browser already released the sentinel under us
        // (visibilitychange, tab close). No further work needed.
      }
    };

    const acquire = async () => {
      if (!enabledRef.current) return;
      if (sentinelRef.current && !sentinelRef.current.released) return;
      // Race guard: a simultaneous mount-time toggle + visibility
      // change can both call acquire() while the first
      // ``request('screen')`` is still in flight. Without this
      // guard the second resolve would overwrite ``sentinelRef``
      // and orphan the first sentinel — the platform would then
      // have two locks open and only release one.
      if (isRequestingRef.current) return;
      // Skip while the page is hidden — the request would resolve
      // but the platform would release immediately, leaving us
      // racing the visibilitychange handler.
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        return;
      }
      isRequestingRef.current = true;
      try {
        const sentinel = await nav.wakeLock!.request('screen');
        if (!enabledRef.current) {
          await sentinel.release().catch(() => undefined);
          return;
        }
        sentinelRef.current = sentinel;
        const onSentinelRelease = () => {
          // Platform-driven release (most often visibilitychange
          // → hidden). Drop our reference; the visibilitychange
          // handler below re-acquires when the page comes back.
          if (sentinelRef.current === sentinel) {
            sentinelRef.current = null;
          }
        };
        sentinel.addEventListener('release', onSentinelRelease);
      } catch {
        // Permission denied / no user activation / unsupported
        // policy. No-op — the toggle would have done the same
        // thing on a non-supporting browser.
      } finally {
        isRequestingRef.current = false;
      }
    };

    handlersRef.current = { acquire, release };

    const onVisibilityChange = () => {
      if (typeof document === 'undefined') return;
      if (document.visibilityState === 'visible' && enabledRef.current) {
        void acquire();
      }
    };

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibilityChange);
    }

    return () => {
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisibilityChange);
      }
      handlersRef.current = null;
      // Final release on unmount uses the latest local closure so
      // any half-set sentinel from a still-in-flight ``request``
      // can't outlive the consumer.
      void release();
    };
    // Mount-once binding. ``enabled`` is read via ref above; the
    // toggle effect below drives acquire/release on each flip.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Drive acquire/release from the latest ``enabled`` value
  // without disturbing the visibility listener bound in the
  // mount effect above.
  useEffect(() => {
    const handlers = handlersRef.current;
    if (!handlers) return;
    if (enabled) {
      void handlers.acquire();
    } else {
      void handlers.release();
    }
  }, [enabled]);
}
