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

  // Single code path: the mount load IS a reload, so an early manual
  // reload() can never race a divergent copy of the same fetch.
  useEffect(() => {
    void reload();
  }, [reload]);

  return { overlays, loading, error, reload };
}
