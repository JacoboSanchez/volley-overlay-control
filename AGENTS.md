# AGENTS.md — Volley Overlay Control Project Guide for AI Agents

This document provides everything an AI coding agent needs to understand, navigate, and contribute to the Volley Overlay Control project correctly and efficiently.

---

## Project Overview

Volley Overlay Control is a self-hostable application that bundles a React control UI, a Python/FastAPI backend, and an overlay serving engine into a single deployable service. It manages match state (scores, sets, timeouts, serve), renders overlay HTML templates for OBS browser sources, and synchronizes state with overlay backends — either the hosted **overlays.uno** cloud service or **in-process custom overlays** (with optional external overlay server support).

**Backend stack:** Python 3.x · FastAPI · Uvicorn · Jinja2 · requests · python-dotenv · websocket-client · Docker
**Frontend stack:** React 19 · Vite · PWA (vite-plugin-pwa) · react-colorful
**Test stack:** pytest · pytest-asyncio · flake8 (backend) · Vitest · React Testing Library (frontend)
**No database** — game state is in-memory; overlay state is persisted to JSON files (`data/overlay_state_{id}.json`). The frontend is built with Vite and served as static files by FastAPI in production.

---

## Repository Layout

```
volley-overlay-control/
├── main.py                    # App entry point — creates FastAPI app, mounts SPA + API, starts uvicorn
├── requirements.txt           # Runtime dependencies
├── requirements-dev.txt       # Dev/test dependencies
├── Dockerfile                 # Multi-stage build (Node.js frontend + Python backend)
├── docker-compose.yml         # Compose config (reads from .env)
├── pytest.ini                 # asyncio_mode=auto
├── .pre-commit-config.yaml    # flake8 + formatting hooks
│
├── frontend/                  # React control UI (built with Vite, served by FastAPI)
│   ├── package.json           # Frontend dependencies and scripts
│   ├── vite.config.js         # Vite config (PWA, dev proxy to :8080, test setup)
│   ├── index.html             # SPA entry point
│   ├── src/                   # React source code
│   │   ├── App.jsx            # Main app component
│   │   ├── api/client.js      # REST API client (relative paths: /api/v1/)
│   │   ├── api/websocket.js   # WebSocket client (uses window.location.host)
│   │   ├── components/        # UI components (TeamPanel, ConfigPanel, ScoreButton, etc.)
│   │   ├── hooks/             # React hooks (useGameState, useSettings, usePreview, etc.)
│   │   ├── i18n.jsx           # Internationalization
│   │   ├── theme.js           # Theme constants and font scales
│   │   └── test/              # Vitest test suite (158 tests)
│   └── public/                # Static assets (icons, fonts)
│
├── app/                       # Backend source code
│   ├── state.py               # Data model — match state dictionary
│   ├── game_manager.py        # Business logic — volleyball rules & score mutations
│   ├── backend.py             # Coordinator — delegates to overlay backend strategies
│   ├── overlay_backends.py    # Strategy: UnoOverlayBackend, LocalOverlayBackend, CustomOverlayBackend
│   ├── ws_client.py           # Persistent WebSocket client for external overlay servers (optional)
│   ├── customization.py       # Team names, colors, logos, layout geometry
│   ├── conf.py                # Configuration object — wraps env vars
│   ├── authentication.py      # AuthMiddleware, PasswordAuthenticator
│   ├── app_storage.py         # In-memory key-value storage
│   ├── oid_utils.py           # OID parsing utilities (extract_oid, compose_output)
│   ├── env_vars_manager.py    # Centralized env var access with remote config caching
│   ├── logging_config.py      # Logging level configuration
│   ├── constants.py           # SVG favicon, overlays.uno API base URL
│   ├── messages.py            # i18n strings — English ("en") and Spanish ("es")
│   ├── config_validator.py    # Startup configuration validation (env var checks)
│   │
│   ├── api/                   # REST API + WebSocket layer for frontends
│   │   ├── __init__.py        # Exports api_router
│   │   ├── routes.py          # FastAPI endpoints under /api/v1/
│   │   ├── schemas.py         # Pydantic request/response models
│   │   ├── game_service.py    # Service layer — single entry point for all game actions
│   │   ├── session_manager.py # Thread-safe game session management by OID
│   │   ├── ws_hub.py          # WebSocket notification hub for real-time state push
│   │   └── dependencies.py    # Auth + session FastAPI dependencies
│   │
│   ├── overlay/               # In-process overlay serving (from volleyball-scoreboard-overlay)
│   │   ├── __init__.py        # Singletons: OverlayStateStore, ObsBroadcastHub
│   │   ├── state_store.py     # Overlay state — in-memory + JSON file persistence
│   │   ├── broadcast.py       # OBS WebSocket broadcast hub — 50ms debounced pushes
│   │   └── routes.py          # HTTP/WS: /overlay/, /ws/, /api/config/, CRUD, themes
│   │
│   ├── admin/                 # Overlay manager page + CRUD API (password-protected, independent of the scoreboard)
│   │   ├── __init__.py        # Exports admin_router, admin_page_router, managed_overlays_store
│   │   ├── routes.py          # /manage HTML page + /api/v1/admin/overlays CRUD endpoints
│   │   ├── store.py           # OverlaysStore — thread-safe JSON persistence at data/managed_overlays.json
│   │   └── static/overlays.html  # Self-contained manager page (vanilla JS, no React)
│   │
│   └── pwa/                   # Legacy PWA assets (icons)
│
├── overlay_templates/         # Jinja2 HTML templates for overlay styles (16 templates)
├── overlay_static/            # Static assets for overlays (JS, CSS, images)
├── data/                      # Persisted overlay state (overlay_state_{id}.json) + managed overlay catalogue (managed_overlays.json)
│
├── tests/                     # Pytest suite (181 tests)
│   ├── conftest.py            # Shared fixtures: load_test_env
│   ├── test_state.py          # Unit tests for State model
│   ├── test_game_manager.py   # Unit tests for scoring rules and set logic
│   ├── test_backend.py        # Unit tests for API communication
│   ├── test_api.py            # SessionManager, GameService, API key auth tests
│   ├── test_customization.py  # Unit tests for team/color customization
│   ├── test_env_vars_manager.py
│   ├── test_config_validator.py
│   ├── test_ws_client.py      # WebSocket client and Backend WS integration tests
│   ├── test_admin.py          # Overlay manager page + CRUD + auth tests
│   └── test_coverage_proposals.py  # Additional WSControlClient coverage
│
└── font/                      # Custom TTF/OTF scoreboard fonts
```

