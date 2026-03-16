# AGENTS.md — Remote-Scoreboard Project Guide for AI Agents

This document provides everything an AI coding agent needs to understand, navigate, and contribute to the Remote-Scoreboard project correctly and efficiently.

---

## Project Overview

Remote-Scoreboard is a self-hostable web application for controlling volleyball scoreboards. It provides a control interface for managing match state (scores, sets, timeouts, serve) and synchronizes that state to overlay graphics engines — either the hosted **overlays.uno** cloud service or a fully self-hosted **custom overlay** server.

**Stack:** Python 3.11 · NiceGUI 3.8.0 · requests · python-dotenv · Docker
**Test stack:** pytest · pytest-asyncio · pytest-playwright · flake8
**No database** — all state is in-memory with browser-local storage persistence.

---

## Repository Layout

```
remote-scoreboard/
├── main.py                    # App entry point — starts NiceGUI with auth middleware
├── requirements.txt           # Runtime dependencies
├── requirements-dev.txt       # Dev/test dependencies
├── Dockerfile                 # Multi-stage Docker image
├── docker-compose.yml         # Compose config (reads from .env)
├── pytest.ini                 # asyncio_mode=auto; marks mobile_browser tests
├── .pre-commit-config.yaml    # flake8 + formatting hooks
│
├── app/                       # All application source code
│   ├── state.py               # Data model — match state dictionary
│   ├── game_manager.py        # Business logic — volleyball rules & score mutations
│   ├── backend.py             # HTTP bridge — pushes state to overlay servers
│   ├── gui.py                 # Presentation layer — NiceGUI layout orchestrator
│   ├── startup.py             # Route definitions and lifecycle hooks
│   ├── customization.py       # Team names, colors, logos, layout geometry
│   ├── customization_page.py  # Customization settings UI page
│   ├── conf.py                # Configuration object — wraps env vars + AppStorage
│   ├── authentication.py      # AuthMiddleware, PasswordAuthenticator, login page
│   ├── app_storage.py         # Wrapper over NiceGUI browser-local storage
│   ├── env_vars_manager.py    # Centralized env var access with remote config caching
│   ├── logging_config.py      # Logging level configuration
│   ├── constants.py           # SVG favicon, overlays.uno API base URL
│   ├── messages.py            # i18n strings — English ("en") and Spanish ("es")
│   ├── theme.py               # Tailwind CSS classes, font scales, default colors
│   ├── oid_dialog.py          # Overlay ID entry dialog
│   ├── options_dialog.py      # Settings dialog
│   ├── preview.py             # Preview logic
│   ├── preview_page.py        # Preview page UI
│   ├── gui_update_mixin.py    # Mixin with UI refresh helper methods for GUI
│   ├── config_validator.py    # Startup configuration validation (env var checks)
│   │
│   └── components/            # Reusable NiceGUI UI components
│       ├── score_button.py    # ui.button wrapper with long-press / tap detection
│       ├── team_panel.py      # Team column (score, timeouts, serve indicator)
│       ├── center_panel.py    # Middle section (score table, set tabs, preview)
│       ├── control_buttons.py # Action bars (visibility, simple mode, undo, config)
│       ├── button_interaction.py  # Long-press (1s) vs tap vs double-tap logic
│       └── button_style.py    # Button appearance utilities
│
├── tests/
│   ├── conftest.py            # Shared fixtures: mock_backend, load_test_env
│   ├── test_state.py          # Unit tests for State model
│   ├── test_game_manager.py   # Unit tests for scoring rules and set logic
│   ├── test_backend.py        # Unit tests for API communication
│   ├── test_customization.py  # Unit tests for team/color customization
│   ├── test_env_vars_manager.py
│   ├── test_config_validator.py
│   ├── test_ui.py             # NiceGUI test-client integration tests
│   ├── test_mobile_viewport.py  # Playwright browser tests (marked mobile_browser)
│   └── fixtures/              # JSON test data (game states, overlay configs)
│
└── font/                      # 10 custom TTF/OTF scoreboard fonts
```

