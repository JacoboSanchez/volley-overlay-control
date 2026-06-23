/**
 * REST API client for the Volley Overlay Control backend.
 *
 * Types are derived from the OpenAPI schema snapshot at
 * ``frontend/schema/openapi.json``. Run ``npm run gen:types`` after backend
 * schema changes to regenerate ``./schema.d.ts``.
 */

import type { components } from './schema';

type Schemas = components['schemas'];

export type Team = 1 | 2;

// Per-point classification vocabulary — mirrors the backend
// ``POINT_TYPES`` / ``ERROR_TYPES`` in ``app/api/schemas.py``. Keep in sync.
export const POINT_TYPES = ['ace', 'kill', 'block', 'opp_error'] as const;
export type PointType = (typeof POINT_TYPES)[number];
export const ERROR_TYPES = [
  'serve_error',
  'attack_error',
  'reception_error',
  'ball_handling',
  'net_fault',
  'position_fault',
  'other',
] as const;
export type ErrorType = (typeof ERROR_TYPES)[number];

export type GameState = Schemas['GameStateResponse'];
export type ActionResponse = Schemas['ActionResponse'];
export type AppConfig = Schemas['AppConfigResponse'];
export type InitRequest = Schemas['InitRequest'];
/** One of the caller's overlays (DB-backed, per-user). ``name`` is a
 *  board-friendly label derived from ``display_name`` or the oid. */
export interface OverlayPayload {
  name: string;
  oid: string;
  display_name: string | null;
  public_token: string;
  output_url: string;
  control_token: string | null;
  control_url: string | null;
  public_control: boolean;
  public_control_url: string | null;
}

export interface OverlaySettings {
  display_name?: string | null;
  public_control?: boolean;
}
export type TeamState = Schemas['TeamState'];

export type InitOptions = Omit<InitRequest, 'oid'>;

const BASE_URL = '/api/v1';

// Authentication is cookie-based now (HttpOnly session cookie). Requests are
// same-origin so the cookie is sent automatically; ``credentials: 'include'``
// makes that explicit and survives any future cross-origin dev setup.

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';

// Unauthenticated board modes. When set, board-scoped requests address the
// board by capability instead of the owner's ``?oid=`` + session cookie:
//   * controlToken → ``?c=<token>``           (shareable, revocable operator link)
//   * publicUser   → ``?u=<username>&oid=<oid>`` (stable, opt-in bookmark link)
// Both are ``null`` in the normal owner (cookie) mode.
let controlToken: string | null = null;
let publicUser: string | null = null;

export function setControlToken(token: string | null): void {
  controlToken = token || null;
}

export function getControlToken(): string | null {
  return controlToken;
}

export function setPublicUser(username: string | null): void {
  publicUser = username || null;
}

export function getPublicUser(): string | null {
  return publicUser;
}

/** Board-scoping query string for the active credential mode. */
function withOid(oid: string): string {
  if (controlToken) return `?c=${encodeURIComponent(controlToken)}`;
  if (publicUser) {
    return `?u=${encodeURIComponent(publicUser)}&oid=${encodeURIComponent(oid)}`;
  }
  return `?oid=${encodeURIComponent(oid)}`;
}

/** Thrown on a non-2xx API response; carries the HTTP status and a
 *  human-facing ``detail`` (the API's ``detail`` field when present) so pages
 *  can show a clean message instead of the raw JSON envelope. */
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail || message;
  }
}

/** Pull a clean human message out of a FastAPI error body (string ``detail``,
 *  a 422 validation array, or the raw text as a last resort). */
function extractDetail(text: string): string {
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed.detail === 'string') return parsed.detail;
    if (parsed && Array.isArray(parsed.detail)) {
      const msgs = parsed.detail
        .map((d: { msg?: string }) => (d && d.msg) || '')
        .filter(Boolean);
      if (msgs.length) return msgs.join('; ');
    }
  } catch {
    /* not JSON — fall through to the raw text */
  }
  return text;
}

