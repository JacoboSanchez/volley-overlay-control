import { useEffect, useState } from 'react';
import * as api from '../api/client';
import type { GameState, AuditRecord } from '../api/client';
import type { components } from '../api/schema';

type TeamState = components['schemas']['TeamState'];

export type RecentEventKind =
  | 'point_add'
  | 'point_undo'
  | 'set_won'
  | 'match_won'
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
  // Timeouts are part of the key — without them a timeout-only state
  // push wouldn't refetch the audit log, and the clock chip would
  // only surface when the next scoring event arrived.
  return [
    teamScoreSum(state.team_1),
    teamScoreSum(state.team_2),
    state.team_1?.sets ?? 0,
    state.team_2?.sets ?? 0,
    state.team_1?.timeouts ?? 0,
    state.team_2?.timeouts ?? 0,
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
  // Last seen post-state timeout counts. Used to detect "popped"
  // forward timeouts (when a later undo physically removed the
  // forward record from the audit log via ``pop_last_forward``,
  // intermediate records still show the bumped count and we can
  // synthesize the missing chip from the upward diff) and to spot
  // adjacent vs non-adjacent undoes.
  let prevTimeouts: { 1: number; 2: number } | null = null;
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

    const t1Tos = (result.team_1 as Record<string, unknown> | undefined)?.timeouts;
    const t2Tos = (result.team_2 as Record<string, unknown> | undefined)?.timeouts;

    // ── Synthesized forward timeout chips ──────────────────────────
    // ``pop_last_forward`` physically deletes the original forward
    // record from the audit log when the operator undoes a timeout,
    // so we never see it directly. Whenever a record's post-state
    // shows team_X.timeouts higher than the previous record's, and
    // the bump isn't accounted for by *this* record being the
    // forward itself, the bump must come from a record that has
    // since been popped. Synthesize the missing chip and place it
    // right before the current record's chip — chronologically
    // correct since the original happened before the in-between
    // actions that observed the bumped state.
    if (prevTimeouts !== null) {
      const isOurForward = (t: 1 | 2) =>
        r.action === 'add_timeout' && !undo && team === t;
      if (typeof t1Tos === 'number' && t1Tos > prevTimeouts[1] && !isOurForward(1)) {
        events.push({ ts: r.ts - 1e-6, team: 1, kind: 'timeout' });
      }
      if (typeof t2Tos === 'number' && t2Tos > prevTimeouts[2] && !isOurForward(2)) {
        events.push({ ts: r.ts - 1e-6, team: 2, kind: 'timeout' });
      }
    }

    // ── Action-driven chips ────────────────────────────────────────
    if (validTeam) {
      const t = team as 1 | 2;
      switch (r.action) {
        case 'add_point':
          events.push({ ts: r.ts, team: t, kind: undo ? 'point_undo' : 'point_add' });
          break;
        case 'add_timeout': {
          if (undo) {
            // Adjacency: was the previous record's post-state
            // already at this record's post-state? Then the popped
            // forward had no in-between records — both the original
            // and the undo collapse to nothing visible. Otherwise
            // we already synthesized the forward chip above (one or
            // more in-between records carried the bumped count) and
            // the undo gets its struck chip here.
            const post = (result[`team_${t}`] as Record<string, unknown> | undefined)?.timeouts;
            const prev = prevTimeouts ? prevTimeouts[t] : post;
            if (typeof post === 'number' && prev === post) {
              // Adjacent — emit nothing.
            } else {
              events.push({ ts: r.ts, team: t, kind: 'timeout_undo' });
            }
          } else {
            events.push({ ts: r.ts, team: t, kind: 'timeout' });
          }
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

    // ── Timeout state refresh (synthesis baseline) ─────────────────
    if (typeof t1Tos === 'number' || typeof t2Tos === 'number') {
      prevTimeouts = {
        1: typeof t1Tos === 'number' ? t1Tos : prevTimeouts?.[1] ?? 0,
        2: typeof t2Tos === 'number' ? t2Tos : prevTimeouts?.[2] ?? 0,
      };
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