---

## Architecture — Four-Layer MVC

| Layer | Class | File | Responsibility |
|-------|-------|------|----------------|
| Model | `State` | `app/state.py` | Single source of truth; match state dict |
| Controller | `GameManager` | `app/game_manager.py` | Enforces volleyball rules; mutates State |
| View | `GUI` | `app/gui.py` | NiceGUI layout; instantiates components |
| Sync | `Backend` | `app/backend.py` | HTTP bridge to overlay servers |

### Canonical Data Flow — "User adds a point"

```
User clicks Team 1 score button
  → GUI.handle_button_press/release()
    → GameManager.add_game(team=1)
      → State: validates & increments score
        → checks set-win conditions, auto-switches serve
          → Backend.save(state)
            → POST to overlays.uno OR custom overlay server
              → GUI.update_ui()
                → GUI._broadcast_to_others()  ← deep-copies state to other open tabs
```

**Never bypass this chain.** Do not call `Backend.save()` directly from the GUI layer, and do not mutate `State` without going through `GameManager`.

---

## State Model

The entire match lives in a flat dictionary with these keys:

```python
{
    "Serve": "A" | "B" | "None",
    "Team 1 Sets": int,         # 0–5
    "Team 2 Sets": int,
    "Team 1 Game 1 Score": int, # 0–25  (set 1)
    "Team 1 Game 2 Score": int, # 0–25  (set 2)
    ...                         # Game 3–5 for both teams
    "Team 2 Game 1 Score": int,
    ...
    "Team 1 Timeouts": int,     # 0–2 per set
    "Team 2 Timeouts": int,
    "Current Set": int,         # 1–5
}
```

- `State` uses string keys by convention throughout the codebase — do not switch to integer keys.
- Access scores via `state.get_game(team, set_num)` / `state.set_game(team, set_num, value)`.
- The `simplify_model()` method strips all but the current set's data for "simple mode".

---

## GameManager Rules

Key scoring rules enforced in `GameManager`:

- **Points to win a set:** `MATCH_GAME_POINTS` (default 25) — must win by 2.
- **Points to win the final set:** `MATCH_GAME_POINTS_LAST_SET` (default 15) — must win by 2.
- **Sets in a match:** `MATCH_SETS` (default 5); match ends when a team wins `(sets // 2) + 1` sets.
- **Timeouts per set:** Max 2. `add_timeout()` is a no-op if already at 2.
- **Undo:** Pass `undo=True` to `add_game()`, `add_set()`, or `add_timeout()` to reverse the action.
- **Auto serve switch:** `add_game()` calls `change_serve()` automatically after each point.

When you add new scoring variants (e.g., beach volleyball mode), adjust the point/set limits via the constructor parameters — do not hardcode new constants in `game_manager.py`.

---

## Backend & Overlay Integration

`Backend` communicates with two overlay types:

| OID Prefix | Type | Protocol |
|-----------|------|---------|
| *(none / plain token)* | overlays.uno cloud | `PUT https://app.overlays.uno/apiv2/controlapps/{oid}/api` with command JSON |
| `C-{id}` or `C-{id}/{style}` | Custom self-hosted overlay | `POST {APP_CUSTOM_OVERLAY_URL}/api/state/{id}` with match state JSON |

**Caching:** `_customization_cache` in `Backend` prevents redundant GET requests. Do not clear it except in tests.

**Threading:** When `ENABLE_MULTITHREAD=true`, overlay updates run in a `ThreadPoolExecutor` (5 workers) so the UI is never blocked by slow HTTP calls. Any new backend calls that touch the network must be safe to run on a thread-pool thread.

**Custom overlay state schema** is defined in `CUSTOM_OVERLAY_API.yaml`. When modifying what gets sent to a custom overlay, update that file too.

---

## UI Layer (NiceGUI)

