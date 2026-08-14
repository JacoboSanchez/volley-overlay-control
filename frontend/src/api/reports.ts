/** Archived match reports — ``/api/v1/matches/*``. */

import { request } from './http';

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

export type MatchSort = 'ended' | 'duration';
export type SortDirection = 'asc' | 'desc';

export interface ReportListParams {
  oid?: string;
  mode?: string;
  day?: string | null;
  sort?: MatchSort;
  direction?: SortDirection;
  limit?: number;
  offset?: number;
}

export interface ReportListResponse {
  count: number;
  matches: MatchSummary[];
  limit: number;
  offset: number;
  sort: MatchSort;
  direction: SortDirection;
}

/** Local-day epoch bounds. Constructing both midnights in local time also
 * handles 23/25-hour daylight-saving transition days correctly. */
function localDayBounds(day: string): [number, number] {
  const start = new Date(`${day}T00:00:00`);
  const next = new Date(start);
  next.setDate(start.getDate() + 1);
  return [start.getTime() / 1000, next.getTime() / 1000];
}

function query(params: ReportListParams, includePage: boolean): string {
  const q = new URLSearchParams();
  if (params.oid) q.set('oid', params.oid);
  if (params.mode) q.set('mode', params.mode);
  if (params.day) {
    const [from, to] = localDayBounds(params.day);
    q.set('ended_from', String(from));
    q.set('ended_to', String(to));
  }
  if (includePage) {
    q.set('sort', params.sort ?? 'ended');
    q.set('direction', params.direction ?? 'desc');
    q.set('limit', String(params.limit ?? 20));
    q.set('offset', String(params.offset ?? 0));
  }
  return q.toString();
}

export function listReports(params: ReportListParams = {}): Promise<ReportListResponse> {
  return request('GET', `/matches?${query(params, true)}`);
}

export function listReportDays(
  params: Pick<ReportListParams, 'oid' | 'mode'> = {},
): Promise<{ days: string[] }> {
  const q = new URLSearchParams(query(params, false));
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  q.set('tz', timezone);
  return request('GET', `/matches/days?${q.toString()}`);
}

export function deleteMatch(matchId: string): Promise<void> {
  return request('DELETE', `/matches/${encodeURIComponent(matchId)}`);
}

/** Server-side cap on one bulk-delete request (``BulkDeleteMatchesRequest``
 *  in ``app/api/routes/matches.py``). Selections survive paging, so an
 *  operator can easily exceed it. */
export const BULK_DELETE_CHUNK = 100;

/**
 * Delete every id, in chunks the API will accept. Sent sequentially so a
 * large selection does not fan out into parallel writes; the totals are
 * summed across chunks. A failing chunk rejects, and the ids already
 * deleted by earlier chunks stay deleted — callers should refresh.
 */
export async function deleteMatches(
  matchIds: string[],
): Promise<{ requested: number; deleted: number }> {
  const totals = { requested: 0, deleted: 0 };
  for (let i = 0; i < matchIds.length; i += BULK_DELETE_CHUNK) {
    const chunk = matchIds.slice(i, i + BULK_DELETE_CHUNK);
    const res = await request<{ requested: number; deleted: number }>(
      'POST',
      '/matches/bulk-delete',
      { match_ids: chunk },
    );
    totals.requested += res.requested;
    totals.deleted += res.deleted;
  }
  return totals;
}