---

## Architecture — Service-Oriented

| Layer | Class | File | Responsibility |
|-------|-------|------|----------------|
| Model | `State` | `app/state.py` | Single source of truth; match state dict |
| Controller | `GameManager` | `app/game_manager.py` | Enforces volleyball rules; mutates State |
| Service | `GameService` | `app/api/game_service.py` | Single entry point for all game actions |
| API | `api_router` | `app/api/routes.py` | REST + WebSocket endpoints for frontends |
| Session | `SessionManager` | `app/api/session_manager.py` | Thread-safe game session management by OID |
| WS Hub | `WSHub` | `app/api/ws_hub.py` | WebSocket notification hub for real-time state push |
| Sync | `Backend` | `app/backend.py` | Coordinator — delegates to overlay backend strategies |
| Overlay | `LocalOverlayBackend` | `app/overlay_backends.py` | In-process overlay state management (default for C- OIDs) |
| Overlay | `OverlayStateStore` | `app/overlay/state_store.py` | In-memory + JSON persistence for overlay state |
| Overlay | `ObsBroadcastHub` | `app/overlay/broadcast.py` | Debounced WebSocket broadcasts to OBS browser sources |
| Admin | `OverlaysStore` | `app/admin/store.py` | Thread-safe CRUD on `data/managed_overlays.json` (manager page) |
| Admin | `admin_router`, `admin_page_router` | `app/admin/routes.py` | `/manage` page + `/api/v1/admin/overlays` CRUD (Bearer = `OVERLAY_MANAGER_PASSWORD`) |

> See [FRONTEND_DEVELOPMENT.md](FRONTEND_DEVELOPMENT.md) for the full API reference.

### Canonical Data Flow — "JS frontend adds a point"

