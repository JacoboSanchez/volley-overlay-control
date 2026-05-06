# Authentication Coverage Audit

Last audited: 2026-04-18 (branch `claude/overlay-auth-hardening`).

This document is the single source of truth for **which routes are
protected, which are intentionally public, and where the gaps are**. It
complements `README.md` (user-facing env var setup) and
`DEVELOPER_GUIDE.md` (code organisation) with a route-by-route inventory.

## 1. Auth mechanisms in use

The codebase has **three independent auth layers**, each gated by a
different environment variable:

| Layer | Env var | How it's enforced | Where |
| :--- | :--- | :--- | :--- |
| `verify_api_key` dependency | `SCOREBOARD_USERS` (per-user `password` or `password_hash`) | Per-route `Depends(verify_api_key)`. Returns `401` when the header is missing, `403` when the Bearer token does not match any configured user. | `app/api/dependencies.py` |
| `require_admin` dependency | `OVERLAY_MANAGER_PASSWORD` or `OVERLAY_MANAGER_PASSWORD_HASH` | Per-route `Depends(require_admin)`. Returns `503` when neither env var is set, `401` when the header is missing, `403` when the Bearer token does not match. | `app/admin/routes.py` |
| `require_overlay_server_token` dependency | `OVERLAY_SERVER_TOKEN` or `OVERLAY_SERVER_TOKEN_HASH` | Per-route `Depends(require_overlay_server_token)`. Auto-populated by the security bootstrap when neither is set (unless `OVERLAY_SERVER_TOKEN_DISABLED=true`). When set: `401` without header, `403` with a mismatched Bearer token. | `app/overlay/routes.py` |

Each row's `_HASH` env var (or `password_hash` user field) is the
preferred form: storing a scrypt record on disk means the cleartext
credential never sits in `.env`. See §8 for the migration guide and
the verifier's caching/rotation semantics.

The `check_oid_access` helper is a second-level check layered on top of
`verify_api_key`: it compares the caller's `control` OID (stored in
`SCOREBOARD_USERS`) against the OID in the request and returns `403`
when they differ.

By default a user entry without a `control` field is allowed on every
OID (backward-compatible "open inside authenticated" behavior). Setting
the **opt-in** env var `STRICT_OID_ACCESS=true` flips that default so
any authenticated user without an explicit `control` is denied
(`403`). Use this on multi-tenant deployments where each user must be
scoped to a specific OID.

## 2. Route inventory

Legend: `Y` = authenticated when the corresponding env var is set;
`—` = always public; `L` = leaks data (see findings).

### 2.1 Scoreboard REST API — `api_router` (`app/api/routes.py`)

Prefix `/api/v1`. Every route below has `Depends(verify_api_key)`; the
ones that also take an `oid` go through `check_oid_access` transitively
via `get_session` (or explicitly inside the handler).

| Method | Path | Auth | Notes |
| :--- | :--- | :--- | :--- |
| `POST` | `/session/init` | Y + OID | Explicit `check_oid_access` |
| `GET` | `/state` | Y + OID | Via `get_session` |
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
| `GET` | `/overlays` | Y | Filters by `allowed_users` |
| `GET` | `/teams` | Y | |
| `GET` | `/themes` | Y | |
| `GET` | `/links` | Y + OID | |
| `GET` | `/styles` | Y + OID | |
| `WS` | `/ws` | Y + OID | Explicit `check_oid_access`; accepts token via `Sec-WebSocket-Protocol: bearer, <token>` (preferred) or `?token=…` query param (deprecated, kept for legacy clients) |

### 2.2 Admin — `admin_router` + `admin_page_router` (`app/admin/routes.py`)

| Method | Path | Auth | Notes |
| :--- | :--- | :--- | :--- |
| `GET` | `/manage` | — | Static HTML page; JS prompts for password client-side and keeps it in a closure variable only. |
| `GET` | `/api/v1/admin/status` | — | Returns `{"enabled": bool}` only — does not leak the password itself. |
| `POST` | `/api/v1/admin/login` | `require_admin` | Used by the management page to validate the password. |
| `POST` | `/api/v1/admin/match/{match_id}/sign-url` | `require_admin` | Mints an HMAC-signed capability URL for the gated match report. Body: `{"ttl_seconds": int}`. Response: `{"url", "expires_at", "expires_in"}`. The URL embeds `?exp=&sig=` — never the admin password. |
| `GET` | `/api/v1/admin/custom-overlays` | `require_admin` | Lists custom overlays managed by the in-process engine. |
| `POST` | `/api/v1/admin/custom-overlays` | `require_admin` | Creates a custom overlay (optional `copy_from` to clone). |
| `DELETE` | `/api/v1/admin/custom-overlays/{id}` | `require_admin` | Deletes a custom overlay and its persisted state. |