`GUI` in `app/gui.py` is the layout orchestrator. It:

1. Instantiates `TeamPanel` (×2), `CenterPanel`, `ControlButtons`.
2. Tracks all active browser-tab instances via a class-level `WeakSet(_instances)`.
3. Calls `_broadcast_to_others()` after every state change to sync all open tabs without a server round-trip.

**Component authoring rules:**
- All UI components live in `app/components/`.
- Components receive `gui` (the parent `GUI` instance) as their first constructor argument.
- Button touch/click events must go through `ButtonInteraction` to get consistent long-press / double-tap handling across desktop and mobile.
- Use Tailwind utility classes from `app/theme.py` (`TACOLOR`, `TBCOLOR`, etc.) rather than inline styles.
- Use `messages.py` keys for all user-visible strings (never hard-code display text in components).

**Orientation:** `GUI.is_portrait` is `True` when `height > 1.2 × width` and `width < 800px`. Layout components must handle both orientations.

---

## Configuration System

Config is loaded by `app/conf.py` → `Conf` class, which reads from two sources in priority order:

1. `AppStorage` (browser-local storage, per-user persistent)
2. Environment variables (from `.env` or Docker compose)

All environment variables are listed in the table below. When adding a new config option:

1. Add the env var to `app/env_vars_manager.py`.
2. Expose it via a property in `app/conf.py`.
3. Document it in `README.md` under the environment variables section.
4. Add a default to `docker-compose.yml` if it has a safe default.

| Variable | Default | Description |
|----------|---------|-------------|
| `UNO_OVERLAY_OID` | — | overlays.uno control token (required for cloud mode) |
| `APP_PORT` | 8080 | TCP port |
| `APP_TITLE` | "Scoreboard" | Page title and storage-secret seed |
| `APP_DARK_MODE` | "auto" | "on" / "off" / "auto" |
| `MATCH_GAME_POINTS` | 25 | Points to win a set |
| `MATCH_GAME_POINTS_LAST_SET` | 15 | Points to win the final set |
| `MATCH_SETS` | 5 | Total sets in match |
| `ENABLE_MULTITHREAD` | true | Non-blocking overlay updates |
| `LOGGING_LEVEL` | "warning" | debug / info / warning / error |
| `SCOREBOARD_LANGUAGE` | "en" | "en" or "es" |
| `SCOREBOARD_USERS` | — | JSON: `{"user": {"password": "...", "control": "OID"}}` |
| `PREDEFINED_OVERLAYS` | — | JSON: predefined overlay list |
| `APP_TEAMS` | — | JSON: predefined teams with colors/icons |
| `APP_THEMES` | — | JSON: customization presets |
| `APP_CUSTOM_OVERLAY_URL` | http://localhost:8000 | Custom overlay server base URL |
| `APP_CUSTOM_OVERLAY_OUTPUT_URL` | *(falls back to above)* | External-facing URL for preview |
| `REMOTE_CONFIG_URL` | — | URL for remote JSON config (10s cache) |
| `SHOW_PREVIEW` | true | Show preview iframe on control page |
| `AUTO_HIDE_ENABLED` | false | Auto-hide overlay after inactivity |
| `DEFAULT_HIDE_TIMEOUT` | 5 | Seconds before auto-hide |
| `AUTO_SIMPLE_MODE` | false | Auto-switch to simple mode during play |
| `STORAGE_SECRET` | `APP_TITLE+APP_PORT` | Encryption key for browser storage |
| `MINIMIZE_BACKEND_USAGE` | true | Cache customization responses |
| `SINGLE_OVERLAY_MODE` | true | One active overlay at a time |
| `ORDERED_TEAMS` | true | Alphabetically sort team list |
| `HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED` | false | Hide manual overlay entry if predefined list exists |
| `AUTO_SIMPLE_MODE_TIMEOUT` | false | Switch back to full view on timeout |
| `APP_DEFAULT_LOGO` | *(flaticon URL)* | Fallback team logo URL |
| `APP_RELOAD` | false | Auto-reload on code changes (dev mode) |
| `APP_SHOW` | false | Auto-open in browser on startup |
| `REST_USER_AGENT` | "curl/8.15.0" | User-Agent for outbound HTTP (avoids Cloudflare bot detection) |
| `UNO_OVERLAY_AIR_ID` | — | NiceGUI On Air token for local-only setups |
| `UNO_OVERLAY_OUTPUT` | — | Custom output URL override |

