import { useEffect, useState } from 'react';
import * as api from '../api/client';
import type { GameState } from '../api/client';
import type { components } from '../api/schema';

type TeamState = components['schemas']['TeamState'];

export interface RecentPoint {
  team: 1 | 2;
  ts: number;
}

const DEFAULT_AUDIT_FETCH_LIMIT = 20;

function teamScoreSum(team: TeamState | undefined | null): number {
  if (!team) return 0;
  const scores = (team.scores ?? {}) as Record<string, unknown>;
  let total = 0;
  for (const value of Object.values(scores)) {
    if (typeof value === 'number') total += value;
  }
  return total;
}

function scoringKey(state: GameState | null): string {
  if (!state) return '';
  return [
    teamScoreSum(state.team_1),
    teamScoreSum(state.team_2),
    state.team_1?.sets ?? 0,
    state.team_2?.sets ?? 0,
  ].join(':');
}

export function useRecentPoints(
  oid: string | null,
  enabled: boolean,
  state: GameState | null,
  max: number = 5,
): RecentPoint[] {
  const [points, setPoints] = useState<RecentPoint[]>([]);
  const key = scoringKey(state);

  useEffect(() => {
    if (!enabled || !oid) {
      setPoints([]);
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    api
      .getAudit(oid, DEFAULT_AUDIT_FETCH_LIMIT, controller.signal)
      .then((res) => {
        if (cancelled) return;
        const recent: RecentPoint[] = [];
        for (const r of res.records) {
          if (r.action !== 'add_point') continue;
          if (r.params?.undo) continue;
          const team = r.params?.team;
          if (team !== 1 && team !== 2) continue;
          recent.push({ team, ts: r.ts });
        }
        setPoints(recent.slice(-max));
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        console.warn('Failed to fetch recent points:', err);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [oid, enabled, key, max]);

  return points;
}
