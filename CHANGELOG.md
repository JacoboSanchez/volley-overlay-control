# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once a first tagged release ships.

## [Unreleased]

### Added

- **In-process overlay engine**: `LocalOverlayBackend` serves Jinja2 overlay
  templates and broadcasts state to OBS via WebSocket entirely in-process — no
  external overlay server required. Persists overlay state to JSON files, debounces
  WS broadcasts at 50 ms, and exposes 16 bundled templates out of the box
  (`#145`, `#143`).
- **Custom overlay manager**: password-protected `/manage` admin page (vanilla JS,
  no React) with CRUD for custom overlays. `GET`/`POST /api/v1/admin/custom-overlays`
  and `DELETE /api/v1/admin/custom-overlays/{name}`; optional `copy_from` param
  deep-clones an existing overlay's config on creation (`#146`, `#160`).
- **Standalone `/preview` page**: full-screen preview SPA route with a low-opacity
  toolbar for zoom −/+, dark/light backdrop toggle, and native fullscreen. Preview
  URL encoded in `/api/v1/links` for both custom and overlays.uno OIDs (`#163`).
- **Per-session style override in preview**: discreet style `<select>` in the
  `/preview` toolbar lets a remote viewer render with a different template via the
  existing `?style=` param without changing the session's saved `preferredStyle`
  used for streaming. Selector appears only when the server advertises more than
  one style; preview URL gains a `styles=` hint from `/api/v1/links` (`#183`).
- **Mosaic preview grid**: `?style=mosaic` on `/overlay/{id}` renders all overlay
  layouts side-by-side in a responsive iframe grid for at-a-glance style selection.
  A new `get_renderable_styles()` list on `OverlayStateStore` is a superset of the
  user-selectable list to keep `mosaic` out of the style picker (`#173`).
- **OID resolution by file existence**: `resolve_overlay_kind()` in
  `app/overlay_backends/utils.py` determines `CUSTOM` (overlay JSON exists on disk),
  `UNO` (22-char alphanumeric format), or `INVALID` — eliminating the required `C-`
  prefix. Legacy `C-` IDs continue to work (`#164`).
- **`APP_TITLE` env var**: configures the browser tab title, SPA `<title>`, PWA
  manifest `name`/`short_name`, and `/manage` page heading without rebuilding the
  frontend (default: `Volley Scoreboard`) (`#165`).
- **Frontend error reporting**: `window.onerror` / `unhandledrejection` pipeline
  ships errors to `POST /api/v1/log` so JavaScript exceptions surface in the
  backend log stream. `ErrorBoundary` wraps `ScoreboardView` and `ConfigPanel` and
  forwards React-caught errors through the same reporter (`#171`, `#176`).
- **Logging — JSON output + correlation IDs**: `dictConfig`-based logging pipeline
  (`app/logging_config.py`) with two formatters: `text` (ANSI, default) and `json`
  (one object per line, suitable for Loki/Datadog/CloudWatch). Every request gets a
  `X-Request-ID` correlation header and `request_id` injected into log records by
  `CorrelationMiddleware`. Uvicorn's access log is routed into the same pipeline
  (`#170`).
- **Secret scrubbing**: `RedactFilter` on the root logger scrubs `Bearer …` tokens
  and `password=`/`api_key=`/`token=`/`secret=` key-value pairs from every log
  record, complementing the existing `redact_url`/`redact_oid` helpers (`#171`).
- **WS zombie detection**: `WSControlClient` tracks `_last_inbound_ts`; `is_connected`
  returns `False` and the read loop breaks to trigger reconnect when no inbound
  traffic arrives within 55 s, preventing a hung socket from silently failing sends
  while blocking the HTTP fallback (`#167`).
- **Per-OID session creation locks**: each overlay ID now gets its own `asyncio.Lock`
  for the first-init path, preventing duplicate backend initialisation under
  concurrent requests (`#167`).
- **Observability timing spans**: `perf_counter` spans wrap `Backend.save_model`
  (split into `.model` and `.push` phases), `get_current_model`,
  `get_current_customization`, and `GameService.get_state`. Logs at DEBUG below
  threshold (500 ms remote / 50 ms in-process), WARNING above (`#180`).
- **HTTP compression**: `GZipMiddleware(minimum_size=1024)` attached outermost in
  `app/bootstrap.py` so it compresses final response bodies after observability
  middlewares (`#180`).
- **Static asset caching**: `CachedStaticFiles` subclass stamps
  `Cache-Control: public, max-age=31536000, immutable` on `/fonts` and the
  Vite-fingerprinted `/assets` mount. `index.html` gets `no-cache, must-revalidate`
  so clients always pick up new hashed asset URLs after a frontend rebuild (`#180`).