async function request<T = unknown>(
  method: HttpMethod,
  path: string,
  body: unknown = null,
  signal?: AbortSignal,
): Promise<T> {
  const opts: RequestInit = {
    method,
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  };
  if (body !== null) {
    opts.body = JSON.stringify(body);
  }
  if (signal) {
    opts.signal = signal;
  }
  const res = await fetch(`${BASE_URL}${path}`, opts);
  if (!res.ok) {
    // A 401 on any non-auth route means the session cookie expired or was
    // revoked mid-use. Signal the app so AuthProvider drops to /login instead
    // of leaving the user on a stuck/stale page. Auth routes (login,
    // claim-admin, context, logout) handle their own 401s and must not loop.
    if (res.status === 401 && !path.startsWith('/auth/') && typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('auth:unauthorized'));
    }
    const text = await res.text();
    throw new ApiError(
      res.status,
      `API ${method} ${path} failed (${res.status}): ${text}`,
      extractDetail(text),
    );
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// Session
export function initSession(oid: string, opts: InitOptions = {}): Promise<ActionResponse> {
  // Owner mode carries the oid in the body (+ cookie); a capability mode needs
  // the token or username+oid on the query so the server can resolve the board.
  let q = '';
  if (controlToken) q = `?c=${encodeURIComponent(controlToken)}`;
  else if (publicUser) {
    q = `?u=${encodeURIComponent(publicUser)}&oid=${encodeURIComponent(oid)}`;
  }
  return request<ActionResponse>('POST', `/session/init${q}`, { oid, ...opts });
}

// State queries
export function getState(oid: string): Promise<GameState> {
  return request<GameState>('GET', `/state${withOid(oid)}`);
}

export function getConfig(oid: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('GET', `/config${withOid(oid)}`);
}

export function getCustomization(oid: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('GET', `/customization${withOid(oid)}`);
}

// Game actions
export function addPoint(
  oid: string,
  team: Team,
  undo = false,
  pointType?: PointType,
  errorType?: ErrorType,
): Promise<ActionResponse> {
  const body: Record<string, unknown> = { team, undo };
  // Scouting tags are optional; only send them when set so an untyped
  // point posts the same minimal body as before.
  if (pointType) body.point_type = pointType;
  if (errorType) body.error_type = errorType;
  return request<ActionResponse>('POST', `/game/add-point${withOid(oid)}`, body);
}

export function addSet(oid: string, team: Team, undo = false): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/game/add-set${withOid(oid)}`, { team, undo });
}

export function addTimeout(oid: string, team: Team, undo = false): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/game/add-timeout${withOid(oid)}`, { team, undo });
}

export function changeServe(oid: string, team: Team): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/game/change-serve${withOid(oid)}`, { team });
}

export function setScore(
  oid: string,
  team: Team,
  setNumber: number,
  value: number,
): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/game/set-score${withOid(oid)}`, {
    team,
    set_number: setNumber,
    value,
  });
}

export function setSets(oid: string, team: Team, value: number): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/game/set-sets${withOid(oid)}`, { team, value });
}

export function undoLast(oid: string): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/game/undo${withOid(oid)}`);
}

export function resetGame(oid: string): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/game/reset${withOid(oid)}`);
}

export function startMatch(oid: string): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/game/start-match${withOid(oid)}`);
}

// Display controls
export function setVisibility(oid: string, visible: boolean): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/display/visibility${withOid(oid)}`, { visible });
}

export function setSimpleMode(oid: string, enabled: boolean): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/display/simple-mode${withOid(oid)}`, { enabled });
}

export const SET_SUMMARY_STYLES = [
  'brand_ledger',
  'bento',
  'glass',
  'brand_columns',
  'ledger_diff',
  'bumper',
] as const;
export type SetSummaryStyle = (typeof SET_SUMMARY_STYLES)[number];

export function setSwapSides(oid: string, swapped: boolean): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/display/swap-sides${withOid(oid)}`, { swapped });
}

export function setAutoSwapSides(oid: string, enabled: boolean): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/display/auto-swap-sides${withOid(oid)}`, { enabled });
}

export function setSetSummary(oid: string, enabled: boolean): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/display/set-summary${withOid(oid)}`, { enabled });
}

export function setSetSummaryStyle(oid: string, style: SetSummaryStyle): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/display/set-summary-style${withOid(oid)}`, { style });
}

export type MatchMode = 'indoor' | 'beach';

export interface SetRulesPayload {
  mode?: MatchMode;
  points_limit?: number;
  points_limit_last_set?: number;
  sets_limit?: number;
  reset_to_defaults?: boolean;
}

