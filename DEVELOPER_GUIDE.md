# Developer Guide — Volley Overlay Control

> A comprehensive reference for developers contributing to or extending the Volley Overlay Control codebase. For user-facing setup and configuration, see [README.md](README.md).

---

## 1. Project Overview

Volley Overlay Control is a self-contained, **multi-user** application that bundles a React frontend, a Python/FastAPI backend, and an overlay serving engine into a single deployable service. It manages game logic (score, sets, serving, timeouts), authenticates users with cookie sessions and roles, serves the touch-friendly control UI, renders overlay templates for OBS browser sources, and synchronizes state with the in-process overlay engine. Each user owns their own overlays, teams, presets, and match reports; durable state lives in a SQL database (SQLite by default, Postgres optional).

The React frontend lives in the `frontend/` directory and is built with Vite. In production, FastAPI serves the built SPA as static files. During development, Vite's dev server provides hot-reload and proxies API calls to the backend.

### Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Frontend** | React 19, Vite, PWA (vite-plugin-pwa) |
| **REST API** | FastAPI router at `/api/v1/` with WebSocket real-time updates |
| **HTTP Server** | Uvicorn (ASGI) — serves both the API and the frontend SPA |
| **Backend Logic** | Python 3.x |
| **Persistence** | SQLAlchemy 2.0 ORM + Alembic migrations (SQLite default, Postgres via `postgresql+psycopg://`); in-memory + JSON file persistence for live overlay rendering state |
| **Auth** | HttpOnly cookie sessions (opaque token, hashed server-side) with `user`/`admin` roles |
| **Overlay Templates** | Jinja2 HTML templates for OBS browser sources (16 styles) |
| **Containerization** | Docker (multi-stage: Node.js + Python) |
| **CI/CD** | GitHub Actions pipelines (`.github/workflows/`) for automated testing and linting |

### Key Dependencies

**Backend (Python):**

| Package | Purpose |
| :--- | :--- |
| `fastapi` | REST API framework + static file serving |
| `uvicorn` | ASGI server |
| `sqlalchemy` | ORM + engine for the multi-user database (users, overlays, teams, presets, reports, settings) |
| `alembic` | Schema migrations (auto-run on startup, also `alembic upgrade head`) |
| `psycopg` | Postgres driver (optional — only needed for `postgresql+psycopg://`) |
| `requests` | HTTP utility library |
| `jinja2` | Overlay HTML template rendering for OBS browser sources |
| `python-dotenv` | `.env` file loading |
| `pytest` / `pytest-asyncio` | Test suite |

Passwords and session/share tokens are hashed with the Python standard
library (`hashlib.scrypt` / SHA-256) — there is no `bcrypt`/`passlib`
dependency.

**Frontend (Node.js):**

| Package | Purpose |
| :--- | :--- |
| `react` / `react-dom` | UI framework |
| `react-colorful` | Color picker component |
| `vite` | Build tool and dev server |
| `vite-plugin-pwa` | PWA support (service worker, manifest) |
| `vitest` / `@testing-library/react` | Test suite |

---

## 2. Directory Structure & Key Files

