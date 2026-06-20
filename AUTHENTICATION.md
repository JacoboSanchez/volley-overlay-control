# Authentication Coverage Audit

> ℹ️ **Rewritten for the multi-user refactor.** The app moved from a
> single-tenant Bearer/admin-password posture to **multi-user cookie
> sessions with roles** (`app/auth/`). The scoreboard API, control
> WebSocket, and account self-service are gated by a **logged-in user via
> an HttpOnly `vsession` cookie**, and every session is addressed by the
> per-user storage key `"<user_id>:<oid>"`, so a user can only ever reach
> their own scoreboards. The public OBS surface
> (`/overlay/{token}`, `/follow/{token}`, `/ws/{token}`) is addressed by an
> unguessable per-overlay `public_token` and carries no credential. The
> `OVERLAY_SERVER_TOKEN` machine-to-machine layer (§5 below) is unchanged
> and remains a Bearer ladder. The legacy `SCOREBOARD_USERS` Bearer ladder,
> the `OVERLAY_MANAGER_PASSWORD` admin Bearer + `/manage`, `check_oid_access`
> / `STRICT_OID_ACCESS`, and the match-report `?token=<password>` flow were
> all **removed in the multi-user refactor**; they are noted here only where
> a reader might expect them.

Last audited: 2026-06-19 (multi-user cookie-session refactor).

This document is the single source of truth for **which routes are
protected, which are intentionally public, and where the gaps are**. It
complements `README.md` (user-facing env var setup) and
`DEVELOPER_GUIDE.md` (code organisation) with a route-by-route inventory.

## 1. Auth mechanisms in use

The codebase now has **two distinct kinds of auth**: a cookie-session
layer for human users (the scoreboard, the SPA, and account
self-service), and a machine-to-machine Bearer layer for the overlay
server. They are independent and gate different surfaces.

| Layer | Credential | How it's enforced | Where |
| :--- | :--- | :--- | :--- |
| User session dependencies (`current_user` → `require_user` → `require_admin`) | HttpOnly `vsession` cookie → `auth_sessions` row | Per-route `Depends(require_user)` / `Depends(require_admin)`. `401` when anonymous, `409 PASSWORD_CHANGE_REQUIRED` when a forced password change is pending, `403` when an admin-only route is hit by a non-admin. | `app/auth/dependencies.py` |
| `verify_api_key` alias | (same cookie session) | Kept as a name on the many `dependencies=[Depends(verify_api_key)]` call sites; it is now simply an alias for `require_user`. | `app/api/dependencies.py` |
| `require_overlay_server_token` dependency | `OVERLAY_SERVER_TOKEN` or `OVERLAY_SERVER_TOKEN_HASH` | Per-route `Depends(require_overlay_server_token)`. Auto-populated by the security bootstrap when neither is set (unless `OVERLAY_SERVER_TOKEN_DISABLED=true`). When set: `401` without `Authorization: Bearer`, `403` with a mismatched token. | `app/overlay/auth.py` |

Passwords and the overlay-server token are stored hashed: user passwords
as scrypt records in the `users` table, the overlay-server token via the
preferred `OVERLAY_SERVER_TOKEN_HASH` scrypt record (see §8). The session
cookie value is itself stored hashed — only the SHA-256 of the opaque
token is persisted (§2.1). The cleartext credential never has to sit in
`.env`.

The user-session 401s carry `WWW-Authenticate: Cookie`; the
overlay-server 401 carries `WWW-Authenticate: Bearer
realm="overlay-server"` per RFC 7235 §4.1. The realm hint lets operators
tell from access logs which layer rejected a request — the only Bearer
ladder left is the overlay-server one.

### 1.1 Sessions, roles, and the forced-password-change gate

A session is an opaque `secrets.token_urlsafe(32)` value carried in the
`vsession` cookie (`SameSite=Lax`, `HttpOnly`, `Path=/`; `Secure`
auto-set over HTTPS, forceable via `SESSION_COOKIE_SECURE`). Only its
SHA-256 (`token_hash`) is stored, alongside `user_id`, `expires_at`, and
`last_seen_at` in `auth_sessions`. Storing server-side is what makes
logout, admin password-reset, and "log out everywhere on password change"
possible — a stateless signed cookie could not be revoked without a
denylist table. TTL is `SESSION_TTL_HOURS` (default `336` = 14 days).

Roles are `user` and `admin`. The dependency chain in
`app/auth/dependencies.py`:

