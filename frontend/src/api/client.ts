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

export type GameState = Schemas['GameStateResponse'];
export type ActionResponse = Schemas['ActionResponse'];
export type AppConfig = Schemas['AppConfigResponse'];
export type InitRequest = Schemas['InitRequest'];
export type OverlayPayload = Schemas['OverlayPayload'];

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
  return request<GameState>('GET', `/state?oid=${encodeURIComponent(oid)}`);
}

export function getConfig(oid: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('GET', `/config?oid=${encodeURIComponent(oid)}`);
}

export function getCustomization(oid: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('GET', `/customization?oid=${encodeURIComponent(oid)}`);
}

// Game actions
export function addPoint(oid: string, team: Team, undo = false): Promise<ActionResponse> {
  return request<ActionResponse>(
    'POST',
    `/game/add-point?oid=${encodeURIComponent(oid)}`,
    { team, undo },
  );
}

export function addSet(oid: string, team: Team, undo = false): Promise<ActionResponse> {
  return request<ActionResponse>(
    'POST',
    `/game/add-set?oid=${encodeURIComponent(oid)}`,
    { team, undo },
  );
}

export function addTimeout(oid: string, team: Team, undo = false): Promise<ActionResponse> {
  return request<ActionResponse>(
    'POST',
    `/game/add-timeout?oid=${encodeURIComponent(oid)}`,
    { team, undo },
  );
}

export function changeServe(oid: string, team: Team): Promise<ActionResponse> {
  return request<ActionResponse>(
    'POST',
    `/game/change-serve?oid=${encodeURIComponent(oid)}`,
    { team },
  );
}

export function setScore(
  oid: string,
  team: Team,
  setNumber: number,
  value: number,
): Promise<ActionResponse> {
  return request<ActionResponse>(
    'POST',
    `/game/set-score?oid=${encodeURIComponent(oid)}`,
    { team, set_number: setNumber, value },
  );
}

export function setSets(oid: string, team: Team, value: number): Promise<ActionResponse> {
  return request<ActionResponse>(
    'POST',
    `/game/set-sets?oid=${encodeURIComponent(oid)}`,
    { team, value },
  );
}

export function undoLast(oid: string): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/game/undo?oid=${encodeURIComponent(oid)}`);
}

export function resetGame(oid: string): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/game/reset?oid=${encodeURIComponent(oid)}`);
}

export function startMatch(oid: string): Promise<ActionResponse> {
  return request<ActionResponse>('POST', `/game/start-match?oid=${encodeURIComponent(oid)}`);
}

// Display controls
export function setVisibility(oid: string, visible: boolean): Promise<ActionResponse> {
  return request<ActionResponse>(
    'POST',
    `/display/visibility?oid=${encodeURIComponent(oid)}`,
    { visible },
  );
}

export function setSimpleMode(oid: string, enabled: boolean): Promise<ActionResponse> {
  return request<ActionResponse>(
    'POST',
    `/display/simple-mode?oid=${encodeURIComponent(oid)}`,
    { enabled },
  );
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
  return request<ActionResponse>(
    'POST',
    `/session/rules?oid=${encodeURIComponent(oid)}`,
    payload,
  );
}

// Customization
export function updateCustomization(
  oid: string,
  data: Record<string, unknown>,
): Promise<ActionResponse> {
  return request<ActionResponse>('PUT', `/customization?oid=${encodeURIComponent(oid)}`, data);
}

// Predefined data
export function getTeams(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('GET', '/teams');
}

export function getThemes(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('GET', '/themes');
}

export function getLinks(oid: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('GET', `/links?oid=${encodeURIComponent(oid)}`);
}

export function getStyles(oid: string): Promise<string[]> {
  return request<string[]>('GET', `/styles?oid=${encodeURIComponent(oid)}`);
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
  return request<AuditResponse>(
    'GET',
    `/audit?oid=${encodeURIComponent(oid)}&limit=${limit}`,
    null,
    signal,
  );
}