---

## Routes & Endpoints

| Route | Description |
|-------|-------------|
| `/` | Main control panel (default indoor mode) |
| `/indoor` | Indoor volleyball mode (25 pts/set, best of 5) |
| `/beach` | Beach volleyball mode (21 pts/set, best of 3) |
| `/login` | Login page (active when `SCOREBOARD_USERS` is configured) |
| `/preview` | Full-page overlay preview (no auth required) |
| `/health` | Health check — returns `200 OK` with timestamp |

Routes are defined in `app/startup.py`. All routes except `/login`, `/preview`, and `/health` pass through `AuthMiddleware`.

---

## Internationalization

All user-visible strings must come from `app/messages.py`. Keys are referenced as `messages.KEY` throughout the codebase.

- To add a string: add the key to the `Messages` class/dict in `messages.py` for both `"en"` and `"es"`.
- Do **not** hard-code English text in component files.
- The active language is determined by `SCOREBOARD_LANGUAGE` env var.

---

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Optional: configure environment
# Create a .env file with your settings, for example:
# UNO_OVERLAY_OID=your_token_here
# SCOREBOARD_LANGUAGE=en

# Start the app
python main.py
# → http://localhost:8080
```

```bash
# Docker (recommended for production)
docker-compose up -d
# → http://localhost:${EXTERNAL_PORT:-8080}
```

---

## Testing

```bash
# Run full test suite (excludes Playwright mobile tests)
pytest tests/ -v

# Run a specific module
pytest tests/test_game_manager.py -v

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing

# Run Playwright browser tests (requires: playwright install chromium)
pytest tests/test_mobile_viewport.py -v -m mobile_browser
```

**Test conventions:**
- `conftest.py` provides `mock_backend` (Backend with JSON fixtures) and `load_test_env` (clears AppStorage between tests).
- JSON fixtures in `tests/fixtures/` represent known game states — `base_model.json` (fresh game), `midgame_model.json`, `endgame_model.json`.
- Unit tests for scoring logic belong in `test_game_manager.py`.
- Unit tests for state mutations belong in `test_state.py`.
- Tests for HTTP communication go in `test_backend.py` — mock the `requests.Session` rather than making real HTTP calls.
- Full UI interaction tests using NiceGUI's test client go in `test_ui.py`.
- `asyncio_mode = auto` is set globally in `pytest.ini`; do not add `@pytest.mark.asyncio` manually.

**CI exclusions:** The `mobile_browser` marker is excluded from the default CI run. Never add tests that require a real browser to the default marker set.

---

## Linting

```bash
# Lint (mirrors CI)
flake8 app/ tests/ main.py --max-complexity=10
```

Rules enforced by CI:
- Max cyclomatic complexity: **10** per function.
- No unused imports (`F401`), no undefined names (`F821`).
- Line length: default flake8 limit (79) — the project uses standard line lengths.

Run `flake8` before committing. Pre-commit hooks in `.pre-commit-config.yaml` automate this.

---

## CI/CD

| Workflow | File | Trigger | Steps |
|----------|------|---------|-------|
| CI | `.github/workflows/ci.yml` | Push/PR to `main`, `dev` | flake8 lint → pytest (Python 3.11) → coverage |
| Docker publish (release) | `docker-publish.yml` | Release tag | Build & push to Docker Hub |
| Docker publish (dev) | `docker-publish-dev.yml` | Push to `dev` | Build & push `:dev` tag |

The Docker base image is `zauberzeug/nicegui:3.8.0`. When upgrading NiceGUI, update both `requirements.txt` and the `FROM` line in `Dockerfile`.

---

## Key Patterns & Conventions

### State access
Always use `State` accessor methods; never read from or write to `state.current_model` directly outside of `State` itself.

```python
# Correct
score = state.get_game(team=1, set_num=2)
state.set_game(team=1, set_num=2, value=score + 1)

