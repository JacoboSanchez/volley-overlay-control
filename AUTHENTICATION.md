# Authentication Coverage Audit

> ℹ️ **Rewritten for the multi-user refactor.** The app moved from a
> single-tenant Bearer/admin-password posture to **multi-user cookie
> sessions with roles** (`app/auth/`). Account and admin surfaces require
> an HttpOnly `vsession` cookie. The scoreboard API and control WebSocket
> instead accept any board credential: the owner's cookie, an unguessable
> `control_token`, or an opted-in, guessable public bookmark. Each resolves
> to the per-user storage key `"<user_id>:<oid>"`, so it reaches only its
> intended scoreboard. The public OBS surface (`/overlay/{token}`,
> `/follow/{token}`, `/ws/{token}`) uses a separate, unguessable
> `public_token` path capability for read-only output. The app is purely
> in-process — there is no external overlay server and no machine-to-machine
> Bearer layer. The legacy `SCOREBOARD_USERS` Bearer ladder, the
> `OVERLAY_MANAGER_PASSWORD` admin Bearer + `/manage`, `check_oid_access` /
> `STRICT_OID_ACCESS`, and the match-report `?token=<password>` flow were all
> **removed in the multi-user refactor**; they are noted here only where a
> reader might expect them.

Last audited: 2026-07-28 (board credentials and complete route inventory).

