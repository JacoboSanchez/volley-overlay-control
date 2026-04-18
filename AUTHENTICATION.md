# Authentication Coverage Audit

Last audited: 2026-04-18 (branch `claude/auth-middleware-audit`).

This document is the single source of truth for **which routes are
protected, which are intentionally public, and where the gaps are**. It
complements `README.md` (user-facing env var setup) and
`DEVELOPER_GUIDE.md` (code organisation) with a route-by-route inventory.

## 1. Auth mechanisms in use

The codebase has **three independent auth layers**, each gated by a
different environment variable:

| Layer | Env var | How it's enforced | Where |
| :--- | :--- | :--- | :--- |
| `AuthMiddleware` | `SCOREBOARD_USERS` | Registered as middleware when `PasswordAuthenticator.do_authenticate_users()` returns `True`. **The current implementation is a pass-through `call_next`** — it does not block any request. | `app/authentication.py`, registered in `app/bootstrap.py::_register_auth` |
| `verify_api_key` dependency | `SCOREBOARD_USERS` | Per-route `Depends(verify_api_key)`. Returns `401` when the header is missing, `403` when the Bearer token does not match any configured user. | `app/api/dependencies.py` |
| `require_admin` dependency | `OVERLAY_MANAGER_PASSWORD` | Per-route `Depends(require_admin)`. Returns `503` when the password env var is unset, `401` when the header is missing, `403` when the Bearer token does not match. | `app/admin/routes.py` |

The `check_oid_access` helper is a second-level check layered on top of
`verify_api_key`: it compares the caller's `control` OID (stored in
`SCOREBOARD_USERS`) against the OID in the request and returns `403`
when they differ.

> **Finding F-1 (low):** `AuthMiddleware.dispatch` is a pass-through and
> has been since the REST API adopted dependency-based auth. It is kept
> as a hook for future static-asset protection, but the module docstring
> suggests it still "restricts access" — this is misleading. Either
> delete the class or update the docstring.

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
| `GET` | `/manage` | — | Static HTML page; JS prompts for password client-side and stores it in `sessionStorage`. |
| `GET` | `/api/v1/admin/status` | — | Returns `{"enabled": bool}` only — does not leak the password itself. |
| `POST` | `/api/v1/admin/login` | `require_admin` | Used by the management page to validate the password. |
| `GET` | `/api/v1/admin/overlays` | `require_admin` | |
| `POST` | `/api/v1/admin/overlays` | `require_admin` | |
| `PUT` | `/api/v1/admin/overlays/{name}` | `require_admin` | |
| `DELETE` | `/api/v1/admin/overlays/{name}` | `require_admin` | |

### 2.3 Overlay server — `overlay_router` (`app/overlay/routes.py`)

This router powers the **in-process custom overlay server**
(`LocalOverlayBackend`) and is mounted when
`_register_overlay_routes()` finds the `overlay_templates/` directory.
It is **also consumed by `CustomOverlayBackend` when a remote app
instance points at this server** (`APP_CUSTOM_OVERLAY_URL=…`).

| Method | Path | Auth today | Classification |
| :--- | :--- | :--- | :--- |
| `GET` | `/favicon.ico` | — | Public OK |
| `GET` | `/overlay/{overlay_id_or_output_key}` | — | **Capability URL** — intentionally public for OBS. Accepts either the raw OID or its SHA-256 prefix ("output key"). See F-2. |
| `WS` | `/ws/{overlay_id}` | — | **Capability URL** — public for OBS browser sources. See F-2. |
| `POST` | `/api/state/{overlay_id}` | — | **F-3 (high): unauthenticated mutation.** Anyone who can guess an overlay ID can overwrite its live scoreboard state. |
| `GET`,`POST` | `/create/overlay/{overlay_id}` | — | **F-3 (high): unauthenticated mutation.** `GET` creates an overlay — drive-by requests suffice. |
| `GET`,`POST`,`DELETE` | `/delete/overlay/{overlay_id}` | — | **F-3 (high): unauthenticated mutation.** `GET` deletes. |
| `GET` | `/list/overlay` | `require_admin` | **F-4 (high): recon.** Returns every overlay id plus its deterministic output key. Trivially defeats the capability-URL design. Gated in this audit PR. |
| `GET` | `/api/raw_config/{overlay_id}` | — | **F-5 (medium): leaks model + customization.** |
| `POST` | `/api/raw_config/{overlay_id}` | — | **F-3 (high): unauthenticated mutation.** |
| `GET` | `/api/config/{overlay_id}` | — | **F-5 (medium):** returns `outputUrl` + `outputKey`, breaking the capability-URL assumption for any known OID. |
| `GET` | `/api/themes` | — | Public OK (theme name list is not sensitive). |
| `POST` | `/api/theme/{overlay_id}/{theme_name}` | — | **F-3 (high): unauthenticated mutation.** |

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
static assets (e.g. hiding the SPA behind a login wall), the hook point
is `AuthMiddleware.dispatch` — see F-1.

