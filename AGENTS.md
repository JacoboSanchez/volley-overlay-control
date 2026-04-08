# AGENTS.md — Volley Overlay Control Project Guide for AI Agents

This document provides everything an AI coding agent needs to understand, navigate, and contribute to the Volley Overlay Control project correctly and efficiently.

---

## Project Overview

Volley Overlay Control is a self-hostable Python backend service for controlling volleyball scoreboards. It exposes a REST + WebSocket API that powers the React frontend ([volley-control-ui](../volley-control-ui)), managing match state (scores, sets, timeouts, serve) and synchronizing it to overlay graphics engines — either the hosted **overlays.uno** cloud service or a fully self-hosted **custom overlay** server.

**Stack:** Python 3.x · FastAPI · Uvicorn · requests · python-dotenv · websocket-client · Docker
**Test stack:** pytest · pytest-asyncio · flake8
**No database** — all state is in-memory.

---

## Repository Layout

```
volley-overlay-control/
├── main.py                    # App entry point — creates FastAPI app, starts uvicorn
├── requirements.txt           # Runtime dependencies
├── requirements-dev.txt       # Dev/test dependencies
├── Dockerfile                 # Docker image (python:3.12-slim)
├── docker-compose.yml         # Compose config (reads from .env)
├── pytest.ini                 # asyncio_mode=auto
├── .pre-commit-config.yaml    # flake8 + formatting hooks
│
├── app/                       # All application source code
│   ├── state.py               # Data model — match state dictionary
│   ├── game_manager.py        # Business logic — volleyball rules & score mutations
│   ├── backend.py             # Sync bridge — pushes state via WebSocket (preferred) or HTTP
│   ├── overlay_backends.py    # Strategy pattern: UnoOverlayBackend, CustomOverlayBackend
│   ├── ws_client.py           # Persistent WebSocket client for custom overlay control channel
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
│   └── pwa/                   # Progressive Web App assets (Service Worker, Manifest, Icons)
│
├── tests/
│   ├── conftest.py            # Shared fixtures: load_test_env
│   ├── test_state.py          # Unit tests for State model
│   ├── test_game_manager.py   # Unit tests for scoring rules and set logic
│   ├── test_backend.py        # Unit tests for API communication
│   ├── test_api.py            # SessionManager, GameService, API key auth tests
│   ├── test_customization.py  # Unit tests for team/color customization
│   ├── test_env_vars_manager.py
│   ├── test_config_validator.py
│   ├── test_ws_client.py      # WebSocket client and Backend WS integration tests
│   ├── test_coverage_proposals.py  # Additional WSControlClient coverage
│   └── fixtures/              # JSON test data (game states, overlay configs)
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
| Sync | `Backend` | `app/backend.py` | WebSocket-first / HTTP-fallback bridge to overlay servers |
| Sync | `WSControlClient` | `app/ws_client.py` | Persistent WebSocket connection to custom overlay server |

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

`Backend` communicates with two overlay types:

| OID Prefix | Type | Protocol |
|-----------|------|---------|
| *(none / plain token)* | overlays.uno cloud | `PUT` to overlays.uno API |
| `C-{id}` or `C-{id}/{style}` | Custom self-hosted | WebSocket-first via `/ws/control/{id}`, HTTP fallback |

**WebSocket sync (custom overlays):** `Backend.init_ws_client()` probes `GET /api/config/{id}` for a `controlWebSocketUrl`. If found, it creates a `WSControlClient` with auto-reconnect (exponential backoff 1s->30s) and heartbeat pings every 25s.

**Custom overlay state schema** is defined in `CUSTOM_OVERLAY_API.yaml`.

---

## Configuration System

Config is loaded by `app/conf.py` -> `Conf` class from environment variables (`.env` or Docker compose).

Key variables: `UNO_OVERLAY_OID`, `APP_PORT`, `MATCH_GAME_POINTS`, `MATCH_SETS`, `SCOREBOARD_USERS`, `APP_CUSTOM_OVERLAY_URL`, `ENABLE_MULTITHREAD`, `LOGGING_LEVEL`, `SCOREBOARD_LANGUAGE`.

Full list in [README.md](README.md).

---

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `/api/v1/*` | REST API (see [FRONTEND_DEVELOPMENT.md](FRONTEND_DEVELOPMENT.md)) |
| `/api/v1/ws?oid=X` | WebSocket for real-time state updates |
| `/health` | Health check — returns `200 OK` with timestamp |

---

## Testing

```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=term-missing
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

### OID utilities
Use `app/oid_utils.py` for `extract_oid()` and `compose_output()` — do not import from deleted modules.

---

## Common Pitfalls

- **Do not block the event loop** — long-running I/O must use the `ThreadPoolExecutor` in `Backend`.
- **Do not skip `GameManager.save()`** — after any mutation, save must be called.
- **Custom overlay IDs start with `C-`** — `Backend.is_custom_overlay()` checks this prefix.
- **Undo is a flag, not a stack** — reverses only the most recent action of that type.

---

## Documentation Files

| File | Purpose |
|------|---------|
| `README.md` | End-user setup and configuration guide |
| `DEVELOPER_GUIDE.md` | Architecture deep-dive and coding patterns |
| `FRONTEND_DEVELOPMENT.md` | REST API reference + guide for building JS frontends |
| `CUSTOM_OVERLAY.md` | Guide for building a custom overlay server |
| `CUSTOM_OVERLAY_API.yaml` | OpenAPI 3.0 spec for the custom overlay REST contract |
| `AGENTS.md` | This file — AI agent guide |
