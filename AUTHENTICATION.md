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
| `verify_api_key` dependency | `SCOREBOARD_USERS` | Per-route `Depends(verify_api_key)`. Returns `401` when the header is missing, `403` when the Bearer token does not match any configured user. | `app/api/dependencies.py` |
| `require_admin` dependency | `OVERLAY_MANAGER_PASSWORD` | Per-route `Depends(require_admin)`. Returns `503` when the password env var is unset, `401` when the header is missing, `403` when the Bearer token does not match. | `app/admin/routes.py` |
| `require_overlay_server_token` dependency | `OVERLAY_SERVER_TOKEN` | Per-route `Depends(require_overlay_server_token)`. **No-op when the env var is unset** (logs a startup warning). When set: `401` without header, `403` with a mismatched Bearer token. | `app/overlay/routes.py` |

The `check_oid_access` helper is a second-level check layered on top of
`verify_api_key`: it compares the caller's `control` OID (stored in
`SCOREBOARD_USERS`) against the OID in the request and returns `403`
when they differ.

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
| `WS` | `/ws` | Y + OID | Explicit `check_oid_access`; accepts token via `?token=…` query param |

### 2.2 Admin — `admin_router` + `admin_page_router` (`app/admin/routes.py`)

| Method | Path | Auth | Notes |
| :--- | :--- | :--- | :--- |
| `GET` | `/manage` | — | Static HTML page; JS prompts for password client-side and keeps it in a closure variable only. |
| `GET` | `/api/v1/admin/status` | — | Returns `{"enabled": bool}` only — does not leak the password itself. |
| `POST` | `/api/v1/admin/login` | `require_admin` | Used by the management page to validate the password. |
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

One deployment-visible change operators should be aware of:

1. **`OVERLAY_SERVER_TOKEN` is recommended** — set it on any deployment
   that exposes overlay routes (the default in-process overlay server
   setup). Control apps pointed at an external overlay server via
   `APP_CUSTOM_OVERLAY_URL` must also set it to the same value. Leaving
   it unset is backward-compatible but triggers a startup warning.