```
JS Frontend: POST /api/v1/game/add-point?oid=X
  → GameService.add_point(session, team=1)
    → GameManager.add_game(team=1)
      → State: validates & increments score
        → checks set-win conditions, auto-switches serve
          → GameManager.save()
            → Backend: push to overlay server
              → WSHub.broadcast(state)
                → WebSocket: {"type":"state_update", "data":{...}}
  → HTTP 200 ActionResponse
```

**Never bypass this chain.** Do not call `Backend.save()` directly, and do not mutate `State` without going through `GameManager`.

---

## State Model

The entire match lives in a flat dictionary with these keys:

```python
{
    "Serve": "A" | "B" | "None",
    "Team 1 Sets": int,         # 0–5
    "Team 2 Sets": int,
    "Team 1 Game 1 Score": int, # 0–25  (set 1)
    ...                         # Game 2–5 for both teams
    "Team 1 Timeouts": int,     # 0–2 per set
    "Team 2 Timeouts": int,
    "Current Set": int,         # 1–5
}
```

- Access scores via `state.get_game(team, set_num)` / `state.set_game(team, set_num, value)`.
- The `simplify_model()` method strips all but the current set's data for "simple mode".

---

## GameManager Rules

- **Points to win a set:** `MATCH_GAME_POINTS` (default 25) — must win by 2.
- **Points to win the final set:** `MATCH_GAME_POINTS_LAST_SET` (default 15) — must win by 2.
- **Sets in a match:** `MATCH_SETS` (default 5); match ends when a team wins `(sets // 2) + 1` sets.
- **Timeouts per set:** Max 2.
- **Undo:** Pass `undo=True` to `add_game()`, `add_set()`, or `add_timeout()` to reverse the action.
- **Auto serve switch:** `add_game()` calls `change_serve()` automatically after each point.

---

## Backend & Overlay Integration

`Backend` communicates with overlay backends using the strategy pattern:

| OID Prefix | Type | Backend Class | Communication |
|-----------|------|--------------|---------------|
| *(none / plain token)* | overlays.uno cloud | `UnoOverlayBackend` | HTTP to overlays.uno API |
| `C-{id}` or `C-{id}/{style}` | Custom (local) | `LocalOverlayBackend` | In-process via `OverlayStateStore` |
| `C-{id}` (with `APP_CUSTOM_OVERLAY_URL` set) | Custom (external) | `CustomOverlayBackend` | WebSocket + HTTP to external server |

**Default behavior:** Custom overlays (`C-` prefix) are managed **in-process** by `LocalOverlayBackend`. State flows directly from `GameManager` → `Backend` → `LocalOverlayBackend` → `OverlayStateStore` → `ObsBroadcastHub` → OBS browser sources.

**External server mode:** When `APP_CUSTOM_OVERLAY_URL` is set, the system falls back to `CustomOverlayBackend` which communicates with an external overlay server. See [CUSTOM_OVERLAY.md](CUSTOM_OVERLAY.md) for the external server API contract.

**Overlay templates:** 16 Jinja2 HTML templates in `overlay_templates/` serve overlay graphics to OBS browser sources at `/overlay/{id}`. The overlay `app.js` connects via WebSocket at `/ws/{id}` for real-time state updates.

---

## Configuration System

Config is loaded by `app/conf.py` -> `Conf` class from environment variables (`.env` or Docker compose).

Key variables: `UNO_OVERLAY_OID`, `APP_PORT`, `MATCH_GAME_POINTS`, `MATCH_SETS`, `SCOREBOARD_USERS`, `APP_CUSTOM_OVERLAY_URL`, `ENABLE_MULTITHREAD`, `LOGGING_LEVEL`, `SCOREBOARD_LANGUAGE`, `OVERLAY_MANAGER_PASSWORD` (enables the `/manage` admin page).

Full list in [README.md](README.md).

