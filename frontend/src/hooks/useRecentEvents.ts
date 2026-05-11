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
  // Timeouts are part of the key — without them a timeout-only state
  // push wouldn't refetch the audit log, and the clock chip would
  // only surface when the next scoring event arrived.
  // ``match_started_at`` is part of the key so a match reset that
  // lands on already-zero scores (e.g. after the operator just
  // undid everything back to 0:0) still refires the effect — the
  // matchBoundary detector inside then clears ``priorEventsRef``
  // and the strip drops any leftover undo chips. Without this the
  // chips would linger until the next scoring event changed the
  // numeric portion of the key.
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

// Inverse mapping used to suppress recovered "alive" chips whose
// undo counterpart is already in the fresh classification (or
// synthesized from the state-diff). Keeps the strip consistent
// with history / report — both of which only surface the undone
// entry once the forward has been tombstoned.
const INVERSE_UNDO_KIND: Partial<Record<RecentEventKind, RecentEventKind>> = {
  point_add: 'point_undo',
  timeout: 'timeout_undo',
  set_won: 'set_undo',
  match_won: 'match_undo',
};

interface PriorSnapshot {
  sets1: number;
  sets2: number;
  matchFinished: boolean;
  matchStartedAt: number | null;
}

function snapshotState(state: GameState | null): PriorSnapshot | null {
  if (!state) return null;
  return {
    sets1: state.team_1?.sets ?? 0,
    sets2: state.team_2?.sets ?? 0,
    matchFinished: state.match_finished === true,
    matchStartedAt:
      typeof state.match_started_at === 'number' ? state.match_started_at : null,
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
  // Snapshot we last successfully classified against. We diff prior
  // vs current to detect set / match undoes — those can't be
  // detected from the audit log alone (``pop_last_forward``
  // physically removes the original forward record and doesn't
  // store the popped payload anywhere visible to the classifier).
  const priorSnapshotRef = useRef<PriorSnapshot | null>(null);
  // The full event list we last surfaced. Used to keep chips that
  // aged out of the audit fetch window visible across refetches.
  // We deliberately do NOT use this buffer to resurrect chips whose
  // underlying record was popped by ``pop_last_forward`` — when the
  // operator undoes an action, the strip should drop the "alive"
  // chip and surface only the struck/undone chip, mirroring how
  // history and report render the same event.
  const priorEventsRef = useRef<RecentEvent[]>([]);

  useEffect(() => {
    if (!enabled || !oid) {
      setEvents([]);
      priorSnapshotRef.current = null;
      priorEventsRef.current = [];
      return;
    }
    const prior = priorSnapshotRef.current;
    const cur = snapshotState(state);
    // Drop the stickiness buffer when the operator (re)starts the
    // match — ``match_started_at`` flipping from one timestamp to
    // another (or to / from null) means the prior chips belong to
    // a different match and shouldn't bleed across the boundary.
    const matchBoundary =
      prior !== null && cur !== null && prior.matchStartedAt !== cur.matchStartedAt;
    if (matchBoundary) {
      priorEventsRef.current = [];
    }
    const priorEvents = priorEventsRef.current;
    const controller = new AbortController();
    let cancelled = false;
    // 3× headroom over ``max`` covers interleaved ``add_set`` /
    // ``set_score`` records that don't always surface as chips.
    const fetchLimit = Math.max(DEFAULT_AUDIT_FETCH_LIMIT, max * 3);
    api
      .getAudit(oid, fetchLimit, controller.signal)
      .then((res) => {
        if (cancelled) return;
        const fresh = classifyRecords(res.records);

        // Pre-compute the synthetic set/match undo chips that will
        // be appended from the state-diff below — we need them in
        // the suppression set so a recovered ``set_won`` / ``match_won``
        // is dropped when its undo only surfaces via the snapshot
        // diff (not the audit log).
        const syntheticUndoes: RecentEvent[] = [];
        if (prior && cur) {
          const matchUndone = prior.matchFinished && !cur.matchFinished;
          if (cur.sets1 < prior.sets1) {
            syntheticUndoes.push({
              ts: 0,
              team: 1,
              kind: matchUndone ? 'match_undo' : 'set_undo',
            });
          }
          if (cur.sets2 < prior.sets2) {
            syntheticUndoes.push({
              ts: 0,
              team: 2,
              kind: matchUndone ? 'match_undo' : 'set_undo',
            });
          }
        }

        // Build the suppression set keyed by ``team:kind`` so we can
        // drop a recovered "alive" chip whose undo counterpart is
        // already visible — either from the fresh classification or
        // synthesized from the state-diff.
        const undoPresent = new Set<string>();
        for (const e of fresh) undoPresent.add(`${e.team}:${e.kind}`);
        for (const e of syntheticUndoes) undoPresent.add(`${e.team}:${e.kind}`);

        // Recover events whose underlying audit record aged out of
        // the fetch window. ``pop_last_forward`` deletes the original
        // ``add_point`` / ``add_timeout`` row when the operator
        // undoes it, so a fresh re-classification would be silently
        // missing the chip we showed last time — but we deliberately
        // do NOT resurrect the "alive" chip in that case, so the
        // strip matches history / report (both show only the
        // struck/undone entry).
        // ``value`` is part of the identity for ``manual`` chips — two
        // different manual corrections can land at the same ts (e.g.
        // low-resolution server clock) and must not dedupe each other.
        const isSame = (a: RecentEvent, b: RecentEvent) =>
          a.ts === b.ts &&
          a.team === b.team &&
          a.kind === b.kind &&
          a.value === b.value;
        const popped = priorEvents.filter((p) => {
          if (fresh.some((f) => isSame(f, p))) return false;
          const inverse = INVERSE_UNDO_KIND[p.kind];
          if (inverse && undoPresent.has(`${p.team}:${inverse}`)) return false;
          return true;
        });
        const merged: RecentEvent[] = [...popped, ...fresh].sort(
          (a, b) => a.ts - b.ts,
        );

        // Append the synthetic state-diff undoes now, anchoring each
        // ts to the latest merged event rather than ``Date.now()``
        // — the audit log's ts is the server clock and a drifted
        // client clock could otherwise sort the undo chip ahead of
        // records that actually happened later.
        if (syntheticUndoes.length > 0) {
          const lastMerged = merged[merged.length - 1];
          let ts = lastMerged ? lastMerged.ts : Date.now() / 1000;
          for (const u of syntheticUndoes) {
            ts += 1e-3;
            merged.push({ ...u, ts });
          }
        }

        const capped = merged.slice(-max);
        setEvents(capped);
        priorSnapshotRef.current = cur;
        // Keep extra headroom over ``max`` so a popped event still
        // sitting just off the visible window can be recovered on
        // the next refetch (otherwise a single intervening chip
        // would push it past the cap and lose the recovery anchor).
        priorEventsRef.current = merged.slice(-max * 4);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        // Drop any previous events so the strip doesn't keep showing
        // stale data after a score change whose refetch failed.
        console.warn('Failed to fetch recent events:', err);
        setEvents([]);
        priorEventsRef.current = [];
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [oid, enabled, key, max]);

  return events;
}