```
├── main.py                  # Entry point. Validates config, sets up logging, calls create_app(), starts uvicorn.
├── alembic.ini              # Alembic configuration (migration scripts dir, logging).
├── migrations/              # Alembic environment + versioned migration scripts.
│   ├── env.py               # Resolves DATABASE_URL, targets Base.metadata.
│   └── versions/            # Migration revisions (starts at 0001_initial; the schema baseline).
├── Dockerfile               # Multi-stage build (Node.js + Python).
├── docker-compose.yml       # Docker Compose configuration.
├── frontend/                # React control UI (built with Vite, TypeScript).
│   ├── package.json         # Frontend dependencies and scripts.
│   ├── vite.config.js       # Vite config (PWA, dev proxy, test setup).
│   ├── index.html           # SPA entry point.
│   ├── src/                 # React source code.
│   │   ├── App.tsx          # Main application component.
│   │   ├── api/client.ts    # REST API client (relative paths: /api/v1/).
│   │   ├── api/websocket.ts # WebSocket client (relative URLs).
│   │   ├── api/schema.d.ts  # Generated OpenAPI type definitions.
│   │   ├── components/      # UI components (TeamPanel, ConfigPanel, etc.).
│   │   ├── constants.ts     # Centralised tunable constants (timing, history cap).
│   │   ├── hooks/           # React hooks (useGameState, useSettings, useDoubleTap, etc.).
│   │   ├── i18n.tsx         # Internationalization.
│   │   ├── theme.ts         # Theme constants.
│   │   └── test/            # Vitest test suite.
│   └── public/              # Static assets (icons, fonts).
├── app/
│   ├── bootstrap.py         # App factory — create_app() wires security/migrations/admin bootstrap, routers, SPA.
│   ├── backend.py           # Coordinator — delegates to the in-process overlay backend.
│   ├── overlay_backends/    # Strategy pattern package: base, local, utils (resolver).
│   ├── game_manager.py      # Core business logic (rules, scoring, limits).
│   ├── state.py             # Data model definition. Holds the match state.
│   ├── customization.py     # Logic for handling team names, colors, logos, and layout.
│   ├── conf.py              # Configuration object mapping env vars to settings.
│   ├── constants.py         # Centralized hardcoded strings, URLs, and favicon.
│   ├── overlay_key.py       # Per-user storage-key helpers: make_skey/split_skey ("<user_id>:<oid>").
│   ├── id_validation.py     # Overlay-ID charset/length validation.
│   ├── password_hash.py     # scrypt credential hashing (stdlib, zero deps).
│   ├── security_bootstrap.py # Resolve/mint/persist SESSION_SECRET at startup.
│   ├── app_storage.py       # In-memory key-value storage.
│   ├── oid_utils.py         # OID parsing utilities (extract_oid).
│   ├── db/                  # SQLAlchemy persistence layer.
│   │   ├── base.py          # Declarative Base + TimestampMixin (naming convention).
│   │   ├── engine.py        # Engine/sessionmaker from DATABASE_URL; session_scope() + get_db() dep.
│   │   ├── migrate.py       # run_migrations() — in-process `alembic upgrade head` (cross-process file lock).
│   │   └── models/          # ORM models: user (User, AuthSession), overlay (UserOverlay + public_token,
│   │       │                #   OverlaySessionMeta), team, preset (Preset), report (MatchReport), setting.
│   ├── auth/                # Cookie-session authentication + account management.
│   │   ├── passwords.py     # hash/verify (thin layer over password_hash) + temp-password generator.
│   │   ├── sessions.py      # Opaque cookie `vsession`; SHA-256 hash stored in auth_sessions.
│   │   ├── dependencies.py  # current_user / require_user / require_admin FastAPI deps.
│   │   ├── service.py       # User CRUD, authenticate, password/role/active changes.
│   │   ├── routes.py        # /api/v1/auth/* (register, login, logout, me, change-password, claim-admin).
│   │   ├── bootstrap.py     # First-admin claim flow (startup-logged token → claim-admin).
│   │   └── schemas.py       # Pydantic auth request/response models.
│   ├── teams_service.py     # DB-backed teams (global catalog, admin team-groups, per-user lists).
│   ├── presets_service.py   # DB-backed customization presets (global + per-user).
│   ├── settings_service.py  # DB-backed settings (REGISTRATION_OPEN, admin-bootstrap-claimed): env-seed-then-DB-override.
│   ├── overlays_service.py  # Per-user overlay CRUD + public_token + skey resolution.
│   ├── match_report.py      # Server-rendered print report router at /match/{id}/report.
│   ├── match_report_access.py # Read gate: owner cookie / signed URL / MATCH_REPORT_PUBLIC.
│   ├── match_report_signing.py # HMAC capability URLs derived from SESSION_SECRET.
│   ├── api/                 # REST API + WebSocket layer for frontends.
│   │   ├── __init__.py      # Re-exports api_router.
│   │   ├── routes/          # Domain-split endpoint modules under /api/v1/ (game, session, state,
│   │   │   │                #   overlays, teams, matches, customization, websocket, admin_users, metrics, ...).
│   │   ├── schemas.py       # Pydantic request/response models.
│   │   ├── game_service.py  # Service layer — single entry point for all game actions.
│   │   ├── session_manager.py # Thread-safe game session management, keyed by skey.
│   │   ├── match_archive.py # Archives finished matches to the match_reports table.
│   │   ├── ws_hub.py        # WebSocket notification hub for real-time state push.
│   │   ├── middleware/      # ASGI middleware (auth rate-limit, metrics, security headers, logging, errors).
│   │   └── dependencies.py  # verify_api_key (= require_user) + get_session keyed by skey.
│   ├── overlay/             # In-process overlay serving (absorbed from volleyball-scoreboard-overlay).
│   │   ├── __init__.py      # Package init — creates singleton OverlayStateStore & ObsBroadcastHub.
│   │   ├── state_store.py   # Overlay state management — in-memory + JSON file persistence.
│   │   ├── broadcast.py     # OBS WebSocket broadcast hub — debounced 50ms pushes.
│   │   └── routes.py        # Public OBS surface: /overlay|follow|ws/{public_token}, /api/themes.
│   ├── env_vars_manager.py  # Dynamic environment variable management.
│   ├── logging_config.py    # Logging level configuration.
│   ├── config_validator.py  # Startup configuration validation (env var checks).
│   └── pwa/                 # Legacy PWA assets (icons).
├── overlay_templates/       # Jinja2 HTML templates for overlay styles (16 templates).
├── overlay_static/          # Static assets for overlays (JS, CSS, images).
├── data/                    # Runtime data dir: SQLite app.db (default), live overlay state JSON,
│                            #   audit logs, and minted-token files (.session_secret, .admin_bootstrap_token, etc.).
├── font/                    # Custom font files for the overlay.
└── tests/                   # Pytest suite.
    ├── conftest.py          # Test fixtures: in-memory SQLite db_session, make_user, login_client, auth_client, app_client.
    ├── test_api.py          # API layer tests (SessionManager, GameService, auth).
    ├── test_auth.py         # Cookie-session auth + account-management tests.
    ├── test_admin_users.py  # Admin user-management endpoint tests.
    ├── test_bootstrap.py    # App-factory / first-admin bootstrap tests.
    ├── test_db_migrations.py # Alembic migration tests.
    ├── test_overlays_service.py # Per-user overlay CRUD + public_token tests.
    ├── test_teams.py        # DB-backed teams (catalog/groups/lists) tests.
    ├── test_match_archive.py # match_reports archiving tests.
    ├── test_match_report.py # Print-report rendering + access-gate tests.
    ├── test_backend.py      # Backend API communication tests.
    ├── test_customization.py # Customization logic tests.
    ├── test_env_vars_manager.py # Environment variable manager tests.
    ├── test_game_manager.py     # Game rules and scoring tests.
    ├── test_state.py            # State model tests.
    └── test_config_validator.py # Startup configuration validation tests.
```