## 3. Findings

### F-1 — `AuthMiddleware` is a no-op (low)

`AuthMiddleware.dispatch` just calls `call_next` today, yet the class
docstring reads "Restrict access to the API when user authentication is
enabled." The behavior has shifted to per-route dependencies, but the
module is still registered in `_register_auth()` when
`SCOREBOARD_USERS` is set. This is misleading but harmless.

**Recommendation:** update the docstring to clearly say "no-op hook for
future static-asset protection", or remove the middleware and the
`_register_auth()` registration. Either change is fine; the important
thing is that code and docs agree.

### F-2 — Overlay capability URL is weakened by `resolve_overlay_id` (medium)

`/overlay/{…}` and `/ws/{…}` both call
`OverlayStateStore.resolve_overlay_id`, which accepts **either** the
raw overlay ID or its SHA-256 prefix. Because `get_output_key` is a
deterministic hash of the ID, the key is only a capability as long as
the raw ID is not learnable. `/list/overlay`, `/api/config/{id}`, and
`/overlay/{raw_id}` itself all leak the mapping.

**Recommendation:** change `resolve_overlay_id` to accept the output
key only. The in-process backend already constructs URLs using the
output key (`LocalOverlayBackend.fetch_output_token`), so this is
backward-compatible for the default deployment. OBS configurations
that hardcode `/overlay/{raw_id}` would need updating — call this out
in release notes.

### F-3 — Unauthenticated mutation endpoints on the overlay router (high)

The overlay router exposes seven mutation endpoints without any auth:

- `POST /api/state/{id}`
- `GET`/`POST /create/overlay/{id}`
- `GET`/`POST`/`DELETE /delete/overlay/{id}`
- `POST /api/raw_config/{id}`
- `POST /api/theme/{id}/{name}`

These are a direct data-integrity risk: anyone with network access to
the app (or who gets a victim to visit a crafted URL, since `GET` is
accepted for create/delete) can overwrite, create, or destroy overlays.

**Recommendation:** introduce a new env var `OVERLAY_SERVER_TOKEN` and
a matching `require_overlay_server_token` dependency. Apply it to all
mutation endpoints. When the env var is unset, log a startup warning
but leave the endpoints open (for backward compatibility with existing
deployments). `CustomOverlayBackend` would need to learn to send the
token — that's the only client-side change.

### F-4 — `/list/overlay` leaks all overlay IDs and output keys (high)

`GET /list/overlay` returns `{"overlays": [{"id": "...", "output_key": "..."}, ...]}`
for every overlay on disk. This is the single most damaging recon
primitive today — it defeats the capability-URL design (F-2) for every
overlay in one request, and there is no known consumer in this repo.

**Recommendation:** gate behind `require_admin`. Already implemented as
part of this audit PR; the behavior change is:

- When `OVERLAY_MANAGER_PASSWORD` is set → requires `Authorization: Bearer <password>`.
- When unset → endpoint returns `503 Overlay management is disabled.`
  instead of data. Operators that currently rely on `/list/overlay`
  being open must either set `OVERLAY_MANAGER_PASSWORD` or open a
  follow-up issue.

### F-5 — Read endpoints leak config (medium)

- `GET /api/raw_config/{id}` returns the full model and customization
  (team names, logos, colors).
- `GET /api/config/{id}` returns the `outputUrl` and `outputKey` —
  useful for an attacker building an OBS source against someone else's
  overlay.

**Recommendation:** same gate proposed in F-3 (`require_overlay_server_token`).
`CustomOverlayBackend` calls both endpoints and would need to send
the token.

## 4. Tripwire tests

`tests/test_auth_coverage.py` pins the current behavior of every
sensitive route so that future changes to auth coverage cannot slip in
silently. The matrix is parametrized over
`(method, path, expected_status_without_token, expected_status_with_valid_token)`
with `SCOREBOARD_USERS` / `OVERLAY_MANAGER_PASSWORD` set as
appropriate. When a finding is fixed, update the expected status in
that test.

## 5. Follow-up plan

The items below are **recommendations**, not changes applied in this
audit PR (except F-4, which has minimal blast radius):

1. Fix F-1 (docstring or deletion) — trivial.
2. Fix F-3 and F-5 together by introducing `OVERLAY_SERVER_TOKEN` —
   requires coordinated change to `CustomOverlayBackend`.
3. Fix F-2 by hardening `resolve_overlay_id` — call out in release
   notes.
