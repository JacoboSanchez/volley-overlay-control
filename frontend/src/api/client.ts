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
export type OverlayPayload = Schemas['OverlayPayload'];
export type TeamState = Schemas['TeamState'];

export type InitOptions = Omit<InitRequest, 'oid'>;

const BASE_URL = '/api/v1';

let apiKey: string | null = null;

export function setApiKey(key: string | null): void {
  apiKey = key;
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (apiKey) h['Authorization'] = `Bearer ${apiKey}`;
  return h;
}

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';

function withOid(oid: string): string {
  return `?oid=${encodeURIComponent(oid)}`;
}

async function request<T = unknown>(
  method: HttpMethod,
  path: string,
  body: unknown = null,
  signal?: AbortSignal,
): Promise<T> {
  const opts: RequestInit = { method, headers: headers() };
  if (body !== null) {
    opts.body = JSON.stringify(body);
  }
  if (signal) {
    opts.signal = signal;
  }
  const res = await fetch(`${BASE_URL}${path}`, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${method} ${path} failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<T>;
}

// Session
export function initSession(oid: string, opts: InitOptions = {}): Promise<ActionResponse> {
  return request<ActionResponse>('POST', '/session/init', { oid, ...opts });
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
  'podium',
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
  created_at: number;
  source: 'user' | 'system';
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

export async function deletePreset(slug: string): Promise<void> {
  // ``request`` always tries to ``res.json()`` and the delete handler
  // returns 204 No Content with no body, which would throw. Use the
  // raw fetch path here so the caller gets a clean ``void`` resolve.
  const path = `/customization/presets/${encodeURIComponent(slug)}`;
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'DELETE',
    headers: headers(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API DELETE ${path} failed (${res.status}): ${text}`);
  }
}

export function getLinks(oid: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('GET', `/links${withOid(oid)}`);
}

export function getStyles(oid: string): Promise<string[]> {
  return request<string[]>('GET', `/styles${withOid(oid)}`);
}

export function getOverlays(): Promise<OverlayPayload[]> {
  return request<OverlayPayload[]>('GET', '/overlays');
}

export function getAppConfig(): Promise<AppConfig> {
  return request<AppConfig>('GET', '/app-config');
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
