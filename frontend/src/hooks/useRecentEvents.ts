import { useEffect, useState } from 'react';
import * as api from '../api/client';
import type { GameState, AuditRecord, TeamState } from '../api/client';

export type RecentEventKind = 'point_add' | 'set_won' | 'match_won' | 'timeout' | 'manual';

export interface RecentEvent {
  ts: number;
  team: 1 | 2;
  kind: RecentEventKind;
  /** Absolute new score — present only for kind === 'manual'. */
  value?: number;
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
  // ``match_started_at`` is part of the key so a match reset that
  // lands on already-zero scores (e.g. after the operator just
  // undid everything back to 0:0) still refires the effect — the
  // empty audit log then surfaces an empty strip. Timeouts are in
  // the key for the same reason: a timeout-only state push must
  // refetch so the clock chip appears immediately.
  return [
    teamScoreSum(state.team_1),
    teamScoreSum(state.team_2),
    state.team_1?.sets ?? 0,
    state.team_2?.sets ?? 0,
    state.team_1?.timeouts ?? 0,
    state.team_2?.timeouts ?? 0,
    typeof state.match_started_at === 'number' ? state.match_started_at : 0,
  ].join(':');
}

function classifyRecords(records: AuditRecord[]): RecentEvent[] {
  const events: RecentEvent[] = [];
  // Last seen post-state score per (set, team), used to spot no-op
  // ``set_score`` corrections (typed value === current).
  const lastScore: Record<string, number> = {};
  const k = (set: number, team: 1 | 2) => `${set}:${team}`;
  // Last seen post-state set counts. Used to detect set wins from
  // any record whose post-state advances ``team_X.sets`` — covers
  // both explicit ``add_set`` calls and the much more common
  // set-winning ``add_point`` (which the backend doesn't log as
  // ``add_set``).
  let prevSets: { 1: number; 2: number } | null = null;
  // Track match-finished transitions so a set-winning record that
  // also ends the match emits a ``match_won`` chip rather than the
  // regular set-won star.
  let prevMatchFinished = false;

  for (const r of records) {
    const params = (r.params ?? {}) as Record<string, unknown>;
    const result = (r.result ?? {}) as Record<string, unknown>;
    const team = params.team;
    const validTeam = team === 1 || team === 2;
    const undo = !!params.undo;

    // The strip is a "current state activity" indicator — undo
    // records have no on-screen counterpart (the matching forward
    // was tombstoned by ``pop_last_forward``), so surfacing the
    // struck chip alone would float without context. Skip emitting
    // a chip but still let the state trackers (``prevSets``,
    // ``prevMatchFinished``, ``lastScore``) advance below — if we
    // bailed out of the iteration entirely, a subsequent forward
    // would diff against a stale baseline and silently lose its
    // chip (e.g. an undone set-winning point followed by a fresh
    // set-winning point would no longer emit the trophy).

    // ── Action-driven chips ────────────────────────────────────────
    if (validTeam && !undo) {
      const t = team as 1 | 2;
      switch (r.action) {
        case 'add_point':
          events.push({ ts: r.ts, team: t, kind: 'point_add' });
          break;
        case 'add_timeout':
          events.push({ ts: r.ts, team: t, kind: 'timeout' });
          break;
        case 'set_score': {
          const setNum = params.set_number;
          const newVal = params.value;
          if (typeof setNum === 'number' && typeof newVal === 'number') {
            const prev = lastScore[k(setNum, t)] ?? 0;
            if (newVal !== prev) {
              events.push({ ts: r.ts, team: t, kind: 'manual', value: newVal });
            }
          }
          break;
        }
        // ``add_set`` intentionally not handled here. Trophy / star
        // chips fall out of the post-state ``team_X.sets`` diff
        // below, so the explicit add_set path and the set-winning
        // add_point path share the same trigger.
      }
    }

    // ── Set / match win detection via post-state diff ──────────────
    const t1Sets = (result.team_1 as Record<string, unknown> | undefined)?.sets;
    const t2Sets = (result.team_2 as Record<string, unknown> | undefined)?.sets;
    const matchFinished = result.match_finished === true;
    if (typeof t1Sets === 'number' && typeof t2Sets === 'number') {
      if (prevSets !== null) {
        // A sets++ that also ends the match is a match-winning event,
        // not just a set-winning one — promote the chip kind so the
        // operator sees the trophy instead of the regular set star.
        const matchWin = matchFinished && !prevMatchFinished;
        if (t1Sets > prevSets[1]) {
          events.push({ ts: r.ts, team: 1, kind: matchWin ? 'match_won' : 'set_won' });
        }
        if (t2Sets > prevSets[2]) {
          events.push({ ts: r.ts, team: 2, kind: matchWin ? 'match_won' : 'set_won' });
        }
      }
      prevSets = { 1: t1Sets, 2: t2Sets };
    }
    prevMatchFinished = matchFinished;

    // ── Score cache refresh (manual delta detection) ───────────────
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
        // The strip is a pure projection of the tombstone-filtered
        // audit log. Every fetch fully replaces the chip list, so
        // rapid-pair tombstones, generic undoes, and reset all
        // converge to a deterministic "current state activity" view.
        // Undo records contribute nothing to the strip (see the
        // ``if (undo) continue`` in ``classifyRecords``) — they live
        // only in the history drawer and the printable report.
        const fresh = classifyRecords(res.records);
        setEvents(fresh.slice(-max));
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
