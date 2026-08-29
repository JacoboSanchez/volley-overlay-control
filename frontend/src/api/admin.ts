/** Admin-only surface — ``/api/v1/admin/*``: user management, the
 *  registration toggle, and the global catalogs (teams, team groups, presets,
 *  icons) that every account reads but only an admin authors. */

import { getAllPages, request, requestMultipart } from './http';
import type { UserOut } from './auth';
import { iconForm, type IconImportResult, type IconOut } from './icons';
import type { PresetSummary } from './presets';
import type { TeamFields, TeamGroupOut, TeamOut } from './teams';

// ---- Users and registration -------------------------------------------------

export function adminListUsers(): Promise<UserOut[]> {
  return getAllPages<UserOut[], UserOut>('/admin/users', (rows) => rows);
}

export function adminCreateUser(
  username: string,
  opts: { password?: string; role?: 'admin' | 'user'; email?: string; display_name?: string } = {},
): Promise<{ user: UserOut; temp_password: string }> {
  return request('POST', '/admin/users', { username, ...opts });
}

export function adminResetPassword(
  userId: number,
): Promise<{ user: UserOut; temp_password: string }> {
  return request('POST', `/admin/users/${userId}/reset-password`, {});
}

export function adminUpdateUser(
  userId: number,
  data: { role?: 'admin' | 'user'; is_active?: boolean; display_name?: string; email?: string },
): Promise<UserOut> {
  return request('PATCH', `/admin/users/${userId}`, data);
}

export function adminDeleteUser(userId: number): Promise<{ ok: boolean }> {
  return request('DELETE', `/admin/users/${userId}`);
}

export function adminGetRegistration(): Promise<{ registration_open: boolean }> {
  return request('GET', '/admin/registration');
}

export function adminSetRegistration(open: boolean): Promise<{ registration_open: boolean }> {
  return request('PUT', '/admin/registration', { registration_open: open });
}

// ---- Global presets ---------------------------------------------------------

export async function adminListGlobalPresets(): Promise<{ items: PresetSummary[] }> {
  const items = await getAllPages<{ items: PresetSummary[] }, PresetSummary>(
    '/admin/presets',
    (body) => body.items,
  );
  return { items };
}

export function adminCreateGlobalPreset(
  name: string,
  values: Record<string, unknown>,
  isActive = true,
): Promise<PresetSummary> {
  return request('POST', '/admin/presets', { name, values, is_active: isActive });
}

export function adminSetPresetActive(
  slug: string,
  isActive: boolean,
): Promise<{ slug: string; is_active: boolean }> {
  return request('PATCH', `/admin/presets/${encodeURIComponent(slug)}`, { is_active: isActive });
}

export function adminDeleteGlobalPreset(slug: string): Promise<void> {
  return request<void>('DELETE', `/admin/presets/${encodeURIComponent(slug)}`);
}

export function adminExportPresets(): Promise<Record<string, Record<string, unknown>>> {
  return request('GET', '/admin/presets/export');
}

export function adminImportPresets(
  themes: Record<string, Record<string, unknown>>,
  replace = false,
): Promise<{ imported: number }> {
  return request('POST', '/admin/presets/import', { themes, replace });
}

// ---- Global teams -----------------------------------------------------------
// JSON import/export uses the APP_TEAMS shape.

export function adminExportTeams(): Promise<Record<string, Record<string, unknown>>> {
  return request('GET', '/admin/teams/export');
}

export function adminImportTeams(
  teams: Record<string, Record<string, unknown>>,
  replace = false,
): Promise<{ imported: number }> {
  return request('POST', '/admin/teams/import', { teams, replace });
}

export interface TeamCatalogTransferLogo {
  mime: 'image/webp';
  data: string;
}

export interface TeamCatalogTransferTeam extends TeamFields {
  key: string;
  logo_asset: string | null;
}

export interface TeamCatalogTransferPackage {
  format: 'volley-overlay-team-catalog';
  version: 1;
  teams: TeamCatalogTransferTeam[];
  logos: Record<string, TeamCatalogTransferLogo>;
}

