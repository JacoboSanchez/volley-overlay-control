/**
 * Board-scoped API surface: everything addressed by a board credential
 * (owner cookie + ``?oid=``, the shareable ``?c=`` control token, or the
 * ``?u=``/``?oid=`` public bookmark) — session lifecycle, scoring, display
 * toggles, match rules, customization, the team-group picker, links, styles
 * and the audit feed.
 *
 * Types are derived from the OpenAPI schema snapshot at
 * ``frontend/schema/openapi.json``. Run ``npm run gen:types`` after backend
 * schema changes to regenerate ``./schema.d.ts``.
 */

import type { components } from './schema';
import { getControlToken, getPublicUser, request, withOid } from './http';

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
export type InitRequest = Schemas['InitRequest'];
export type TeamState = Schemas['TeamState'];

export type InitOptions = Omit<InitRequest, 'oid'>;

function mutationHeaders(expectedRevision?: number): Record<string, string> | undefined {
  return typeof expectedRevision === 'number'
    ? { 'X-Expected-State-Revision': String(expectedRevision) }
    : undefined;
}

function mutate<T>(
  method: 'POST' | 'PUT',
  path: string,
  body: unknown,
  expectedRevision?: number,
): Promise<T> {
  return request<T>(method, path, body, undefined, mutationHeaders(expectedRevision));
}