- **`STRICT_OID_ACCESS` env var**: flips the default so any authenticated user
  without an explicit `control` field is denied with `403`. Off by default to
  preserve single-tenant setups; see `AUTHENTICATION.md` (`#174`).
- **Frontend a11y**: score buttons gained `aria-label` / `aria-live="polite"` so
  assistive tech announces score changes (`#176`).
- **DX — ruff + mypy expansion**: ruff `select` now includes `I` (isort) and `B`
  (flake8-bugbear); mypy checks cover `app/api/routes` and `app/api/middleware` in
  addition to the existing `app/api` service layer (`#176`).
- **OpenAPI snapshot + TypeScript tooling**: `frontend/openapi.json` snapshot and a
  CI schema-drift guard ensure the generated API types stay in sync with the backend
  (`#147`).
- **`?oid=` URL param**: documented in `FRONTEND_DEVELOPMENT.md` — passing `?oid=`
  in the control URL pre-selects an overlay and persists it, replacing any previously
  stored value (`#178`).

### Changed

- **Architecture — NiceGUI retired**: the entire NiceGUI UI layer (~6 000 lines) is
  removed. The React frontend is now the sole operator interface; `main.py` becomes
  pure FastAPI + Uvicorn glue (`#139`).
- **Architecture — overlay server merged in**: the standalone overlay server is
  folded into the backend, eliminating the double-hop latency (Backend → Overlay
  Server → OBS) and an entire service deployment (`#143`).
- **Frontend — full TypeScript migration**: all `.js`/`.jsx` files under
  `frontend/src/` converted to `.ts`/`.tsx`. Typed prop interfaces, exported API
  types, OpenAPI-generated `GameState` schema, and type-safe test mocks across eight
  incremental PRs (`#150`–`#156`).
- **Backend factory**: `create_app()` extracted into `app/bootstrap.py` so tests
  build an isolated app via `TestClient(create_app())` without relying on `main.py`
  import side effects (`#147`).
- **`overlay_backends/` split**: the 721-line monolith split into a per-strategy
  package (`uno.py`, `local.py`, `base.py`, `utils.py`), mirroring the routes split
  pattern (`#147`).
- **`app/api/routes.py` split**: the 394-line routes file split into domain
  submodules under `app/api/routes/` — `lifespan`, `session`, `state`, `game`,
  `display`, `customization`, `overlays`, `links`, `admin` (`#157`).
- **Docker image slimmed**: stage 2 switches from `COPY . .` to an explicit whitelist
  (`main.py`, `app/`, `font/`, `overlay_static/`, `overlay_templates/`,
  `frontend/dist`). `.dockerignore` expanded to exclude docs, tests, scripts, and
  compose files from the build context (`#158`).
- **Service worker unified**: the legacy hand-written `app/pwa/sw.js` removed;
  `vite-plugin-pwa`'s Workbox-generated worker is the single service worker.
  `/sw.js` endpoint and `app/pwa/` directory deleted (`#159`).
- **Typed state model**: `State`'s internal `dict[str, str]` replaced with a `Serve`
  enum and `GameState` dataclass. Legacy dict format preserved at system boundaries
  via `_from_dict()`/`_to_dict()` — no changes in `GameManager`, `GameService`,
  backends, or overlay code (`#166`).
- **Logger hygiene**: all loggers switched to `getLogger(__name__)` (replaces
  hardcoded strings like `"Storage"`, `"APIRoutes"`). Log calls use lazy `%`-style
  args; OID values redacted from URLs before logging (`#169`).
- **Backend HTTP client**: `Backend.session` mounts an `HTTPAdapter` with
  `pool_connections=10`, `pool_maxsize=20`, and
  `Retry(total=2, backoff_factor=0.3, status_forcelist=(502,503,504))` on both
  `http://` and `https://` (`#180`).
- **Backend customization cache**: `GameService.refresh_customization` now has a 5 s
  TTL read-through cache per session, coalescing bursts of identical fetches.
  Writes prime the timestamp so the next read is immediately consistent (`#175`).
- **`ConfigPanel` lazy sections**: the six config sections (Teams / Overlay /
  Position / Buttons / Behavior / Links) are `React.lazy` chunks behind a `Suspense`
  boundary with a shimmer skeleton fallback. Production build emits a separate JS
  bundle per section (~14 kB deferred from initial open) (`#175`).
- **Score tap debounce**: single-tap debounce drops from 400 ms to 220 ms, halving
  perceived latency for a normal point while still distinguishing double-taps (~150 ms
  typical) (`#172`).