### 2.3 Overlay server — `overlay_router` (`app/overlay/routes.py`)

This router powers the **in-process custom overlay server**
(`LocalOverlayBackend`) and is mounted when
`_register_overlay_routes()` finds the `overlay_templates/` directory.
It is **also consumed by `CustomOverlayBackend` when a remote app
instance points at this server** (`APP_CUSTOM_OVERLAY_URL=…`).

| Method | Path | Auth | Classification |
| :--- | :--- | :--- | :--- |
| `GET` | `/favicon.ico` | — | Public OK |
| `GET` | `/overlay/{id}` | — | Public for OBS browser sources. Accepts **either** the raw overlay id or the SHA-256 output key. |
| `WS` | `/ws/{id}` | — | Public for OBS browser sources. Accepts **either** the raw overlay id or the SHA-256 output key. |
| `POST` | `/api/state/{overlay_id}` | `require_overlay_server_token` | Mutation endpoint (F-3 fix). |
| `GET`,`POST` | `/create/overlay/{overlay_id}` | `require_overlay_server_token` | Mutation endpoint (F-3 fix). |
| `GET`,`POST`,`DELETE` | `/delete/overlay/{overlay_id}` | `require_overlay_server_token` | Mutation endpoint (F-3 fix). |
| `GET` | `/list/overlay` | `require_admin` | **F-4 fix.** Returns every overlay id plus its output key — gated behind the admin password. |
| `GET` | `/api/raw_config/{overlay_id}` | `require_overlay_server_token` | Leak endpoint (F-5 fix). |
| `POST` | `/api/raw_config/{overlay_id}` | `require_overlay_server_token` | Mutation endpoint (F-3 fix). |
| `GET` | `/api/config/{overlay_id}` | `require_overlay_server_token` | Leak endpoint (F-5 fix). |
| `GET` | `/api/themes` | — | Public OK (theme name list is not sensitive). |
| `POST` | `/api/theme/{overlay_id}/{theme_name}` | `require_overlay_server_token` | Mutation endpoint (F-3 fix). |

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

### 2.4 Static mounts and system endpoints — `app/bootstrap.py`

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

All five findings documented in the initial audit have been addressed.
The sections below describe each finding and the fix that was applied.

### F-1 — Dead `AuthMiddleware` (low) — **fixed**

`AuthMiddleware.dispatch` was a pass-through that served no purpose;
the real auth lives in per-route dependencies. The class and its
registration in `_register_auth()` have been removed. If future
cross-cutting auth is needed (e.g. gating static assets behind a login
wall), add a dedicated middleware at that time.

### F-2 — Overlay capability URL was weakened by `resolve_overlay_id` (medium) — **intentionally reverted**

The original finding proposed treating `/overlay/{…}` and `/ws/{…}` as
capability URLs by accepting the SHA-256 output key only. That was
applied and later reverted: the raw overlay id is a valid entrypoint
again so operators can share friendly `/overlay/{id}` URLs.

Confidentiality of custom overlays therefore relies on
`/list/overlay` (admin-gated, F-4) and the `/api/config/{id}` /
`/api/raw_config/{id}` leaks (F-5) not exposing ids to unauthenticated
callers. The overlay content itself is intentionally public for OBS.

### F-3 — Unauthenticated mutation endpoints on the overlay router (high) — **fixed**

The overlay router used to expose seven mutation endpoints without any
auth. These are now gated by the new
`require_overlay_server_token` dependency:

- `POST /api/state/{id}`
- `GET`/`POST /create/overlay/{id}`
- `GET`/`POST`/`DELETE /delete/overlay/{id}`
- `POST /api/raw_config/{id}`
- `POST /api/theme/{id}/{name}`

The dependency reads `OVERLAY_SERVER_TOKEN`:

- **Unset** → dependency is a no-op (backward compatible); a warning is
  emitted at startup when the overlay routes are mounted.
- **Set** → requests must include `Authorization: Bearer <token>`,
  otherwise 401/403 is returned.

`CustomOverlayBackend` forwards the same token via a new
`_auth_headers()` helper so control-app deployments pointed at an
external overlay server (`APP_CUSTOM_OVERLAY_URL`) can set
`OVERLAY_SERVER_TOKEN` on both sides and start enforcing.

