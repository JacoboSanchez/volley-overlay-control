/**
 * Transport layer shared by every domain module in ``src/api``.
 *
 * Owns the one ``fetch`` call site, the error envelope, the paginated-listing
 * walk, and the board credential mode. Domain modules (``board``, ``auth``,
 * ``admin``, …) build their paths and hand them here; nothing outside this
 * file talks to ``fetch`` directly.
 */

import { clientHeaders } from './clientIdentity';

const BASE_URL = '/api/v1';

// Authentication is cookie-based now (HttpOnly session cookie). Requests are
// same-origin so the cookie is sent automatically; ``credentials: 'include'``
// makes that explicit and survives any future cross-origin dev setup.

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';

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
export function withOid(oid: string): string {
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
export function extractDetail(text: string): string {
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed.detail === 'string') return parsed.detail;
    if (parsed && Array.isArray(parsed.detail)) {
      const msgs = parsed.detail.map((d: { msg?: string }) => (d && d.msg) || '').filter(Boolean);
      if (msgs.length) return msgs.join('; ');
    }
  } catch {
    /* not JSON — fall through to the raw text */
  }
  return text;
}

export async function request<T = unknown>(
  method: HttpMethod,
  path: string,
  body: unknown = null,
  signal?: AbortSignal,
  extraHeaders?: Record<string, string>,
): Promise<T> {
  const opts: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...clientHeaders(),
      ...extraHeaders,
    },
    credentials: 'include',
  };
  if (body !== null) {
    opts.body = JSON.stringify(body);
  }
  if (signal) {
    opts.signal = signal;
  }
  return send<T>(method, path, opts);
}

/** Multipart variant of {@link request} for file uploads. No manual
 *  Content-Type: the browser must set the multipart boundary itself. */
export async function requestMultipart<T = unknown>(
  method: HttpMethod,
  path: string,
  form: FormData,
): Promise<T> {
  return send<T>(method, path, {
    method,
    body: form,
    credentials: 'include',
    headers: clientHeaders(),
  });
}

async function send<T>(method: HttpMethod, path: string, opts: RequestInit): Promise<T> {
  return (await sendWithResponse<T>(method, path, opts)).data;
}

async function sendWithResponse<T>(
  method: HttpMethod,
  path: string,
  opts: RequestInit,
): Promise<{ data: T; response: Response }> {
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
    // A 409 password_change_required means an admin reset this account's
    // password mid-session. Mirror the 401 handling so RequireAuth routes to
    // /change-password instead of surfacing a raw error on a stuck page.
    if (
      res.status === 409 &&
      !path.startsWith('/auth/') &&
      typeof window !== 'undefined' &&
      extractDetail(text) === 'password_change_required'
    ) {
      window.dispatchEvent(new CustomEvent('auth:password-change-required'));
    }
    throw new ApiError(
      res.status,
      `API ${method} ${path} failed (${res.status}): ${text}`,
      extractDetail(text),
    );
  }
  if (res.status === 204) return { data: undefined as T, response: res };
  return { data: (await res.json()) as T, response: res };
}

// ---- paginated listings -----------------------------------------------------
// The API caps any single list response (at LIST_DEFAULT_LIMIT) and reports the
// full in-scope size in X-Total-Count. A one-shot GET would therefore silently
// hide every row past the first page, so these helpers walk the pages until the
// client holds the whole listing — the SPA's own screens (overlays, team
// catalog, groups, icons, presets, admin users) all expect the complete set.

function pagedPath(path: string, offset: number): string {
  const sep = path.includes('?') ? '&' : '?';
  // Deliberately no `limit`: the ceiling is operator-configurable
  // (LIST_MAX_LIMIT), so any value hard-coded here could exceed it and make
  // every listing 422. Omitting it lets the server apply its own default,
  // which is always within its own bound.
  return `${path}${sep}offset=${offset}`;
}

export async function getPage<B>(
  path: string,
  offset: number,
): Promise<{ body: B; total: number }> {
  const { data, response } = await sendWithResponse<B>('GET', pagedPath(path, offset), {
    method: 'GET',
    headers: { 'Content-Type': 'application/json', ...clientHeaders() },
    credentials: 'include',
  });
  const header = response.headers?.get('X-Total-Count');
  const raw = header === null || header === undefined ? NaN : Number(header);
  // A missing/garbled header (an older server, or a stubbed Response) means
  // "no paging information" — treat the single page as the whole listing
  // rather than looping forever.
  return { body: data, total: Number.isFinite(raw) && raw >= 0 ? raw : -1 };
}

/** GET every page of a listing and concatenate the rows.
 *
 *  `extract` pulls the row array out of one page's body, which is either the
 *  array itself or an envelope such as `{ items: [...] }`.
 *
 *  The walk advances by however many rows the server actually returned, so it
 *  works with whatever page size the deployment is configured for.
 */
export async function getAllPages<B, R>(path: string, extract: (body: B) => R[]): Promise<R[]> {
  const rows: R[] = [];
  for (let offset = 0; ;) {
    const { body, total } = await getPage<B>(path, offset);
    const page = extract(body);
    // A body that isn't the expected array (an error envelope, a shape change)
    // ends the walk with whatever we have, rather than throwing an opaque
    // "spread requires an iterable" from the push below.
    if (!Array.isArray(page)) return rows;
    rows.push(...page);
    offset += page.length;
    // Stop on: no paging info, an empty page (the listing ended, and also the
    // only way `offset` could stop advancing), or having collected everything
    // the server says exists.
    if (total < 0 || page.length === 0 || rows.length >= total) return rows;
  }
}