---

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `/` | Control UI (React SPA — served from `frontend/dist/`) |
| `/manage` | Overlay manager page (password-protected via `OVERLAY_MANAGER_PASSWORD`) |
| `/api/v1/*` | REST API (see [FRONTEND_DEVELOPMENT.md](FRONTEND_DEVELOPMENT.md)) |
| `/api/v1/admin/overlays` | CRUD for managed overlays (`Authorization: Bearer $OVERLAY_MANAGER_PASSWORD`) |
| `/api/v1/admin/login`, `/api/v1/admin/status` | Admin auth check + feature-enabled probe |
| `/api/v1/ws?oid=X` | WebSocket for real-time state updates (frontend) |
| `/overlay/{overlay_id}` | Overlay HTML template for OBS browser sources |
| `/ws/{overlay_id}` | WebSocket for OBS browser sources (overlay state broadcast) |
| `/api/config/{overlay_id}` | Overlay config (output URL, available styles) |
| `/api/state/{overlay_id}` | Overlay state update endpoint |
| `/create/overlay/{overlay_id}` | Create a new overlay |
| `/list/overlay` | List all overlays |
| `/api/themes` | List preset overlay themes |
| `/health` | Health check — returns `200 OK` with timestamp |
| `/sw.js` | PWA service worker (from frontend build) |
| `/manifest.webmanifest` | PWA manifest (from frontend build) |

---

## Testing

```bash
# Backend
pytest tests/ -v
pytest tests/ --cov=app --cov-report=term-missing

# Frontend
cd frontend && npm test
```

**Test conventions:**
- `conftest.py` provides `load_test_env` (clears AppStorage between tests).
- JSON fixtures in `tests/fixtures/` represent known game states.
- `asyncio_mode = auto` is set globally in `pytest.ini`.

---

## Key Patterns & Conventions

### State access
Always use `State` accessor methods; never read/write `state.current_model` directly.

### Adding a new API endpoint
1. Add the route in `app/api/routes.py`.
2. Add schemas in `app/api/schemas.py`.
3. Add business logic in `app/api/game_service.py`.

### Extending the overlay manager page
1. Extend storage in `app/admin/store.py` — every mutation must call `_write_to_disk()` under `self._lock`.
2. Add the FastAPI route in `app/admin/routes.py` with `Depends(require_admin)` so the Bearer check is enforced.
3. Update the UI in `app/admin/static/overlays.html` — single-file vanilla JS, no build step.
4. Managed overlays are merged into `GET /api/v1/overlays` (managed wins over `PREDEFINED_OVERLAYS` on name conflict).

### OID utilities
Use `app/oid_utils.py` for `extract_oid()` and `compose_output()` — do not import from deleted modules.

---

## Common Pitfalls

- **Do not block the event loop** — long-running I/O must use the `ThreadPoolExecutor` in `Backend`.
- **Do not skip `GameManager.save()`** — after any mutation, save must be called.
- **Custom overlay IDs start with `C-`** — `Backend.is_custom_overlay()` checks this prefix.
- **Undo is a flag, not a stack** — reverses only the most recent action of that type.

---

## SPA & Overlay Serving

`main.py` mounts routes in this order (earlier mounts take priority):
1. `app.include_router(api_router)` — `/api/v1/*` REST + WebSocket API
2. `app.include_router(admin_page_router)` — `/manage` standalone page
3. `app.include_router(admin_router)` — `/api/v1/admin/*` CRUD
4. `app.include_router(overlay_router)` — `/overlay/*`, `/ws/*`, `/api/config/*`, CRUD, themes
5. `app.mount("/fonts", ...)` — scoreboard fonts
6. `app.mount("/static", ...)` — overlay JS/CSS/images
7. `app.mount("/pwa", ...)` — PWA icons
8. `app.mount("/", SPAStaticFiles(...))` — SPA catch-all (last — never shadows other routes)

The SPA mount uses a custom `SPAStaticFiles` class that falls back to `index.html` for unknown paths (SPA routing). If `frontend/dist/` doesn't exist (e.g., during backend-only development or testing), the SPA is not mounted and a warning is logged. Similarly, if `overlay_templates/` doesn't exist, overlay routes are disabled.

## Documentation Files

| File | Purpose |
|------|---------|
| `README.md` | End-user setup and configuration guide |
| `DEVELOPER_GUIDE.md` | Architecture deep-dive and coding patterns |
| `FRONTEND_DEVELOPMENT.md` | REST API reference + guide for building JS frontends |
| `CUSTOM_OVERLAY.md` | Guide for building a custom overlay server |
| `CUSTOM_OVERLAY_API.yaml` | OpenAPI 3.0 spec for the custom overlay REST contract |
| `AGENTS.md` | This file — AI agent guide |
