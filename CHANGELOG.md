# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once a first tagged release ships.

## [Unreleased]

### Added

- **DX**: `ruff` lint set expanded to include `I` (isort) and `B` (flake8-bugbear);
  `mypy` checks now cover `app/api/routes` and `app/api/middleware` in addition to
  the original `app/api` service layer (`pyproject.toml`).
- **Frontend a11y**: top-level `ErrorBoundary` wraps `ScoreboardView` and
  `ConfigPanel`, forwarding React-caught errors through the existing
  `errorReporter` so they land in the same backend log stream as
  `window.onerror`. Score buttons gained `aria-label` / `aria-live="polite"`
  so assistive tech announces score changes.
- **Docs**: this `CHANGELOG.md`.
- **Preview style override**: the standalone `/preview` page now shows a
  discreet style selector when the overlay advertises more than one style,
  letting a remote viewer render their preview with a different template
  via the existing `?style=` query param on `/overlay/{id}` — without
  touching the session's saved `preferredStyle` used for streaming. The
  `/api/v1/links` response includes a `styles` entry in the preview URL
  so the standalone page knows what options to offer.
- **HTTP compression**: `fastapi.middleware.gzip.GZipMiddleware` is now
  attached to the FastAPI app with `minimum_size=1024`, registered
  outermost so it compresses the final response body after the
  observability middlewares (`app/bootstrap.py`).
- **Static asset caching**: new `CachedStaticFiles` subclass stamps
  `Cache-Control: public, max-age=31536000, immutable` on `/fonts` and
  the Vite-fingerprinted `/assets` mount for 200/206/304 responses. The
  SPA shell `index.html` gets `no-cache, must-revalidate` so clients
  always pick up new hashed asset URLs after a frontend rebuild.
- **Observability**: `perf_counter` timing spans wrap the overlay hot
  paths — `Backend.save_model` (split into `.model` and `.push` so the
  executor branch is measured where the work actually runs),
  `Backend.get_current_model`, `Backend.get_current_customization`, and
  `GameService.get_state`. Logs at DEBUG under threshold, WARNING above
  (500 ms remote / 50 ms in-process).

### Changed

- **Frontend `ConfigPanel`**: the six config sections (Teams / Overlay /
  Position / Buttons / Behavior / Links) are now `React.lazy` chunks behind
  a `Suspense` boundary with a shimmer skeleton fallback. Production build
  emits a separate JS bundle per section (~14 kB deferred from initial open).
- **Fonts**: all 10 scoreboard `@font-face` rules use `font-display: swap` so
  scores stay visible during font fetch instead of hiding under FOIT.
  `index.html` gets `<link rel="preconnect">` hints for the Google Fonts
  origins the Material Icons stylesheet uses.
- **Backend customization cache**: `GameService.refresh_customization` now
  has a 5 s TTL read-through cache per session, coalescing bursts of
  identical fetches when the React UI reopens the config panel. Writes
  prime the timestamp so the next read is immediately consistent.
- **Backend HTTP client**: `Backend.session` now mounts an `HTTPAdapter`
  with `pool_connections=10`, `pool_maxsize=20`, and
  `Retry(total=2, backoff_factor=0.3, status_forcelist=(502,503,504))`
  on both `http://` and `https://` so transient overlay-server hiccups
  no longer surface to the UI and the `ThreadPoolExecutor` has enough
  pool headroom to avoid new-connection overhead under load.
- **Logs**: demoted noisy INFO log lines on `Backend.save_model` /
  `save_json_model` / `save_json_customization` / `get_current_model` /
  `get_current_customization` to DEBUG so the new timing WARNINGs are
  not drowned out during a match.

### Fixed

- **Backend**: `GameService.set_score` rejects `set_number` values below 1 or
  above `sets_limit` (was upper-bound-only before).
- **Backend WSHub**: concurrent broadcast with per-socket timeout
  (`_BROADCAST_SEND_TIMEOUT`) so a stuck subscriber can't stall updates to
  the rest; the cleanup pass no longer pops an OID whose set was replaced
  by a concurrent reconnect.
- **Backend customization cache**: initial call always hits the backend even
  on systems where `time.monotonic()` starts close to zero (sentinel-`None`
  default instead of `0.0`).

### Security

- **Auth**: new `STRICT_OID_ACCESS=true` env var flips the default so any
  authenticated user without an explicit `control` field is denied (`403`).
  Off by default to preserve single-tenant setups; see
  [AUTHENTICATION.md](AUTHENTICATION.md) for details.
- **Overlay-id sanitizer**: `OverlayStateStore._sanitize_id` replaces the
  prior `os.path.basename` stripping with a strict allow-list regex
  (`^(?!\.{1,2}$)[A-Za-z0-9._-]{1,64}$`). Invalid ids now raise
  `ValueError` at the single choke point between user input and the
  on-disk `overlay_state_<id>.json` paths; `overlay_exists`,
  `create_overlay`, and `delete_overlay` catch it and return `False` to
  preserve their bool contract. See [CUSTOM_OVERLAY.md](CUSTOM_OVERLAY.md)
  for the allowed character set.
- **Iframe src validation**: `OverlayPreview` now runs `overlayUrl`
  through a scheme check that only accepts `http:`/`https:`, so
  `javascript:`, `data:`, `file:`, and similar cannot reach the iframe.
  The Uno-overlay hostname match was also tightened from a substring
  test to an exact hostname / subdomain match so `evil-overlays.uno`
  does not ride the Uno code path.
