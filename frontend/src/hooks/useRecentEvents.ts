import { useMemo } from 'react';
import type { AuditRecord, PointType } from '../api/board';

export type RecentEventKind = 'point_add' | 'set_won' | 'match_won' | 'timeout' | 'manual';

export interface RecentEvent {
  ts: number;
  team: 1 | 2;
  kind: RecentEventKind;
  /** Absolute new score — present only for kind === 'manual'. */
  value?: number | undefined;
  /**
   * Optional per-point classification — present only for
   * kind === 'point_add' when the operator tagged the point.
   */
  pointType?: PointType | undefined;
}

/**
 * Project a window of audit records onto the chips the momentum strip
 * renders. Exported for direct testing: it is the whole substance of this
 * module, and every rule below is about how the log reads rather than how
 * it is fetched.
 */
export function classifyRecords(records: AuditRecord[]): RecentEvent[] {
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
        case 'add_point': {
          const pt =
            typeof params.point_type === 'string' ? (params.point_type as PointType) : undefined;
          events.push({ ts: r.ts, team: t, kind: 'point_add', pointType: pt });
          break;
        }
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

/**
 * The momentum strip's chips, derived from the board's live audit feed.
 *
 * A pure projection — the records arrive already maintained by
 * ``useAuditFeed`` (one fetch per board, then WebSocket pushes). It used to
 * own a fetch of its own keyed on a digest of the score, which is what made
 * every point cost an extra ``GET /audit`` and forced the strip to trigger
 * off ``confirmedState`` so the refetch wouldn't race the in-flight POST.
 * Neither concern exists once the records are pushed: there is no fetch to
 * race, and the chips update when the log does rather than when the score
 * happens to change.
 *
 * The strip is a full projection of the tombstone-filtered log, so
 * rapid-pair tombstones, generic undos and reset all converge on the same
 * "current activity" view. Undo records emit no chip of their own (see
 * ``classifyRecords``) — they live in the history drawer and the printable
 * report.
 */
export function useRecentEvents(records: AuditRecord[], max: number = 8): RecentEvent[] {
  return useMemo(() => classifyRecords(records).slice(-max), [records, max]);
}
