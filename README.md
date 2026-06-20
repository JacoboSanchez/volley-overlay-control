# Volley Overlay Control

[![License](https://img.shields.io/github/license/jacobosanchez/volley-overlay-control)](https://github.com/jacobosanchez/volley-overlay-control)
![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
[![CI](https://github.com/jacobosanchez/volley-overlay-control/actions/workflows/ci.yml/badge.svg)](https://github.com/jacobosanchez/volley-overlay-control/actions/workflows/ci.yml)
![Docker](https://img.shields.io/badge/docker-available-2496ED?logo=docker&logoColor=white)
![FastAPI](https://img.shields.io/badge/built%20with-FastAPI-009688.svg)
![React](https://img.shields.io/badge/react-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/typescript-5.x-3178C6?logo=typescript&logoColor=white)

**Volley Overlay Control** is a powerful, self-hostable application for controlling volleyball scoreboards. It bundles a touch-friendly React frontend, a FastAPI backend, and a **built-in overlay engine** into a single deployable service.

It includes 27 overlay style templates served directly to OBS browser sources — no external overlay server required. It also works with *overlays.uno* cloud overlays and with fully custom, external overlay engines. Complete match control — scores, sets, timeouts, and serving teams. Highly customizable and built for versatility, it is a **multi-user** app: each account signs in, manages its own scoreboards/overlays, teams, presets and match reports, while admins curate a shared global catalog of teams and presets.

---

## Screenshots

| Control UI (phone, landscape) | Control UI (phone, portrait) |
|---|---|
| ![Scoreboard control UI in landscape](docs/screenshots/02-scoreboard.png) | ![Scoreboard control UI in portrait](docs/screenshots/03-scoreboard-phone.png) |

| Sign-in page | Configuration panel |
|---|---|
| ![Sign-in page](docs/screenshots/01-init-screen.png) | ![Config panel — teams, colors, layout](docs/screenshots/04-config-panel.png) |

| Per-point classification picker (opt-in) |
|---|
| <p align="center"><img src="docs/screenshots/11-point-type-picker.png" alt="Scoreboard with the opt-in point-type picker open — ace, kill, block, opponent error, or quick point" width="65%"></p> |

| My overlays (`/overlays`) | Match report (`/match/{id}/report`) |
|---|---|
| ![Account overlays page listing the signed-in user's overlays with copyable OBS output URLs](docs/screenshots/05-manage-page.png) | <p align="center"><img src="docs/screenshots/08-match-report.png" alt="Print-friendly match report with hero, set-by-set, highlights and per-set score charts" width="65%"></p> |

| Public spectator page (`/follow/{public_token}`) |
|---|
| <p align="center"><img src="docs/screenshots/09-spectator-page.png" alt="Mobile-first spectator page with scoreboard, set chart, history and live stats" width="40%"></p> |

**Built-in overlay styles** rendered live to OBS browser sources via `/overlay/{public_token}`. All 27 selectable styles laid out side-by-side in a single preview grid via `/overlay/{public_token}?style=mosaic`. The pair below doubles as the theme demo — full data is captured with the forced light theme (`?theme=light`), simple mode with the forced dark one (`?theme=dark`); styles without the matching palette keep their native look:

| Full match data | Simple mode (current set only) |
|---|---|
| ![Mosaic preview grid showing every overlay style with full match data](docs/screenshots/06-overlay-mosaic-full.png) | ![Mosaic preview grid showing every overlay style in simple mode](docs/screenshots/07-overlay-mosaic-simple.png) |

**Set-summary recap overlay** (opt-in) fades in over the scoreboard between sets to surface the just-played set's score, point-progression chart and key stats. Ships in six visual variants — the `brand_columns` example below pairs each team's brand-coloured column with a centre chart panel. An optional "auto-show" mode triggers the recap automatically after each set, with a configurable pre-show delay so the broadcast camera can stay on the players' reaction first.

<p align="center"><img src="docs/screenshots/10-overlay-set-summary.png" alt="Set-summary recap overlay (brand_columns variant) — Thunder Wolves 22 vs Solar Hawks 25 with point-progression chart and per-set stats" width="65%"></p>

> Captured with invented "Thunder Wolves" / "Solar Hawks" demo data — see [scripts/screenshots/](scripts/screenshots/) to regenerate.

---

## Features

### Complete Match Control
*   **Score Management**: Manage points, sets, and timeouts for both teams via REST API.
*   **Service Indicator**: Track the serving team.
*   **Side Switching**: A swap button in the scoreboard centre column mirrors the operator UI, all 27 OBS overlay styles (behind a quick fold transition) and the public spectator page — team identity, stats and the audit log never change, only the presentation. An optional auto mode (Match Rules section) follows the physical court: switch on every set change, every 7/5 combined points in beach mode, and at the deciding-set midpoint indoors; the manual button stays usable as a correction, and an undo rewinds the orientation automatically since it's derived from the live score.
*   **Undo Capability**: Step back through recent scoring actions one at a time, including set-winning points. The bottom-bar Undo button uses the server-side LIFO stack (`POST /api/v1/game/undo`) so it survives reload and is shared between concurrent clients. Double-tap a score or timeout button on the React UI for an instant team-specific undo — both paths share the same audit-log stack.
*   **Game Modes**: Support for both **Indoor** (25 points, 5 sets) and **Beach Volleyball** (21 points, 3 sets), switchable per-session from a dedicated "Match rules" config-panel section. Beach matches surface a side-switch indicator below the set pagination ("Switch sides now" pulse on the boundary point).
*   **Match Rules Editor**: Per-session, persisted across restarts. Pick best-of-1/3/5, set custom points-per-set and points-per-final-set (best-of-1 collapses both into a single input), or reset to the indoor/beach preset.
*   **Points History Strip**: When the overlay preview is hidden, the centre column shows a two-row action timeline (one row per team) sourced from the audit log. Each rally, set win, match win, timeout and manual correction renders as a chip on its team's row only — `+1`/`−1` for points and undos, a star (or struck star on undo) when a set is won, a trophy (or struck trophy on undo) when the match ends, a clock (or struck clock on undo) for timeouts, and a pencil with the new score for manual corrections. Non-adjacent timeout undoes also reconstruct the original forward chip from the post-state diff so the timeline matches what the operator saw before clicking undo. Logo + colour markers anchor each row; honours `followTeamColors` and per-team customisation overrides. Window auto-shrinks on narrow landscape phones so it never overflows the centre slot.

### Match History
*   **Auto-archive on match end**: Every finished match is recorded as a row in the `match_reports` table (DB-backed, scoped to the owning user) with the final state, customization, audit log, and config — frozen so cosmetic edits made afterwards do not retroactively rewrite history. Browse your own reports from the account area via `GET /api/v1/matches`, fetch or delete one via `GET`/`DELETE /api/v1/matches/{id}`.
*   **Print-friendly per-match report** at `/match/{match_id}/report` (designed for the browser's "Save as PDF" workflow). The route is gated three ways: the owner's session cookie, an owner-minted signed share URL (`POST /api/v1/matches/{match_id}/sign-url`, HMAC-keyed by `SESSION_SECRET`), or fully open when `MATCH_REPORT_PUBLIC=true`.
*   **Per-OID action audit log** capturing every state mutation with a compact post-state snapshot, kept on disk as JSONL re-keyed by the per-user storage key. Exposed read-only via `GET /api/v1/audit?oid=...`.
*   **Outbound webhooks** on `set_end`, `match_end`, `timeout`, and `serve_change` events. Configure via `WEBHOOKS_URL` (single endpoint) or `WEBHOOKS_JSON` (multi-target with per-event filtering); bodies are HMAC-SHA256-signed when a secret is set.

### Advanced Customization
*   **Team Identity**: Customize team names, logos, and colors.
*   **Scoreboard Layout**: Adjust dimensions (height, width) and position (horizontal, vertical).
*   **Style-aware overlay knobs**: The Overlay section only surfaces a control where it actually changes the selected style — the **dark/light theme** selector appears for styles that ship a light/dark palette, and a **top / center / bottom** vertical-anchor selector appears for edge-pinned styles (`pylons`, `pylons_gradient`) that dock to the screen edges instead of following the free x/y geometry.
*   **Visual Effects**: Apply glossy/gradient effects.
*   **Presets**: Create, save, and load customization presets. Your own presets follow you across every scoreboard you own; admins can additionally activate global presets that all users see.

### Accounts and Overlay Management
*   **Multi-User Accounts**: Each user registers, signs in, and owns an isolated set of scoreboards, overlays, teams, presets and match reports. Sessions are HttpOnly cookies — there is no shared password or API key.
*   **Roles**: `user` and `admin`. Admins manage users, the registration toggle, the global team catalog and global presets from the in-app `/admin` page.
*   **Multi-Overlay Control**: Each account manages multiple overlays from a single instance. Overlays are keyed per user, so two accounts can independently own the same `oid`.
*   **OBS Output Tokens**: Each overlay carries an unguessable `public_token`; OBS loads `/overlay/{public_token}`, `/follow/{public_token}` and `/ws/{public_token}` — no cookie or account leaked into the URL.
*   **Internationalization**: Control UI available in **English**, **Spanish**, **Portuguese**, **Italian**, **French** and **German**, with volleyball-specific terminology per locale.

### REST + WebSocket API
*   **Session management** — initialise sessions, update match rules (`POST /api/v1/session/rules`)
*   **Game actions** — add points, sets, timeouts, change serve, reset matches; server-side undo stack (`POST /api/v1/game/undo`)
*   **Display controls** — toggle overlay visibility and simple mode
*   **Customization** — read and update team names, colors, logos
*   **History** — `GET /api/v1/matches[/{id}]` for archived match snapshots; `GET /api/v1/audit?oid=...` for the action log
*   **Real-time WebSocket** — receive instant state updates at `ws://<host>/api/v1/ws?oid=<OID>`

Every `/api/v1/*` scoreboard/control route is gated by the session cookie and per-user ownership of the `oid` — there is no Bearer path for these user routes. Auth lives under `/api/v1/auth` (register, login, logout, `GET /context`, change-password, `PATCH`/`DELETE me`, claim-admin).

For the full endpoint reference, request/response schemas, and WebSocket protocol, see [**FRONTEND_DEVELOPMENT.md**](FRONTEND_DEVELOPMENT.md).

### Built-In Overlay Engine
*   **27 Selectable Overlay Styles**: Pre-built HTML templates rendered via Jinja2 and served directly to OBS/vMix browser sources. Available styles: `default`, `baseline`, `beach`, `beach_twoline`, `broadcast`, `clear_jersey`, `compact`, `corner_gradient`, `corner_jersey`, `corner_tags`, `corner_wedge`, `diagonal`, `esports`, `glass`, `led`, `micro`, `neo_jersey`, `neon`, `original`, `pill`, `pylons`, `pylons_gradient`, `ribbon`, `shield`, `split`, `split_jersey`, `vertical`. The `corner_*` styles form the **corners** family — horizontal, corner-docked cousins of `pylons`: one chip per team pinned to a top or bottom corner (sets-won pips by the score; serve lamp and timeout bars by the team icon), with `corner_jersey` leading on a team-kit jersey icon. A meta-style `mosaic` renders every selectable style in a single preview grid via `/overlay/{public_token}?style=mosaic`.
*   **Dark/Light Overlay Theme**: A three-state appearance setting (default / dark / light) flips the card surface on styles that support it (`broadcast`, `baseline`, `neon`, `pylons`, `micro`, `led`, and dark variants for the light-native `neo_jersey`, `clear_jersey`, `split_jersey`); "default" keeps each style's native palette. Styles whose surface *is* the team colour (e.g. `glass`) intentionally ignore the toggle. A `?theme=` query on the overlay URL (or the mosaic) pins a theme per browser source. Team accents are contrast-corrected automatically against the active surface, so a dark team colour stays legible on a dark card and vice versa.
*   **Real-Time Updates**: OBS browser sources connect via WebSocket (`/ws/{public_token}`) and receive 50ms-debounced state pushes — no polling needed.
*   **Manage Overlays From Your Account**: Create and delete overlays via `/api/v1/overlays`, surfaced in the account dashboard. Each overlay exposes an unguessable `public_token` for its OBS output; render state is persisted to disk and served immediately.
*   **Preset Themes**: Apply dark, light, esports, neo_jersey, split_jersey, or clear_jersey themes with one click.

### Single-App Deployment
*   **All-in-one**: The React control UI, Python backend, and overlay engine run as a single process from a single Docker image.
*   **Local Execution**: Run locally as a standard Python application (with optional Vite dev server for frontend hot-reload).
*   **Docker Support**: Deploy easily using a single Docker container — no nginx or reverse proxy required.

---

## Getting Started

> **Multi-user application.** This is now a full multi-user app with a
> database. The landing page is a **login** screen, and every user manages
> their own scoreboards/overlays, teams, presets and match reports.
>
> **First run:** on first start, no administrator exists yet, so the service
> logs a one-time **admin bootstrap token** (visible in `docker logs`). Open
> `/claim-admin`, paste the token, and create the first administrator. After
> that, users self-register at `/register` (an admin can disable registration
> in the admin panel), and admins manage users, the global team catalog and
> global presets.
>
> **Persistence:** SQLAlchemy + Alembic via `DATABASE_URL` — SQLite by default
> (`data/app.db`), PostgreSQL supported (`postgresql+psycopg://…`). The schema
> migrates to head automatically on startup; nothing to run by hand.
>
> **Sessions:** HttpOnly cookies (the old `SCOREBOARD_USERS` Bearer auth is
> gone). The public OBS output URL for each overlay uses an unguessable token,
> so usernames/oids never appear in it. See the session-related env vars in
> the *Configuration* table below (`SESSION_SECRET`, `SESSION_TTL_HOURS`,
> `REGISTRATION_OPEN`, `ADMIN_BOOTSTRAP_TOKEN`, …).

### Prerequisites

*   **Python 3.11+**
*   **Node.js 20+** and **npm** (for building the frontend)
*   *(Optional)* An account on **[overlays.uno](https://overlays.uno)** for cloud overlays. Not needed when using the built-in overlay engine.

### Creating an Overlay

1.  **Login** to your *overlays.uno* account.
2.  Navigate to [this overlay](https://overlays.uno/library/437-Volleyball-Scorebug---Standard) and click **Add to My Overlays**.
3.  **Open your overlay** to get the necessary tokens:
    *   **Control URL**: Copy the URL. The part after `https://app.overlays.uno/control/` is your **`UNO_OVERLAY_OID`**.

### Using the Built-In Overlay Engine

The fastest way to get started is with the built-in overlay engine. Once signed in, create an overlay from your account dashboard (or via `POST /api/v1/overlays`) — say, `mybroadcast` — then use that ID directly as the OID in the control UI. Each overlay is handed an unguessable `public_token`: point OBS at `/overlay/{public_token}` (plus the `mosaic` preview grid via `?style=mosaic`) and it receives state updates over WebSocket at `/ws/{public_token}`. No external server or account is required.

### Building a Custom External Overlay

If you need a fully custom overlay engine (e.g., built in React, Vue, or Godot), you can point Remote-Scoreboard at an **external overlay server** by setting `APP_CUSTOM_OVERLAY_URL`. Refer to the [Custom Overlay Documentation](CUSTOM_OVERLAY.md) for the API contract.

---

## Usage

### Running Locally

1.  **Clone the repository** and install dependencies:
    ```bash
    pip install -U pip uv
    uv pip install -r requirements.lock -r requirements-dev.lock
    ```

2.  **Build the frontend**:
    ```bash
    cd frontend && npm ci && npm run build && cd ..
    ```

3.  **Configure Environment Variables** *(optional)*:
    Create a `.env` file in the root directory or export variables in your terminal. Nothing is required for first run — the app ships with sensible defaults and persists to SQLite at `data/app.db`. `UNO_OVERLAY_OID` is required only when using overlays.uno; set `DATABASE_URL` to point at PostgreSQL instead of SQLite.

    ```env
    # .env file (all optional)
    UNO_OVERLAY_OID=XXXXXXXX
    # DATABASE_URL=postgresql+psycopg://user:pass@host/db
    ```

4.  **Start the Application**:
    ```bash
    python main.py
    ```
    Alembic migrates the schema to head automatically on startup. The FastAPI server starts on port 8080 (configurable via `APP_PORT`). The app is available at `http://localhost:8080/` — the front door is a **login** screen.

5.  **Claim the first admin** — On the very first start with no administrator, a one-time **bootstrap token** is logged at `WARNING` level (look in the startup output / `docker logs`). Open `/claim-admin`, paste the token, and create the first admin account. After that, users self-register at `/register` (an admin can toggle registration off), and each user creates overlays from their account dashboard. The overlay's OBS output is served at `http://localhost:8080/overlay/{public_token}`. To use an *external* overlay server instead of the built-in engine, set `APP_CUSTOM_OVERLAY_URL`. See [CUSTOM_OVERLAY.md](CUSTOM_OVERLAY.md) for details.

> **Tip:** For frontend development with hot-reload, run `cd frontend && npm run dev` alongside `python main.py`. Vite serves on port 3000 and proxies API calls to the backend on port 8080.

### Running with Docker

The Dockerfile uses a multi-stage build: Node.js builds the React frontend, then the result is copied into the Python image. No separate frontend container or nginx is needed.

1.  Create a `.env` file (everything here is optional):
    ```env
    EXTERNAL_PORT=80
    APP_TITLE=MyScoreboard
    # UNO_OVERLAY_OID=<overlay_control_token>   # only for overlays.uno
    # DATABASE_URL=postgresql+psycopg://user:pass@host/db  # default: SQLite under data/
    ```
2.  Run Docker Compose:
    ```bash
    docker-compose up -d
    ```
3.  **Claim the first admin:** read the one-time bootstrap token from the
    startup log (`docker-compose logs app` — logged at `WARNING`), open
    `/claim-admin`, and create the first administrator. The SQLite database,
    session secret and bootstrap/overlay-server token files all live under
    `data/`, so persist that directory across container restarts.

### Upgrading from a single-tenant deployment

> ⚠️ **This is a clean break — there is no automatic data migration.** The
> multi-user app keys runtime data per user (`"<user_id>:<oid>"`) instead of by
> the bare overlay id, so an older single-tenant deployment's on-disk data is
> **not** carried over: pre-existing `data/overlay_state_*.json`,
> `data/audit_*.jsonl`, and the old file-based `data/matches/` archive are left
> orphaned (nothing is deleted, but the new app never reads them).
>
> To upgrade, **start from a fresh `data/` directory**: let the app create a new
> database, claim the first admin from the startup-log token, then recreate your
> users, overlays, teams and presets. An existing **teams/presets catalog** can
> be carried across with the admin JSON import (the **Teams** and **Presets**
> admin pages, or `POST /api/v1/admin/{teams,presets}/import`). In-progress
> overlay state and historical match reports are not migrated.

---

## Configuration

Configure the application using the following environment variables:

| Variable | Description | Default Value |
| :--- | :--- | :--- |
| `UNO_OVERLAY_OID` | The control token for your overlays.uno overlay. | |
| `APP_PORT` | The TCP port where the application will run. | `8080` |
| `APP_TITLE` | Application title shown in the browser tab, the init screen heading and the PWA manifest. | `Volley Scoreboard` |
| `APP_CUSTOM_OVERLAY_URL` | *(Optional)* Base URL of an external custom overlay server. When set, custom overlays use the external server instead of the built-in engine. | *(unset — built-in engine)* |
| `APP_CUSTOM_OVERLAY_OUTPUT_URL` | *(Optional)* Public-facing base URL for overlay links. Used to replace the host in output URLs when the overlay server is behind a proxy. | |
| `OVERLAY_PUBLIC_URL` | *(Optional)* Public base URL for overlay output links served by the built-in engine. If unset, URLs are constructed from the request's host. | |
| `MATCH_GAME_POINTS` | Points needed to win a set. | `25` |
| `MATCH_GAME_POINTS_LAST_SET` | Points needed to win the last set. | `15` |
| `MATCH_SETS` | Total sets in the match (best of N). | `5` |
| `STALE_SET_THRESHOLD_MINUTES` | Minutes a single set may run before the control-UI "match looks abandoned" prompt fires on the next page load. `0` disables the prompt entirely (useful for long all-day tournaments). Negative values clamp to `0`; non-numeric values fall back to the default. | `60` |
| `ORDERED_TEAMS` | If `true`, the team list will be displayed in alphabetical order. | `true` |
| `ENABLE_MULTITHREAD` | If `true`, overlay API calls run in a thread pool. | `true` |
| `LOGGING_LEVEL` | Log level (`debug`, `info`, `warning`, `error`). | `warning` |
| `LOG_FORMAT` | Log output format: `text` (ANSI-coloured, for dev) or `json` (one JSON object per line, for log aggregators). | `text` |
| `LOG_FILE` | *(Optional)* Path to a rotating log file. When set, a file handler is attached alongside stdout; when unset, logs go to stdout only. | |
| `LOG_FILE_MAX_BYTES` | Rotation threshold for `LOG_FILE` in bytes. | `10485760` (10 MiB) |
| `LOG_FILE_BACKUPS` | Number of rotated log files to retain. | `5` |
| `LOG_REDACT` | If `true`, PII fields (OIDs, URLs) are redacted in log output and error reports from the SPA. | `true` |
| `REST_USER_AGENT` | User-Agent to avoid Cloudflare bot detection. | `curl/8.15.0` |
| `DATABASE_URL` | SQLAlchemy 2.0 database URL. SQLite by default; point at PostgreSQL (`postgresql+psycopg://…`) with no code change. Alembic migrates to head automatically on startup. | `sqlite:///data/app.db` |
| `SESSION_SECRET` | Secret that hardens cookie sessions and signs report share URLs. **Auto-minted and persisted to `data/.session_secret` on first start when unset.** | *(auto)* |
| `SESSION_COOKIE_SECURE` | Forces the `Secure` flag on the `vsession` cookie. By default it is set automatically when the request is served over HTTPS. | *(auto over HTTPS)* |
| `SESSION_TTL_HOURS` | Lifetime of a login session in hours. | `336` (14 days) |
| `REGISTRATION_OPEN` | Whether self-service registration at `/register` is allowed. DB-backed after first boot; admins toggle it from the `/admin` page. | `true` |
| `ADMIN_BOOTSTRAP_TOKEN` | First-admin bootstrap token. When unset, a one-time token is minted on first start, logged at `WARNING`, and persisted to `data/.admin_bootstrap_token` (mode `0600`). Set it explicitly to pin a known value. See [AUTHENTICATION.md](AUTHENTICATION.md). | *(auto)* |
| `OVERLAY_SERVER_TOKEN` | Bearer token required by the built-in overlay server's mutation and config endpoints (peer/machine auth). **Auto-generated and persisted to `data/.overlay_server_token` on first start when unset.** Set explicitly here to override (e.g. when an external `CustomOverlayBackend` peer must use the same value). See [AUTHENTICATION.md](AUTHENTICATION.md) §5. | *(auto)* |
| `OVERLAY_SERVER_TOKEN_HASH` | scrypt-hashed alternative to `OVERLAY_SERVER_TOKEN`. When set, the bootstrap skips auto-generating the persisted plaintext file — a hash-only deployment keeps zero cleartext on this server (the peer keeps the cleartext). | |
| `OVERLAY_SERVER_TOKEN_DISABLED` | If `true`, opts back into legacy unauthenticated overlay-server endpoints. The bootstrap logs a `CRITICAL` startup warning when active. Only safe on a trusted LAN. | `false` |
| `TRUSTED_HOSTS` | Comma-separated allow-list of hostnames the app accepts in the `Host` header. Wildcard subdomains (`*.example.com`) supported. Requests outside the list are rejected with HTTP 400 before any handler reads `request.base_url`. See [AUTHENTICATION.md](AUTHENTICATION.md) §6.2. | *(unset → no enforcement)* |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allow-list of origins permitted to call the API cross-origin. `*` is rejected (credentialed API; explicit origins only). Default: same-origin only. See [AUTHENTICATION.md](AUTHENTICATION.md) §6.3. | *(unset → no CORS)* |
| `REMOTE_CONFIG_URL` | URL to a remote JSON file with non-account configuration fetched on startup. | |
| `MINIMIZE_BACKEND_USAGE` | If `true`, caches customization responses to reduce API round-trips. | `true` |
| `CUSTOMIZATION_CACHE_TTL_SECONDS` | Single knob overriding the TTL (seconds) of both customization caches. When unset, the GameService cache defaults to `5` and the Backend cache to `60`. | *(per-cache defaults)* |
| `METRICS_REQUIRE_ADMIN` | If `true`, `GET /metrics` is gated behind the `OVERLAY_SERVER_TOKEN` Bearer. Default: the Prometheus exposition is unauthenticated (aggregates only — no payloads, no per-OID labels). | `false` |
| `APP_DEFAULT_LOGO` | URL of the fallback team logo used when a team has none configured. | *(flaticon volleyball icon)* |
| `DEFAULT_TEAM_LOGO` | Logo path baked into a blank in-process overlay state (used by the built-in overlay server when an overlay is created). | `/static/images/default_volleyball.svg` |
| `SET_SUMMARY_DEFAULT_STYLE` | Default style of the between-sets summary panel. | `brand_ledger` |
| `OVERLAY_LOCALE` | Fallback locale for overlay rendering when neither the `?lang=` query parameter nor a persisted overlay locale is present. | *(browser/`en`)* |
| `UNO_OVERLAY_ID` | Internal instance identifier sent to overlays.uno. Rarely needs changing. | *(fixed UUID)* |
| `APP_RELOAD` | Development only: if `true`, runs uvicorn with auto-reload. | `false` |
| `UNO_OVERLAY_OUTPUT` | Custom output URL override for the overlay display link. | |
| `WEBHOOKS_URL` | *(Optional)* Single outbound webhook endpoint. POSTed JSON `{event, oid, ts, state, details}` on `set_end`, `match_end`, `timeout`, `serve_change`. | |
| `WEBHOOKS_SECRET` | *(Optional)* Shared secret for HMAC-SHA256 signing of single-URL webhook bodies. Sent as `X-Webhook-Signature: sha256=<hex>`. | |
| `WEBHOOKS_EVENTS` | *(Optional)* CSV subset of events the single-URL webhook should receive. | *(all events)* |
| `WEBHOOKS_TIMEOUT_S` | *(Optional)* Per-target POST timeout in seconds. | `5` |
| `WEBHOOKS_JSON` | *(Optional)* JSON list of webhook targets, e.g. `[{"url":"…","secret":"…","events":["set_end"],"timeout_s":5}]`. Takes precedence over `WEBHOOKS_URL`. | |
| `WEBHOOKS_ALLOW_PRIVATE_IPS` | If `true`, allows webhook targets whose host resolves to private / loopback / link-local IPs. Default: `false` — such targets are rejected with a logged warning to block accidental SSRF (`http://localhost/admin`, cloud metadata at `169.254.169.254`, etc.). Trusted-LAN deployments that need to call internal receivers opt in here. | `false` |
| `MATCH_REPORT_PUBLIC` | If `true`, `/match/{id}/report` is reachable by anyone, with no cookie or signed URL required. When unset, the report is reachable only by its owner's session cookie or an owner-minted signed share URL. | `false` |

<br>

### Accounts, Teams and Presets

Teams and presets are stored in the database, not in environment variables:

*   **Teams** — A global catalog (curated and activated by admins) plus each
    user's own team list. Users work with `/api/v1/teams`, `/teams/catalog`,
    `/teams/mine`, and admin-published `/team-groups` (with
    `/team-groups/{id}/copy-to-mine`). Admins manage the catalog under
    `/api/v1/admin/teams…` and `/admin/team-groups…`.
*   **Presets** — A user's own customization presets follow them across all
    of their scoreboards; admins can additionally activate global presets that
    every user sees. Users work with `/api/v1/customization/presets`
    (`GET`/`POST`/`DELETE {slug}`); admins manage globals under
    `/api/v1/admin/presets…`.
*   **Migration import/export** — Admins can bulk-import and export teams and
    presets as JSON. The team payload follows the legacy `APP_TEAMS` shape and
    the preset payload follows the legacy `APP_THEMES` shape; these formats
    now live only as the admin import/export JSON contract, not as runtime
    environment variables.

#### Team import/export JSON (`APP_TEAMS` shape)
```json
{
    "Local": {
        "icon": "https://cdn-icons-png.flaticon.com/512/8686/8686758.png",
        "color": "#060f8a",
        "text_color": "#ffffff"
    },
    "Visitor": {
        "icon": "https://cdn-icons-png.flaticon.com/512/8686/8686758.png",
        "color": "#ffffff",
        "text_color": "#000000"
    }
}
```

#### Preset import/export JSON (`APP_THEMES` shape)
```json
{
    "Change position and show logos theme": {
        "Height": 10,
        "Left-Right": -33.5,
        "Logos": true
    },
    "Change only game status colors": {
        "Game Status Color": "#252525",
        "Game Status Text Color": "#ffffff"
    }
}
```

### Overlay server token (`OVERLAY_SERVER_TOKEN`)

When the built-in overlay server is mounted (i.e. the `overlay_templates/`
directory is present), its mutation and config endpoints are gated behind
a Bearer token. Every request to the following routes must include
`Authorization: Bearer <token>`:

- `POST /api/state/{id}`
- `GET` / `POST /create/overlay/{id}`
- `GET` / `POST` / `DELETE /delete/overlay/{id}`
- `GET` / `POST /api/raw_config/{id}`
- `GET /api/config/{id}`
- `POST /api/theme/{id}/{name}`

The token is **auto-generated and persisted to `data/.overlay_server_token`
on first start**. Subsequent restarts reuse the same value, so an external
`CustomOverlayBackend` peer pointed at this app via
`APP_CUSTOM_OVERLAY_URL` only needs to be configured once: read the value
from the persisted file or set `OVERLAY_SERVER_TOKEN` explicitly on both
sides.

To opt back into the legacy unauthenticated behaviour (e.g. for a
trusted-LAN install or local debugging), set
`OVERLAY_SERVER_TOKEN_DISABLED=true`. A `CRITICAL` startup warning is
logged whenever this opt-out is active so the choice is visible in the
startup tail.

The OBS capability URLs (`/overlay/{public_token}` and `/ws/{public_token}`)
are intentionally **not** gated by this token — they are the public-by-design
entry points that OBS loads.

See [AUTHENTICATION.md](AUTHENTICATION.md) for the full route inventory.

### Remote Configuration
Import non-account configuration from an external resource via `REMOTE_CONFIG_URL`. The application fetches this JSON file on startup. (Teams and presets are no longer sourced remotely — they live in the database; see *Accounts, Teams and Presets* above.)

### Available Endpoints

| Endpoint | Description |
| :--- | :--- |
| `/` | Account dashboard (React SPA; redirects to `/login` when unauthenticated) |
| `/login` · `/register` · `/claim-admin` · `/admin` | SPA routes for sign-in, self-registration, first-admin claim, and the admin panel |
| `/board?oid=X` | Scoreboard / control screen (SPA route, scoped to the signed-in user) |
| `/api/v1/...` | REST API (see [FRONTEND_DEVELOPMENT.md](FRONTEND_DEVELOPMENT.md)) |
| `/api/v1/auth/...` | Account auth: `register`, `login`, `logout`, `GET context`, `change-password`, `PATCH`/`DELETE me`, `claim-admin`. |
| `/api/v1/admin/users` | Admin user management (create with temp password, reset-to-temp, set role/active, delete) plus the registration toggle. |
| `/api/v1/overlays` | Manage the signed-in user's overlays (list/create/delete; each carries a `public_token`). |
| `/api/v1/app-config` | Runtime SPA bootstrap config (currently `{ title }`). Used by the SPA on load. |
| `/api/v1/_log` | `POST` endpoint for SPA client-side error reports. Rate-limited per peer IP; unauthenticated by design. |
| `/api/v1/ws?oid=X` | WebSocket for real-time state updates (frontend; cookie-authenticated). |
| `/api/v1/session/rules?oid=X` | `POST` — update match rules (`mode` indoor/beach, `points_limit`, `points_limit_last_set`, `sets_limit`, `reset_to_defaults`). Backs the React config panel's "Match rules" section. |
| `/api/v1/audit?oid=X[&limit=N]` | `GET` — recent records from the per-OID action audit log (default `limit=100`, max `1000`). |
| `/api/v1/matches[?oid=X]` | `GET` — list the user's archived match reports, newest first (optional OID filter). |
| `/api/v1/matches/{match_id}` | `GET`/`DELETE` — full archived match snapshot, or delete it. |
| `/api/v1/matches/{match_id}/sign-url` | `POST` — owner mints an HMAC-signed share URL for the printable report. |
| `/api/v1/game/undo` | `POST` — pop the last forward `add_point`/`add_set`/`add_timeout` from the audit log and reverse it. Returns 200 with `success=false` and `message="Nothing to undo."` when the log is empty. |
| `/match/{match_id}/report` | `GET` — print-friendly HTML match report. Reachable by the owner's session cookie, an owner-minted signed URL, or by anyone when `MATCH_REPORT_PUBLIC=true`. |
| `/overlay/{public_token}` | Overlay HTML for OBS browser sources (built-in engine; no cookie). `?style=mosaic` renders a preview grid of every selectable style. |
| `/follow/{public_token}` | Public mobile-first spectator page (no cookie). |
| `/ws/{public_token}` | WebSocket for OBS browser sources (overlay state broadcast; no cookie). |
| `/api/config/{id}` | Overlay config (output URL, available styles) |
| `/api/themes` | List preset overlay themes |
| `/health` | Health check endpoint. Returns `200 OK` with a timestamp. |

For a full audit of every route and its authentication requirements
(including the overlay server endpoints consumed by OBS and
`CustomOverlayBackend`), see [AUTHENTICATION.md](AUTHENTICATION.md).

---

## Troubleshooting

| Issue | Solution |
| :--- | :--- |
| App won't start | Check logs for errors (Alembic runs migrations on startup). Ensure the `data/` directory is writable. `UNO_OVERLAY_OID` is required only when using overlays.uno. |
| Overlay not updating | Ensure the overlay control token is valid. Try calling `POST /api/v1/session/init` again. |
| Docker container crashes | Check logs with `docker-compose logs app`. Ensure all environment variables in `.env` are properly formatted (especially JSON values). |
| "Outdated overlay version" error | Your overlay was created before March 2025. Create a new overlay from the [overlays.uno library](https://overlays.uno/library/437-Volleyball-Scorebug---Standard). |
| Can't sign in on first run | No administrator exists yet. Check the startup log / `docker logs` for the one-time bootstrap token (logged at `WARNING`), then claim the first admin at `/claim-admin`. The token is also persisted to `data/.admin_bootstrap_token`. |
| Custom overlay not receiving updates | Confirm the overlay exists (create it from your account dashboard if needed) and that OBS is pointed at its `public_token` URL (`/overlay/{public_token}`). For built-in overlays, check that `overlay_templates/` exists. For external overlays, verify `APP_CUSTOM_OVERLAY_URL` is reachable. See [Custom Overlay docs](CUSTOM_OVERLAY.md). |

---

## Contributing

Contributions are welcome! Here's how to get started:

1.  **Fork** the repository and create a feature branch.
2.  **Install dependencies** and ensure tests pass:
    - Backend: `uv pip install -r requirements.lock -r requirements-dev.lock && pytest tests/`
    - Frontend: `cd frontend && npm ci && npm test`
3.  **Follow existing patterns** — see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) for architecture and conventions.
4.  **Submit a Pull Request** against the `dev` branch with a clear description of your changes.

For custom overlay development, see [CUSTOM_OVERLAY.md](CUSTOM_OVERLAY.md).

---

## License

This project is licensed under the **Apache License 2.0**. See the [LICENSE](LICENSE) file for details.

---

## Disclaimer

This software was developed as a personal project and is provided **as-is**. It was built iteratively and may lack comprehensive error handling.

> [!CAUTION]
> **Security Warning:** Although the app uses per-user accounts with HttpOnly cookie sessions, it was built for trusted, small-scale use. **Do not expose this application directly to the internet without additional security measures** (HTTPS termination, `TRUSTED_HOSTS`, a strong `SESSION_SECRET`, and a locked-down registration policy).

**Use at your own risk.**
