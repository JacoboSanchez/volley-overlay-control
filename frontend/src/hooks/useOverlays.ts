import { useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';

export interface UseOverlaysResult {
  overlays: api.OverlayPayload[];
  loading: boolean;
  /** True if the (re)load failed. Pages map this to their own copy. */
  error: boolean;
  reload: () => Promise<void>;
}

/**
 * Load the signed-in user's overlays once on mount, with a manual ``reload``.
 * Centralises the fetch / cancel-on-unmount / error boilerplate that was
 * copy-pasted across the account dashboard, the Overlays manager and the board
 * init screen.
 */
export function useOverlays(): UseOverlaysResult {
  const [overlays, setOverlays] = useState<api.OverlayPayload[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setOverlays(await api.getOverlays());
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const ovs = await api.getOverlays();
        if (!cancelled) {
          setOverlays(ovs);
          setError(false);
        }
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { overlays, loading, error, reload };
}