### F-4 — `/list/overlay` leaks all overlay IDs and output keys (high) — **fixed**

`/list/overlay` is now gated behind `require_admin`
(`OVERLAY_MANAGER_PASSWORD`). When the password is unset the endpoint
returns 503 instead of leaking data.

### F-5 — Read endpoints leak config (medium) — **fixed**

`GET /api/raw_config/{id}` and `GET /api/config/{id}` now require
`OVERLAY_SERVER_TOKEN` (same dependency as F-3). The `outputUrl` /
`outputKey` pair returned by `/api/config/{id}` is no longer readable
by unauthenticated callers.

## 4. Tripwire tests

`tests/test_auth_coverage.py` pins the auth behavior of every sensitive
route so that future changes to coverage cannot slip in silently. The
matrix covers:

- Scoreboard REST API (`SCOREBOARD_USERS` set) — 401 without Bearer,
  403 with invalid Bearer.
- Admin API (`OVERLAY_MANAGER_PASSWORD` set) — 401/403/200 as
  appropriate.
- Overlay server mutation + read endpoints (`OVERLAY_SERVER_TOKEN` set)
  — 401/403 without correct Bearer; "no-op open" behavior verified
  when the env var is unset.
- `/list/overlay` — admin-gated, with 503 when admin password is unset.

When adding a new route, add a matching entry in this test file.

## 5. Release notes

Two deployment-visible changes operators should be aware of:

1. **`OVERLAY_SERVER_TOKEN` is now auto-generated.** When the env var
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
   bootstrap logs a `CRITICAL` warning when this opt-out is active.
2. **`SCOREBOARD_USERS` unset now triggers a startup warning.** The
   API still works without auth — backwards compatible — but the
   open-API posture is now visible in the startup tail. Set
   `SCOREBOARD_USERS_DISABLED=true` to silence the warning for
   trusted-LAN deployments.

## 6. Defence-in-depth middleware

Two middlewares wrap every request and complement the per-route auth
ladder above. Both are wired in `app/bootstrap.py:create_app` so
operators don't need to opt in.

### 6.1 `AuthRateLimitMiddleware` — brute-force backstop

Located in `app/api/middleware/auth_rate_limit.py`. Watches the
`/api/v1/` and `/manage` path prefixes; when a response carries a
401 or 403 status, the caller's IP is recorded in a sliding-window
counter. Once the bucket exceeds the configured threshold the next
request from that IP is short-circuited with `429 Too Many
Requests` and a `Retry-After` header before reaching the handler.
The bucket is reset only by the sliding window — non-failure
responses are intentionally ignored so an attacker cannot launder
failures by interleaving login attempts with hits to a public
endpoint under the same prefix (e.g. `/api/v1/admin/status`).

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
`/api/config/{id}`, the signed-URL minter, etc.). Wildcard
subdomains are honoured (`*.example.com` matches any subdomain).

| Env var | Default | Meaning |
| :--- | :--- | :--- |
| `TRUSTED_HOSTS` | unset | Comma-separated allow-list. Whitespace around entries is stripped. |

Operators behind a reverse proxy must also configure uvicorn with
`--proxy-headers` so the ASGI scope reflects the real `Host`. The
overlay routes (`/overlay/{id}`) remain reachable from any host
because the `Host` check happens before the route is dispatched —
see `_maybe_register_trusted_hosts` if you need to relax that for
OBS browser sources on a different domain.

### 6.3 `CORSMiddleware` — cross-origin SPA scaffolding (opt-in)

Wired in `app/bootstrap.py:_maybe_register_cors`. When
`CORS_ALLOWED_ORIGINS` is unset the middleware is not installed
(default, backwards compatible — the bundled SPA is served by
FastAPI itself, no cross-origin requests). When set to a
comma-separated list of origins, browser preflight responses get
explicit allow-list semantics:

* `Access-Control-Allow-Origin` is echoed only for listed origins.
* `Access-Control-Allow-Credentials: true` so the React UI can
  forward `Authorization` headers.
* `Access-Control-Allow-Headers` includes `Authorization`,
  `Content-Type`, `X-Request-ID`, and `Sec-WebSocket-Protocol`
  — the headers the existing auth flows and the WS subprotocol
  handshake actually use.

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

This section documents how each credential travels on the wire, and
the H-4 hardening that flipped two of them away from the URL line.