# Wrong — bypasses validation
state.current_model["Team 1 Game 2 Score"] += 1
```

### UI updates
Always call `gui.update_ui()` after mutating state. Never call individual component refresh methods directly from outside the component.

### Adding a new UI component
1. Create a file in `app/components/`.
2. Class receives `gui: GUI` as its first constructor argument.
3. Use `app/theme.py` constants for all styling.
4. Use `app/messages.py` for all user-visible text.
5. Wire click/touch events through `ButtonInteraction`.
6. Add a unit test or UI test covering the new component's behavior.

### Adding a new route
Define the route handler in `app/startup.py`. Routes must pass through `AuthMiddleware` (automatically applied to all routes except `/login`).

### Overlay command pattern (overlays.uno)
Commands sent to the cloud API follow this envelope:
```python
{
    "command": "SetOverlayContent",  # or ShowOverlay, HideOverlay, etc.
    "data": { ... }
}
```
Custom overlay servers receive the full match state JSON directly via `POST /api/state/{id}`.

---

## Common Pitfalls

- **Do not hardcode display text** — always use `messages.py`.
- **Do not block the event loop** — long-running I/O must use the `ThreadPoolExecutor` in `Backend` or `asyncio.run_in_executor`.
- **Do not skip `Backend.save()`** — after any `GameManager` mutation, `Backend.save()` must be called so the overlay stays in sync.
- **Do not use `app.storage.user` or `app.storage.browser` directly** — always go through `AppStorage` which picks the right backend automatically and provides a test-safe in-memory fallback.
- **Visual-only settings must not propagate across browsers** — any setting that has no effect on overlay output must be listed in `_LOCAL_STORAGE_KEYS` in `app_storage.py` (for documentation) and must be read through `self._local_visual_settings` on the `GUI` instance rather than directly from `AppStorage`. Each `GUI` instance loads these settings from `AppStorage` once at construction time (in its own browser context) and caches them. The options dialog fires `on_visual_settings_changed()` on the owning instance to refresh the cache when a user changes a setting. Because `update_button_style()` uses the per-instance cache instead of calling `AppStorage.load()` directly, broadcasts from another tab never overwrite a browser's own visual preferences. Current local-only settings: button colors, button font, button icon visibility/opacity.
- **Custom overlay IDs start with `C-`** — `Backend.is_custom_overlay()` checks this prefix. Do not assume plain tokens are always cloud overlays.
- **Font scale matters** — each custom font in `app/theme.py:FONT_SCALES` has a `scale` and `offset_y` value for visual normalization. When adding a new font, measure and add both values.
- **Undo is a flag, not a stack** — `GameManager` undo reverses only the most recent action of that type. There is no multi-level history.
- **`WeakSet` for broadcast** — `GUI._instances` uses `WeakSet` so closed tabs are garbage-collected automatically. Never convert it to a strong-reference container.

---

## Documentation Files

| File | Purpose |
|------|---------|
| `README.md` | End-user setup and configuration guide |
| `DEVELOPER_GUIDE.md` | Architecture deep-dive and coding patterns |
| `CUSTOM_OVERLAY.md` | Guide for building a custom overlay server |
| `CUSTOM_OVERLAY_API.yaml` | OpenAPI 3.0 spec for the custom overlay REST contract |
| `AGENTS.md` | This file — AI agent guide |

When making changes that affect user-facing behavior, environment variables, or the custom overlay API contract, update the corresponding documentation file.
