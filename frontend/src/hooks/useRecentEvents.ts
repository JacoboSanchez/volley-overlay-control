import { useEffect, useState } from 'react';
import * as api from '../api/client';
import type { GameState, AuditRecord } from '../api/client';
import type { components } from '../api/schema';

type TeamState = components['schemas']['TeamState'];

export type RecentEventKind =
  | 'point_add'
  | 'point_undo'
  | 'set_won'
  | 'timeout'
  | 'timeout_undo'
  | 'manual';

export interface RecentEvent {
  ts: number;
  team: 1 | 2;
  kind: RecentEventKind;
  /** Signed delta — present only for kind === 'manual'. */
  delta?: number;
}

const DEFAULT_AUDIT_FETCH_LIMIT = 40;

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

function classifyRecords(records: AuditRecord[]): RecentEvent[] {
  const events: RecentEvent[] = [];
  // Last seen post-state score per (set, team), used to derive deltas
  // for manual ``set_score`` corrections — those carry the absolute
  // value, not the delta.
  const lastScore: Record<string, number> = {};
  const k = (set: number, team: 1 | 2) => `${set}:${team}`;

  for (const r of records) {
    const params = (r.params ?? {}) as Record<string, unknown>;
    const team = params.team;
    const validTeam = team === 1 || team === 2;
    const undo = !!params.undo;

    if (validTeam) {
      const t = team as 1 | 2;
      switch (r.action) {
        case 'add_point':
          events.push({ ts: r.ts, team: t, kind: undo ? 'point_undo' : 'point_add' });
          break;
        case 'add_set':
          // Only forward set wins surface — undoing a set transition
          // is a rare corrective action and adds visual noise without
          // helping the operator read momentum.
          if (!undo) events.push({ ts: r.ts, team: t, kind: 'set_won' });
          break;
        case 'add_timeout':
          events.push({ ts: r.ts, team: t, kind: undo ? 'timeout_undo' : 'timeout' });
          break;
        case 'set_score': {
          const setNum = params.set_number;
          const newVal = params.value;
          if (typeof setNum === 'number' && typeof newVal === 'number') {
            const prev = lastScore[k(setNum, t)] ?? 0;
            const delta = newVal - prev;
            if (delta !== 0) {
              events.push({ ts: r.ts, team: t, kind: 'manual', delta });
            }
          }
          break;
        }
      }
    }

    // Refresh the score cache from this record's post-state so the
    // next ``set_score`` delta is computed against the latest known
    // value — even when the intermediate record wasn't user-rendered.
    const result = (r.result ?? {}) as Record<string, unknown>;
    const scoreSet = result.score_set;
    if (typeof scoreSet === 'number') {
      const t1 = (result.team_1 as Record<string, unknown> | undefined)?.score;
      const t2 = (result.team_2 as Record<string, unknown> | undefined)?.score;
      if (typeof t1 === 'number') lastScore[k(scoreSet, 1)] = t1;
      if (typeof t2 === 'number') lastScore[k(scoreSet, 2)] = t2;
    }
  }
  return events;
}

export function useRecentEvents(
  oid: string | null,
  enabled: boolean,
  state: GameState | null,
  max: number = 8,
): RecentEvent[] {
  const [events, setEvents] = useState<RecentEvent[]>([]);
  const key = scoringKey(state);

  useEffect(() => {
    if (!enabled || !oid) {
      setEvents([]);
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    // 3× headroom over ``max`` covers interleaved ``add_set`` /
    // ``set_score`` records that don't always surface as chips.
    const fetchLimit = Math.max(DEFAULT_AUDIT_FETCH_LIMIT, max * 3);
    api
      .getAudit(oid, fetchLimit, controller.signal)
      .then((res) => {
        if (cancelled) return;
        const all = classifyRecords(res.records);
        setEvents(all.slice(-max));
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        // Drop any previous events so the strip doesn't keep showing
        // stale data after a score change whose refetch failed.
        console.warn('Failed to fetch recent events:', err);
        setEvents([]);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [oid, enabled, key, max]);

  return events;
}
