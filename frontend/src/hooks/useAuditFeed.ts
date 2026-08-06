import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from '../api/board';
import type { AuditRecord } from '../api/board';

/**
 * Window size for the live audit feed.
 *
 * Sized to cover its widest consumer — the history drawer's 20 rows and the
 * momentum strip's 8 chips, the latter reading through up to 3× that many
 * records because ``add_set`` / ``set_score`` rows don't all surface as
 * chips. One window serves both, so the board never holds two copies of the
 * same log.
 */
export const AUDIT_FEED_LIMIT = 60;

export interface AuditFeed {
  /** Records oldest-first, exactly as ``GET /audit`` returns them. */
  records: AuditRecord[];
  loading: boolean;
  error: string | null;
  /** Force a re-read. Also the recovery path for every inconsistency. */
  refresh: () => void;
  /** Apply an ``audit_append`` push. See ``AuditAppendMessage``. */
  onAppend: (version: number, record: AuditRecord) => void;
  /** Apply an ``audit_invalidate`` push. See ``AuditInvalidateMessage``. */
  onInvalidate: (version: number) => void;
  /** Call after a WebSocket (re)connect — pushes missed while the socket
   *  was down leave a gap no version check can reconstruct. */
  onResync: () => void;
}

/**
 * Live mirror of the per-board action log.
 *
 * Reads ``GET /audit`` once per board and then follows the log over the
 * WebSocket the board already holds, instead of re-fetching after every
 * confirmed point (roughly 150-200 redundant round trips over a five-set
 * match, each racing the POST that caused it).
 *
 * **The fetch is the source of truth; the stream is a hint.** A pushed
 * record is applied only when its ``version`` is exactly one ahead of the
 * version we hold. Any other value means we missed, duplicated or
 * reordered a message, and we re-read instead. Same for an explicit
 * invalidate (an undo tombstone hiding an earlier row, a clear, rotation)
 * and for a reconnect. So the worst a bad frame costs is one extra fetch,
 * never a history that disagrees with the server.
 */
export function useAuditFeed(oid: string | null, enabled: boolean): AuditFeed {
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  // Version the current ``records`` were read at. ``null`` means "we hold
  // nothing trustworthy yet", which makes every push a miss until the
  // first fetch lands — the conservative direction.
  const versionRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const refresh = useCallback(() => {
    // Drop the version before re-reading so a push racing the in-flight
    // fetch can't be mistaken for contiguous with the records we are
    // about to replace.
    versionRef.current = null;
    setRefreshTick((n) => n + 1);
  }, []);

  // Declared before the read below so it runs first on a board switch:
  // the previous board's rows must leave the screen when the board does,
  // not when the new board's read happens to land. Keyed on ``oid`` alone
  // so an ordinary refresh does not blank the strip mid-match.
  useEffect(() => {
    setRecords([]);
    versionRef.current = null;
  }, [oid]);

  useEffect(() => {
    if (!oid || !enabled) {
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
      // Never leave another board's rows on screen after a switch.
      setRecords([]);
      setLoading(false);
      setError(null);
      versionRef.current = null;
      return;
    }

    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);

    api
      .getAudit(oid, AUDIT_FEED_LIMIT, controller.signal)
      .then((res) => {
        if (controller.signal.aborted) return;
        setRecords(res.records ?? []);
        versionRef.current = typeof res.version === 'number' ? res.version : null;
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        // Clear rather than keep: a stale strip that silently stops
        // tracking play is worse than an empty one.
        setRecords([]);
        versionRef.current = null;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });

    return () => {
      controller.abort();
      if (abortRef.current === controller) abortRef.current = null;
    };
  }, [oid, enabled, refreshTick]);

  const onAppend = useCallback(
    (version: number, record: AuditRecord) => {
      const held = versionRef.current;
      if (held === null || version !== held + 1) {
        // Missed, duplicated or reordered — the log we hold is no longer
        // provably contiguous, so stop guessing and re-read.
        refresh();
        return;
      }
      versionRef.current = version;
      setRecords((prev) => {
        const next = [...prev, record];
        // Bounded like the fetch, so a long match can't grow this without
        // limit. Consumers slice their own window off the tail.
        return next.length > AUDIT_FEED_LIMIT ? next.slice(-AUDIT_FEED_LIMIT) : next;
      });
    },
    [refresh],
  );

  // The version is not consulted: an invalidate means records already
  // delivered changed meaning, and no counter can reconstruct that.
  const onInvalidate = useCallback(() => refresh(), [refresh]);

  const onResync = useCallback(() => refresh(), [refresh]);

  return { records, loading, error, refresh, onAppend, onInvalidate, onResync };
}