export interface TeamCatalogConflict {
  key: string;
  incoming_name: string;
  existing_team_id: number | null;
  existing_name: string;
  kind: 'catalog' | 'file';
}

export interface TeamCatalogConflictResolution {
  key: string;
  action: 'replace' | 'rename';
  name?: string;
  expected_team_id?: number;
}

export function adminExportTeamCatalog(includeLogos: boolean): Promise<TeamCatalogTransferPackage> {
  return request(
    'GET',
    `/admin/teams/transfer/export?include_logos=${includeLogos ? 'true' : 'false'}`,
  );
}

export function adminPreviewTeamCatalogImport(
  catalog: TeamCatalogTransferPackage,
): Promise<{ teams: number; conflicts: TeamCatalogConflict[] }> {
  return request('POST', '/admin/teams/transfer/preview', catalog);
}

export function adminImportTeamCatalog(
  catalog: TeamCatalogTransferPackage,
  resolutions: TeamCatalogConflictResolution[],
): Promise<{ imported: number; created: number; replaced: number }> {
  return request('POST', '/admin/teams/transfer/import', {
    catalog,
    resolutions,
  });
}

export function adminCreateTeam(fields: TeamFields): Promise<TeamOut> {
  return request<TeamOut>('POST', '/admin/teams', fields);
}

export function adminUpdateTeam(id: number, fields: Partial<TeamFields>): Promise<TeamOut> {
  return request<TeamOut>('PATCH', `/admin/teams/${id}`, fields);
}

export function adminDeleteTeam(id: number): Promise<{ ok: boolean }> {
  return request('DELETE', `/admin/teams/${id}`);
}

// ---- Global icons -----------------------------------------------------------

export function adminUploadIcon(name: string, file: File): Promise<IconOut> {
  return requestMultipart<IconOut>('POST', '/admin/icons', iconForm(name, file));
}

export function adminRenameIcon(id: number, name: string): Promise<IconOut> {
  return request<IconOut>('PATCH', `/admin/icons/${id}`, { name });
}

export function adminGetIconUsage(id: number): Promise<{ teams: number }> {
  return request('GET', `/admin/icons/${id}/usage`);
}

export function adminDeleteIcon(id: number): Promise<{ ok: boolean; teams_cleared: number }> {
  return request('DELETE', `/admin/icons/${id}`);
}

export function adminImportIconsFromTeams(
  teamIds: number[],
): Promise<{ results: IconImportResult[] }> {
  return request('POST', '/admin/icons/import-from-teams', { team_ids: teamIds });
}

// ---- Team-group authoring ---------------------------------------------------
// Users only ever read active groups (getMyGroups); the admin manager works
// against every group, active or not, and can build/publish/delete them.

export function adminListGroups(): Promise<TeamGroupOut[]> {
  return getAllPages<TeamGroupOut[], TeamGroupOut>('/admin/team-groups', (rows) => rows);
}

export function adminCreateGroup(name: string): Promise<TeamGroupOut> {
  return request<TeamGroupOut>('POST', '/admin/team-groups', { name });
}

export function adminAddGroupMember(groupId: number, teamId: number): Promise<{ ok: boolean }> {
  return request('POST', `/admin/team-groups/${groupId}/members`, { team_id: teamId });
}

export function adminRemoveGroupMember(
  groupId: number,
  teamId: number,
): Promise<{ ok: boolean; removed: boolean }> {
  return request('DELETE', `/admin/team-groups/${groupId}/members/${teamId}`);
}

export function adminSetGroupActive(
  groupId: number,
  isActive: boolean,
): Promise<{ id: number; is_active: boolean }> {
  return request('PATCH', `/admin/team-groups/${groupId}`, { is_active: isActive });
}

export function adminDeleteGroup(groupId: number): Promise<{ ok: boolean }> {
  return request('DELETE', `/admin/team-groups/${groupId}`);
}