* `current_user` — resolves the cookie session to a `User`, or `None`.
* `current_user_or_401` — same, but `401` when anonymous; does **not**
  enforce the password-change gate, so change-password / logout / context
  stay reachable mid-rotation.
* `require_user` — `current_user_or_401` plus `409 PASSWORD_CHANGE_REQUIRED`
  when the account still owes a forced password change.
* `require_admin` — `require_user` plus `403` unless the role is admin.

Admin-created users and admin password resets set `must_change_password`;
`require_user` returns `409` until the user changes it (only
change-password, logout, and the context endpoints are exempt). The
**admin role + the SPA `/admin` page** replace the old `/manage` admin
console; there is no separate admin password.

## 2. Route inventory

Legend: `Y` = requires a logged-in user (cookie session); `A` = requires
an admin session; `OID` = additionally scoped to the caller's per-user
session key `"<user_id>:<oid>"`; `—` = always public (capability URL or
intentionally open).

### 2.1 Cookie sessions — the `vsession` cookie

Every `Y`/`A`/`OID` route below is gated by the `vsession` HttpOnly
cookie, not a Bearer token. The cookie value is an opaque
`secrets.token_urlsafe(32)` minted by `app/auth/sessions.py`; the
`auth_sessions` table stores only its SHA-256 (`token_hash`), with
`user_id`, `expires_at`, and `last_seen_at`. `resolve_session` validates
hash → row → expiry → account-active and throttles the `last_seen_at`
write (at most once every 5 minutes) so authenticated reads don't turn
into a DB write per request. Cookie flags: `SameSite=Lax`, `HttpOnly`,
`Path=/`, and `Secure` (auto over HTTPS, forceable via
`SESSION_COOKIE_SECURE`). TTL = `SESSION_TTL_HOURS` (default 14 days).

### 2.2 Auth & account self-service — `auth_router` (`app/auth/routes.py`)

Prefix `/api/v1/auth`.

| Method | Path | Auth | Notes |
| :--- | :--- | :--- | :--- |
| `GET` | `/context` | — | Public boot payload: `{authenticated, user, registration_open, needs_admin_bootstrap}`. The SPA uses it to decide where to route. |
| `GET` | `/me` | Y (no change-pw gate) | `current_user_or_401`. |
| `POST` | `/register` | — | `403` unless registration is open (see §1.1 / §5). Starts a session on success. |
| `POST` | `/login` | — | `401` on bad credentials; returns `{user, must_change_password}` and sets the cookie. |
| `POST` | `/logout` | — | Revokes the current session row and clears the cookie. |
| `POST` | `/change-password` | Y (no change-pw gate) | Verifies the current password, sets the new one, clears `must_change_password`, and revokes every **other** session for the user. |
| `PATCH` | `/me` | Y | Update display name / email. |
| `DELETE` | `/me` | Y | Self-delete; clears the cookie. |
| `POST` | `/claim-admin` | one-time token | First-admin bootstrap (§9). `410 Gone` once any admin exists. |

### 2.3 Scoreboard REST API — `api_router` (`app/api/routes/*`)

Prefix `/api/v1`. Every route below has `Depends(verify_api_key)`, which
is now an alias for `require_user`; the ones that take an `oid` resolve
their `GameSession` via `get_session`, which builds the key
`make_skey(user.id, oid)` — so passing another user's `oid` simply
resolves to a different key with no session (404), never another user's
data. There is no second-level `check_oid_access`: isolation is
structural in the session key.

