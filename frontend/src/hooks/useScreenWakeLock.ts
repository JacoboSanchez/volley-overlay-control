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
 */
export function useScreenWakeLock(enabled: boolean): void {
  const sentinelRef = useRef<WakeLockSentinelLike | null>(null);
  // ``enabled`` mirrored on a ref so the visibilitychange handler
  // can read the latest value without having to re-bind on every
  // ``enabled`` flip.
  const enabledRef = useRef(enabled);

  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  useEffect(() => {
    const nav = navigator as WakeLockNavigator;
    if (!nav.wakeLock || typeof nav.wakeLock.request !== 'function') {
      return undefined;
    }

    let cancelled = false;

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
      if (cancelled || !enabledRef.current) return;
      if (sentinelRef.current && !sentinelRef.current.released) return;
      // Skip while the page is hidden — the request would resolve
      // but the platform would release immediately, leaving us
      // racing the visibilitychange handler.
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        return;
      }
      try {
        const sentinel = await nav.wakeLock!.request('screen');
        if (cancelled || !enabledRef.current) {
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
      }
    };

    if (enabled) {
      void acquire();
    } else {
      void release();
    }

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
      cancelled = true;
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisibilityChange);
      }
      void release();
    };
  }, [enabled]);
}
