/** Team catalog, the caller's own custom teams, and their groups —
 *  ``/api/v1/teams/*`` and ``/api/v1/my/groups/*``. */

import { getAllPages, request } from './http';
import type { BoardGroupKind } from './board';

export interface TeamOut {
  id: number;
  name: string;
  icon: string | null;
  color: string | null;
  text_color: string | null;
  is_global: boolean;
}

export interface TeamGroupOut {
  id: number;
  name: string;
  is_active: boolean;
  teams: TeamOut[];
}

export interface TeamFields {
  name: string;
  icon?: string | null;
  color?: string | null;
  text_color?: string | null;
}

/** The team catalog, complete (every page walked).
 *
 *  `scope: 'all'` returns the caller's whole universe — every global team plus
 *  their own custom teams — i.e. the same set as the synthetic "All teams"
 *  group. Prefer it over the roster embedded in {@link getMyGroups}, which is
 *  capped: that endpoint pages *groups*, so it cannot page a nested team list.
 */
export function getTeamCatalog(scope: 'global' | 'all' = 'global'): Promise<TeamOut[]> {
  const path = scope === 'all' ? '/teams/catalog?scope=all' : '/teams/catalog';
  return getAllPages<TeamOut[], TeamOut>(path, (rows) => rows);
}

/** Delete one of the caller's own custom teams, dropping it from every group. */
export function deleteMyTeam(teamId: number): Promise<{ ok: boolean }> {
  return request('DELETE', `/teams/mine/${teamId}`);
}

export function createMyTeam(fields: TeamFields): Promise<TeamOut> {
  return request<TeamOut>('POST', '/teams/mine/custom', fields);
}

export function updateMyTeam(teamId: number, fields: Partial<TeamFields>): Promise<TeamOut> {
  return request<TeamOut>('PATCH', `/teams/mine/custom/${teamId}`, fields);
}

// ---- Account: my groups (groups-as-primary-unit) ---------------------------
// A group's `id` is null only for the synthetic "All" group. `removable_ids`
// are the teams the caller added themselves and may remove (admin-intrinsic
// members of a shared group, and the "All" group, are not removable).

export interface GroupDetail {
  id: number | null;
  name: string;
  kind: BoardGroupKind;
  is_private: boolean;
  teams: TeamOut[];
  removable_ids: number[];
}

export function getMyGroups(): Promise<GroupDetail[]> {
  return getAllPages<GroupDetail[], GroupDetail>('/my/groups', (rows) => rows);
}

export function createMyGroup(name: string): Promise<GroupDetail> {
  return request<GroupDetail>('POST', '/my/groups', { name });
}

export function renameMyGroup(groupId: number, name: string): Promise<GroupDetail> {
  return request<GroupDetail>('PATCH', `/my/groups/${groupId}`, { name });
}

export function deleteMyGroup(groupId: number): Promise<{ ok: boolean }> {
  return request('DELETE', `/my/groups/${groupId}`);
}

export function addTeamsToMyGroup(groupId: number, teamIds: number[]): Promise<{ added: number }> {
  return request('POST', `/my/groups/${groupId}/teams`, { team_ids: teamIds });
}

export function removeTeamFromMyGroup(
  groupId: number,
  teamId: number,
): Promise<{ ok: boolean; removed: boolean }> {
  return request('DELETE', `/my/groups/${groupId}/teams/${teamId}`);
}