| Method | Path | Auth | Notes |
| :--- | :--- | :--- | :--- |
| `POST` | `/session/init` | Y + OID | Creates the caller's `"<user_id>:<oid>"` session. |
| `GET` | `/state` | Y + OID | Via `get_session`. |
| `GET` | `/customization` | Y + OID | |
| `GET` | `/config` | Y + OID | |
| `POST` | `/game/add-point` | Y + OID | |
| `POST` | `/game/add-set` | Y + OID | |
| `POST` | `/game/add-timeout` | Y + OID | |
| `POST` | `/game/change-serve` | Y + OID | |
| `POST` | `/game/set-score` | Y + OID | |
| `POST` | `/game/set-sets` | Y + OID | |
| `POST` | `/game/reset` | Y + OID | |
| `POST` | `/display/visibility` | Y + OID | |
| `POST` | `/display/simple-mode` | Y + OID | |
| `PUT` | `/customization` | Y + OID | |
| `GET` | `/overlays` | Y | Scoped to the caller's overlays. |
| `GET` | `/teams` | Y | |
| `GET` | `/links` | Y + OID | |
| `GET` | `/styles` | Y + OID | |
| `GET` | `/matches/{id}` | Y | Owner-only (`404` otherwise). |
| `DELETE` | `/matches/{id}` | Y | Owner-only delete (§8 / §7.1). |
| `POST` | `/matches/{id}/sign-url` | Y | Owner mints an HMAC capability URL for the gated match report. Body: `{"ttl_seconds": int}`. Response embeds `?exp=&sig=` — never a credential. Key is `SESSION_SECRET`. |
| `WS` | `/ws` | Y + OID | Authenticated by the same `vsession` cookie — browsers send cookies on same-origin WS upgrades, so no subprotocol/query-param token is needed. Resolves to `make_skey(user.id, oid)`; closes `4003` when anonymous, `4004` when no session exists. |

### 2.4 Admin user management — `app/api/routes/admin_users.py`

Prefix `/api/v1/admin`. Every route is `Depends(require_admin)`. The
admin role + the SPA `/admin` page replace the old `/manage` console.

| Method | Path | Auth | Notes |
| :--- | :--- | :--- | :--- |
| `GET` | `/users` | A | List users. |
| `POST` | `/users` | A | Create a user. With no password supplied, mints a temp password (returned once) and forces a first-login change. |
| `PATCH` | `/users/{id}` | A | Update profile / role / active flag. Guards against demoting or deactivating the **last active admin**. |
| `POST` | `/users/{id}/reset-password` | A | Reset to a temp password (forced change) and revoke all of that user's sessions. |
| `DELETE` | `/users/{id}` | A | Delete; refuses the last active admin. |
| `GET` | `/registration` | A | Read the open-registration toggle. |
| `PUT` | `/registration` | A | Flip the open-registration toggle (DB flag). |
| `POST` | `/webhooks/replay` | A | Re-deliver dead-lettered webhook records (counts only; bodies never echoed). |

### 2.5 Overlay server — `overlay_router` (`app/overlay/routes.py`)

This router powers the **in-process custom overlay server**
(`LocalOverlayBackend`) and is mounted when
`_register_overlay_routes()` finds the `overlay_templates/` directory.
It is **also consumed by `CustomOverlayBackend` when a remote app
instance points at this server** (`APP_CUSTOM_OVERLAY_URL=…`).

| Method | Path | Auth | Classification |
| :--- | :--- | :--- | :--- |
| `GET` | `/favicon.ico` | — | Public OK |
| `GET` | `/overlay/{public_token}` | — | Public for OBS browser sources. Addressed by the unguessable per-overlay `public_token` (a capability URL); carries no credential. |
| `GET` | `/follow/{public_token}` | — | Public spectator/follow page; same `public_token` capability URL, same `/ws/{public_token}` feed. |
| `WS` | `/ws/{public_token}` | — | Public for OBS browser sources. Same `public_token` capability URL. |
| `POST` | `/api/state/{overlay_id}` | `require_overlay_server_token` | Mutation endpoint (F-3 fix). |
| `GET`,`POST` | `/create/overlay/{overlay_id}` | `require_overlay_server_token` | Mutation endpoint (F-3 fix). |
| `GET`,`POST`,`DELETE` | `/delete/overlay/{overlay_id}` | `require_overlay_server_token` | Mutation endpoint (F-3 fix). |
| `GET` | `/api/raw_config/{overlay_id}` | `require_overlay_server_token` | Leak endpoint (F-5 fix). |
| `POST` | `/api/raw_config/{overlay_id}` | `require_overlay_server_token` | Mutation endpoint (F-3 fix). |
| `GET` | `/api/config/{overlay_id}` | `require_overlay_server_token` | Leak endpoint (F-5 fix). |
| `GET` | `/api/themes` | — | Public OK (theme name list is not sensitive). |
| `POST` | `/api/theme/{overlay_id}/{theme_name}` | `require_overlay_server_token` | Mutation endpoint (F-3 fix). |

> **Removed in the multi-user refactor:** `GET /list/overlay` no longer
> exists. It used to enumerate every overlay id plus its output key behind
> the admin password; with public output addressed by an unguessable
> per-overlay `public_token` there is no id-enumeration endpoint to gate.
> The old F-4 finding is therefore moot (§3).

