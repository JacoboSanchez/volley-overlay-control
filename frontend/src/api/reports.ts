/** Archived match reports — ``/api/v1/matches/*``. */

import { request, withOid } from './http';

export interface MatchSummary {
  match_id: string;
  oid: string;
  ended_at: number | null;
  duration_s: number | null;
  winning_team: number | null;
  team_1_sets?: number | null;
  team_2_sets?: number | null;
  team_1_name?: string | null;
  team_2_name?: string | null;
  mode?: string | null;
}

export function listReports(oid?: string): Promise<{ count: number; matches: MatchSummary[] }> {
  // The server pages this endpoint (default 100); request its maximum page.
  // The Reports page filters client-side, so one large page keeps that UX;
  // `count` in the response is the total should a library ever outgrow it.
  const q = oid ? `${withOid(oid)}&limit=500` : '?limit=500';
  return request('GET', `/matches${q}`);
}

export function deleteMatch(matchId: string): Promise<void> {
  return request('DELETE', `/matches/${encodeURIComponent(matchId)}`);
}
