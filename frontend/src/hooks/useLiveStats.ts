import { useEffect, useRef, useState } from 'react';
import * as api from '../api/client';
import type { GameState, LiveStatsResponse, TeamState } from '../api/client';

export interface UseLiveStatsOptions {
  /**
   * Number of recent points to fetch. The sparkline uses 20 by
   * default — enough to read momentum without saturating the WS
   * push pipeline on a long deuce.
   */
  limit?: number;
  /**
   * Authoritative state. Refetches when this changes so the
   * sparkline reflects the latest scoring event without polling.
   */
  trigger: GameState | null | undefined;
}

export interface UseLiveStatsResult {
  stats: LiveStatsResponse | null;
  loading: boolean;
  error: string | null;
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
 * Hook that mirrors :func:`compute_live_stats` into a React state slice.
 *
 * Refetches whenever the authoritative state changes (so the sparkline
 * updates after every confirmed point). Cancels in-flight requests on
 * OID swap / disable / unmount. Mirrors :func:`useAuditLog` so future
 * consumers (dashboards, /follow page) can read the same shape.
 */
export function useLiveStats(
  oid: string | null,
  enabled: boolean,
  { trigger, limit = DEFAULT_LIMIT }: UseLiveStatsOptions,
): UseLiveStatsResult {
  const [stats, setStats] = useState<LiveStatsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const key = triggerKey(trigger);

  useEffect(() => {
    if (!oid || !enabled) {
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
      setStats(null);
      setLoading(false);
      setError(null);
      return;
    }

    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    api.getLiveStats(oid, limit, controller.signal)
      .then((res) => {
        if (controller.signal.aborted) return;
        setStats(res);
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
  }, [oid, enabled, key, limit]);

  return { stats, loading, error };
}