> **Note on `require_overlay_server_token`:** when `OVERLAY_SERVER_TOKEN`
> is unset the dependency is a no-op (logged at startup). Existing
> deployments keep working unchanged; setting the env var opts in to
> enforcement. See F-3 below.

> **Note on `{overlay_id}` format:** every path parameter marked
> `{overlay_id}` / `{id}` above is validated against the strict allow-list
> regex enforced by `OverlayStateStore._sanitize_id`:
>
> ```
> ^(?!\.{1,2}$)[A-Za-z0-9._-]{1,64}$
> ```
>
> Requests carrying path-separator characters (`/`, `\`), traversal
> segments (`.`, `..`), NUL, whitespace, or non-ASCII are rejected at
> the store boundary — `create_overlay` / `delete_overlay` return
> `False`, `overlay_exists` returns `False`, and read/write helpers
> raise `ValueError`. This complements `require_overlay_server_token`:
> auth gates *who* may call the endpoints, the sanitizer gates *what*
> ids those calls may name.

### 2.6 Static mounts and system endpoints — `app/bootstrap.py`

| Method | Path | Auth | Notes |
| :--- | :--- | :--- | :--- |
| `GET` | `/fonts/**` | — | Static assets |
| `GET` | `/static/**` | — | Overlay static assets |
| `GET` | `/pwa/**` | — | PWA manifest/icons |
| `GET` | `/assets/**` | — | SPA build output |
| `GET` | `/sw.js` | — | PWA service worker |
| `GET` | `/manifest.webmanifest` | — | PWA manifest |
| `GET` | `/manifest.json` | — | PWA manifest |
| `GET` | `/health` | — | Health check |
| `GET` | `/**` (SPA fallback) | — | Serves `index.html` for unknown paths |

All of these are intentionally public. If a future change needs to gate
static assets (e.g. hiding the SPA behind a login wall), add a custom
`BaseHTTPMiddleware` at that point — there is no longer a pre-wired hook.

## 3. Findings

The five findings from the original audit are carried forward below.
Three (F-1, F-3, F-5) describe the still-current machine-auth posture;
two (F-2, F-4) were rendered moot by the multi-user refactor's move to
per-overlay `public_token` capability URLs.

### F-1 — Dead `AuthMiddleware` (low) — **fixed**

`AuthMiddleware.dispatch` was a pass-through that served no purpose;
the real auth lives in per-route dependencies. The class and its
registration in `_register_auth()` have been removed. The user-session
layer is likewise per-route (`require_user` / `require_admin`), not a
catch-all middleware. If future cross-cutting auth is needed (e.g.
gating static assets behind a login wall), add a dedicated middleware at
that time.

### F-2 — Overlay capability URL was weakened by `resolve_overlay_id` (medium) — **moot after the refactor**

The original finding wrestled with whether `/overlay/{…}` and `/ws/{…}`
should accept the raw overlay id or only the SHA-256 output key. The
multi-user refactor settles it: the public OBS surface is now addressed
solely by an **unguessable per-overlay `public_token`**
(`/overlay/{public_token}`, `/follow/{public_token}`,
`/ws/{public_token}`). There is no raw-id entrypoint to leak, so the
capability-URL property holds by construction. The overlay content
itself remains intentionally public for OBS browser sources.

### F-3 — Unauthenticated mutation endpoints on the overlay router (high) — **fixed**

The overlay router used to expose seven mutation endpoints without any
auth. These are now gated by the new
`require_overlay_server_token` dependency:

- `POST /api/state/{id}`
- `GET`/`POST /create/overlay/{id}`
- `GET`/`POST`/`DELETE /delete/overlay/{id}`
- `POST /api/raw_config/{id}`
- `POST /api/theme/{id}/{name}`

The dependency resolves its credential hash-first
(`OVERLAY_SERVER_TOKEN_HASH`, else `OVERLAY_SERVER_TOKEN`):

- **Credential present** (the default — the security bootstrap
  auto-mints and persists `OVERLAY_SERVER_TOKEN` on first run, §5) →
  requests must include `Authorization: Bearer <token>`, otherwise
  `401` (missing) / `403` (mismatch).
- **`OVERLAY_SERVER_TOKEN_DISABLED=true`** → the dependency fails open
  (no-op) and logs a warning. This is the only way back to the legacy
  unauthenticated behaviour and is safe only on a trusted LAN.

`CustomOverlayBackend` forwards the same token so control-app
deployments pointed at an external overlay server
(`APP_CUSTOM_OVERLAY_URL`) can set `OVERLAY_SERVER_TOKEN` on both sides
and enforce.

### F-4 — `/list/overlay` leaks all overlay IDs and output keys (high) — **moot after the refactor**

The route was **removed in the multi-user refactor**. Public output is
addressed by an unguessable per-overlay `public_token`, so there is no
id-enumeration endpoint left to leak, and the old admin-password gate it
relied on (`OVERLAY_MANAGER_PASSWORD`) no longer exists. Nothing replaces
it: enumerating overlays is a per-user, session-scoped concern handled by
`GET /api/v1/overlays` (§2.3), which only returns the caller's own.

### F-5 — Read endpoints leak config (medium) — **fixed**

`GET /api/raw_config/{id}` and `GET /api/config/{id}` require the
overlay-server token (same dependency as F-3). The `outputUrl` /
`outputKey` pair returned by `/api/config/{id}` is not readable by
unauthenticated callers. This is overlay-server machine auth and is
unaffected by the move to user cookie sessions.

## 4. Tripwire tests

`tests/test_auth_coverage.py` pins the auth behavior of every sensitive
route so that future changes to coverage cannot slip in silently. The
matrix covers:

- Scoreboard REST API — `401` without a `vsession` cookie; with a logged-in
  user, a session is reachable only under the caller's own
  `"<user_id>:<oid>"` key (another user's `oid` resolves to a 404, not
  another user's data).
- The forced-password-change gate — `409 PASSWORD_CHANGE_REQUIRED` on
  `require_user` routes while `must_change_password` is set, with the
  change-password / logout / context endpoints staying reachable.
- Admin user-management API (`require_admin`) — `403` for non-admins,
  plus the last-active-admin guards on role/active/delete.
- Overlay server mutation + read endpoints — `401`/`403` without the
  correct Bearer token; the fail-open path verified only when
  `OVERLAY_SERVER_TOKEN_DISABLED=true`.

When adding a new route, add a matching entry in this test file.

## 5. Release notes

Deployment-visible changes operators should be aware of:

1. **`OVERLAY_SERVER_TOKEN` is auto-generated.** When the env var
   is unset on first start, the bootstrap mints a random token,
   persists it to `data/.overlay_server_token` (mode `0o600`), and
   exposes it via `os.environ` so the rest of the app picks it up
   transparently. Subsequent restarts read the same file, so the
   token stays stable. Operators pairing this app with an external
   overlay server (`APP_CUSTOM_OVERLAY_URL`) must either set
   `OVERLAY_SERVER_TOKEN` explicitly on both sides, or read the
   generated value from the persisted file. Set
   `OVERLAY_SERVER_TOKEN_DISABLED=true` to opt back into the legacy
   unauthenticated behaviour (only safe on a trusted LAN); the
   bootstrap logs a warning when this opt-out is active.
2. **First start prints a one-time admin-bootstrap token.** With no
   admin account yet, startup logs an `ADMIN BOOTSTRAP TOKEN` at
   `WARNING` (visible in `docker logs`) and persists it to
   `data/.admin_bootstrap_token` (mode `0o600`). Claim the first admin
   by POSTing it to `/api/v1/auth/claim-admin` (SPA route
   `/claim-admin`); see §9. Set `ADMIN_BOOTSTRAP_TOKEN` to pin it.
3. **`SESSION_SECRET` is auto-minted if unset.** It hardens sessions and
   is the HMAC key for signed match-report share URLs. On first boot,
   if unset, the bootstrap mints `secrets.token_urlsafe(...)` and
   persists it to `data/.session_secret` (mode `0o600`) — mirroring the
   overlay-server-token bootstrap. Pin it explicitly
   (`SESSION_SECRET=…`) across multiple replicas, or each replica will
   reject the others' sessions and signed URLs.
4. **Registration is closed unless opened.** `REGISTRATION_OPEN` only
   seeds the initial value; after first boot the DB flag wins and admins
   toggle it via `PUT /api/v1/admin/registration`. While closed,
   `POST /api/v1/auth/register` returns `403` and admins create accounts
   directly (§2.4).

## 6. Defence-in-depth middleware

Two middlewares wrap every request and complement the per-route auth
ladder above. Both are wired in `app/bootstrap.py:create_app` so
operators don't need to opt in.

### 6.1 `AuthRateLimitMiddleware` — brute-force backstop

Located in `app/api/middleware/auth_rate_limit.py`. Watches the
`/api/v1/` prefix (the `/auth/login` and `/auth/claim-admin`
endpoints are the meaningful targets now; a stale `/manage` prefix is
also still listed but matches no live route); when a response carries a
401 or 403 status, the caller's IP is recorded in a sliding-window
counter. Once the bucket exceeds the configured threshold the next
request from that IP is short-circuited with `429 Too Many
Requests` and a `Retry-After` header before reaching the handler.
The bucket is reset only by the sliding window — non-failure
responses are intentionally ignored so an attacker cannot launder
failures by interleaving login attempts (`POST /api/v1/auth/login`)
with hits to a public endpoint under the same prefix (e.g.
`GET /api/v1/auth/context`).

The caller IP is sourced exclusively from `scope["client"]` —
client-supplied `X-Forwarded-For` headers are ignored to defeat
spoofing. **Operators behind a reverse proxy must configure
uvicorn with `--proxy-headers` and `--forwarded-allow-ips=<proxy
IP>`** so the ASGI scope reflects the real remote IP rather than
the proxy hop. Without that, every caller behind the proxy
collapses into a single bucket and a single attacker can lock out
all legitimate users.

| Env var | Default | Meaning |
| :--- | :--- | :--- |
| `AUTH_RATE_LIMIT_MAX_FAILURES` | `10` | 401/403 responses per window before blocking |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | `60` | sliding-window length |
| `AUTH_RATE_LIMIT_BLOCK_SECONDS` | `60` | how long the IP stays blocked once the threshold trips |

State is process-local. Multi-replica deployments should still front
the app with a layer-7 limiter (Cloudflare, Nginx, etc.) — this
middleware is the single-replica self-hosted backstop.

### 6.2 `TrustedHostMiddleware` — Host-header poisoning defence (opt-in)

Wired in `app/bootstrap.py:_maybe_register_trusted_hosts`. When
`TRUSTED_HOSTS` is unset the middleware is not installed (default,
backwards compatible). When set to a comma-separated list of
hostnames, Starlette's `TrustedHostMiddleware` rejects requests
whose `Host` header doesn't match any entry with HTTP 400 before
any handler reads `request.base_url` (used by `/links`,
`/api/config/{id}`, the match-report signed-URL minter, etc.).
Wildcard subdomains are honoured (`*.example.com` matches any
subdomain).

| Env var | Default | Meaning |
| :--- | :--- | :--- |
| `TRUSTED_HOSTS` | unset | Comma-separated allow-list. Whitespace around entries is stripped. |

Operators behind a reverse proxy must also configure uvicorn with
`--proxy-headers` so the ASGI scope reflects the real `Host`.
Enforcement is global — the overlay routes
(`/overlay/{public_token}`, `/ws/{public_token}`) are subject to the
same allow-list because the `Host` check fires before route dispatch.
If OBS browser sources on a different domain need to load an overlay,
add that domain (or a wildcard parent) to `TRUSTED_HOSTS`; do not try
to special-case the overlay router downstream of the middleware.

### 6.3 `CORSMiddleware` — cross-origin SPA scaffolding (opt-in)

Wired in `app/bootstrap.py:_maybe_register_cors`. When
`CORS_ALLOWED_ORIGINS` is unset the middleware is not installed
(default, backwards compatible — the bundled SPA is served by
FastAPI itself, no cross-origin requests). When set to a
comma-separated list of origins, browser preflight responses get
explicit allow-list semantics:

* `Access-Control-Allow-Origin` is echoed only for listed origins.
* `Access-Control-Allow-Credentials: true` — load-bearing now that
  the SPA authenticates with the `vsession` cookie: the browser only
  sends the cookie cross-origin (and the response is readable) when
  credentials are explicitly allowed.
* `Access-Control-Allow-Headers` includes `Authorization`,
  `Content-Type`, `X-Request-ID`, and `Sec-WebSocket-Protocol`. The
  cookie itself needs no allow-listed header, but `Authorization`
  remains allowed for the overlay-server Bearer flows and
  `Content-Type` / `X-Request-ID` for ordinary JSON requests.

| Env var | Default | Meaning |
| :--- | :--- | :--- |
| `CORS_ALLOWED_ORIGINS` | unset | Comma-separated allow-list of origins. `*` is **rejected** to prevent a copy-paste footgun on a credentialed API; an `ERROR` is logged and CORS stays disabled. |

### 6.4 `SecurityHeadersMiddleware` — HTTP response hardening

Located in `app/api/middleware/security_headers.py`. Adds:

* `X-Content-Type-Options: nosniff` and `Referrer-Policy:
  strict-origin-when-cross-origin` and a `Permissions-Policy` that
  denies geolocation/microphone/camera/payment/usb on every response.
* `Content-Security-Policy` (locked to `'self'` plus
  `'unsafe-inline'`/`'unsafe-eval'` to keep the existing inline
  match-report and SPA scripts working) and `X-Frame-Options:
  SAMEORIGIN` on HTML responses. The `/overlay/*` routes get
  `frame-ancestors *` instead so OBS browser sources can still embed
  them off-origin.
* `Cache-Control: no-store` on `/api/v1/` responses that don't
  already set a `Cache-Control` header — keeps authenticated JSON
  out of intermediary caches.

Operators can override individual headers via env vars:
`SECURITY_CSP`, `SECURITY_REFERRER_POLICY`,
`SECURITY_PERMISSIONS_POLICY`, and `SECURITY_HSTS_SECONDS`
(opt-in HSTS, off by default so non-HTTPS deployments are not
locked out). Existing handler-level `Cache-Control` headers are
always preserved.

## 7. Credential transport patterns

This section documents how access travels on the wire. The
multi-user refactor moved both the match report and the control
WebSocket off the URL line entirely: nothing in either flow puts a
credential in a request line, query string, or proxy access log.

### 7.1 Match report — three ways in, no credential on the wire

Access to ``/match/{match_id}/report`` is resolved by
``app/match_report_access.py`` in this order:

1. **Owner session cookie.** The report's owner, authenticated by the
   ``vsession`` cookie, can always read their own report. Ownership is
   the `user_id` embedded in the stored match's ``oid`` skey.
2. **HMAC capability URL.** The owner mints one via
   ``POST /api/v1/matches/{match_id}/sign-url`` (owner-only,
   ``require_user``). The response carries
   ``/match/{id}/report?exp=<unix_seconds>&sig=<hmac_hex>``. The
   signing key is ``SESSION_SECRET``, so:
   * Anyone who holds the URL can read the report until ``exp`` passes.
   * No credential — neither the cookie nor ``SESSION_SECRET`` — ever
     leaves the server; only an opaque, TTL-bounded signature does.
   * Rotating ``SESSION_SECRET`` invalidates every outstanding signed
     URL — the desired behaviour after a suspected leak.
3. **Public mode.** ``MATCH_REPORT_PUBLIC=true`` opens the report to
   anyone who holds the non-guessable ``match_id``.

Otherwise the route returns ``401`` (``WWW-Authenticate: Cookie``).
Deleting a match is owner-only (``DELETE /api/v1/matches/{id}``).

> **Removed in the multi-user refactor:** the legacy
> ``/match/{id}/report?token=$OVERLAY_MANAGER_PASSWORD`` flow — which
> leaked the admin password into URLs, bookmarks, and ``Referer``
> headers — is gone, along with the admin-password signing key. The
> three paths above replace it.

### 7.2 ``/api/v1/ws``: cookie-authenticated upgrade

Browsers send cookies on **same-origin** WebSocket upgrades, so the
control socket simply reuses the ``vsession`` cookie — no subprotocol
token, no ``?token=`` query parameter, nothing on the request line.
``_resolve_skey`` resolves the cookie to the caller's
``make_skey(user.id, oid)`` and the socket only ever streams a session
that key owns. The server closes with ``4003`` when the cookie is
missing/invalid and ``4004`` when no session exists for ``(user, oid)``.

> **Removed in the multi-user refactor:** the old
> ``Sec-WebSocket-Protocol: bearer, <token>`` / ``Authorization:
> Bearer`` / ``?token=`` ladder is gone — the same-origin cookie makes
> it unnecessary.

## 8. Hashed credentials at rest

Two kinds of secret are stored hashed, both via `app/password_hash.py`
(`hashlib.scrypt`, stdlib-only, no new dependency):

* **User passwords** live as scrypt records in the `users` table — the
  cleartext is never persisted. `app/auth/passwords.py` is a thin
  re-export of `hash_password` / `verify_password` so the auth package
  has a single import surface.
* **The overlay-server token** can be supplied as a scrypt record via
  the preferred `OVERLAY_SERVER_TOKEN_HASH`, so a hash-only deployment
  keeps zero cleartext on the server side.

Separately, the **session cookie** value is stored hashed too — only the
SHA-256 of the opaque token reaches the DB (§2.1) — and `SESSION_SECRET`
hardens sessions and signs match-report share URLs.

### 8.1 Hash format

Hashes are produced by `app/password_hash.py` using
`hashlib.scrypt`. The wire format is::

    scrypt$n=16384,r=8,p=1$<salt-hex>$<hash-hex>

* `n`, `r`, `p` are the standard scrypt parameters; the verifier
  reads them from the record so existing hashes keep working when
  the defaults change.
* `salt` is 16 random bytes, lowercase hex (32 chars).
* `hash` is the 32-byte derived key, lowercase hex (64 chars).

Mint a hash via the CLI helper::

    python -m app.password_hash                    # interactive (no echo)
    echo -n 'mypw' | python -m app.password_hash --stdin
    python -m app.password_hash --stdin --n 32768  # heavier hash

### 8.2 Per-surface configuration

| Credential | Where stored | Cleartext source | Hash form |
| :--- | :--- | :--- | :--- |
| User password | `users.password_hash` (scrypt record) | never persisted | always hashed |
| Overlay server token | env / `data/.overlay_server_token` | `OVERLAY_SERVER_TOKEN` | `OVERLAY_SERVER_TOKEN_HASH` (preferred) |
| Session cookie value | `auth_sessions.token_hash` (SHA-256) | the `vsession` cookie | always hashed |

For the overlay-server token, when both forms are configured the hash
wins. This matters for the migration path: an operator who has minted a
hash but hasn't yet deleted the plaintext is already authenticating
against the new value, otherwise the old token keeps working until both
are rotated.

### 8.3 Verification cost

`hashlib.scrypt` at the default parameters costs ~50 ms per check, so the
design keeps password verification off the hot path. A scrypt verify
happens only at **`POST /api/v1/auth/login`** (and change-password /
claim-admin); thereafter every request authenticates by the cookie's
SHA-256 lookup (`resolve_session`), which is a single indexed query, not
a scrypt call. Revocation is immediate and server-side: logout deletes
the row, an admin password reset revokes all of a user's sessions, and
change-password revokes every session except the caller's — so there is
no cache window in which a removed credential keeps working.

### 8.4 Auto-generation interaction

`security_bootstrap.ensure_overlay_server_token` auto-generates
`OVERLAY_SERVER_TOKEN` and persists it to `data/.overlay_server_token`
on first start. When `OVERLAY_SERVER_TOKEN_HASH` is set, the
bootstrap skips that step — a hash-only deployment intentionally
keeps zero cleartext on the server side. The peer
(`CustomOverlayBackend`) still reads the cleartext token from its
own configuration, so the hash-only model splits trust cleanly:
this server stores only a hash, the peer stores only the cleartext.

## 9. First-admin bootstrap

`app/auth/bootstrap.py` solves the chicken-and-egg of creating the first
admin with no admin to create it — modelled on the overlay-server-token
bootstrap.

On first start with **no admin user**, `ensure_admin_bootstrap` mints a
one-time token (`secrets.token_urlsafe(32)`, unless `ADMIN_BOOTSTRAP_TOKEN`
is set), logs it at `WARNING` (so it shows up in `docker logs`), and
persists it to `data/.admin_bootstrap_token` (mode `0o600`). The operator
claims the first admin with:

    POST /api/v1/auth/claim-admin {token, username, password}

`claim_first_admin` compares the token with `secrets.compare_digest`,
and only while **no admin exists**: on success it creates the admin
account (with `must_change_password=False`), deletes the token file, and
records `admin_bootstrap_claimed`. Any later claim returns `410 Gone`.
The SPA exposes this at the `/claim-admin` route; `GET
/api/v1/auth/context` advertises `needs_admin_bootstrap` so the SPA can
send the operator there.

## 10. Metrics endpoint

`GET /metrics` (`app/api/routes/metrics.py`) is **unauthenticated by
default** — Prometheus exposition. Setting `METRICS_REQUIRE_ADMIN=true`
gates it behind the **overlay-server Bearer token** (reusing
`require_overlay_server_token`), not the user cookie session: a scraper
cannot carry a `vsession` cookie, so the machine-auth Bearer is the right
gate here. This is the only user-facing read endpoint deliberately wired
to the machine-auth layer rather than to `require_user`.
