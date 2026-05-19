import { useEffect, useRef, useState } from 'react';
import * as api from '../api/client';
import type { AuditRecord, GameState, TeamState } from '../api/client';

export interface UseAuditLogOptions {
  /**
   * Maximum records returned. The backend caps the page at 1000;
   * we default to 20 because the live drawer only ever surfaces
   * the most recent slice.
   */
  limit?: number;
  /**
   * Authoritative state used as the refetch trigger. Pass
   * ``confirmedState`` from ``useGameState`` so we only refetch
   * after the server has acknowledged a change — depending on the
   * optimistic ``state`` would race the audit GET against an
   * in-flight POST and silently drop the chip for the action that
   * just happened.
   */
  trigger: GameState | null | undefined;
}

export interface UseAuditLogResult {
  records: AuditRecord[];
  loading: boolean;
  error: string | null;
  /** Force a refetch outside the normal trigger flow. */
  refresh: () => void;
}

const DEFAULT_LIMIT = 20;

function teamScoreSum(team: TeamState | undefined | null): number {
  if (!team) return 0;
  let total = 0;
  for (const value of Object.values(team.scores ?? {})) {
    if (typeof value === 'number') total += value;
  }
  return total;
}

/**
 * Stable cache key derived from the parts of state that change
 * meaningfully when an action lands. Includes timeouts so a pure
 * timeout-only state push refetches the audit, not just scoring.
 */
function triggerKey(state: GameState | null | undefined): string {
  if (!state) return '';
  return [
    teamScoreSum(state.team_1),
    teamScoreSum(state.team_2),
    state.team_1?.sets ?? 0,
    state.team_2?.sets ?? 0,
    state.team_1?.timeouts ?? 0,
    state.team_2?.timeouts ?? 0,
    state.match_finished ? 1 : 0,
  ].join(':');
}

/**
 * Hook that mirrors the per-OID audit log into a React state slice.
 *
 * Lazily fetches when ``oid`` and ``enabled`` are both truthy. On
 * subsequent ``trigger`` changes (i.e. a new authoritative state
 * arrives), refetches the latest ``limit`` records. Cancels in-
 * flight requests when ``oid`` flips, ``enabled`` falls, or the
 * component unmounts.
 *
 * Returns records **newest-first** so the drawer can render them
 * top-to-bottom without an extra sort pass.
 */
export function useAuditLog(
  oid: string | null,
  enabled: boolean,
  { trigger, limit = DEFAULT_LIMIT }: UseAuditLogOptions,
): UseAuditLogResult {
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const key = triggerKey(trigger);

  useEffect(() => {
    if (!oid || !enabled) {
      // Cancel any in-flight request and clear stale rows so the
      // drawer never paints data from a different OID after a
      // session swap.
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
      setRecords([]);
      setLoading(false);
      setError(null);
      return;
    }

    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    api
      .getAudit(oid, limit, controller.signal)
      .then((res) => {
        if (controller.signal.aborted) return;
        // Backend returns records oldest-first within the page;
        // reverse so the drawer renders newest at the top. ``reverse``
        // is O(n) where a comparison sort would be O(n log n) — same
        // result given the page is already monotonically ordered by
        // the backend.
        const sorted = [...(res.records ?? [])].reverse();
        setRecords(sorted);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        setLoading(false);
      });

    return () => {
      controller.abort();
      if (abortRef.current === controller) abortRef.current = null;
    };
  }, [oid, enabled, key, limit, refreshTick]);

  return {
    records,
    loading,
    error,
    refresh: () => setRefreshTick((n) => n + 1),
  };
}