### 7.1 Match report: signed capability URLs

The legacy share flow for the gated match report was
``/match/{id}/report?token=$OVERLAY_MANAGER_PASSWORD``. Pasting
the URL into chat tools, browser bookmarks, or anywhere a
``Referer`` header could be sent leaked the actual admin password.

Operators should now mint a capability URL via
``POST /api/v1/admin/match/{match_id}/sign-url`` (admin Bearer
required). The response carries a URL of the form
``/match/{id}/report?exp=<unix_seconds>&sig=<hmac_hex>``. The
signing key is derived from ``OVERLAY_MANAGER_PASSWORD``, so:

* Anyone who holds the URL can read the report until ``exp``
  passes.
* The admin password itself never leaves the server.
* Rotating ``OVERLAY_MANAGER_PASSWORD`` invalidates every
  outstanding signed URL — the desired behaviour after a suspected
  leak.
* TTL is bounded to ``[60 s, 30 days]``; the default is one day.

The legacy ``?token=`` flow is preserved for backwards
compatibility but should be considered deprecated. The matches
index (``/matches/index.html``) deliberately does *not* honour
signed URLs — it would need a separate list-all capability that
also unlocks per-row deletion, and that feature is intentionally
not provided yet.

### 7.2 `/api/v1/ws`: Bearer subprotocol auth

WebSocket connections from JavaScript clients cannot set custom
headers. The legacy workaround was a ``?token=<value>`` query
parameter, which leaks via every reverse-proxy access log.

The route now resolves auth in this order:

1. ``Sec-WebSocket-Protocol: bearer, <token>`` — preferred.
   Browser clients open the socket with
   ``new WebSocket(url, ["bearer", token])``. The server
   selects the ``bearer`` subprotocol and echoes it back during
   the handshake (RFC 6455 §4.1).
2. ``Authorization: Bearer <token>`` header — for non-browser
   clients that can set headers on the upgrade request.
3. ``?token=<value>`` query parameter — legacy fallback. Kept
   so existing CLI / script clients keep working; documented as
   deprecated in the OpenAPI schema.

The token never appears in the request line for browser clients
that adopt path 1.

## 8. Hashed credentials at rest

The three credential env vars all started life as plaintext values
read directly from `.env` / compose. `secrets.compare_digest` /
`hmac.compare_digest` made the *comparison* constant-time, but the
source value sat in cleartext on disk where any operator with shell
access could read it. PR 4 of the security plan added an opt-in
hashed alternative without introducing a new dependency.

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

| Credential | Plaintext env var | Hash env var | Field name |
| :--- | :--- | :--- | :--- |
| Scoreboard user | inside `SCOREBOARD_USERS` JSON: `password` | inside `SCOREBOARD_USERS` JSON: `password_hash` | (per-user) |
| Admin (`/manage`, `/api/v1/admin/*`) | `OVERLAY_MANAGER_PASSWORD` | `OVERLAY_MANAGER_PASSWORD_HASH` | env var |
| Overlay server | `OVERLAY_SERVER_TOKEN` | `OVERLAY_SERVER_TOKEN_HASH` | env var |

When both forms are configured, the hash wins. This matters for the
migration path: an operator who has minted a hash but hasn't yet
deleted the plaintext should already be authenticating against the
new value, otherwise the old password keeps working until both are
rotated.

### 8.3 Verification cache

`hashlib.scrypt` at the default parameters costs ~50 ms per check.
Routes protected by `verify_api_key` are called many times per
second from the React UI, so unhashed verification is essentially
free but hashed verification would add real latency. The
`PasswordAuthenticator._verify_cache` keeps a 60-second per-process
TTL cache keyed on `sha256(provided_token)`; cached lookups skip
the scrypt call entirely. The cache is invalidated automatically
on `SCOREBOARD_USERS` rotation, so a removed user cannot remain
authenticated past the env-var change.

### 8.4 Auto-generation interaction

`security_bootstrap.ensure_overlay_server_token` (PR 2) auto-generates
`OVERLAY_SERVER_TOKEN` and persists it to `data/.overlay_server_token`
on first start. When `OVERLAY_SERVER_TOKEN_HASH` is set, the
bootstrap skips that step — a hash-only deployment intentionally
keeps zero cleartext on the server side. The peer
(`CustomOverlayBackend`) still reads the cleartext token from its
own configuration, so the hash-only model splits trust cleanly:
this server stores only a hash, the peer stores only the cleartext.