---

## 3. Core Architecture & Data Flow

The application follows a service-oriented architecture:

| Role | Component | Description |
| :--- | :--- | :--- |
| **Model** | `State` | Snapshot of the game (scores, timeouts, serve status) |
| **Controller** | `GameManager` | Manipulates the Model based on volleyball rules |
| **Service** | `GameService` | Single entry point for all game actions |
| **API** | `api/routes/` | REST + WebSocket endpoints for frontends (domain-split modules) |
| **Auth** | `app/auth/` | Cookie sessions, roles, account management |
| **Persistence** | `app/db/` | SQLAlchemy engine/models — users, overlays, teams, presets, reports, settings |
| **Sync** | `Backend` | Pushes Model changes to the in-process overlay backend |
| **Overlay** | `OverlayStateStore` | In-memory + JSON persistence for live overlay render state |
| **Overlay** | `ObsBroadcastHub` | Debounced WebSocket broadcasts to OBS browser sources |

Every authenticated surface is keyed by a **storage key** `skey =
"<user_id>:<oid>"` (`app/overlay_key.py`): the `SessionManager`,
`OverlayStateStore`, audit log, session-meta persistence, and match archive
are all re-keyed by `skey` so two users can drive the same `oid` in
isolation. The public OBS output is addressed by an unguessable
`public_token` (stored on the user's overlay row), never by `oid`.

### Data Flow (e.g., Adding a Point from a JS Frontend)

```mermaid
sequenceDiagram
    participant JS as JS Frontend
    participant API as REST API
    participant GS as GameService
    participant GM as GameManager
    participant WS as WSHub
    participant Backend as Backend

    JS->>API: POST /api/v1/game/add-point?oid=X
    API->>GS: add_point(session, team=1)
    GS->>GM: add_game(team=1)
    GM->>GM: Validate & increment score
    GS->>GM: save()
    GM->>Backend: Push state to overlay
    GS->>WS: broadcast(state)
    WS-->>JS: WebSocket: {"type":"state_update", "data":{...}}
    API-->>JS: HTTP 200 ActionResponse
```

See [FRONTEND_DEVELOPMENT.md](FRONTEND_DEVELOPMENT.md) for the complete API reference.

---

## 4. Class & Method Reference

### A. Core Logic

#### `app/state.py` — class `State`

Represents the data structure of the match.

- **Responsibility**: Holds the "Single Source of Truth" dictionary (`current_model`) that maps keys (e.g., `'Team 1 Sets'`) to values.
- **Key Methods**:
  - `get_game(team, set)` / `set_game(...)` — Get/Set points for a specific set.
  - `get_sets(team)` / `set_sets(...)` — Get/Set sets won.
  - `simplify_model(simplified)` — Prepares the state for "simple mode" (reduced data payload).

#### `app/game_manager.py` — class `GameManager`

The "Brain" of the application. Enforces volleyball rules.

- **Responsibility**: Manipulate `State` safely.
- **Key Methods**:
  - `add_game(team, ...)` — Increments score. Handles "Winning by 2", point limits, and match completion.
  - `add_set(team)` — Increments set count and resets serve. Timeouts are tracked per-set, so the new set's counter naturally starts at 0 while the prior set's history is preserved (undoing a set-winning point across a set boundary brings the previous set's timeouts back).
  - `change_serve(team)` — Updates the serving indicator.
  - `match_finished()` — Returns `True` if a team has reached the set limit.
  - `save(simple, current_set)` — Persists state via `Backend`.

#### `app/backend.py` — class `Backend`

The "Bridge" to the overlay engine.

- **Responsibility**: Coordinates overlay communication using the strategy pattern. Delegates to `LocalOverlayBackend`, the in-process overlay engine that serves every overlay.
- **Key Internals**:
  - Uses a shared `requests.Session` for all HTTP calls to enable TCP connection reuse.
  - A `ThreadPoolExecutor` (5 workers) handles overlay updates asynchronously when `ENABLE_MULTITHREAD=true`.
  - `_customization_cache` — In-memory cache for the last fetched customization state.
  - `_build_overlay_payload()` — Constructs the standardized overlay state JSON from game model + customization.
- **Key Methods**:
  - `get_current_model()` — Fetches the last known state from the overlay backend.
  - `get_current_customization()` — Fetches team/color/layout settings.
  - `save_model(current_model, simple)` — Pushes local state changes to the overlay.
  - `change_overlay_visibility(show)` — Toggles overlay show/hide.

#### `app/overlay_backends/` — Overlay Backend Strategy

The overlay backend implementation in `local.py` provides the `OverlayBackend` interface defined in `base.py`; `utils.py` holds the per-request resolver:

- **`LocalOverlayBackend`** — Serves every overlay in-process (the legacy `C-` prefix is also accepted for backward compatibility). Manages state via `OverlayStateStore`, broadcasts to OBS via `ObsBroadcastHub`. No external server needed.

#### `app/overlay/state_store.py` — class `OverlayStateStore`

In-memory + JSON file persistence for overlay state.

- **Responsibility**: Manages overlay state with lazy-loading from disk, deep merge, normalization, CRUD, raw config pass-through, output key generation, and style enumeration.
- **Key Methods**: `get_state()`, `update_state()`, `set_raw_config()`, `get_raw_config()`, `create_overlay()`, `ensure_overlay()`, `get_available_styles_list()`, `get_renderable_styles()`.
- **Style enumeration** distinguishes two lists: `get_available_styles_list()` returns user-selectable styles (what the `GET /api/v1/styles` endpoint exposes and what the picker UI shows); `get_renderable_styles()` is a superset that also includes meta-styles like `mosaic` — valid as a `?style=` URL parameter but hidden from the picker so users cannot accidentally adopt them as a broadcast layout.

#### `app/overlay/broadcast.py` — class `ObsBroadcastHub`

Debounced WebSocket broadcasts to OBS browser sources.

- **Responsibility**: Tracks OBS browser source WebSocket connections per overlay and broadcasts state updates with 50ms debouncing.
- **Key Methods**: `add_client()`, `remove_client()`, `schedule_broadcast()`, `get_client_count()`.

### B. API Layer

#### `app/api/game_service.py` — class `GameService`

Stateless service that operates on `GameSession` instances.

- **Key Methods**: `add_point()`, `add_set()`, `add_timeout()`, `change_serve()`, `set_score()`, `reset()`, `set_visibility()`, `set_simple_mode()`, `update_customization()`.

#### `app/api/session_manager.py` — class `SessionManager`

Thread-safe singleton managing `GameSession` instances keyed by storage key (`skey = "<user_id>:<oid>"`), so each user's session for an `oid` is isolated.

- **Key Methods**: `get_or_create()`, `get()`, `remove()`, `clear()`, `cleanup_expired()`.

#### `app/api/ws_hub.py` — class `WSHub`

WebSocket notification hub for broadcasting state updates to connected frontend clients.

#### `app/api/routes/overlays.py` — per-user overlays

The control UI manages a user's own overlays through `/api/v1/overlays`
(list/create/update/delete). Each overlay row carries a user-facing `oid`
(unique per user) and an unguessable `public_token` for the OBS output.
Backed by `app/overlays_service.py`; there is no longer a standalone,
password-protected `/manage` page or `custom-overlays` admin API.

#### `app/api/routes/admin_users.py` — admin user management

`router` mounted at `/api/v1/admin` — list/create/update/delete users,
reset a user to a temp password, and toggle the `REGISTRATION_OPEN`
setting. Every endpoint is gated by `Depends(require_admin)`.

> For the full per-route authentication matrix (scoreboard API, admin
> API, overlay server, static mounts) and known gaps, see
> [AUTHENTICATION.md](AUTHENTICATION.md).

### B2. Authentication & Persistence

#### `app/auth/` — cookie-session authentication

Replaces the old env-var `SCOREBOARD_USERS` Bearer ladder. A login mints a
random opaque token stored in an **HttpOnly** cookie named `vsession`; only
its SHA-256 hash is persisted in the `auth_sessions` table (server-side
storage is what makes logout and "log out everywhere on password change"
possible). Accounts carry a `user`/`admin` role.

- **`sessions.py`** — create/resolve/revoke sessions; cookie set/clear.
- **`dependencies.py`** — `current_user` (resolve or `None`),
  `require_user` (401 if anonymous, 409 if a forced password change is
  pending), `require_admin` (403 unless admin role).
- **`service.py`** — user CRUD, `authenticate`, password/role/active changes.
- **`routes.py`** — `/api/v1/auth/*`: `register` (gated by the DB-backed
  `REGISTRATION_OPEN` toggle), `login`, `logout`, `me`, `change-password`,
  and the first-admin `claim-admin`.
- **`bootstrap.py`** — first-admin bootstrap: when no admin exists, a
  one-time claim token is minted (or read from `ADMIN_BOOTSTRAP_TOKEN`),
  logged at startup, and exchanged via `POST /api/v1/auth/claim-admin`.
  Once an admin exists the flow is a no-op and the endpoint returns 410.
- **`passwords.py` / `app/password_hash.py`** — scrypt hashing (stdlib only).

`app/api/dependencies.py` keeps the legacy name `verify_api_key` as an
alias for `require_user` (so the many `dependencies=[Depends(verify_api_key)]`
call sites keep working), and `get_session` resolves the caller's session by
`skey = "<user_id>:<oid>"`. The control WebSocket `/api/v1/ws?oid=` is
authenticated by the same cookie.

#### `app/db/` — SQLAlchemy persistence

- **`engine.py`** — builds the engine + `sessionmaker` from `DATABASE_URL`
  (default: SQLite file `data/app.db`; Postgres via
  `postgresql+psycopg://`). Exposes `session_scope()` for non-request code
  and the `get_db()` FastAPI dependency. SQLite gets `PRAGMA foreign_keys=ON`
  so the `ON DELETE CASCADE` rules (deleting a user wipes their overlays,
  teams, presets, reports, and sessions) actually fire.
- **`migrate.py`** — `run_migrations()` runs `alembic upgrade head`
  in-process during `create_app`, guarded by a cross-process file lock so
  multiple workers don't race the first boot. The Docker entrypoint also
  runs `alembic upgrade head` (belt-and-suspenders; both idempotent).
- **`models/`** — `User` + `AuthSession`, `UserOverlay`
  (`public_token`, optional per-overlay default rules) + `OverlaySessionMeta`,
  `Team`/`TeamGroup`/`UserTeamListItem`, `Preset`, `MatchReport`, `Setting`.

#### DB-backed services

- **`app/teams_service.py`** — global team catalog, admin team-groups, and
  per-user lists. Replaces the env-driven `APP_TEAMS`; the wire shape
  (`{name: {icon, color, text_color}}`) is unchanged.
- **`app/presets_service.py`** — global (admin-activated) and per-user
  customization presets. Replaces the on-disk preset store and env-driven
  `APP_THEMES`.
- **`app/settings_service.py`** — boolean app settings (`REGISTRATION_OPEN`,
  admin-bootstrap-claimed) with env-seed-then-DB-override semantics ("DB
  wins after first boot").
- **`app/api/match_archive.py`** — archives a finished match to the
  `match_reports` table (per `skey`), read back by the print report.

#### Match report (`/match/{id}/report`)

`app/match_report.py` server-renders a print-friendly per-match HTML page.
The route is gated by `app/match_report_access.py`, which admits a reader if
any of: the **owner's** session cookie is present; the URL carries a valid
HMAC capability (`?exp=…&sig=…`, minted via
`POST /api/v1/matches/{id}/sign-url` and signed with `SESSION_SECRET` in
`app/match_report_signing.py`); or `MATCH_REPORT_PUBLIC=true`. The old
`?token=` and admin paths are gone.

### C. Configuration & Extras

#### `app/bootstrap.py` — application factory

`create_app()` assembles the FastAPI instance in a fixed order:
`run_security_bootstrap()` (resolve/mint `SESSION_SECRET`) →
`run_migrations()` (schema to head) →
`ensure_admin_bootstrap()` (mint/log the first-admin claim token) → routers
(auth first so `/api/v1/auth/*` is never shadowed, then `api_router` +
admin-users, then the match-report and metrics routers) → static mounts →
the SPA catch-all mount (must be last). `main.py` only validates config,
sets up logging, and calls `create_app()`.

#### `app/customization.py`

- **Responsibility**: Manages cosmetic data (Team Names, Logos, Colors, Overlay geometry).

#### `app/app_storage.py` — class `AppStorage`

- **Responsibility**: In-memory key-value storage for session state.

#### `app/conf.py`

- **Responsibility**: Loads environment variables into a structured `Conf` object.

#### `app/oid_utils.py`

- **Responsibility**: Overlay ID parsing utilities — `extract_oid()` normalises a raw overlay ID input.

#### `app/config_validator.py`

- **Responsibility**: Validates environment variables at startup. Logs warnings for misconfigurations.

---

## 5. Testing

### Running Tests Locally

```bash
# Backend tests
uv pip install -r requirements.lock -r requirements-dev.lock
pytest tests/

# Frontend tests
cd frontend && npm ci && npm test
```

### Backend Test Organization

| File | Coverage Area |
| :--- | :--- |
| `test_state.py` | `State` model operations |
| `test_game_manager.py` | Scoring rules, set logic, undo functionality |
| `test_backend.py` | API communication, overlay integration |
| `test_api.py` | SessionManager, GameService, cookie-session auth |
| `test_auth.py` | Cookie sessions, login/logout, account self-service |
| `test_admin_users.py` | Admin user-management endpoints |
| `test_bootstrap.py` | App-factory wiring + first-admin bootstrap |
| `test_db_migrations.py` | Alembic migrations |
| `test_overlays_service.py` | Per-user overlay CRUD + `public_token` |
| `test_teams.py` | DB-backed teams (catalog, groups, per-user lists) |
| `test_match_archive.py` / `test_match_report.py` | Match archiving + print report + access gate |
| `test_customization.py` | Team/color customization logic |
| `test_env_vars_manager.py` | Environment variable loading |
| `test_config_validator.py` | Startup environment variable validation |

#### Test fixtures (`tests/conftest.py`)

The multi-user model is exercised through a small set of fixtures:

- **`db_session`** (autouse) — gives every test a fresh in-memory SQLite
  database via a `StaticPool` (so the schema and rows survive across
  sessions within one test). The app's engine is pointed at it and
  `run_migrations` is stubbed to a no-op (the schema is built with
  `Base.metadata.create_all`). Yields a live `Session` for direct
  seeding/inspection.
- **`make_user(db_session, ...)`** — create and commit a user.
- **`app_client`** — `TestClient` over a freshly-built app (unauthenticated).
- **`login_client(client, db_session, ...)` / `auth_client`** — a client with
  its session cookie set; the user's id is attached as `client.test_user_id`
  so tests can build `make_skey(client.test_user_id, oid)`.

### Frontend Tests

Frontend tests use Vitest + React Testing Library and live in `frontend/src/test/`. They cover API client, WebSocket client, all UI components, hooks, i18n, and theming.

### CI Pipeline

The GitHub Actions CI pipeline (`.github/workflows/ci.yml`) runs on `push` / `pull_request` to `main` and `dev` branches:

1. **Lint** — `ruff check .` for syntax errors and style warnings.
2. **Type-check** — `mypy` on the strict-typed modules listed in `pyproject.toml`.
3. **Test** — Full `pytest tests/` suite with `--cov=app --cov-fail-under=70`; coverage XML uploaded as an artifact.
4. **Frontend** — `npm ci`, schema drift check (`scripts/generate_openapi.py` + `npm run gen:types`), `npm run typecheck`, and Vitest.

---

## 6. Important Logic Flows for Developers

### State Synchronization

The app assumes it is the **primary controller**. However, `GameManager.reset()` reloads data from `Backend` to ensure it syncs with any external resets.

### Overlay State Flow

Every overlay is managed **in-process** by `LocalOverlayBackend`. State flows directly from `GameManager` → `LocalOverlayBackend` → `OverlayStateStore` → `ObsBroadcastHub` → OBS browser sources — no inter-process communication needed.

### OID resolution

`resolve_overlay_kind` (in `app/overlay_backends/utils.py`) maps every request to the in-process `LocalOverlayBackend`. A bare OID (or the legacy `C-<id>` form) resolves to the in-process engine; the `OverlayStateStore` holds its render state on disk in `data/overlay_state_<hash>.json`, where the hashed input is the per-user storage key (`skey`), not the bare id.

The bare ID is always preferred; the `C-` prefix is accepted for backwards compatibility but omitted from the UI.

### Session lifecycle and per-OID init locks

The API router installs its own lifespan (`app/api/routes/lifespan.py`):

- **Background cleanup** — an hourly task calls `SessionManager.cleanup_expired()` and logs the number of evicted entries.
- **Per-OID init locks** — `get_init_lock(oid)` returns a `WeakValueDictionary`-backed `asyncio.Lock` so concurrent `POST /api/v1/session/init` calls for the same OID serialize on the same lock; the entry is garbage-collected once no caller holds it, avoiding a race where a manual cleanup could split two waiters onto different locks.

---

## 7. Common Modification Scenarios

### Adding a new Rule (e.g., Golden Set)

1. Modify `app/game_manager.py` -> `add_game` to check for the new condition.
2. Update `app/state.py` if new counters are needed.

### Adding a new API Endpoint

1. Add the route to the appropriate domain module under `app/api/routes/`
   (or create a new module and register it in `app/api/routes/__init__.py`).
2. Add request/response schemas in `app/api/schemas.py` (or inline Pydantic
   models in the route module, as several domain routers do).
3. Add the business logic in `app/api/game_service.py` or the relevant
   service module (`teams_service.py`, `presets_service.py`, etc.).
4. Gate it: `dependencies=[Depends(verify_api_key)]` (any logged-in user) or
   `Depends(require_admin)` for admin-only routes.

### Adding a DB model or migration

1. Add/extend the ORM model under `app/db/models/` and export it from
   `app/db/models/__init__.py` so Alembic and the test `create_all`
   discover the table.
2. Generate a migration: `alembic revision --autogenerate -m "..."`, review
   the script in `migrations/versions/`, and commit it.
3. Wire ON DELETE CASCADE for user-owned rows so account deletion cleans up
   (SQLite FK enforcement is enabled in `app/db/engine.py`).
4. The schema is applied automatically on the next `create_app()`
   (`run_migrations()` → `alembic upgrade head`).

### Adding a new Setting

For a static, boot-time setting:

1. Add the field to `app/conf.py`.
2. Add the env var to `docker-compose.yml` and `README.md`.

For an operator-toggleable setting that should persist (DB wins after first
boot, like `REGISTRATION_OPEN`): add a key + accessor in
`app/settings_service.py` (seeded from an env var, then overridden by the
`settings` table) and an admin endpoint to flip it.

---

## 8. Environment Setup (Quick Start)

```bash
# 1. Clone the repository
git clone <repo-url>
cd volley-overlay-control

# 2. Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install backend dependencies
uv pip install -r requirements.lock -r requirements-dev.lock

# 4. Build the frontend
cd frontend && npm ci && npm run build && cd ..

# 5. Configure environment (all optional — sensible defaults apply)
# Create a .env file with your settings, for example:
# DATABASE_URL=postgresql+psycopg://user:pass@localhost/volley   # default: SQLite data/app.db
# REGISTRATION_OPEN=true                                          # public self-registration

# 6. Run the application (serves both API and UI on port 8080)
# On startup the DB schema is migrated to head automatically, and — when
# no admin exists yet — a one-time ADMIN BOOTSTRAP TOKEN is logged. POST it
# to /api/v1/auth/claim-admin (or use the /claim-admin page) to create the
# first admin account, then log in with the session cookie.
python main.py

# 7. Run the test suites
pytest tests/ -v           # Backend tests
cd frontend && npm test    # Frontend tests
```

The database is created and migrated automatically on first run. To apply
migrations manually (e.g. for a Postgres instance before first boot):

```bash
alembic upgrade head
```

### Frontend Development with Hot-Reload

For active frontend work, use Vite's dev server instead of the built static files:

```bash
# Terminal 1: Start the backend
python main.py

# Terminal 2: Start the Vite dev server (hot-reload on port 3000)
cd frontend && npm run dev
```

Vite proxies all `/api` requests to `http://localhost:8080`. Open `http://localhost:3000` for development.