export function setRules(oid: string, payload: SetRulesPayload): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/session/rules${withOid(oid)}`, payload);
}

// Customization
export function updateCustomization(
  oid: string,
  data: Record<string, unknown>,
): Promise<ActionResponse> {
  return request<ActionResponse>('PUT', `/customization${withOid(oid)}`, data);
}

// Predefined data
export function getTeams(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('GET', '/teams');
}

// Operator-saved and env-driven presets (CRUD lives at
// /customization/presets/*). Load is purely client-side: the React
// panel deep-merges ``values`` into its in-memory edit model and
// persists via the existing PUT /customization save flow. ``source``
// is ``"system"`` for read-only entries derived from ``APP_THEMES``
// and ``"user"`` for records the operator saved themselves.
export interface PresetCategory {
  id: 'team1_name' | 'team1_color' | 'team2_name' | 'team2_color' | 'position' | 'style';
}

export interface PresetSummary {
  slug: string;
  name: string;
  source: 'user' | 'global';
  is_active?: boolean;
  categories: string[];
  values: Record<string, unknown>;
}

export function listPresets(): Promise<{ items: PresetSummary[] }> {
  return request<{ items: PresetSummary[] }>('GET', '/customization/presets');
}

export function createPreset(
  name: string,
  values: Record<string, unknown>,
): Promise<PresetSummary> {
  return request<PresetSummary>('POST', '/customization/presets', { name, values });
}

export function deletePreset(slug: string): Promise<void> {
  return request<void>('DELETE', `/customization/presets/${encodeURIComponent(slug)}`);
}

// Admin global-preset management.
export function adminListGlobalPresets(): Promise<{ items: PresetSummary[] }> {
  return request('GET', '/admin/presets');
}

export function adminCreateGlobalPreset(
  name: string,
  values: Record<string, unknown>,
  isActive = true,
): Promise<PresetSummary> {
  return request('POST', '/admin/presets', { name, values, is_active: isActive });
}

export function adminSetPresetActive(slug: string, isActive: boolean): Promise<{ slug: string; is_active: boolean }> {
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

// Admin global-team JSON import/export (APP_TEAMS shape).
export function adminExportTeams(): Promise<Record<string, Record<string, unknown>>> {
  return request('GET', '/admin/teams/export');
}

export function adminImportTeams(
  teams: Record<string, Record<string, unknown>>,
  replace = false,
): Promise<{ imported: number }> {
  return request('POST', '/admin/teams/import', { teams, replace });
}

// ---- Teams: catalog, my list, groups --------------------------------------

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

export function getTeamCatalog(): Promise<TeamOut[]> {
  return request<TeamOut[]>('GET', '/teams/catalog');
}

/** The caller's team list as rows with ids (global + own custom teams). */
export function getMyTeams(): Promise<TeamOut[]> {
  return request<TeamOut[]>('GET', '/teams/mine');
}

export function addTeamsToMine(teamIds: number[]): Promise<{ added: number }> {
  return request('POST', '/teams/mine', { team_ids: teamIds });
}

export function removeTeamFromMine(teamId: number): Promise<{ ok: boolean }> {
  return request('DELETE', `/teams/mine/${teamId}`);
}

export function removeTeamsFromMine(teamIds: number[]): Promise<{ removed: number }> {
  return request('POST', '/teams/mine/remove', { team_ids: teamIds });
}

export function createMyTeam(fields: TeamFields): Promise<TeamOut> {
  return request<TeamOut>('POST', '/teams/mine/custom', fields);
}

export function updateMyTeam(teamId: number, fields: Partial<TeamFields>): Promise<TeamOut> {
  return request<TeamOut>('PATCH', `/teams/mine/custom/${teamId}`, fields);
}

export function getTeamGroups(): Promise<TeamGroupOut[]> {
  return request<TeamGroupOut[]>('GET', '/team-groups');
}

export function copyGroupToMine(groupId: number): Promise<{ added: number }> {
  return request('POST', `/team-groups/${groupId}/copy-to-mine`, {});
}

export interface TeamFields {
  name: string;
  icon?: string | null;
  color?: string | null;
  text_color?: string | null;
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

// ---- Match reports (per overlay) ------------------------------------------

export interface MatchSummary {
  match_id: string;
  oid: string;
  ended_at: number | null;
  duration_s: number | null;
  winning_team: number | null;
}

export function listReports(oid?: string): Promise<{ count: number; matches: MatchSummary[] }> {
  const q = oid ? withOid(oid) : '';
  return request('GET', `/matches${q}`);
}

// ---- Admin -----------------------------------------------------------------

export function adminListUsers(): Promise<UserOut[]> {
  return request<UserOut[]>('GET', '/admin/users');
}

export function adminCreateUser(
  username: string,
  opts: { password?: string; role?: 'admin' | 'user'; email?: string; display_name?: string } = {},
): Promise<{ user: UserOut; temp_password: string }> {
  return request('POST', '/admin/users', { username, ...opts });
}

export function adminResetPassword(userId: number): Promise<{ user: UserOut; temp_password: string }> {
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

export function getLinks(oid: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('GET', `/links${withOid(oid)}`);
}

export function getStyles(oid: string): Promise<string[]> {
  return request<string[]>('GET', `/styles${withOid(oid)}`);
}

/** Per-style UI capability flags reported by the backend. */
export interface StyleCapabilities {
  /** Style ships a dark/light override block — show the theme selector. */
  theme: boolean;
  /** Style is edge-pinned — show the top/center/bottom vertical-anchor control. */
  verticalAnchor: boolean;
}

export function getStyleCapabilities(oid: string): Promise<Record<string, StyleCapabilities>> {
  return request<Record<string, StyleCapabilities>>('GET', `/style-capabilities${withOid(oid)}`);
}

type OverlayRow = Omit<OverlayPayload, 'name'>;

function withName(r: OverlayRow): OverlayPayload {
  return { name: r.display_name || r.oid, ...r };
}

export async function getOverlays(): Promise<OverlayPayload[]> {
  const rows = await request<OverlayRow[]>('GET', '/overlays');
  return rows.map(withName);
}

export async function createOverlay(
  oid: string,
  settings: OverlaySettings = {},
): Promise<OverlayPayload> {
  const row = await request<OverlayRow>('POST', '/overlays', { oid, ...settings });
  return withName(row);
}

export async function updateOverlay(
  oid: string,
  settings: OverlaySettings,
): Promise<OverlayPayload> {
  const row = await request<OverlayRow>('PATCH', `/overlays/${encodeURIComponent(oid)}`, settings);
  return withName(row);
}

export function deleteOverlay(oid: string): Promise<void> {
  return request<void>('DELETE', `/overlays/${encodeURIComponent(oid)}`);
}

/** Mint a fresh control link for an overlay, revoking the previous one. */
export async function regenerateControlToken(oid: string): Promise<OverlayPayload> {
  const row = await request<OverlayRow>(
    'POST', `/overlays/${encodeURIComponent(oid)}/regenerate-control-token`, {},
  );
  return withName(row);
}

export function getAppConfig(): Promise<AppConfig> {
  return request<AppConfig>('GET', '/app-config');
}

// ---- Auth / account --------------------------------------------------------

export interface UserOut {
  id: number;
  username: string;
  display_name: string | null;
  email: string | null;
  role: 'admin' | 'user';
  is_active: boolean;
  must_change_password: boolean;
}

export interface AuthContext {
  authenticated: boolean;
  user: UserOut | null;
  registration_open: boolean;
  needs_admin_bootstrap: boolean;
}

export function getAuthContext(): Promise<AuthContext> {
  return request<AuthContext>('GET', '/auth/context');
}

export function login(username: string, password: string): Promise<{ user: UserOut; must_change_password: boolean }> {
  return request('POST', '/auth/login', { username, password });
}

export function registerAccount(
  username: string,
  password: string,
  display_name?: string,
  email?: string,
): Promise<{ user: UserOut }> {
  return request('POST', '/auth/register', { username, password, display_name, email });
}

export function claimAdmin(
  token: string,
  username: string,
  password: string,
): Promise<{ user: UserOut }> {
  return request('POST', '/auth/claim-admin', { token, username, password });
}

export function logout(): Promise<{ ok: boolean }> {
  return request('POST', '/auth/logout', {});
}

export function changePassword(current_password: string, new_password: string): Promise<UserOut> {
  return request('POST', '/auth/change-password', { current_password, new_password });
}

export function updateMe(data: { display_name?: string; email?: string }): Promise<UserOut> {
  return request('PATCH', '/auth/me', data);
}

export function deleteMe(): Promise<{ ok: boolean }> {
  return request('DELETE', '/auth/me');
}

// Audit log
export interface AuditParams {
  team?: 1 | 2;
  undo?: boolean;
  [key: string]: unknown;
}

export interface AuditRecord {
  ts: number;
  action: string;
  params: AuditParams;
  result?: Record<string, unknown>;
}

export interface AuditResponse {
  oid: string;
  count: number;
  records: AuditRecord[];
}

export function getAudit(
  oid: string,
  limit: number = 20,
  signal?: AbortSignal,
): Promise<AuditResponse> {
  return request<AuditResponse>('GET', `/audit${withOid(oid)}&limit=${limit}`, null, signal);
}
