import { useEffect, useRef, useState } from 'react';
import * as api from '../api/client';
import type { GameState, AuditRecord, TeamState } from '../api/client';

export type RecentEventKind =
  | 'point_add'
  | 'point_undo'
  | 'set_won'
  | 'set_undo'
  | 'match_won'
  | 'match_undo'
  | 'timeout'
  | 'timeout_undo'
  | 'manual';

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

    // ── Action-driven chips ────────────────────────────────────────
    if (validTeam) {
      const t = team as 1 | 2;
      switch (r.action) {
        case 'add_point':
          events.push({ ts: r.ts, team: t, kind: undo ? 'point_undo' : 'point_add' });
          break;
        case 'add_timeout': {
          // The forward audit record is physically removed by
          // ``pop_last_forward`` when the operator undoes a timeout,
          // so a popped forward never reaches the classifier — only
          // its undo does. We emit the struck chip on undo to match
          // history / report (which both surface only the undone
          // entry once the forward is tombstoned).
          events.push({
            ts: r.ts,
            team: t,
            kind: undo ? 'timeout_undo' : 'timeout',
          });
          break;
        }
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

interface PriorSnapshot {
  sets1: number;
  sets2: number;
  matchFinished: boolean;
}

function snapshotState(state: GameState | null): PriorSnapshot | null {
  if (!state) return null;
  return {
    sets1: state.team_1?.sets ?? 0,
    sets2: state.team_2?.sets ?? 0,
    matchFinished: state.match_finished === true,
  };
}

export function useRecentEvents(
  oid: string | null,
  enabled: boolean,
  state: GameState | null,
  max: number = 8,
): RecentEvent[] {
  const [events, setEvents] = useState<RecentEvent[]>([]);
  const key = scoringKey(state);
  // We diff prior vs current snapshot to detect set / match undoes:
  // when the operator undoes a set-winning point the audit log loses
  // the forward record (``pop_last_forward`` tombstones it) and the
  // remaining undo record's post-state has the dropped sets count,
  // but there's no anchor inside the log to diff against. The prior
  // snapshot carries that anchor forward across refetches.
  const priorSnapshotRef = useRef<PriorSnapshot | null>(null);

  useEffect(() => {
    if (!enabled || !oid) {
      setEvents([]);
      priorSnapshotRef.current = null;
      return;
    }
    const prior = priorSnapshotRef.current;
    const cur = snapshotState(state);
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
        // audit log plus the synthetic set/match-undo chips that the
        // log can't express on its own. We deliberately do NOT carry
        // any chips forward across refetches: every fetch fully
        // replaces the chip list, so rapid-pair tombstones, generic
        // undoes, and reset all converge to the same view that the
        // history drawer and printable report render.
        const fresh = classifyRecords(res.records);

        // Set / match undo via state-diff. Anchor the synthetic ts
        // above the last audit chip so the struck chip lands on the
        // right of the chips that triggered it.
        if (prior && cur) {
          const matchUndone = prior.matchFinished && !cur.matchFinished;
          const lastChip = fresh[fresh.length - 1];
          let ts = lastChip ? lastChip.ts : Date.now() / 1000;
          if (cur.sets1 < prior.sets1) {
            ts += 1e-3;
            fresh.push({
              ts,
              team: 1,
              kind: matchUndone ? 'match_undo' : 'set_undo',
            });
          }
          if (cur.sets2 < prior.sets2) {
            ts += 1e-3;
            fresh.push({
              ts,
              team: 2,
              kind: matchUndone ? 'match_undo' : 'set_undo',
            });
          }
        }

        // ``classifyRecords`` already walks audit records in append
        // order, so chips are in chronological order — but the
        // synthetic state-diff chips are pushed at the end with a
        // bumped ts, which keeps them rightmost without needing a
        // sort. Slice to the most recent ``max`` chips.
        setEvents(fresh.slice(-max));
        priorSnapshotRef.current = cur;
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