This document is the single source of truth for **the auth model and
which routes are protected, which are intentionally public, and where
the gaps are**. The other docs deliberately do not restate the model —
they link here (see the documentation ownership table in
[`AGENTS.md`](AGENTS.md#documentation-files)). `README.md` owns
operator-facing env var setup and `DEVELOPER_GUIDE.md` owns code
organisation; both point at this file for the model itself.

## 1. Auth mechanisms in use

Three credential families exist: **cookie sessions** for human users,
**board-control credentials** for login-free operator access (an unguessable
`control_token` or an explicitly enabled public bookmark), and the separate
**`public_token` output capability** used by OBS pages (§1.2). A signed-in
owner's cookie is also accepted by the board-control gate. The app is purely
in-process, so there is no machine-to-machine Bearer layer to gate an
external overlay server.

| Layer | Credential | How it's enforced | Where |
| :--- | :--- | :--- | :--- |
| User session dependencies (`current_user` → `require_user` → `require_admin`) | HttpOnly `vsession` cookie → `auth_sessions` row | Per-route `Depends(require_user)` / `Depends(require_admin)`. `401` when anonymous, `409 PASSWORD_CHANGE_REQUIRED` when a forced password change is pending, `403` when an admin-only route is hit by a non-admin. | `app/auth/dependencies.py` |
| `get_session` board gate | control token / public bookmark / cookie session | Single per-route dependency: resolves the caller's credential to a storage key (403 on a bad token/bookmark, 401/409 via the cookie path) and returns the `GameSession`. There is no separate route-level credential gate — that would repeat the same lookup on every action. | `app/api/dependencies.py` |

User passwords are stored hashed as scrypt records in the `users` table
(see §8). The session cookie value is itself stored hashed — only the
SHA-256 of the opaque token is persisted (§2.1). The cleartext credential
never has to sit in `.env`.

The user-session 401s carry `WWW-Authenticate: Cookie`. There is no
Bearer ladder left in the app.

### 1.1 Sessions, roles, and the forced-password-change gate

A session is an opaque `secrets.token_urlsafe(32)` value carried in the
`vsession` cookie (`SameSite=Lax`, `HttpOnly`, `Path=/`; `Secure`
auto-set over HTTPS, forceable via `SESSION_COOKIE_SECURE`). Only its
SHA-256 (`token_hash`) is stored, alongside `user_id`, `expires_at`, and
`last_seen_at` in `auth_sessions`. Server-side storage makes selective
revocation possible: logout removes the current session, self password
change removes every other session, and an admin password reset removes
all sessions (§1.2). A stateless signed cookie could not provide that
control without a denylist table. TTL is `SESSION_TTL_HOURS` (default
`336` = 14 days).

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

### 1.2 Board credentials — the four ways to reach one overlay

A login is **not** the only way to drive a board. Three credentials grant
control, and a fourth grants read-only output. Every one of them resolves
to the same per-overlay storage key `skey = "<user_id>:<oid>"`, so no
credential can ever reach an overlay it was not issued for.

| # | Credential | Carried as | Grants | Guessable? | Revoke by |
| :-- | :--- | :--- | :--- | :--- | :--- |
| 1 | **Owner session** — `vsession` cookie | HttpOnly cookie (§2.1) | Full control of every overlay the user owns, plus account/admin surfaces | No | Logout (this session), self password change (**every other** session), admin password reset or account delete (**all** sessions) — see below |
| 2 | **`control_token`** — shareable operator link | `?c=<token>` query or `X-Control-Token` header | Full control of **that one** overlay, with no login | No — `secrets.token_urlsafe(18)`, unique per overlay | `POST /api/v1/overlays/{oid}/regenerate-control-token` (mints a new token; every previously-shared link dies instantly) |
| 3 | **Public bookmark** — `public_control` | `?u=<username>&oid=<oid>` query | Full control of that one overlay, with no login | **Yes — by design** (see below) | `PATCH /api/v1/overlays/{oid}` with `{"public_control": false}` |
| 4 | **`public_token`** — OBS output | Path segment (`/overlay/{token}`) | Read-only render feed; no control (§2.5) | No — same 24-char url-safe shape | Not revocable independently; delete/recreate the overlay |

**Session revocation is not all-or-nothing, and the difference matters after
a cookie theft.** `POST /api/v1/auth/change-password` deliberately keeps the
caller's own session alive — it passes that cookie's hash as
`except_token_hash` (`app/auth/routes.py`) so changing your password does not
log you out of the tab you changed it in. The consequence: if an attacker
holds a *copy* of the cookie you are currently using, changing your password
from that same browser does **not** lock them out. Log out (which revokes the
session row itself, invalidating every copy of that cookie) or have an admin
run `POST /api/v1/admin/users/{id}/reset-password`, which calls
`revoke_all_for_user` with no exception and kills every session including the
current one. Password change alone is the right tool for "someone may have
learned my password", not for "someone may have my cookie".

Precedence in `resolve_board_skey` (`app/api/dependencies.py`): control
token → public bookmark → cookie user. A present-but-invalid token or a
bookmark for an overlay that has not opted in both fail closed with `403`
and the same opaque `"Invalid or revoked control link."` detail — the
message deliberately does not distinguish "no such token" from "revoked",
so a prober learns nothing from it. Only when neither is supplied does the
cookie path run, returning `401` when anonymous and `409` when a forced
password change is pending.

> ⚠️ **`public_control` trades unguessability for a stable URL.** The rest
> of this document stresses that the capability tokens are unguessable;
> credential 3 is the deliberate exception. `/board?u=alice&oid=court1`
> contains no secret — **anyone who can guess a username and an overlay id
> gets full control of that board**, including resetting the score
> mid-match. Both halves are routinely guessable: usernames are short and
> overlay ids tend to describe the venue (`court1`, `main`). It exists
> because a token link cannot be bookmarked usefully across a token
> rotation, and a tablet in a gym wants one permanent URL.
>
> It is **off by default**, per overlay, and the SPA shows a warning when
> enabling it. Prefer credential 2 (`?c=`) for anything shared outside a
> trusted room; reach for `public_control` only on a private network, and
> pick a non-obvious `oid` if you do.

Both login-free board-control paths are exercised by
`tests/test_control_token.py` (token accepted, revoked token rejected,
`public_control` off → `403`).

## 2. Route inventory

Legend: `Y` = requires a logged-in user (cookie session); `A` = requires
an admin session; `B` = **board credential** — any of the three control
credentials in §1.2 (control token, opted-in public bookmark, or the
owner's cookie session), always scoped to the resolved storage key
`"<user_id>:<oid>"`; `G` = **gated, multi-mode** — no `require_user`
dependency, but a hand-rolled gate admitting any of several credentials,
which differ per route (table below); `—` = always public (capability URL
or intentionally open).

`B` is deliberately not `Y`: those routes are reachable with no login at
all when a valid `?c=` token or an opted-in `?u=` bookmark is present.

`G` is deliberately not `—`: an anonymous request with no credential is
**rejected**, so listing those routes as public would misdescribe them in
the document whose whole job is being unambiguous about access. It is also
not `Y`: the owner's cookie is *one* accepted mode, not a requirement, and
there is no `require_user` dependency to point at.

The accepted modes differ per route — the signed-URL mode exists only for
the report pair, so a signed report link does **not** open match history:

| Route | `MATCH_REPORT_PUBLIC=true` | Signed URL (`?exp=&sig=`) | Owner cookie | Otherwise |
| :--- | :-: | :-: | :-: | :--- |
| `/match/{id}/report` | ✅ | ✅ | ✅ | `401` |
| `/match/{id}/report.csv` | ✅ | ✅ (same signature) | ✅ | `401` |
| `/matches/{public_token}` | ✅ | — none | ✅ | `401` |

One trap worth stating: a `{public_token}` in the path does **not** imply
the token is the credential. On `/overlay/` and `/follow/` it is; on
`/matches/` it only selects the overlay, and with public mode off the
owner's cookie is the *only* way in. Read the gate, not the path shape.

### 2.1 Cookie sessions — the `vsession` cookie

Every `Y`/`A` route below is gated by the `vsession` HttpOnly cookie, not
a Bearer token (a `B` route accepts it too, as credential 1 of §1.2, but
does not require it). The cookie value is an opaque
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

Prefix `/api/v1`. Every `B` route below authorizes through its
`Depends(get_session)` parameter, which resolves whichever board
credential is present (§1.2) to the storage key `"<user_id>:<oid>"` — so
passing another user's `oid` simply resolves to a different key with no
session (404), never another user's data. There is no second-level
`check_oid_access`: isolation is structural in the session key.

Note what `B` implies: the whole scoring surface is reachable **without a
login** by anyone holding the overlay's control token or, when
`public_control` is on, anyone who can guess `username` + `oid`. That is
the intended design (an operator running the match is usually not the
account owner), and §1.2 covers the trade-off. Account-level routes —
overlay CRUD, teams, matches, icons — stay `Y`: a control link drives one
board and cannot touch the owner's account.

| Method | Path | Auth | Notes |
| :--- | :--- | :--- | :--- |
| `POST` | `/session/init` | B | Creates/reuses the board's `"<user_id>:<oid>"` session. In owner (cookie) mode only, a missing `oid` is auto-registered as a new overlay; token and bookmark modes require the overlay to exist. |
| `GET` | `/state` | B | Via `get_session`. |
| `GET` | `/customization` | B | |
| `GET` | `/config` | B | |
| `GET` | `/audit` | B | Most-recent records from the board's audit log. |
| `GET` | `/matches/live/stats` | B | Live stats for the *active* board session, computed from its audit log — not an archived match. |
| `POST` | `/session/rules` | B | Update the board's match rules (mode, points, sets). |
| `POST` | `/game/add-point` | B | |
| `POST` | `/game/add-set` | B | |
| `POST` | `/game/add-timeout` | B | |
| `POST` | `/game/change-serve` | B | |
| `POST` | `/game/set-score` | B | |
| `POST` | `/game/set-sets` | B | |
| `POST` | `/game/reset` | B | |
| `POST` | `/game/start-match` | B | |
| `POST` | `/game/undo` | B | |
| `POST` | `/display/visibility` | B | |
| `POST` | `/display/simple-mode` | B | |
| `POST` | `/display/swap-sides` | B | |
| `POST` | `/display/auto-swap-sides` | B | |
| `POST` | `/display/set-summary` | B | |
| `POST` | `/display/set-summary-style` | B | |
| `PUT` | `/customization` | B | |
| `GET` | `/links` | B | |
| `GET` | `/styles`, `/style-capabilities` | B | |
| `GET` | `/board/team-groups`, `/board/team-groups/{group_key}/teams` | B | Team pickers for the board UI, so a no-login operator can set team names. |
| `PUT` | `/board/selected-group` | B | |
| `GET` | `/overlays` | Y | Scoped to the caller's overlays. Response includes each overlay's `control_token` / `control_url` and `public_control` flag (§1.2) — it is the owner's own credential list, so it is owner-only by cookie. |
| `POST` | `/overlays` | Y | Mints `public_token` **and** `control_token`. |
| `PATCH` | `/overlays/{oid}` | Y | Owner-only; this is where `public_control` is toggled. |
| `DELETE` | `/overlays/{oid}` | Y | |
| `POST` | `/overlays/{oid}/regenerate-control-token` | Y | Owner-only revocation of credential 2 — the previously-shared `/board?c=` link stops working immediately. |
| `GET` | `/teams/catalog` | Y | The global catalog the caller can pick from. |
| `POST` | `/teams/mine/custom` | Y | Create a custom team the caller owns. |
| `PATCH` | `/teams/mine/custom/{team_id}` | Y | Edit one of the caller's own custom teams. |
| `DELETE` | `/teams/mine/{team_id}` | Y | Deletes a custom team the caller owns; `404` for anything else, including global catalog teams. |
| `GET` / `POST` | `/my/groups` | Y | The caller's own team groups, plus the admin-published ones visible to them. |
| `PATCH` / `DELETE` | `/my/groups/{id}` | Y | |
| `POST` | `/my/groups/{group_id}/teams` | Y | Add a team to one of the caller's groups. |
| `DELETE` | `/my/groups/{group_id}/teams/{team_id}` | Y | Remove one. |
| `GET` / `POST` | `/customization/presets` | Y | The caller's saved theme presets. |
| `DELETE` | `/customization/presets/{slug}` | Y | |
| `GET` | `/matches` | Y | Lists only the caller's archived matches. |
| `GET` | `/matches/{id}` | Y | Owner-only (`404` otherwise). |
| `DELETE` | `/matches/{id}` | Y | Owner-only delete (§8 / §7.1). |
| `POST` | `/matches/{id}/sign-url` | Y | Owner mints an HMAC capability URL for the gated match report. Body: `{"ttl_seconds": int}`. Response embeds the time-bounded bearer capability `?exp=&sig=`; the signing key remains server-side (`MATCH_REPORT_SECRET`, else `SESSION_SECRET` — §7.1). |
| `GET` | `/icons` | Y | Icon library listing (globals + the caller's own + quota). |
| `POST` | `/icons/mine` | Y | Multipart icon upload into the caller's personal library (server-side resize → WebP; quota-capped). |
| `PATCH` / `DELETE` | `/icons/mine/{id}` | Y | Rename / delete an own icon (delete also clears referencing teams). `404` for ids outside the caller's scope. |
| `GET` | `/icons/mine/{id}/usage` | Y | How many teams reference the icon (pre-delete count). |
| `POST` | `/icons/mine/import-from-teams` | Y | Convert the caller's own teams' external logo URLs into hosted icons (SSRF-guarded download; scope re-checked server-side). |
| `POST` | `/admin/icons` | A | Upload a global icon. |
| `PATCH` / `DELETE` | `/admin/icons/{icon_id}` | A | Mirrors the personal shapes for the global scope. |
| `GET` | `/admin/icons/{icon_id}/usage` | A | |
| `POST` | `/admin/icons/import-from-teams` | A | |
| `POST` | `/admin/teams` | A | Add to the global team catalog. There is no `GET` here — the catalog is read through `/teams/catalog`. |
| `GET` | `/admin/teams/export` | A | Dump the catalog as JSON. |
| `POST` | `/admin/teams/import` | A | Load a catalog JSON map. |
| `PATCH` / `DELETE` | `/admin/teams/{team_id}` | A | |
| `GET` / `POST` | `/admin/team-groups` | A | Publishable team groups. |
| `PATCH` / `DELETE` | `/admin/team-groups/{group_id}` | A | |
| `POST` | `/admin/team-groups/{group_id}/members` | A | Add a team to a group. |
| `DELETE` | `/admin/team-groups/{group_id}/members/{team_id}` | A | Remove one. |
| `GET` / `POST` | `/admin/presets` | A | Global theme presets. |
| `GET` | `/admin/presets/export` | A | Dump them as an `APP_THEMES` JSON map. |
| `POST` | `/admin/presets/import` | A | Load an `APP_THEMES` JSON map. |
| `PATCH` / `DELETE` | `/admin/presets/{slug}` | A | `PATCH` activates/deactivates a global preset. |
| `GET` | `/app-config` | — | Runtime config the SPA reads on load (title, feature flags). Carries no secrets. |
| `POST` | `/_log` | — | Client error reports from the SPA. Unauthenticated by design — an anonymous visitor hitting a crash still needs to report it — so a per-IP rate limit, a body cap and PII redaction do the safety work instead. |
| `WS` | `/ws` | B | Accepts the same three board credentials: `?c=<token>`, `?u=&oid=`, or the `vsession` cookie (browsers send cookies on same-origin WS upgrades, so no subprotocol token is needed). Closes `4400` with neither `oid` nor `c`, `4003` when the credential does not resolve, `4004` when no session exists. |

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

This router powers the **in-process overlay server**
(`LocalOverlayBackend`) and is mounted when
`_register_overlay_routes()` finds the `overlay_templates/` directory.
Every endpoint it exposes is intentionally public: the OBS output
surface is addressed by an unguessable per-overlay `public_token`
(credential 4 in §1.2), and the theme name list is not sensitive. There
are no machine-to-machine peer endpoints — the app is purely in-process,
so there is nothing here for an external overlay server to call. Note
that `public_token` is **output only**: it renders the board and streams
state, and cannot mutate anything. Control needs one of credentials 1–3.

| Method | Path | Auth | Classification |
| :--- | :--- | :--- | :--- |
| `GET` | `/favicon.ico` | — | Public OK |
| `GET` | `/overlay/{public_token}` | — | Public for OBS browser sources. The unguessable per-overlay `public_token` is itself the path capability; no cookie or secondary credential is required. |
| `GET` | `/follow/{public_token}` | — | Public spectator/follow page; same `public_token` capability URL, same `/ws/{public_token}` feed. |
| `WS` | `/ws/{public_token}` | — | Public for OBS browser sources. Same `public_token` capability URL. |
| `GET` | `/api/themes` | — | Public OK (theme name list is not sensitive). |

> **Removed in the multi-user refactor:** `GET /list/overlay` no longer
> exists. It used to enumerate every overlay id plus its output key behind
> the admin password; with public output addressed by an unguessable
> per-overlay `public_token` there is no id-enumeration endpoint to gate.
> The old F-4 finding is therefore moot (§3).

> **Note on `public_token` format:** the per-overlay `public_token` is an
> unguessable random capability token, and any internal overlay-id input
> is validated against the strict allow-list regex enforced by
> `OverlayStateStore._sanitize_id`:
>
> ```
> ^(?!\.{1,2}$)[A-Za-z0-9._-]{1,64}$
> ```
>
> Requests carrying path-separator characters (`/`, `\`), traversal
> segments (`.`, `..`), NUL, whitespace, or non-ASCII are rejected at
> the store boundary — `create_overlay` / `delete_overlay` return
> `False`, `overlay_exists` returns `False`, and read/write helpers
> raise `ValueError`.

### 2.6 Static mounts and system endpoints — `app/bootstrap.py`

| Method | Path | Auth | Notes |
| :--- | :--- | :--- | :--- |
| `GET` | `/fonts/**` | — | Static assets |
| `GET` | `/static/**` | — | Overlay static assets |
| `GET` | `/media/**` | — | Hosted icon-library images (`data/media/`). Public by design: overlay pages in OBS carry no cookies, so the logos they embed must load credential-less — same posture as `/static`. Filenames are content-hashed and unguessable-ish, but treat every uploaded icon as public. |
| `GET` | `/pwa/**` | — | PWA manifest/icons |
| `GET` | `/assets/**` | — | SPA build output |
| `GET` | `/sw.js` | — | PWA service worker |
| `GET` | `/manifest.webmanifest` | — | PWA manifest |
| `GET` | `/manifest.json` | — | PWA manifest |
| `GET` | `/health` | — | Health check |
| `GET` | `/health/ready` | — | Readiness probe: additionally touches the DB and the data dir, so an orchestrator does not route traffic to a pod that cannot serve. Reports status only, never configuration. |
| `GET` | `/metrics` | — *(or `METRICS_TOKEN` bearer)* | Prometheus exposition. Unauthenticated by default — aggregates only, no payloads and no per-OID labels. Gateable with `METRICS_TOKEN` / `METRICS_ENABLED` (§10). |
| `GET` | `/match/{match_id}/report` | G | Print-friendly match report. `check_read_access` admits `MATCH_REPORT_PUBLIC=true`, then a valid HMAC signature, then the owner's cookie; otherwise **401** (§7.1). |
| `GET` | `/match/{match_id}/report.csv` | G | Point-log CSV for the same match, gated identically. A signed *report* link's `exp`/`sig` open the CSV too — the signature covers `match_id\|exp`, not the path. |
| `GET` | `/matches/{public_token}` | G | Per-overlay archived-match listing. **The token is an identifier here, not a credential**: it selects the overlay (`404` if unknown), then the same gate as the report runs — `MATCH_REPORT_PUBLIC=true` or the owner's cookie, else `401`. Unlike `/follow/{public_token}`, holding the token is not sufficient. |
| `GET` | `/**` (SPA fallback) | — | Serves `index.html` for unknown paths |

Everything marked `—` above is intentionally public; the three `G` rows
(both match-report routes and the match-history listing) are not, and are
listed here only because they hang off the root rather than a prefixed
router. If a future change needs to gate static assets (e.g.
hiding the SPA behind a login wall), add a custom `BaseHTTPMiddleware` at
that point — there is no longer a pre-wired hook.

## 3. Findings

The five findings from the original audit are carried forward below.
F-1 was fixed by removing dead middleware; F-2, F-3, F-4, and F-5 were
all rendered moot or fixed by the multi-user refactor's move to
per-overlay `public_token` capability URLs and the removal of the
external overlay-server peer endpoints.

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

### F-3 — Unauthenticated mutation endpoints on the overlay router (high) — **moot after the refactor**

The overlay router used to expose a set of mutation and config-write
endpoints intended as machine-to-machine peer endpoints. **These
endpoints were removed when the app became purely in-process.** Overlay
state is now driven only through the in-process backend on behalf of an
authenticated owner (the scoreboard REST API, §2.3); there is no
externally reachable mutation surface on the overlay router left to
gate, and the Bearer credential that used to protect them no longer
exists.

### F-4 — `/list/overlay` leaks all overlay IDs and output keys (high) — **moot after the refactor**

The route was **removed in the multi-user refactor**. Public output is
addressed by an unguessable per-overlay `public_token`, so there is no
id-enumeration endpoint left to leak, and the old admin-password gate it
relied on (`OVERLAY_MANAGER_PASSWORD`) no longer exists. Nothing replaces
it: enumerating overlays is a per-user, session-scoped concern handled by
`GET /api/v1/overlays` (§2.3), which only returns the caller's own.

### F-5 — Read endpoints leak config (medium) — **moot after the refactor**

The config read endpoints that returned the `outputUrl` / `outputKey`
pair were **removed when the app became purely in-process** — they were
machine-to-machine peer endpoints with no remaining caller. There is no
config-leak surface on the overlay router left to gate.

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

When adding a new route, add a matching entry in this test file.

## 5. Release notes

Deployment-visible changes operators should be aware of:

1. **First start prints a one-time admin-bootstrap token.** With no
   admin account yet, startup logs an `ADMIN BOOTSTRAP TOKEN` at
   `WARNING` (visible in `docker logs`) and persists it to
   `data/.admin_bootstrap_token` (mode `0o600`). Claim the first admin
   by POSTing it to `/api/v1/auth/claim-admin` (SPA route
   `/claim-admin`); see §9. Set `ADMIN_BOOTSTRAP_TOKEN` to pin it.
2. **`SESSION_SECRET` is auto-minted if unset.** It hardens sessions and,
   unless `MATCH_REPORT_SECRET` is set, is also the HMAC key for signed
   match-report share URLs (§7.1). On first boot, if unset, the bootstrap
   mints `secrets.token_urlsafe(...)` and persists it to
   `data/.session_secret` (mode `0o600`). Pin it explicitly
   (`SESSION_SECRET=…`) across multiple replicas, or each replica will
   reject the others' sessions and signed URLs.
3. **Registration auto-closes once the instance has its admin.** With
   `REGISTRATION_OPEN` unset, public sign-ups are allowed only during the
   bootstrap window; claiming the first admin writes the DB flag to
   closed. Setting the env var pins the seed instead, and after first
   write the DB flag wins — admins toggle it via
   `PUT /api/v1/admin/registration`. While closed,
   `POST /api/v1/auth/register` returns `403` and admins create accounts
   directly (§2.4).

## 6. Defence-in-depth middleware

Two middlewares wrap every request and complement the per-route auth
ladder above. Both are wired in `app/bootstrap.py:create_app` so
operators don't need to opt in.

### 6.1 `AuthRateLimitMiddleware` — brute-force backstop

Located in `app/api/middleware/auth_rate_limit.py`. Watches two
surfaces, each with its **own keyspace** and its own set of statuses
that count as a failure:

| Surface | Paths | Counted as failure |
| :--- | :--- | :--- |
| `api` | `/api/v1/*` | 401, 403 |
| `capability` | `/overlay/*`, `/follow/*`, `/match/*` | 401, 403, **404** |

404 counts on the capability surface because an unknown capability
token is reported as "not found" (`app/overlay/routes.py`) — it is the
only signal a token-guessing attempt produces. It deliberately does
**not** count on `/api/v1/`, where a 404 is an ordinary missing
resource and counting it would lock operators out during normal
navigation.

Buckets are keyed on `(surface, IP)`, not IP alone. A single shared
bucket would mean 403s collected by somebody's SPA against `/api/v1/`
could take an on-air `/overlay/` browser source off the air — trading a
brute-force risk for an availability one. Split keyspaces let a surface
throttle only itself.

When a response carries one of the surface's failure statuses, the
caller's IP is recorded in a sliding-window counter. Once the bucket
exceeds the configured threshold the next matching request from that IP
is short-circuited with `429 Too Many Requests` and a `Retry-After`
header before reaching the handler, and
`voc_rate_limit_blocks_total{surface}` is incremented so a lockout is
visible in `/metrics` rather than hiding as a `status="429"` label on
the latency histogram.

Three surfaces are deliberately **not** watched:

* **`/ws/*` and the control WebSocket** — a handshake arrives as ASGI
  scope type `websocket`, not `http`, so this middleware structurally
  cannot observe it. Listing the prefix would imply protection that does
  not exist.
* **`/media/**`** — carries no credential (filenames embed a content
  hash). The exposure is request *volume*, which a failure-based limiter
  does nothing about, while counting its 404s would risk blocking a
  venue's icons after an ordinary delete. Volume limiting belongs at the
  proxy.
* **`/metrics`** — the concern there is exposure, not brute force, and
  it is addressed directly by `METRICS_TOKEN` / `METRICS_ENABLED` (§10).
  Throttling a wrong scrape token would blind an operator's dashboard
  over what is nearly always a misconfigured scraper.
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
| `AUTH_RATE_LIMIT_MAX_FAILURES` | `10` | failure responses per window before blocking |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | `60` | sliding-window length |
| `AUTH_RATE_LIMIT_BLOCK_SECONDS` | `60` | how long the IP stays blocked once the threshold trips |

These are read per call, so setting them at any point takes effect —
they used to be evaluated at module import, which made them apply only
if the variable was set before the first import.

State is process-local. Multi-replica deployments should still front
the app with a layer-7 limiter (Cloudflare, Nginx, etc.) — this
middleware is the single-replica self-hosted backstop.

Note also that keying on IP cannot distinguish several operators behind
one NAT from a single attacker. The split keyspaces bound the blast
radius and the metric makes a lockout visible, but that tradeoff is
inherent to per-IP limiting; a deployment with many operators behind one
address should raise `AUTH_RATE_LIMIT_MAX_FAILURES` accordingly.

### 6.2 `TrustedHostMiddleware` — Host-header poisoning defence (opt-in)

Wired in `app/bootstrap.py:_maybe_register_trusted_hosts`. When
`TRUSTED_HOSTS` is unset the middleware is not installed (default,
backwards compatible). When set to a comma-separated list of
hostnames, Starlette's `TrustedHostMiddleware` rejects requests
whose `Host` header doesn't match any entry with HTTP 400 before
any handler reads `request.base_url` (used by `/links`,
the match-report signed-URL minter, etc.).
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
  cookie itself needs no allow-listed header; `Content-Type` /
  `X-Request-ID` cover ordinary JSON requests.

| Env var | Default | Meaning |
| :--- | :--- | :--- |
| `CORS_ALLOWED_ORIGINS` | unset | Comma-separated allow-list of origins. `*` is **rejected** to prevent a copy-paste footgun on a credentialed API; an `ERROR` is logged and CORS stays disabled. |

### 6.4 `SecurityHeadersMiddleware` — HTTP response hardening

Located in `app/api/middleware/security_headers.py`. Adds:

* `X-Content-Type-Options: nosniff` and `Referrer-Policy:
  strict-origin-when-cross-origin` and a `Permissions-Policy` that
  denies geolocation/microphone/camera/payment/usb on every response.
* `Content-Security-Policy` locks scripts to `'self'` plus
  `'unsafe-inline'` for the existing inline overlay and match-report
  scripts; string evaluation is not allowed. Frames default to `'self'`,
  with the exact HTTP(S) origin from `OVERLAY_PUBLIC_URL` added when
  configured so a split-host overlay preview still works. `img-src`
  retains `https:` because team customization accepts operator-selected
  external logo URLs. HTML responses also get `X-Frame-Options:
  SAMEORIGIN`; `/overlay/*` instead uses `frame-ancestors *` and omits
  that legacy header so OBS browser sources can embed it off-origin.
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

This section documents how access travels on the wire. Credentials use
cookies, headers, query parameters, and capability paths:

* The owner's `vsession` uses an HttpOnly cookie and does not appear in the
  request URL.
* HTTP board clients may put a `control_token` in `X-Control-Token`, but the
  shareable `/board?c=` link and browser WebSocket use the `?c=` query form.
* The public bookmark uses `?u=<username>&oid=<oid>`. It contains no secret by
  design, but authorizes control when that overlay has opted in.
* An overlay `public_token` appears in the path. A signed match-report
  capability appears as `?exp=&sig=`.

Treat URLs containing `c`, `public_token`, or `sig` as bearer secrets. They can
appear in browser history and in request/proxy logs unless the deployment
redacts them.

### 7.1 Match report — owner cookie, signed URL, or public mode

Access to ``/match/{match_id}/report`` is resolved by
``app/match_report_access.py`` in this order:

1. **Owner session cookie.** The report's owner, authenticated by the
   ``vsession`` cookie, can always read their own report. Ownership is
   the `user_id` embedded in the stored match's ``oid`` skey.
2. **HMAC capability URL.** The owner mints one via
   ``POST /api/v1/matches/{match_id}/sign-url`` (owner-only,
   ``require_user``). The response carries
   ``/match/{id}/report?exp=<unix_seconds>&sig=<hmac_hex>``. The
   signing key is ``MATCH_REPORT_SECRET`` when set, otherwise
   ``SESSION_SECRET``, so:
   * Anyone who holds the URL can read the report until ``exp`` passes.
   * The `exp` + `sig` pair is a TTL-bounded bearer credential. The
     signing key never leaves the server.
   * Rotating the signing key invalidates every outstanding signed
     URL — the desired behaviour after a suspected leak.
   * With no ``MATCH_REPORT_SECRET``, that key is shared with the cookie
     sessions, which couples two unrelated revocations: rotating
     ``SESSION_SECRET`` because a cookie leaked also breaks every share
     link, and there is no way to revoke the links alone without logging
     everyone out. Setting ``MATCH_REPORT_SECRET`` separates them. It is
     deliberately **not** auto-minted — leaving it unset has to keep
     validating links signed before it existed, which it can only do by
     falling through to the key those links were signed with.
3. **Public mode.** ``MATCH_REPORT_PUBLIC=true`` opens the report to
   anyone who holds the non-guessable ``match_id``.

Otherwise the route returns ``401`` (``WWW-Authenticate: Cookie``).
Deleting a match is owner-only (``DELETE /api/v1/matches/{id}``).

> **Removed in the multi-user refactor:** the legacy
> ``/match/{id}/report?token=$OVERLAY_MANAGER_PASSWORD`` flow — which
> leaked the admin password into URLs, bookmarks, and ``Referer``
> headers — is gone, along with the admin-password signing key. The
> signed replacement is still a URL credential, but it is scoped to one
> report and expires instead of exposing a global, long-lived password.

### 7.2 `/api/v1/ws` — three board credentials

The control socket accepts the same modes as the REST board surface, in
the same precedence order:

1. `?c=<control_token>` for a shareable operator link. Browser WebSocket
   APIs cannot set `X-Control-Token`, so the token is on the request URL.
2. `?u=<username>&oid=<oid>` for an opted-in public bookmark.
3. `?oid=<oid>` plus the owner's `vsession` cookie, sent automatically on
   a same-origin WebSocket upgrade.

Each mode resolves to one storage key before the connection is accepted.
The server closes with `4400` when neither `oid` nor `c` is supplied,
`4003` when the credential does not resolve, and `4004` when that board
has no active session.

> **Removed in the multi-user refactor:** the old
> ``Sec-WebSocket-Protocol: bearer, <token>`` / ``Authorization:
> Bearer`` / ``?token=`` ladder is gone — the same-origin cookie makes
> that legacy account-auth ladder unnecessary. The per-overlay `?c=`
> query is a different, current board credential.

## 8. Hashed credentials at rest

User passwords are stored hashed via `app/password_hash.py`
(`hashlib.scrypt`, stdlib-only, no new dependency):

* **User passwords** live as scrypt records in the `users` table — the
  cleartext is never persisted. `app/auth/passwords.py` is a thin
  re-export of `hash_password` / `verify_password` so the auth package
  has a single import surface.

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
| Session cookie value | `auth_sessions.token_hash` (SHA-256) | the `vsession` cookie | always hashed |

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

## 9. First-admin bootstrap

`app/auth/bootstrap.py` solves the chicken-and-egg of creating the first
admin with no admin to create it.

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

`GET /metrics` (`app/api/routes/metrics.py`) is Prometheus exposition:
aggregate counters and histograms only, never per-user data and never a
credential. It is **unauthenticated by default** — a scraper cannot carry
a `vsession` cookie, and requiring a secret would make the common case
(a scrape from inside the cluster) harder for no gain.

That default is right for a private scrape network and wrong for the
compose file's `0.0.0.0:80` bind, where the endpoint is internet-facing.
The aggregates are not secrets, but they are an oracle: `voc_active_sessions`
is a logged-in user count, `voc_ws_oids_active` a live-match count, and the
per-route latency series enumerate which routes exist — enough to answer
"is anyone using this instance right now?". Two env vars close that off:

| Variable | Effect |
|----------|--------|
| `METRICS_TOKEN` | Requires `Authorization: Bearer <token>`. A miss returns **401** with a `WWW-Authenticate: Bearer` challenge. Compared with `hmac.compare_digest`, like every other credential here. |
| `METRICS_ENABLED=false` | Removes the endpoint. It returns **404**, not 403 — an operator who switched metrics off wants it to look unmounted, not to advertise a gate. |

Both are read per request, so they can be flipped through
`REMOTE_CONFIG_URL` without a restart. `METRICS_ENABLED=false` wins over
a valid token.

The endpoint is still not watched by the rate limiter (§6). A wrong
`METRICS_TOKEN` is a misconfigured scraper far more often than an attack,
and throttling it would silently blind an operator's dashboard; the token
itself is operator-chosen and not guessable at scrape rates.
