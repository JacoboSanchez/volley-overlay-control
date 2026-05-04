import { useEffect, useRef, useState } from 'react';
import * as api from '../api/client';
import type { GameState, AuditRecord } from '../api/client';
import type { components } from '../api/schema';

type TeamState = components['schemas']['TeamState'];

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
          // Always emit a chip on undo so the operator gets the same
          // visual signal as for any other undone action. The
          // synthesized forward chip above only fires when one or
          // more in-between records observed the bumped count, so:
          //   - Adjacent undo (no in-betweens): just the struck chip.
          //   - Non-adjacent undo: synth forward + in-betweens +
          //     struck — recovers the timeline the operator saw
          //     before clicking undo.
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
  // Snapshot we last successfully classified against. We diff prior
  // vs current to detect set / match undoes — those can't be
  // detected from the audit log alone (``pop_last_forward``
  // physically removes the original forward record and doesn't
  // store the popped payload anywhere visible to the classifier).
  const priorSnapshotRef = useRef<PriorSnapshot | null>(null);
  // The full event list we last surfaced. Used to keep "popped"
  // chips visible across refetches: when the operator undoes a
  // forward action, ``pop_last_forward`` deletes its audit record
  // entirely, so a fresh classification of the post-undo log is
  // missing the original chip. We recover it by carrying forward
  // any prior event that doesn't appear in the new classification
  // — the original chip stays put and the undo chip lands beside
  // it, instead of the original silently morphing into a struck
  // variant.
  const priorEventsRef = useRef<RecentEvent[]>([]);

  useEffect(() => {
    if (!enabled || !oid) {
      setEvents([]);
      priorSnapshotRef.current = null;
      priorEventsRef.current = [];
      return;
    }
    const prior = priorSnapshotRef.current;
    const priorEvents = priorEventsRef.current;
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
        const fresh = classifyRecords(res.records);
        // Recover events whose underlying audit record was popped
        // between fetches. ``pop_last_forward`` deletes the original
        // ``add_point`` / ``add_timeout`` row when the operator
        // undoes it, so a fresh re-classification is silently
        // missing the chip we showed last time. Anything in
        // ``priorEvents`` that isn't matched by an entry in
        // ``fresh`` (same ts + team + kind) is treated as popped
        // and re-added.
        const isSame = (a: RecentEvent, b: RecentEvent) =>
          a.ts === b.ts && a.team === b.team && a.kind === b.kind;
        const popped = priorEvents.filter(
          (p) => !fresh.some((f) => isSame(f, p)),
        );
        const merged: RecentEvent[] = [...popped, ...fresh].sort(
          (a, b) => a.ts - b.ts,
        );
        if (prior && cur) {
          // Set / match undo detection: append a struck-chip when
          // sets dropped or match_finished flipped back to false
          // between refetches. ``Date.now() / 1000`` matches the
          // audit ``ts`` unit so the chip sorts after anything in
          // the response.
          const matchUndone = prior.matchFinished && !cur.matchFinished;
          const ts = Date.now() / 1000;
          if (cur.sets1 < prior.sets1) {
            merged.push({
              ts,
              team: 1,
              kind: matchUndone ? 'match_undo' : 'set_undo',
            });
          }
          if (cur.sets2 < prior.sets2) {
            merged.push({
              ts,
              team: 2,
              kind: matchUndone ? 'match_undo' : 'set_undo',
            });
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