- **Neumorphic CSS tokens deduped**: shared token variables extracted into
  `jersey_shared.css`, eliminating repetition across jersey overlay stylesheets
  (`#168`).
- **Fonts**: all 10 scoreboard `@font-face` rules use `font-display: swap` so scores
  stay visible during font fetch instead of hiding under FOIT (`#180`).
- **Noisy log lines demoted**: INFO logs on `Backend.save_model`, `save_json_model`,
  `save_json_customization`, `get_current_model`, `get_current_customization` demoted
  to DEBUG so timing WARNINGs are not drowned out during a match (`#180`).
- **Backend i18n removed**: `app/messages.py` `Messages` class and
  `SCOREBOARD_LANGUAGE` env var dropped. The Spanish placeholder defaults (`Local` /
  `Visitante`) are replaced with empty strings; users set team names via `APP_TEAMS`
  or the runtime Teams config panel (`#177`).

### Fixed

- **Overlay WebSocket URL**: after capability-URL hardening, `serve_overlay` now
  passes the SHA-256 `output_key` into the template context so `wsUrl` is built
  from the correct key. The prior raw `target_id` caused `/ws/` to close with code
  4004 and no state to reach the page (`#161`).
- **Preview initial load**: `usePreview` now waits for the session to be ready before
  firing `GET /api/v1/links`. The prior race with `initSession` caused the preview to
  be blank on first load and appear only after a manual refresh (`#162`).
- **`/manage` service worker bypass**: `/manage` added to `navigateFallbackDenylist`
  in the Workbox config so the PWA no longer intercepts navigation to the overlay
  manager and serves `index.html` instead of the FastAPI-rendered page (`#182`).
- **`GameService.set_score` bounds**: `set_number` is now validated against both
  lower (`< 1`) and upper (`> sets_limit`) bounds. Previously only the upper bound
  was enforced (`#174`).
- **WSHub concurrent broadcast**: per-socket `_BROADCAST_SEND_TIMEOUT` prevents a
  stuck subscriber from stalling updates to the rest; the cleanup pass no longer
  pops an OID whose set was replaced by a concurrent reconnect (`#174`).
- **Customization cache sentinel**: initial call always hits the backend even on
  systems where `time.monotonic()` starts near zero — sentinel defaults to `None`
  instead of `0.0` (`#175`).

### Security

- **Authentication audit**: `AUTHENTICATION.md` documents full route/mount coverage
  with findings F-1–F-5. `/list/overlay` now requires `OVERLAY_MANAGER_PASSWORD`
  (F-4) — previously unauthenticated (`#148`).
- **Capability URL hardening**: `resolve_overlay_id` accepts the SHA-256 output key
  only — not the raw overlay id — so `/overlay/{…}` and `/ws/{…}` are true
  capability URLs. Dead pass-through `AuthMiddleware` removed (`#149`).
- **Overlay-id sanitizer**: `OverlayStateStore._sanitize_id` replaced the prior
  `os.path.basename` stripping with a strict allow-list regex
  (`^(?!\.{1,2}$)[A-Za-z0-9._-]{1,64}$`). Invalid IDs raise `ValueError` at the
  single choke point between user input and on-disk paths (`#180`).
- **Iframe src validation**: `OverlayPreview` runs `overlayUrl` through a scheme
  check that only accepts `http:`/`https:`. The Uno-overlay hostname match tightened
  from substring to exact hostname/subdomain so `evil-overlays.uno` cannot ride the
  Uno code path (`#180`).
- **`secrets.compare_digest`**: constant-time comparison used in `require_admin`,
  `check_api_key`, and the overlay server token check to prevent timing attacks
  (`#149`).

---

## [4.1.0] - 2026-04-08

### Added

- REST API + WebSocket architecture decoupling frontend from backend; OID
  authorization, session management, and WebSocket authentication.
- `GET /api/v1/overlays` endpoint for predefined overlays.
- `preferredStyle` whitelisted in REST API.
- React scoreboard GUI as the primary operator interface.
- Overlay preview with transparent background.
- Button font selector, team selector, links/theme dialogs, configuration panel
  with logo previews.
- OID persisted across page reloads with logout button.
- Auto-resolve output URL on session init.

### Fixed

- WebSocket reconnect loop.
- Preferred style overwritten by OID default on reconnect.
- `extract_oid` regex aligned with `validate_oid` for all valid OID characters.
- Customization refreshed from overlay server on every load.
- Custom overlay output URL handling.
- Session race conditions.
- Customization refresh and `get_styles` wrapped in thread pool.

### Changed

- `requests` bumped from 2.32.5 to 2.33.1.
- Alternative NiceGUI frontend removed from project.
