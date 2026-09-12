import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from '../api/overlays';

export interface UseOverlaysResult {
  overlays: api.OverlayPayload[];
  /** True only while the *first* load is in flight, so a page can show a
   *  placeholder before it has anything to render. Later reloads keep the
   *  current list on screen — see ``refreshing``. */
  loading: boolean;
  /** True while a ``reload`` refreshes an already-loaded list. */
  refreshing: boolean;
  /** True if the (re)load failed. Pages map this to their own copy. */
  error: boolean;
  reload: () => Promise<void>;
  /** Merge one row — a mutation's own response — into the cached list. */
  applyOverlay: (row: api.OverlayPayload) => void;
  /** Drop one row from the cached list (a delete that already succeeded). */
  removeOverlay: (oid: string) => void;
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
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);
  const loaded = useRef(false);

  const reload = useCallback(async () => {
    // Only the first load may blank the page. A reload that follows an action
    // (regenerate the control link, toggle the public bookmark, rename,
    // favorite) must keep the list mounted: swapping it for a placeholder
    // unmounts the cards, React drops their local UI state, and the operator
    // is thrown back to the collapsed list in the middle of the task —
    // typically right before copying the link they just minted.
    if (loaded.current) setRefreshing(true);
    try {
      setOverlays(await api.getOverlays());
      setError(false);
    } catch {
      setError(true);
    } finally {
      loaded.current = true;
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Mutation endpoints answer with the updated row, and that response — not
  // the refetch that follows it — is what the cache is written from. A refresh
  // can fail after the mutation committed; when it does, the list must still
  // show what the operator just did rather than pre-mutation state (a revoked
  // control URL under a Copy button, a flag that no longer holds).
  const applyOverlay = useCallback((row: api.OverlayPayload) => {
    setOverlays((rows) =>
      rows.some((r) => r.oid === row.oid)
        ? rows.map((r) => (r.oid === row.oid ? row : r))
        : [...rows, row],
    );
  }, []);

  const removeOverlay = useCallback((oid: string) => {
    setOverlays((rows) => rows.filter((r) => r.oid !== oid));
  }, []);

  // Single code path: the mount load IS a reload, so an early manual
  // reload() can never race a divergent copy of the same fetch.
  useEffect(() => {
    void reload();
  }, [reload]);

  return { overlays, loading, refreshing, error, reload, applyOverlay, removeOverlay };
}
