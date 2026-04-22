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
