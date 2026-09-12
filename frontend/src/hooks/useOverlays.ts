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
  /** Insert a row the caller just created. */
  applyOverlay: (row: api.OverlayPayload) => void;
  /** Write the fields one mutation owns onto the cached row. */
  patchOverlay: (oid: string, patch: Partial<api.OverlayPayload>) => void;
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
  // Refreshes no longer blank the list, so the cards stay clickable while one
  // is in flight and two can overlap (favorite then regenerate, say). Their
  // responses can land in either order, and an older one would otherwise
  // overwrite the newer state — the regenerated link reverting to the revoked
  // URL on screen. Each run takes a ticket; only the newest may write.
  const generation = useRef(0);

  const reload = useCallback(async () => {
    // Only the first load may blank the page. A reload that follows an action
    // (regenerate the control link, toggle the public bookmark, rename,
    // favorite) must keep the list mounted: swapping it for a placeholder
    // unmounts the cards, React drops their local UI state, and the operator
    // is thrown back to the collapsed list in the middle of the task —
    // typically right before copying the link they just minted.
    const ticket = ++generation.current;
    const current = () => ticket === generation.current;
    if (loaded.current) setRefreshing(true);
    try {
      const rows = await api.getOverlays();
      if (!current()) return;
      setOverlays(rows);
      setError(false);
    } catch {
      if (!current()) return;
      setError(true);
    } finally {
      // A superseded run settles nothing: the newest one owns these flags and
      // will clear them when it lands.
      if (current()) {
        loaded.current = true;
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  // Mutation endpoints answer with the updated row, and that response — not
  // the refetch that follows it — is what the cache is written from. A refresh
  // can fail after the mutation committed; when it does, the list must still
  // show what the operator just did rather than pre-mutation state (a revoked
  // control URL under a Copy button, a flag that no longer holds).
  //
  // Each response is a *whole-row* snapshot, though, and two mutations on one
  // overlay can be in flight together (the favorite toggle and delete have no
  // guard of their own), so a snapshot can carry another mutation's
  // pre-change fields — a favorite response still holding the control_url the
  // regenerate beside it just revoked. Writing whole rows would put that
  // revoked link back under the Copy button until the next refresh lands, or
  // for good if that refresh fails. So a mutation writes only the fields it
  // owns, and the refetch behind it reconciles the rest.
  const patchOverlay = useCallback((oid: string, patch: Partial<api.OverlayPayload>) => {
    setOverlays((rows) => rows.map((r) => (r.oid === oid ? { ...r, ...patch } : r)));
  }, []);

  // Creation is the one whole-row write: the row cannot conflict with a
  // mutation of an overlay that did not exist a moment ago.
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

  return {
    overlays,
    loading,
    refreshing,
    error,
    reload,
    applyOverlay,
    patchOverlay,
    removeOverlay,
  };
}