// Session
export function initSession(oid: string, opts: InitOptions = {}): Promise<ActionResponse> {
  // Owner mode carries the oid in the body (+ cookie); a capability mode needs
  // the token or username+oid on the query so the server can resolve the board.
  const token = getControlToken();
  const user = getPublicUser();
  let q = '';
  if (token) q = `?c=${encodeURIComponent(token)}`;
  else if (user) {
    q = `?u=${encodeURIComponent(user)}&oid=${encodeURIComponent(oid)}`;
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
  expectedRevision?: number,
): Promise<ActionResponse> {
  const body: Record<string, unknown> = { team, undo };
  // Scouting tags are optional; only send them when set so an untyped
  // point posts the same minimal body as before.
  if (pointType) body.point_type = pointType;
  if (errorType) body.error_type = errorType;
  return mutate<ActionResponse>('POST', `/game/add-point${withOid(oid)}`, body, expectedRevision);
}

export function addSet(
  oid: string,
  team: Team,
  undo = false,
  expectedRevision?: number,
): Promise<ActionResponse> {
  return mutate<ActionResponse>(
    'POST',
    `/game/add-set${withOid(oid)}`,
    { team, undo },
    expectedRevision,
  );
}

export function addTimeout(
  oid: string,
  team: Team,
  undo = false,
  expectedRevision?: number,
): Promise<ActionResponse> {
  return mutate<ActionResponse>(
    'POST',
    `/game/add-timeout${withOid(oid)}`,
    { team, undo },
    expectedRevision,
  );
}

export function changeServe(
  oid: string,
  team: Team,
  expectedRevision?: number,
): Promise<ActionResponse> {
  return mutate<ActionResponse>(
    'POST',
    `/game/change-serve${withOid(oid)}`,
    { team },
    expectedRevision,
  );
}

export function setScore(
  oid: string,
  team: Team,
  setNumber: number,
  value: number,
  expectedRevision?: number,
): Promise<ActionResponse> {
  return mutate<ActionResponse>(
    'POST',
    `/game/set-score${withOid(oid)}`,
    {
      team,
      set_number: setNumber,
      value,
    },
    expectedRevision,
  );
}

export function setSets(
  oid: string,
  team: Team,
  value: number,
  expectedRevision?: number,
): Promise<ActionResponse> {
  return mutate<ActionResponse>(
    'POST',
    `/game/set-sets${withOid(oid)}`,
    { team, value },
    expectedRevision,
  );
}

export function undoLast(oid: string, expectedRevision?: number): Promise<ActionResponse> {
  return mutate<ActionResponse>('POST', `/game/undo${withOid(oid)}`, null, expectedRevision);
}

export function resetGame(oid: string, expectedRevision?: number): Promise<ActionResponse> {
  return mutate<ActionResponse>('POST', `/game/reset${withOid(oid)}`, null, expectedRevision);
}

export function startMatch(oid: string, expectedRevision?: number): Promise<ActionResponse> {
  return mutate<ActionResponse>('POST', `/game/start-match${withOid(oid)}`, null, expectedRevision);
}

// Display controls
export function setVisibility(
  oid: string,
  visible: boolean,
  expectedRevision?: number,
): Promise<ActionResponse> {
  return mutate<ActionResponse>(
    'POST',
    `/display/visibility${withOid(oid)}`,
    { visible },
    expectedRevision,
  );
}

export function setSimpleMode(
  oid: string,
  enabled: boolean,
  expectedRevision?: number,
): Promise<ActionResponse> {
  return mutate<ActionResponse>(
    'POST',
    `/display/simple-mode${withOid(oid)}`,
    { enabled },
    expectedRevision,
  );
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

export function setSwapSides(
  oid: string,
  swapped: boolean,
  expectedRevision?: number,
): Promise<ActionResponse> {
  return mutate<ActionResponse>(
    'POST',
    `/display/swap-sides${withOid(oid)}`,
    { swapped },
    expectedRevision,
  );
}

export function setAutoSwapSides(
  oid: string,
  enabled: boolean,
  expectedRevision?: number,
): Promise<ActionResponse> {
  return mutate<ActionResponse>(
    'POST',
    `/display/auto-swap-sides${withOid(oid)}`,
    { enabled },
    expectedRevision,
  );
}

export function setSetSummary(
  oid: string,
  enabled: boolean,
  expectedRevision?: number,
): Promise<ActionResponse> {
  return mutate<ActionResponse>(
    'POST',
    `/display/set-summary${withOid(oid)}`,
    { enabled },
    expectedRevision,
  );
}

export function setSetSummaryStyle(
  oid: string,
  style: SetSummaryStyle,
  expectedRevision?: number,
): Promise<ActionResponse> {
  return mutate<ActionResponse>(
    'POST',
    `/display/set-summary-style${withOid(oid)}`,
    { style },
    expectedRevision,
  );
}

export type MatchMode = 'indoor' | 'beach' | 'table_tennis';

export interface SetRulesPayload {
  mode?: MatchMode;
  points_limit?: number;
  points_limit_last_set?: number;
  sets_limit?: number;
  reset_to_defaults?: boolean;
}

export function setRules(
  oid: string,
  payload: SetRulesPayload,
  expectedRevision?: number,
): Promise<ActionResponse> {
  return mutate<ActionResponse>('POST', `/session/rules${withOid(oid)}`, payload, expectedRevision);
}

// Customization
export function updateCustomization(
  oid: string,
  data: Record<string, unknown>,
  expectedRevision?: number,
): Promise<ActionResponse> {
  return mutate<ActionResponse>('PUT', `/customization${withOid(oid)}`, data, expectedRevision);
}

// ---- Board team-group picker ----------------------------------------------
// Resolved against the overlay OWNER's universe via the board credential
// (control token / public bookmark / owner cookie) — so an operator running the
// match sees the owner's groups. `id === null` is the virtual "All" group.

export type BoardGroupKind = 'all' | 'shared' | 'private';

export interface BoardGroup {
  id: number | null;
  name: string;
  kind: BoardGroupKind;
  count: number;
}

export interface BoardGroupList {
  groups: BoardGroup[];
  selected_id: number | null;
}

export function getBoardGroups(oid: string): Promise<BoardGroupList> {
  return request<BoardGroupList>('GET', `/board/team-groups${withOid(oid)}`);
}

export function getBoardGroupTeams(
  oid: string,
  groupId: number | null,
): Promise<Record<string, unknown>> {
  const key = groupId === null ? 'all' : String(groupId);
  return request<Record<string, unknown>>('GET', `/board/team-groups/${key}/teams${withOid(oid)}`);
}

export function setBoardSelectedGroup(
  oid: string,
  groupId: number | null,
): Promise<{ ok: boolean; selected_id: number | null }> {
  return request('PUT', `/board/selected-group${withOid(oid)}`, { group_id: groupId });
}

// ---- Board links, styles and style capabilities ----------------------------

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

// ---- Audit log --------------------------------------------------------------

export interface AuditParams {
  team?: 1 | 2;
  undo?: boolean;
  [key: string]: unknown;
}

export interface AuditRecord {
  ts: number;
  action: string;
  params: AuditParams;
  result?: Record<string, unknown> | undefined;
}

export interface AuditResponse {
  oid: string;
  count: number;
  records: AuditRecord[];
  /** Mutation counter these records were read at. Compare against the
   *  ``version`` on ``audit_append`` / ``audit_invalidate`` WebSocket
   *  messages to tell an in-order push from a missed one. */
  version: number;
}

export function getAudit(
  oid: string,
  limit: number = 20,
  signal?: AbortSignal,
): Promise<AuditResponse> {
  return request<AuditResponse>('GET', `/audit${withOid(oid)}&limit=${limit}`, null, signal);
}
