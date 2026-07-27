# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**This file covers the current major (6.x) and the unreleased work in
progress.** Older releases are in
[`docs/CHANGELOG-archive.md`](docs/CHANGELOG-archive.md); the release
workflow moves a superseded major there automatically. Every change is
written into `## [Unreleased]` below; nothing is ever appended to the
archive by hand.

## [Unreleased]

### Security

- **The rate limiter now covers the capability-token routes, and counts
  the status a token miss actually returns.** It watched only `/api/v1/`
  and counted only 401/403 — but an unknown `public_token` on
  `/overlay/*` or `/follow/*` is reported as **404**, so token guessing
  incremented nothing at all and was never throttled. A second `capability`
  surface now covers `/overlay/*`, `/follow/*` and `/match/*`, counting
  401/403/404. `/api/v1/` still ignores 404, where it means an ordinary
  missing resource rather than a credential probe.

  Buckets are keyed on `(surface, IP)` rather than IP alone. This is what
  makes widening the watched set safe: with one shared bucket, 403s
  collected by somebody's SPA against `/api/v1/` could have taken an
  on-air `/overlay/` browser source off the air — trading a brute-force
  risk for an availability one.

  `/ws/*`, `/media/**` and `/metrics` are deliberately still unwatched,
  and `AUTHENTICATION.md` now says why for each: a WebSocket handshake is
  ASGI scope type `websocket` and is structurally invisible to this
  middleware; `/media` carries no credential, so counting its 404s would
  risk blocking a venue's icons after an ordinary delete without
  addressing the actual concern (volume); and `/metrics` needs
  authentication, not throttling.

- **`AUTH_RATE_LIMIT_*` overrides now take effect.** They were evaluated
  at module import, so they only applied if the variable was set before
  the limiter was first imported — a footgun in tests and embedded use,
  and the reason the existing suite had to `importlib.reload` the module
  to change a limit. They are read per call now.

### Added

- **`tests/test_docs_consistency.py` — a drift guard for mechanically
  checkable doc claims**, in the same spirit as `tests/test_env_docs.py`.
  It asserts that the overlay-template and selectable-style counts quoted
  in the docs match what is on disk, that README's explicit style list
  matches `get_available_styles_list()`, that the documented quality-gate
  table matches the steps in `ci.yml` **in both directions** (a CI step
  that can fail the build and is not documented also fails), that every
  relative cross-document link and `#anchor` resolves, and that the
  changelog archive split stays clean. Each check fails loudly if its own
  pattern stops matching, so a reworded doc cannot silently disable the
  guard. This class of error — a template count stated as both 16 and 30,
  a gate list missing six gates CI fails on — is what
  [#448](https://github.com/JacoboSanchez/volley-overlay-control/issues/448)
  was opened about.

- **`voc_rate_limit_blocks_total{surface}`** — counts requests
  short-circuited with 429. Previously a brute-force attempt and a
  shared-NAT lockout of legitimate operators were indistinguishable in
  `/metrics`: both were just a `status="429"` label on the latency
  histogram, so an operator could not alert on either.

### Fixed

- A dangling `#state-model` anchor in `FRONTEND_DEVELOPMENT.md` (the
  heading is *State Model Reference*), and the `/api/v1/ws` module
  docstring, which said the endpoint was authorized "two ways" when it
  resolves three.

- Two wrong paths in the new `AUTHENTICATION.md` §2.3 rows: the live-stats
  route is `/api/v1/matches/live/stats` (not `/api/v1/live-stats`), and the
  board team-group parameter is `{group_key}`. The guard now checks every
  path in that table against the committed OpenAPI schema, so a route
  inventory can no longer send an integrator to a 404.

- `FRONTEND_DEVELOPMENT.md`'s WebSocket section listed only two of the three
  credentials `/api/v1/ws` accepts, omitting the `?u=<username>&oid=<oid>`
  public bookmark that the bundled client already emits — so an integrator
  could have concluded bookmark-mode boards get no real-time updates. It now
  tabulates all three, and notes that the `X-Control-Token` header form is
  unavailable on a browser WebSocket.

- **Docker Compose no longer drops unlisted application settings from
  `.env`.** Both the host-port and Traefik deployment files now pass the full
  optional `.env` through to the container, including security headers, auth
  rate limits, request caps, icon limits, webhook retries, WebSocket limits,
  and future settings. This optional-file support requires Docker Compose
  2.24.0 or newer. Environment documentation guards now also catch stale
  example entries and indirect `_env_*` readers. Fixes
  [#445](https://github.com/JacoboSanchez/volley-overlay-control/issues/445).

### Documentation

- **The two ways to control a board without logging in are finally
  documented.** An overlay's `control_token` (the shareable
  `/board?c=<token>` operator link) and the `public_control` flag (the
  stable `?u=<username>&oid=<oid>` bookmark) both grant *full board
  control with no credential*, and neither appeared anywhere in the
  operator-facing docs — not even in the auth audit, which carefully
  covered `/media/**` while omitting these. `AUTHENTICATION.md` gains
  §1.2, a four-credential table (owner cookie, control token, public
  bookmark, OBS `public_token`) with precedence, failure statuses and how
  to revoke each; `README.md` gains a *Sharing board control* section
  aimed at operators. Both state plainly that `public_control` trades an
  unguessable token for a **guessable** URL — anyone who guesses a
  username and an overlay id gets the board — so it is off by default and
  belongs on trusted networks only. Fixes
  [#430](https://github.com/JacoboSanchez/volley-overlay-control/issues/430).

- **Session revocation is documented per mechanism, because they differ.**
  `AUTHENTICATION.md` §1.2 now spells out that logout revokes the current
  session, a **self password change deliberately keeps it alive** (every
  *other* session is revoked), and only an admin password reset or account
  delete kills all of them. The distinction matters after a cookie theft: if
  an attacker holds a copy of the cookie you are currently using, changing
  your password from that same browser does not lock them out — log out, or
  have an admin reset the account. Behaviour is unchanged; the docs
  previously listed "password change" as a revocation without the caveat,
  contradicting §2.2 of the same file.

- **The route inventory is complete and method-accurate for the first
  time.** 36 registered `/api/v1` routes had no row in `AUTHENTICATION.md`
  — every `/teams/mine*`, `/my/groups*` and `/customization/presets*`
  route, four `display/*` board actions, the whole admin
  teams/groups/presets surface, and the two unauthenticated endpoints
  (`/app-config`, `/_log`). Five non-API surfaces were missing too
  (`/metrics`, `/health/ready`, both `/match/{id}/report*` routes, and the
  public `/matches/{public_token}` listing). A document calling itself the
  per-route auth inventory while omitting 43% of the API is worse than
  none: a reader takes absence for "not an access path".

  The guard now compares **`(method, path)` pairs across the whole schema**,
  in both directions. Path-only comparison had let rows advertise methods
  that 405 — `GET /api/v1/admin/teams` among seven such claims, all from
  over-compressed rows that listed two methods against two paths where each
  method belonged to only one.

- **The route inventory now distinguishes "needs a login" from "needs a
  board credential".** `AUTHENTICATION.md` §2.3 marked the whole scoring
  surface `Y + OID` ("requires a logged-in user"), which was wrong: those
  routes are reachable with a control token and no account. They are now
  `B`, and the missing rows (`/audit`, `/live-stats`, `/session/rules`,
  `/game/start-match`, `/game/undo`, `/style-capabilities`, `/board/*`,
  overlay CRUD, `regenerate-control-token`) are listed. `/api/v1/ws` was
  documented as cookie-only and accepts all three board credentials.

- **One home per topic across the docs.** The auth model was maintained
  independently in four files (`README.md`, `AGENTS.md`,
  `AUTHENTICATION.md`, `DEVELOPER_GUIDE.md`), which is how they drifted
  apart. `AUTHENTICATION.md` is now the single source of truth; the others
  carry a one-line summary and a link. `AGENTS.md` gains a documentation
  ownership table naming the owning file for each topic, and
  `FRONTEND_DEVELOPMENT.md`'s *Authentication* section now documents the
  control-token option a headless client actually wants (with a `curl`
  example) instead of restating the cookie model. Fixes
  [#448](https://github.com/JacoboSanchez/volley-overlay-control/issues/448).

- **The release workflow archives a superseded major by itself.** Cutting a
  version that bumps the major now moves the old major into
  `docs/CHANGELOG-archive.md` and retargets the "current major (N.x)"
  sentence, inside the release commit — so `main` never has to pass through
  a state where the changelog spans two majors. Minor and patch releases
  move nothing, and `--dry-run` previews which releases would move without
  writing. Neither file's heading states a version *range* any more: that
  was one more hand-maintained number waiting to drift.

- **`CHANGELOG.md` is 83 KB instead of 288 KB.** Releases `5.9.0` and
  earlier moved to
  [`docs/CHANGELOG-archive.md`](docs/CHANGELOG-archive.md), linked from the
  top of the live file. An entry is mandatory on every PR, so every
  contributor and every agent was reading and appending to a 5,400-line
  file; the live one now covers the current major plus `[Unreleased]`. No
  entry was reworded and none was lost. `scripts/release/cut_changelog.py`
  only ever reads `[Unreleased]`, so the release workflow is unaffected;
  the once-per-major archiving procedure is in `CONTRIBUTING.md`.

- **Concurrent overlay updates can no longer roll back persisted state.**
  Mutations and atomic JSON writes are now ordered per overlay across both
  synchronous and asynchronous callers, so a delayed older snapshot cannot
  replace a newer one on disk. The shared persistence cores also keep the
  sync and async paths on the same locking behavior. Fixes
  [#429](https://github.com/JacoboSanchez/volley-overlay-control/issues/429).

- **Screen readers now follow the selected language throughout the scoring
  controls.** Score, timeout, serve, dialog, and recent-action accessible
  labels and gesture instructions now use the six-locale catalog. Icon-only
  HUD controls expose translated names and pressed state without announcing
  Material icon ligatures, and a source guard rejects new hard-coded
  accessible text. Fixes
  [#436](https://github.com/JacoboSanchez/volley-overlay-control/issues/436).

- **Scoring a point no longer re-reads and re-parses the entire audit
  log.** `GameService.add_point` writes its audit record *before* building
  the state response, and that write bumps the log version the live-stats
  memo is keyed on — so the memo missed on every single point, and each
  miss walked the active audit file plus every rotated one
  (`AUDIT_LOG_MAX_BYTES` × `AUDIT_LOG_MAX_FILES`, 25 MiB with the
  defaults), `json.loads`-ing every line before running nine aggregation
  passes.

  `action_log` now keeps the parsed records per OID and folds each
  newly-written record into that cache, so the steady-state cost of a
  point is one line appended to a file rather than a full reparse. The
  cache is invalidated on rotation (which can discard the oldest file) and
  on `clear`/`delete`. Aggregation logic is untouched — this changes only
  how the records reach it.

  Handlers still call `GameService` synchronously on the event loop, as
  before. Moving those calls to a worker thread was tried and reverted:
  the single-threaded loop is what currently makes a mutation atomic with
  respect to every other handler, and `session.lock` is held only by the
  mutation routes — `/state` and the WebSocket snapshot never take it,
  and `get_state` itself writes via `_sync_table_tennis_serve`. Offloading
  therefore needs a full audit of every session reader first, tracked
  separately.

- **`WSHub` no longer depends on being called from the event loop to
  deliver a broadcast.** `broadcast_sync` resolved its loop with
  `asyncio.get_running_loop()`, which raises off-loop; the handler logged
  at debug level and returned, so the broadcast vanished with no visible
  error. Every current caller does run on the loop, so this was latent
  rather than live — but it made "must run on the loop" an undocumented
  precondition of a fire-and-forget API. `WSHub` now captures the loop at
  startup and schedules through `call_soon_threadsafe` when off-loop, the
  same approach `ObsBroadcastHub` already used.

- **The per-OID caches are now released when a session is retired.** The
  live-stats payload and the parsed audit records were keyed by OID and
  never evicted — `clear_cache` was documented as test-only, "production
  never needs it" — so an instance retained the full history of every
  overlay it had ever served. `SessionManager.remove` and
  `cleanup_expired` now drop both.

- **Live-stats failures are no longer silent.** Five `except Exception`
  handlers in `game_service.py` returned a fallback with no log line. The
  one wrapping `compute_live_stats` was the worst: on failure `/state`
  degraded permanently and invisibly (`current_set_started_at` became
  `None`, the summary set silently fell back to `current_set - 1`). All
  five now log.

- **The Docker healthcheck no longer marks the container permanently
  unhealthy when `APP_PORT` is changed.** Both `docker-compose.yml` and
  `docker-compose.traefik.yml` hardcoded `localhost:8080` in their
  `healthcheck.test`. A compose-level healthcheck overrides the image's
  own `HEALTHCHECK` (which already resolved `APP_PORT` correctly), so any
  operator moving the app off 8080 got a container that never became
  healthy — and, behind Traefik's health-gating plus
  `restart: unless-stopped`, never became routable either. Both files now
  interpolate `${APP_PORT:-8080}`, as does the published container port in
  `docker-compose.yml`.

### Security

- **Frontend build tooling now uses `fast-uri` 3.1.4.** The transitive
  dependency (via `vite-plugin-pwa` / Workbox / `ajv`) is bumped from
  3.1.2 to include the fixes for GHSA-4c8g-83qw-93j6 and
  GHSA-v2hh-gcrm-f6hx.

- **`requirements.lock` no longer ships versions below the floors declared
  in `requirements.txt`.** CI and the Dockerfile install from the lock
  only, so the declared minimums were not being enforced: the lock carried
  `fastapi==0.137.2` against a `>=0.139.2` floor, `uvicorn==0.49.0`
  against `>=0.51.0`, and `alembic==1.18.4` against `>=1.18.5`. (The two
  CVE-driven floors, `starlette` and `urllib3`, were correctly pinned.)
  The lock has been recompiled, and CI now fails when it cannot satisfy
  `requirements.txt`.

- **Migrated the router off the vulnerable `react-router-dom`.**
  `react-router-dom@7.18.1` is affected by GHSA-qwww-vcr4-c8h2 (high, RSC
  Mode CSRF bypass) and no patched release exists — 7.18.1 is the last
  version ever published, because React Router v8 folded DOM support into
  the core `react-router` package. The dependency is now
  `react-router@8.3.0`, which is above the advisory range.

  This SPA only uses the declarative API (`BrowserRouter`, `Routes`,
  `Route`, `Link`, `NavLink`, `Navigate`, `Outlet`, `MemoryRouter`,
  `useLocation`, `useNavigate`), all of which v8 exports unchanged, so the
  migration is the package swap plus the import specifier in 20 files.
  Verified by driving the built SPA in a real browser: anonymous access to
  a protected route still redirects to login, in-app links still navigate
  client-side without a full reload, the browser back button is still
  handled by the router, and `/board` still loads — with no
  module-resolution or router errors in the console.

  **This raises the Node floor for building the frontend to 22.22.**
  `react-router@8.3.0` declares `node >=22.22.0`, while CI selected Node 20
  and the docs advertised 20+ — so the documented environment would have
  installed an unsupported dependency, and `npm ci` would have failed
  outright anywhere `engine-strict` is set. CI now uses Node 22,
  `README.md` and `CONTRIBUTING.md` state 22.22+, and `frontend/package.json`
  declares the `engines.node` range so the mismatch cannot drift silently
  again. The Docker image already built the frontend on a newer Node, so
  published images were never affected.

### Changed

- **Type checking now covers the bodies of unannotated functions.**
  `check_untyped_defs` was off, so mypy skipped the body of every function
  without annotations while reporting "no issues found in 114 source
  files". Turning it on surfaced five real defects, now fixed: a variable
  reused with two different types in `app/config_validator.py`, an
  undeclared mixin attribute contract in `app/overlay_backends/base.py`,
  a wrongly-inferred payload dict in `app/bootstrap.py`, and an
  unguarded `Path(self.directory)` in `SPAStaticFiles._index_response`
  where `StaticFiles.directory` is optional upstream — that one would
  have raised `TypeError` rather than 404ing if the SPA were ever mounted
  without a directory. `split_custom_oid` / `strip_legacy_prefix` now
  declare the `None` they already accepted at runtime.
- **Lint warnings can no longer accumulate silently.** `npm run lint` runs
  with `--max-warnings 0`, and `no-explicit-any`, `no-unused-vars` and the
  three `jsx-a11y` rules are errors rather than warnings — the cleanup they
  were staged behind is complete. The four deliberate `autoFocus` uses on
  single-purpose auth pages carry justified inline disables.
- **The backend coverage floor lives in `pyproject.toml`.** It existed only
  as a `--cov-fail-under=70` flag in CI, so the plain `pytest --cov=app`
  documented in `AGENTS.md` enforced nothing.
- CI now runs the backend suite against **Python 3.14** as well as 3.11.
  3.14 is what the Dockerfile ships and it had never been tested.
- Every CI job now sets `timeout-minutes`; a hung job previously ran until
  GitHub's 6-hour default.
- `AGENTS.md` now lists the quality gates CI actually enforces (it omitted
  bandit, pip-audit, npm audit, eslint, prettier and the OpenAPI
  schema-drift check), corrects the claim that `npm run build` runs `tsc`
  (it is `vite build`, which does not type-check), and fixes the overlay
  template count (30 files, 27 selectable — one place said 16).

### Removed

- **Dropped the unused `feat/multi-user-db` deployment scaffolding.**
  `docker-publish-new.yml`, `docker-compose.traefik.new.yml` and
  `.env.traefik.new.example` duplicated their mainline counterparts and
  carried a personal hostname as the example value. The multi-user
  refactor they staged is merged.
- **Dropped the `PUID`/`PGID` environment knobs** from
  `docker-compose.yml`. Nothing read them: `docker-entrypoint.sh`
  hardcodes uid/gid 1000. They invited operators to set a value that
  silently did nothing.

## [6.2.2] - 2026-07-20

### Changed

- Refreshed the `08-match-report.png` README screenshot for the
  equal-height scoreboard panels fix below.

### Fixed

- **The winner badge no longer makes one scoreboard panel taller than
  the other.** The match report's hero scoreboard centred each team
  panel at its natural height, so the panel carrying the 🏆 winner
  badge grew past its neighbour. The two panels now stretch to the
  same row height, with each panel's logo/name/sets/badge stack
  vertically centred inside it.

- **Match report chart lines no longer blend together when both teams
  resolve to near-identical colours.** The print report's score-evolution
  chart forced a fallback colour on team 2 only when both teams' resolved
  chart colours were *exactly* equal, so two almost-equal colours — most
  visibly the two near-whites both teams get in the dark-scheme palette
  when their brand colours are too dark to read on the dark surface —
  rendered as a single indistinguishable trace. Collision detection now
  uses the same perceptual RGB-distance threshold as the live spectator
  view (`resolveChartColors` in `spectator.js`), and the swapped-in
  fallback is the one farthest from team 1's colour, so the two polylines
  (and the legend dots and timeout markers that share the palette) stay
  visually distinct in both the light and dark schemes.

## [6.2.1] - 2026-07-18

### Added

- **PWA app shortcuts to your overlays.** Long-pressing the installed
  app icon on Android (or opening the jump list on desktop Chrome/Edge)
  now lists the signed-in owner's overlays, each launching straight into
  its control board (`/board?oid=<id>`). The manifest is fetched with
  credentials (`crossorigin="use-credentials"`, via vite-plugin-pwa
  `useCredentials`), so `GET /manifest.webmanifest` personalises the
  `shortcuts` array from the `vsession` cookie — an anonymous request
  gets none, and one account's overlays never surface in another's
  manifest (the response carries `Vary: Cookie` + `Cache-Control:
  private`). The list is capped at the first 10 overlays (ordered by id;
  Android's launcher only surfaces a handful). Shortcuts refresh
  whenever the browser next re-reads the manifest (roughly on relaunch),
  so a just-created overlay can take a launch or two to appear.

### Fixed

- **PWA installed from the main screen now gets the personalised
  manifest.** The service worker precached the static build-time copy of
  `manifest.webmanifest` and answered the bare manifest URL from that
  cache, so installing from the app root (clean URL) froze the anonymous
  manifest — no per-user overlay `shortcuts`, and the `APP_TITLE` rename
  was lost too. Board installs only escaped because their `?oid=` query
  string bypassed the precache's exact-URL match. The manifest is now
  excluded from the service-worker precache so every manifest (re)fetch
  reaches `GET /manifest.webmanifest`, and a main-screen install lists
  the signed-in owner's overlays in the long-press / jump-list shortcuts
  just like a board install. Existing installations pick the fix up on
  their next service-worker update, no reinstall needed.

### Security

- **Bump `click` 8.3.2 → 8.3.3** to clear PYSEC-2026-2132, a known
  vulnerability that `pip-audit --strict` began failing CI on once the
  advisory was published. `click` is a transitive runtime dependency
  (pulled in via `uvicorn`); the patch release is API-compatible.

## [6.2.0] - 2026-07-11

### Added

- **Serve/receive breakdown in the match report.** The Highlights grid
  now shows, per team, points won on own serve vs on receive
  (side-outs), with honest denominators — derived from the audit log's
  per-action serve snapshots, the same walk the live stats endpoint
  already used, so live and printed numbers reconcile. The first
  rally's server is seeded from the operator's pre-match serve
  assignment; rallies whose server is unknown (legacy archives without
  serve data) are excluded rather than guessed, and fully untracked
  matches simply show no card.
- **"Biggest lead" highlight.** The report surfaces the largest score
  gap either team opened (with the set it happened in), using the same
  ≥ 5-point floor as the set-winning comeback card.
- **The report declares the winner.** The hero scoreboard shows a
  localized trophy badge on the winning team's panel, and the
  set-by-set table bolds the set winner's score in each played set.
- **Dark mode for the match report.** The page follows the viewer's
  `prefers-color-scheme` on screen; print always keeps the light,
  paper-oriented palette. Chart line colours are contrast-checked
  server-side against both surfaces (a navy that reads on white would
  vanish on dark), preserving each team's hue where possible.
- **Report timestamps show in the viewer's local time.** Started /
  Ended / Generated render in the reader's timezone and locale, with
  the UTC original in the tooltip; without JavaScript the UTC text
  stands, so printouts follow whoever prints.
- **CSV export of the point log.** A new **Download CSV** button on the
  report (and `GET /match/{id}/report.csv`) exports the point-by-point
  log — timestamps, set, action, team, scouting tags, running score
  and serve holder — for spreadsheet/scouting analysis. Access mirrors
  the report exactly: owner cookie, signed share URL (an existing
  signed report link's parameters open its CSV too), or
  `MATCH_REPORT_PUBLIC`.
- **Match report links unfurl in chat apps.** The report page now
  carries Open Graph / Twitter meta tags (result title, localized
  per-set scores and end date), so shared links preview with the score
  instead of a bare URL.

### Fixed

- **Public match-history page: unnamed teams read "Team 1" again.**
  The placeholder for archives without team names mistakenly borrowed
  the "Match" column-header string, rendering "Match 1" / "Partido 1".
  All six locales now carry a proper "Team" fallback, and a key-parity
  test keeps the page's string tables from drifting.

### Security

- **Locale tags are now escaped and canonicalised before reaching
  server-rendered HTML** (CodeQL `py/reflective-xss`, alert #57). The
  match report interpolated the locale resolved from `?lang=` /
  `Accept-Language` into `<html lang="…">` without escaping. The value
  was already constrained to the six supported tags, so the page was not
  exploitable, but the request-derived string travelled all the way to
  the response. The report now HTML-escapes the tag at the template
  boundary (as the matches-index page already did), and both
  `resolve_locale` and the overlay's `_normalise_locale` return the
  constant out of `SUPPORTED_LOCALES` instead of a substring of the
  request, so no consumer of a resolved locale can ever echo
  attacker-controlled bytes.

## [6.1.2] - 2026-07-11

### Changed

- **Edge-pinned styles (pylons/corners) are now positioned from the anchor
  grid.** The "Vertical position" dropdown in the Overlay section is gone;
  the Position section's anchor grid takes over in a paired mode for these
  styles: clicking a left or right cell selects the whole pair of corners
  for that row (top / middle / bottom), the centre column is disabled —
  the chips are pinned to the side edges, so a centre column placement
  doesn't exist — and there is no "Free" mode. The steppers that have no
  effect on these styles (Height, Width, H/V position) are hidden, leaving
  only the output-wide Scale and Margin knobs. The persisted field is
  still `verticalAnchor`, so saved presets and existing configurations
  keep working. Consistently with the new home, `verticalAnchor` now
  belongs to the **Position** preset category instead of Style, so a
  saved "Position" preset carries the placement of these styles too.
- **Pylons/corners now default to the top corners.** A never-configured
  edge-pinned overlay used to render mid-frame (the layout these styles
  least recommend); it now docks to the top corners. An explicit centre
  pick — including one saved with the old dropdown — still renders
  mid-frame.

## [6.1.1] - 2026-07-10

### Added

- **Owner boards are installable PWAs too.** "Install app" on the plain
  owner board (`/board?oid=<board>`) now installs a launcher that reopens
  that exact board, same as the public `?u=&oid=` bookmark already did.
  When the session cookie is missing, the launcher round-trips through
  the login screen and lands back on the board (the login redirect now
  preserves the page that required it). Operator `?c=` links remain
  uninstallable on purpose — the token is revocable, so the launcher
  would break when it is regenerated.

### Changed

- **The overlay switcher now also appears on a signed-in owner's own
  `?u=&oid=` bookmark.** The board route detects that the public-bookmark
  URL belongs to the signed-in account and upgrades the visit to full
  owner mode (overlay switcher, sign-out), instead of the reduced
  no-login experience. Switching boards from there rewrites the URL to
  the canonical `?oid=` owner link, since the switched-to board may not
  have the public bookmark opted in. Anonymous visitors and other
  accounts keep the bookmark behaviour unchanged.
- **Share links on the Overlays page wrap instead of truncating.** The
  OBS output, shareable control, and public bookmark URLs were shown in
  one-line inputs that cut off after the scheme + host on a portrait
  phone. They now render as read-only blocks that wrap at the URI's own
  separators (`/ ? & =`), so each line follows the link's structure, and
  the text "Copy" button gave way to the compact copy icon the board's
  link rows already use (tap still selects the full value). The
  regenerate control moved out of the URL row onto the "Link to share"
  label line as a small ghost icon — it revokes the link as a whole, so
  it reads as part of the heading and the URL block keeps the full
  width.

## [6.1.0] - 2026-07-09

### Added

- **Switch scoreboards without leaving the board.** In owner mode the
  board's settings top bar now names the overlay being controlled (a
  small "Scoreboard" label over the oid) and doubles as a switcher:
  tapping it lists the account's other overlays and switches the board
  in place — no round-trip through the Overlays management page. The
  session re-initialises on the chosen oid, the WebSocket reconnects,
  and the URL's `?oid=` is updated so a reload stays on the new board.
  Unsaved customization edits still prompt before the switch. Operator
  (`?c=`) and public-bookmark (`?u=`) boards keep the plain title —
  those credentials resolve a single overlay and cannot list others.

### Changed

- **README config-panel screenshot refreshed** to show the new top-bar
  overlay switcher.

## [6.0.1] - 2026-07-09

### Changed

- **The board install icon is sport-agnostic.** The per-board "Add to
  Home Screen" icon was a volleyball, which only read for one of the
  sports the scoreboard supports. It is now a neutral scoreboard — two
  score windows reading `0 : 0` in the app's home/away colours, a sibling
  of the base app icon. Its raster siblings (`icon-board-192x192.png`,
  `icon-board-512x512.png`) are now generated and shipped, so launchers
  that require PNG icons no longer fall back to the SVG.

### Fixed

- **The base app icon's raster files were stale.** `icon-192x192.png`,
  `icon-512x512.png`, and `apple-touch-icon.png` still carried the old
  volleyball artwork even though `icon.svg` had become a scoreboard
  panel — so the installed-app icon (Chrome/Android) and the iOS
  home-screen icon showed a ball that no longer matched the app. All
  three are regenerated from their SVG source via
  `frontend/scripts/regenerate-icons.sh`.

### Dependencies

- **Backend runtime:** `fastapi` `>=0.137.1` → `>=0.139.0`, `sqlalchemy`
  `>=2.0` → `>=2.0.51`, `psycopg[binary]` `>=3.2` → `>=3.3.4`, and
  `python-multipart` `>=0.0.20` → `>=0.0.32`.
- **Backend dev/test:** `pytest` `>=9.1.0` → `>=9.1.1`.
- **Frontend:** `vite` `8.0.16` → `8.1.0`, `@vitejs/plugin-react` `6.0.2`
  → `6.0.3`, and `globals` `17.6.0` → `17.7.0`.
- **CI (GitHub Actions):** `actions/checkout` `6` → `7`,
  `docker/build-push-action` `7.2.0` → `7.3.0`, `docker/login-action`
  `4.2.0` → `4.4.0`, and `docker/metadata-action` `6.1.0` → `6.2.0`.

## [6.0.0] - 2026-07-08

> [!WARNING]
> **Breaking release — no backward compatibility and no in-place upgrade.**
> This version replaces the single-tenant password/token model with
> multi-user accounts backed by a database. The `SCOREBOARD_USERS`,
> `OVERLAY_MANAGER_PASSWORD`, `PREDEFINED_OVERLAYS`, and `APP_TEAMS` /
> `APP_THEMES` / `REMOTE_CONFIG_URL` settings — and the old `?token=` /
> admin-Bearer access paths — are **gone**; the control API and WebSocket now
> require a logged-in session, and the main page is the login page.
>
> There is **no automatic migration** of an existing deployment's on-disk
> data: runtime state is now keyed per user, so pre-existing
> `data/overlay_state_*.json`, `data/audit_*.jsonl`, and the file-based
> `data/matches/` archive are left orphaned (nothing is deleted, nothing is
> carried over). **Upgrade by starting from a fresh `data/` directory**: claim
> the first admin from the startup-log token, then recreate users, overlays,
> teams, and presets — an existing teams/presets catalog can be moved over via
> the admin JSON import. See **Changed** and **Removed** below for the full list.

### Added

- **Hosted team-icon library.** Team logos can now live in the app instead
  of depending on external image URLs (availability, hotlinking, dead
  links). Administrators manage **global icons** shared with everyone;
  each user has a **personal library** (50 icons by default,
  `ICONS_MAX_PER_USER`). Uploads accept PNG/JPEG/WebP/GIF and are
  resized server-side to fit 512×512 (`ICONS_MAX_DIM`) and re-encoded to
  WebP, so storage stays bounded regardless of the input; SVG is not
  supported. Icons have a display name, can be renamed, and deleting one
  clears the icon on every team that used it — the confirmation dialog
  says how many teams that is. The team editors' *Logo* field gains a
  **Library** button to browse global + personal icons (or upload right
  there), and still accepts a pasted URL; large libraries get a name
  search filter and scroll inside the dialog. The teams pages (personal and
  admin) gain an **Import team logos** tool that lists teams whose logo
  is an external URL, downloads the selected ones (SSRF-guarded,
  size-capped, per-URL timeout), stores them as library icons named
  after each team, and repoints the teams at the hosted copies — re-running
  it skips already-hosted teams. Icon files are served from the new
  public `/media` mount with immutable caching; image bytes live in
  `data/media/icons/` (not in the database), so a backup of the `data/`
  directory — which the app already requires for overlay state and match
  data — captures them alongside the default SQLite database. Deployments
  that serve overlays from a separate origin (`OVERLAY_PUBLIC_URL`) must
  route `/media` to the backend on that origin too.

- **Team logos are editable from the board Config panel.** Clicking a team
  card's logo preview opens a small editor dialog with a *Logo URL* field
  and a clear button — previously a logo could only arrive by picking a
  predefined team, so a custom team could never get one and a broken logo
  could not be removed. The rarely-used control stays out of the card
  itself; a small edit badge on the preview marks it as clickable. A
  failed logo shows a broken-image placeholder (with an "image failed to
  load" note in the editor) instead of silently disappearing.

- **"Applies immediately" hints on the instant Config sections.** The
  sections that persist on touch (Buttons, Display, Stats, Recap, General,
  Match rules) now say so, making the split against the staged sections
  (Teams / Overlay / Position / Presets, which wait for **Save**) visible.

- **Position & Size: labeled "Reset to defaults"** (staged through Save
  like any other edit, disabled when already at defaults) plus a
  values-are-percent units hint. The Buttons colour reset gained a visible
  label to match.

- **Catalog import/export: file download and upload.** The admin teams /
  presets JSON panel can now download the export as a `.json` file and
  import from a chosen file, alongside the existing copy-paste textarea.

- **Inline overlay-id validation.** Creating an overlay checks the id
  against the server rule (1–64 chars; letters, digits, `._-`) in the
  form itself instead of round-tripping to an error.

- **Postgres-ready image.** The published image now bundles the psycopg 3
  driver (`psycopg[binary]`), so pointing `DATABASE_URL` at Postgres
  (`postgresql+psycopg://user:pass@host:5432/db`) works with **no rebuild** —
  previously the driver had to be installed by hand. SQLite stays the default;
  this is a small unconditional dependency that keeps the prebuilt image
  Postgres-ready out of the box. `migrations/env.py` also provisions the Alembic
  `alembic_version.version_num` column as `VARCHAR(255)` (vs Alembic's default
  `VARCHAR(32)`) so the project's long, descriptive revision ids never overflow
  on Postgres, which enforces the declared length.

- **README screenshot of the admin global-configuration page.** The
  Administration page (`/admin`) — the self-registration toggle plus user
  management — is now documented with `docs/screenshots/12-admin-page.png`. The
  screenshot pipeline (`scripts/screenshots/capture.mjs`) seeds a small demo
  user roster so the table is representative.

- **Size-independent overlay placement ("anchor zones").** The Config panel's
  Position section gained a 3×3 **anchor grid** (plus a *Free* fallback). Picking
  a zone (e.g. top-right) pins the overlay's matching corner/edge to that screen
  zone — computed against the overlay's *measured* size in the browser, so the
  same zone lands flush for any style regardless of width (the wide beach board
  or the tiny micro capsule alike). This fixes presets that stored fixed
  coordinates pushing wider overlays off-screen. In zone mode the Left-Right /
  Up-Down steppers act as a fine **nudge** (% of canvas) off the anchor;
  *Free* keeps the legacy absolute-coordinate behaviour and is the default, so
  existing overlays and presets render unchanged. The new `Anchor` field is part
  of the `position` preset category, so a single global "top-right" preset now
  works across every overlay style. Edge-pinned styles (pylons, corners) are
  unaffected. The overlay re-anchors on content/size changes via a
  `ResizeObserver`.

- **Public match-history page.** The board's Share menu "match history" link now
  opens a real, server-rendered listing at `/matches/{public_token}` (gated like
  the match report: open when `MATCH_REPORT_PUBLIC`, otherwise the overlay
  owner). It is sortable by **date** or **duration** (ascending/descending) and
  **paginated**, with a link to each match's full report. No login or SPA
  needed — it is the spectator-facing index the previously-broken link aimed at.

- **The account Reports page is now paginated** (20 per page) on top of the
  existing sort and bulk-delete, so a long archive stays manageable.

- **Filter match reports by type** (indoor / beach / table tennis) and by
  **day**, on both the account Reports page and the public match-history page.
  The public page gained a server-rendered month **calendar** that highlights
  the days with matches (mirroring the account calendar) plus the type filter.
  The match's mode is read from the archived state, so it works for any match
  recorded since modes were introduced.

- **Team groups are now the primary unit of team selection.** The control board
  gained a **group picker** above the two team selectors: choose a group and the
  selectors only offer that group's teams (remembered per overlay). The picker
  always offers **"All teams"** (the whole catalog plus your custom teams), the
  shared groups an admin has published, and your own **private groups**. On the
  account **Teams** page you can now create private groups, add catalog *or*
  custom teams to any group, extend a shared admin group with your own teams
  (visible only to you), and rename/delete your private groups. New endpoints
  back it: account `GET/POST /api/v1/my/groups`, `PATCH|DELETE /my/groups/{id}`,
  `POST|DELETE /my/groups/{id}/teams`, and board `GET /board/team-groups`,
  `GET /board/team-groups/{key}/teams`, `PUT /board/selected-group`.
  - **The board team picker now works for operators, not just the owner.** It is
    resolved against the overlay owner's groups via the board credential
    (control-token / public bookmark / owner cookie), fixing the old
    `GET /teams` which only authorised the owner cookie and left operators with
    an empty team list.
  - A new `0007` migration copies each user's previous team list into a private
    **"My teams"** group so nothing is lost (the legacy `user_team_list` table is
    kept as a rollback safety net). New accounts are seeded the same way.
  - Refreshed `docs/screenshots/04-config-panel.png` to show the group picker.

- **Admin team catalog & group manager on its own page.** Global team
  authoring moved off the user's **Teams** page to a dedicated, admin-only
  **Team catalog** page (`/admin/teams`, linked under a new *Admin* nav
  group), so an operator who manages the shared catalog no longer scrolls
  past their personal roster to reach it. It edits the catalog as cards —
  search, multi-select, bulk delete, and edit-on-demand — and adds a
  **group manager** the backend already supported but never exposed in the
  UI: create a group, add/remove catalog teams, publish/unpublish it (only
  published groups appear in users' one-tap "copy a group" shortcut), and
  delete it. Three new admin endpoints back the manager:
  `GET /api/v1/admin/team-groups` (every group, active or not, with its
  members), `DELETE /api/v1/admin/team-groups/{group_id}/members/{team_id}`,
  and `DELETE /api/v1/admin/team-groups/{group_id}`.

- **Delete and sort match reports.** The account **Reports** page now lets
  you delete an archived report — one at a time, or select several (or all)
  and delete them in bulk — with a confirmation step. The table is also
  sortable by **date** or **duration**, ascending or descending. Backed by
  the existing `DELETE /api/v1/matches/{match_id}` endpoint.

- **The reports list shows who played and filters by day.** Each row now reads
  the two teams and the set score (e.g. "Lions **3–1** Bears") with the winner
  highlighted, instead of a bare "Team 1" winner number. A new **Filter by day**
  control opens a self-contained month calendar that dots the days with
  archived matches; picking one narrows the list to that day (with an *All days*
  reset). No date library and no browser-native picker — it looks the same
  everywhere and shows at a glance which days had matches. Team names ride along
  in the `/matches` summary so the list needs no extra per-match fetch.

- **Reports are reachable from the control board's Share dialog.** The signed-in
  owner gets an **All reports** link (deep-linked to this board's overlay); any
  viewer also sees the read-only **Latest match report** / **Match history**
  links when public reports are enabled (`MATCH_REPORT_PUBLIC`). The board no
  longer dead-ends at "open your account screen" to reach a report.

- **Table tennis match mode.** A third mode (alongside indoor and beach)
  with an 11/11-point preset, best-of **1 / 3 / 5 / 7** (the set cap is
  raised from 5 to 7 across the data model and match report). The serve
  rotates automatically — every 2 points, every point once both players
  reach 10 (deuce) — and the first server alternates each game, so the
  operator never tracks it by hand; the serve toggle instead re-bases who
  serves first. A new **serve-change chip** counts down to the next
  handover and flashes when the serve changes. Teams auto-switch ends
  after every game and at the deciding-game midpoint, and each team gets a
  single timeout for the whole match. New state field `serve_switch`
  (`GameStateResponse`); `POST /api/v1/session/rules` accepts
  `mode: "table_tennis"` and `sets_limit` up to 7.

- **Installable per-board PWA from the permanent bookmark link.** Installing
  the app (Chrome / desktop) from a board's permanent bookmark URL
  (`/board?u=<username>&oid=<oid>`) used to launch the **app root** — the
  static manifest `start_url` ignored which board you installed from. The board
  page now points the manifest at a per-board variant
  (`/manifest.webmanifest?u=…&oid=…`) whose `start_url`/`id` open **that** board
  and whose `id` is distinct so Chrome installs it as its own app. The variant
  is only applied for the stable no-login bookmark (not the revocable control
  token, and not owner mode behind a login). iOS is unaffected — Safari's "Add
  to Home Screen" already captures the current URL, query string included.

- **The account pages are now fully localized, and the language setting moved
  to the app.** The account area (dashboard, My overlays, Teams, Presets,
  Reports, Account, Admin, plus the nav, toasts and confirm dialogs) was
  English-only; it is now translated into all six supported languages (English,
  Spanish, Portuguese, Italian, French, German). The `I18nProvider` was lifted
  to wrap the whole app — so the board and the account pages share one language
  preference (`volley_lang`, still resolved from saved choice → browser
  language → English). The language selector **moved out of the board's General
  config panel** into a new **Preferences** section on the **Account** page, so
  it's a single global app setting rather than a per-board control. Login /
  register pages inherit the resolved default (no switcher there yet).

- **Account UX pass: toasts, styled confirms, and consistent layout.** Every
  account-page mutation (create/save/delete overlays, teams, presets, users;
  batch add/remove, copy group, regenerate links) now shows a transient
  **toast** confirming success or surfacing the real error. All destructive
  actions moved off the browser's native `confirm()` onto a styled in-app
  confirmation dialog, including a clear warning that removing an owned
  **custom** team deletes it permanently. Other polish: the desktop sidebar is
  now **sticky** while content scrolls, empty states only appear after data has
  loaded (no flash), catalog membership is matched by id (so a custom team
  can't mask a same-named catalog team), table headers carry `scope="col"`,
  and the account-settings forms share a single width helper.

- **Select all / none on the Teams lists.** Each team table (My teams,
  Catalog) gained a "Select all" control in its action toolbar (visible on
  mobile, where table headers are hidden), with an indeterminate state when a
  subset is selected.

- **Personal team lists: custom teams, seeding, and batch editing.** A new
  account starts with the **full global team catalog** copied into its list
  (one-time, at registration / admin-create). Users can now create their own
  **custom teams** (name, logo, colours) that live only in their list —
  editable and deletable by the owner; removing a custom team deletes it, while
  removing a global team just unlinks it (it stays in the admin catalog). The
  **Teams** page gained multi-select **batch add** (from the catalog) and
  **batch remove**. New endpoints: `GET /api/v1/teams/mine` (list rows with
  ids), `POST /api/v1/teams/mine/custom`, `PATCH /api/v1/teams/mine/custom/{id}`,
  `POST /api/v1/teams/mine/remove` (batch).

- **Shareable operator control links.** Each overlay now carries an unguessable
  *control token* alongside its public OBS token. The owner can copy a
  ready-made link (`/board?c=<token>`) from **My overlays → Edit → Operator
  control link** and hand it to whoever is running the match: opening it grants
  full board control (scores, serve, timeouts, undo, sets, customization, rules)
  **without logging in**. The token resolves to the owning overlay's storage
  key, so it also separates two users who share the same `oid`, and the live
  control WebSocket accepts it too. "Regenerate link" mints a new token and
  revokes any previously-shared link. New endpoint:
  `POST /api/v1/overlays/{oid}/regenerate-control-token`; the control surface
  (`/api/v1/game/*`, `/state`, `/customization`, `/display/*`, `/session/*`,
  `/ws`, …) now authorizes either a `?c=<token>` (or `X-Control-Token` header)
  or the owner's session cookie.

- **Permanent username+oid bookmark control (opt-in).** Each overlay can also
  opt into a stable, no-login control URL based on the owner's username and the
  overlay id (`/board?u=<username>&oid=<oid>`) — a permanent personal bookmark
  that, unlike the control token, never changes when the token is regenerated.
  Because it is **guessable** it is **off by default** and gated behind a
  per-overlay `public_control` flag (toggle + warning under **My overlays →
  Edit → Permanent bookmark link**); disabling it immediately revokes the URL.
  The control surface and `/ws` accept `?u=<username>&oid=<oid>` only for
  opted-in overlays.

- **Multi-user application (backend).** The app now has real user accounts
  with cookie-based sessions, replacing the env-var Bearer auth. Highlights:
  - Registration + login/logout, self-service account management (change
    password, edit profile, delete account), and a forced
    password-change-on-first-login flow.
  - A first administrator is claimed on first start with a one-time token
    printed to the service log (e.g. visible in `docker logs`).
  - Each user manages their own overlays by id; scoreboards are namespaced
    per user (`user_id:oid`), so two users can drive the same `oid`
    independently. OBS output URLs use an unguessable per-overlay
    `public_token` instead of the username/oid.
  - DB-backed teams: a global catalog, admin-curated team **groups** (e.g.
    "Liga Gallega") that users copy into their own list, and admin JSON
    import/export in the `APP_TEAMS` shape.
  - DB-backed presets: global (admin-authored, admin-activated) and
    per-user, with admin `APP_THEMES`-shape import/export.
  - Admin user management: list/create/delete users, reset a password to a
    temporary one (logging the user out everywhere), and toggle public
    registration.
  - DB-backed match reports (replacing the per-match JSON files) surfaced in
    each user's account, scoped to the owner.
  - Per-overlay settings that the old remote-config app carried: a default
    match format (best-of / points) and an optional output URL (for
    overlays.uno cloud / custom outputs), editable from "My overlays".
  - Admin configuration UIs for the global team catalog (logo, colour, text
    colour, groups) and global presets (activate/deactivate), each with
    JSON import/export in the `APP_TEAMS` / `APP_THEMES` shapes.
  - New persistence layer: SQLAlchemy + Alembic, configured via
    `DATABASE_URL` (SQLite by default, PostgreSQL supported and verified). The
    schema is migrated to head automatically on startup.

### Changed

- **Assorted robustness polish.** Remote-config lookups
  (`REMOTE_CONFIG_URL`) now serve the cached values instantly and refresh
  in the background instead of stalling requests for up to five seconds;
  a malformed numeric env var (e.g. `MATCH_GAME_POINTS=abc`) falls back
  to its default with a warning instead of crashing session init; icon
  files are staged in a private temp directory rather than inside the
  public `/media` tree; the unused `overlay_session_meta` table is
  dropped (migration 0003); deleting a user no longer issues redundant
  per-overlay archive deletes; the Reports page disables its delete
  buttons while a delete is in flight; the team logo field shows a hint
  for unusual URLs; and the icon picker, library section, overlays hook,
  and inline team editor clean up their in-flight requests and timers.

- **The match-history listing is paginated.** `GET /api/v1/matches` now
  takes `limit` (default 100, max 500) and `offset` and reports the total
  in `count`, instead of loading and serializing a user's entire archive
  on every call. The account Reports page requests the maximum page
  (500 newest matches) and keeps filtering client-side.

- **Bulk team operations run as single batches.** Adding many teams to a
  user's list or to a group (including the full-catalog seeding at account
  creation) used to issue two to three database queries per team; each
  batch now validates, dedupes, and inserts with a constant number of
  queries, so copying a large catalog is no longer quadratic in practice.
  A batch containing an unknown (or out-of-scope) team id now fails as a
  whole before adding anything, instead of stopping partway through.

- **The OBS overlay WebSocket hub now tolerates wedged clients and caps
  fan-out.** Broadcasts to browser sources apply the same per-socket send
  timeout as the control hub (`WS_BROADCAST_SEND_TIMEOUT_SECONDS`), so one
  stuck OBS source no longer delays score updates to every other client
  of that overlay, and each overlay accepts at most
  `OBS_MAX_CLIENTS_PER_OVERLAY` connections (default 100) — beyond that
  the upgrade is refused with WebSocket close code 1013, keeping a leaked
  public link from exhausting server sockets.

- **Board actions authorize with a single credential lookup.** Every
  scoreboard route used to run the same control-token / bookmark / cookie
  check twice (a route-level gate plus the session resolver). The
  redundant gate is gone, saving a database round-trip on every point,
  set, timeout, and customization call.

- **Database and image work no longer runs on the server's event loop.**
  The teams / overlays / matches / presets / icons endpoints and the
  board-auth dependencies now execute their blocking SQLAlchemy queries in
  the worker threadpool, and icon uploads and the batch logo import do
  their downloads and image re-encoding there too. Before this, a slow
  database (e.g. Postgres over the network) or a single large logo import
  could stall every other request and WebSocket update; now the server
  stays responsive while that work runs.

- **Saving board customization keeps you in the Config panel.** Save no
  longer bounces the operator back to the scoreboard: the panel stays
  open, a transient "Saved" status confirms the write, and leaving stays
  an explicit back action (the unsaved-changes prompt is unchanged).
  Iterating on colors/position no longer means reopening Config each time.

- **The Config panel opens on the Presets section** (its deliberate first
  position in the section list), so the saved-configuration entry point is
  what an operator sees first.

- **Anchor-zone grid sized for fingers.** The 3×3 position-anchor cells
  grew from ~40×22 px to the 44 px minimum touch target used elsewhere,
  and the fractional position steppers move in 0.5 steps instead of 0.1
  (a full range crossing previously took ~1000 taps).

- **Opening public self-registration now asks for confirmation**, and the
  registration toggle confirms both directions with a toast — previously
  the most security-sensitive switch on the admin page flipped silently.

- **The overlay card's pencil is labelled "Edit settings"** instead of
  "Rename" — the overlay id is immutable; the panel edits the description.

- Refreshed `docs/screenshots/04-config-panel.png` for the new team-card
  logo field and default Presets section.

- **Admin page: change a user's role from the UI.** Each user row gained a
  *Make admin / Make user* action (backed by the existing
  `PATCH /api/v1/admin/users/{id}`), so promoting or demoting no longer needs
  a hand-crafted API call. The action honours the existing last-admin guard,
  the role column shows the translated role label, all row/form actions
  disable while one is in flight (no more double-submit duplicates), and
  *Reset password* refreshes the list so the "must change password" pill
  appears immediately. Deleting **your own** account now warns that you will
  be signed out. `docs/screenshots/12-admin-page.png` refreshed.

- **First-run flow no longer advertises self-registration before the first
  admin is claimed.** While the instance has no administrator, the login page
  hides the "No account? Create one" link (keeping only the claim-admin
  banner) and `/register` short-circuits to the claim-admin guidance even
  when the `REGISTRATION_OPEN` seed is true — creating an ordinary account
  before the first admin exists was a first-run trap.

- **Example configs dropped removed/no-op variables.** `docker-compose.yml`
  no longer ships env rows for features removed by the multi-user refactor
  (`UNO_OVERLAY_OID`/`UNO_OVERLAY_OUTPUT`, `APP_CUSTOM_OVERLAY_URL`/
  `APP_CUSTOM_OVERLAY_OUTPUT_URL`, `OVERLAY_SERVER_TOKEN`[`_HASH`/`_DISABLED`],
  `SCOREBOARD_USERS`[`_DISABLED`], `MATCH_REPORT_PUBLIC_DELETE`,
  `METRICS_REQUIRE_ADMIN`, `STRICT_OID_ACCESS`) — some of which implied
  security controls that silently did nothing. Both Traefik compose files
  lose the same dead `OVERLAY_SERVER_TOKEN` / `METRICS_REQUIRE_ADMIN` rows
  and their misleading "gate /metrics" comment. The dead `Conf` knobs
  `SINGLE_OVERLAY_MODE`, `ORDERED_TEAMS` and `MINIMIZE_BACKEND_USAGE`
  (read but never consumed since the refactor) were removed from the code,
  compose, `.env.example` and README. Example `APP_TITLE` defaults now match
  the documented `Volley Scoreboard`, and the Postgres notes no longer tell
  operators to install psycopg by hand (it ships in the image).

- **Every tunable is now documented.** ~20 real env knobs read through
  helper wrappers (`AUTH_RATE_LIMIT_*`, `SECURITY_CSP`/`SECURITY_HSTS_SECONDS`/
  `SECURITY_REFERRER_POLICY`/`SECURITY_PERMISSIONS_POLICY`,
  `AUDIT_LOG_MAX_*`, `WSHUB_*`, `WS_BROADCAST_SEND_TIMEOUT_SECONDS`,
  `WEBHOOK_RETRY_*`, `WEBHOOK_DEAD_LETTER_MAX_RECORDS`, `PRESETS_MAX_*`,
  and the idle game-session `SESSION_TTL_SECONDS` — distinct from the
  login-cookie `SESSION_TTL_HOURS`) were invisible to the env-docs guard
  test and undocumented. They now live in a new **Advanced tuning** section
  of `.env.example` (linked from the README), and
  `tests/test_env_docs.py` also scans the `_env*()` helper wrappers so
  future indirected reads cannot drift undocumented again.

- **Config validation runs for every entry point.** `validate_config()` is
  now called inside `create_app()` (it used to run only from `main.py`, so
  launching the factory directly via `uvicorn app.bootstrap:create_app
  --factory` skipped env sanitisation). Its fallback default for
  `LOGGING_LEVEL` also matches the real `warning` default instead of `info`.

- **Further internal cleanup (review follow-up).** A `useOverlays()` hook now
  backs the account dashboard, the Overlays manager and the board init screen
  (one fetch/cancel/error path instead of four), and the board Share dialog and
  Config "Links" section share a `LinkRow` component plus a `utils/links` module
  (link metadata, `withLang`) instead of duplicated rows and helpers. The team
  serve indicator and the team-list "select all" control became real,
  consistently-labelled controls (accessibility), and the Account page profile
  fields now re-sync when the auth context refreshes.

- **Account match list scales better.** `GET /api/v1/matches` (no `oid`) now
  filters by `user_id` in SQL instead of scanning the whole `match_report`
  table and narrowing in Python. Internal cleanup from the same review pass:
  a shared clipboard helper, a shared `teamScoreSum`, and a shared overlay
  logo-apply helper replace copy-pasted blocks; the board credential is now set
  in a layout effect rather than via a side-effecting `useMemo`.

- **Redesigned the Overlays management page around each overlay's two jobs.**
  Every overlay card is now split into two clearly labelled sections so it is
  obvious what each link/button is for: **"For OBS · video output"** (the
  browser-source URL you paste into OBS once) and **"To control · scoreboard"**
  (open your own board, or copy a no-login link to hand to whoever keeps score).
  The shareable operator control link is now shown inline with a Copy button and
  a small regenerate (↻) action — no longer buried behind a "Share control"
  expander and a separate "Generate" step. The guessable username+id bookmark
  moved into a collapsed **"Advanced"** disclosure so it is never confused with
  the link you share. Cards are now a **collapsible accordion** (collapsed by
  default) so a long list stays scannable — you expand just the one you need;
  the collapsed header identifies it and shows a chip when the public bookmark
  is on, with Rename/Delete as small header icons. The per-overlay
  **"display name" is now a "description"**: the overlay's `oid` is its name
  (primary text) and the optional description is a small subtitle, instead of
  two competing names. The `user_overlays.display_name` column is renamed to
  `description` by migration `0008` (data preserved). Backend: the username in
  the `/board?u=` bookmark URL is now URL-encoded (matching the oid). Screenshot
  refreshed.

- **The account Reports "select all" now scopes to the current page.** The
  table header checkbox selects/clears just the rows on the visible page (adding
  to selections made on other pages), so the operator can pick a page at a time
  instead of only all-or-nothing across the whole filtered set.

- **Setting a password now requires confirming it twice.** Registration, the
  forced/standalone password change, the self-service password change on the
  Account page, and the first-admin claim each gained a "confirm password"
  field; the form refuses to submit until the two entries match — a guard
  against a typo in a field whose characters are hidden.

- **Reimplemented the team configuration panels for phone portrait.** Both the
  user roster (`/teams`) and the new admin catalog now share a card-based
  layout built for one-handed use on a phone: each team is a tap-friendly card
  that reads at a glance and expands its name/logo/colours editor on demand —
  instead of a wide, always-editable table that needed horizontal panning to
  reach the colours and actions — with a sticky bulk-action bar that floats
  within thumb reach only while a selection is active. The user's personal
  roster is now cleanly separated from admin-only catalog and group authoring
  (see *Added*). The per-list name filter, "shown of total" counter, and
  app-native colour picker introduced below are carried over into the cards.
  The account sidebar now groups admin-only links under an **Admin** heading
  (My overlays screenshot refreshed to show it).

- **Reworked the Teams page for large rosters and consistent colour editing.**
  Three improvements aimed at operators juggling dozens of teams:
  - **Live name filter** above the *My teams*, *Catalog*, and admin-catalog
    lists (shown once a list passes ~8 entries), each with a "shown of total"
    counter and a "select all" that now acts on the filtered subset — so finding
    one team out of fifty is a quick type instead of a long scroll.
  - **Catalog teams can be renamed**, not just recoloured/re-iconed: the admin
    catalog rows gained an inline editable name field (the backend already
    accepted it; the UI just never exposed it). Custom teams could already be
    renamed.
  - **Browser-independent colour picker.** The team colour/text inputs now use
    the app's own picker (presets, recent colours, spectrum, hex) — the same one
    as the scoreboard — instead of the inconsistent native `<input type="color">`
    that varied per browser/OS.

- **Rebuilt the "My overlays" screen around the action you take every match.**
  The page was a flat table that gave equal weight to four different
  destinations and labelled the control board with an ambiguous "Open" button,
  while the copy-once browser-source URL dominated each row. Each overlay is now
  a **card** led by a single prominent **Open scoreboard** button (opens the
  control board in a new tab); the browser-source URL (consumable by any
  streaming program, not just OBS) is demoted to a labelled, copy-once detail
  with a hint; and the operator/bookmark sharing
  links plus rename now live behind tidy **Share control** / **Rename**
  expanders. Reworked the layout to cards also fixes the cramped four-button
  row on phones. Regenerated `docs/screenshots/05-manage-page.png`.

- **New PWA icons — distinct base-app vs. board icon.** The base app
  (`frontend/public/icon.svg`) is now a **scoreboard** mark (two coral / blue
  score windows with a colon divider), and **boards** get their own
  `icon-board.svg`: a flat **volleyball** whose seams are a three-fold "beach
  ball" swirl rather than the previous basketball-style cross. The per-board
  manifest (`/manifest.webmanifest?u=&oid=`) serves the board icon, so an
  installed board looks different from the installed base app (one shared icon
  across all boards). Both SVGs are drawn maskable-safe (key art centred in the
  inner 80%) and act as their own maskable source. Because this environment has
  no SVG→PNG rasteriser, the raster siblings (the PNGs Chrome/iOS use for the
  installed launcher) are regenerated separately via
  `frontend/scripts/regenerate-icons.sh` (needs librsvg / Inkscape /
  ImageMagick); until that runs Chrome falls back to the SVG (a missing PNG is
  skipped) and the base PNGs keep the previous artwork. iOS uses the base
  apple-touch icon for boards too (manifest-based differentiation is
  Chrome/Android/desktop).

- **Overlay output is no longer described as "OBS"-specific.** OBS is one of
  several consumers of an overlay's output URL (vMix, a plain browser, etc.),
  so the OBS-only wording was misleading. The "OBS output URL" column is now
  **"Output URL"**, the links dialog's "OBS overlay" entry is now **"Overlay"**,
  and the setup hint points to "your streaming software (OBS, vMix, …)" rather
  than OBS alone — across all six languages. The corresponding API field
  descriptions (`output_url`, `public_token`) and the register-overlay endpoint
  summary were generalized too, and the OpenAPI snapshot / TS types regenerated.

- **Mobile account navigation redesigned.** On phones the account/management
  navigation (Dashboard, My overlays, Teams, Presets, Reports, Account, Admin)
  was a single horizontally-scrolling row, so links past the viewport edge —
  including Account, Admin, and Sign out — were hidden behind a non-obvious
  swipe. It is now a sticky top bar with a hamburger button that opens an
  off-canvas drawer listing every destination, the signed-in user, and Sign
  out. The drawer closes on navigation, on backdrop tap, and on Escape, and
  locks background scroll while open. The desktop sidebar layout is unchanged.

- **Create-overlay form alignment.** The "My overlays" create form mixed
  fields with and without helper text in a `flex-end` row, so the inputs no
  longer lined up and the helper text widened columns and forced ragged
  wrapping. It now uses a top-aligned responsive grid: inputs line up on one
  row on desktop and stack cleanly to full width on phones, with the submit
  button aligned to the input row.

- **Copyable temporary passwords.** When an admin creates a user or resets a
  password, the temporary password is now shown in a selectable, monospace
  field with a one-tap **Copy** button (shared `CopyField` component) instead
  of as plain inline text that had to be copied character by character.

- **Account-page UI consistency.** Introduced a shared `EmptyState` component
  and reusable CSS classes (tiles, section dividers, colour swatches) so the
  "nothing here yet" placeholders, dashboard tiles, and admin section dividers
  render identically across the account pages instead of via per-page inline
  styles. The **Reports** page now shows a clear call-to-action linking to
  "My overlays" when you have no scoreboards yet, instead of an empty
  scoreboard dropdown.

- **No backward compatibility.** `SCOREBOARD_USERS`, `OVERLAY_MANAGER_PASSWORD`-
  gated scoreboard access, the `PREDEFINED_OVERLAYS` catalog, and the
  `APP_TEAMS` / `APP_THEMES` / `REMOTE_CONFIG_URL` configuration sources for
  teams/presets are superseded by the database. The control API and control
  WebSocket now require a logged-in session; the main page is the login page.

- **No in-place data migration — start clean.** This release is a clean break;
  there is **no automatic migration** of an existing single-tenant deployment's
  on-disk data. Runtime data is now keyed per user (`"<user_id>:<oid>"`) instead
  of by the bare overlay id, so pre-existing `data/overlay_state_*.json`,
  `data/audit_*.jsonl`, and the old file-based `data/matches/` archive are **not**
  read by the new app and stay orphaned on disk (nothing is deleted, but nothing
  is carried over either). Upgrade by starting from a fresh `data/` dir: claim
  the first admin from the startup-log token, then recreate users, overlays,
  teams and presets. Migrate an existing **teams/presets catalog** via the admin
  JSON import (`POST /api/v1/admin/{teams,presets}/import`).

### Removed

- **Per-overlay default match rules (format / points / last-set points).** These
  duplicated what the live control board already configures via its
  customization panel (`POST /session/rules`), so they were redundant. Removed
  the **Format / Points / Last-set** controls from the "My overlays" create and
  edit forms (and the Format column), the `points` / `points_last_set` / `sets`
  columns on `user_overlays` (migration `0006`), those fields from the overlay
  API (`CreateOverlayRequest` / `UpdateOverlayRequest` / `OverlayOut`), and the
  override that applied them at `/session/init`. A fresh board session now
  starts from the env defaults (`MATCH_SETS`, `MATCH_GAME_POINTS`,
  `MATCH_GAME_POINTS_LAST_SET`) and the operator sets the format on the board,
  where it already persists in the session.

- **overlays.uno cloud and external overlay-server support — in-process only.**
  The project now serves **every** overlay with its built-in, in-process engine
  (`LocalOverlayBackend`). Removed: the `UnoOverlayBackend` (overlays.uno cloud
  REST API), the `CustomOverlayBackend` + `app/ws_client.py` (external overlay
  server over WebSocket/HTTP), the 22-char UNO OID format, and the per-overlay
  **custom output URL** (the overlay `output_url` / `custom_output_url` field,
  the "Output URL (cloud, optional)" form field, and `output_url` on
  `POST /api/v1/session/init`). Each overlay's OBS output URL is now always the
  app's own `/overlay/<public_token>` link.
  - **Removed env vars:** `UNO_OVERLAY_ID`, `UNO_OVERLAY_OID`,
    `UNO_OVERLAY_OUTPUT`, `APP_CUSTOM_OVERLAY_URL`,
    `APP_CUSTOM_OVERLAY_OUTPUT_URL`, and the now-unused `WS_RECONNECT_*` /
    `WS_HEARTBEAT_INTERVAL_SECONDS` / `WS_ZOMBIE_DEADLINE_SECONDS` tunables.
  - **Removed docs:** `CUSTOM_OVERLAY.md` and `CUSTOM_OVERLAY_API.yaml` (the
    external-server contract). The control board's overlay preview always uses
    the in-process render path (no overlays.uno iframe branch).
  - **DB:** `user_overlays.output_url` column dropped (migration `0005`).

- **Overlay-server peer endpoints and `OVERLAY_SERVER_TOKEN` removed.** With no
  external overlay server, the Bearer-gated peer endpoints (`POST /api/state/{id}`,
  `/create|delete/overlay/{id}`, `/api/raw_config/{id}`, `/api/config/{id}`,
  `POST /api/theme/{id}/{name}`) and the `OVERLAY_SERVER_TOKEN` machine credential
  (incl. `_HASH` / `_DISABLED`) are gone — `app/overlay/auth.py` and
  `app/security_bootstrap.ensure_overlay_server_token` were deleted. The public
  `GET /api/themes` and the OBS capability routes (`/overlay`, `/follow`, `/ws`)
  remain. `security_bootstrap` now only mints `SESSION_SECRET`.
  - **`/metrics` is now always unauthenticated** (it only ever exposed
    aggregates); the `METRICS_REQUIRE_ADMIN` toggle is removed.

- **`OVERLAY_MANAGER_PASSWORD` and the legacy `/manage` admin.** The single
  shared admin password and everything it gated are gone, replaced by the
  in-app `admin` role (cookie + role gated) and the SPA `/admin` page:
  - Removed the `/manage` console, the custom-overlays admin API, and the
    `/api/v1/admin/status` / `/api/v1/admin/login` endpoints.
  - Removed `GET /list/overlay` (it defeated the capability-URL design).
  - Match-report print access (`/match/{id}/report`) is now gated by the
    report **owner's** session cookie, an owner-minted signed share URL
    (`POST /api/v1/matches/{id}/sign-url`), or `MATCH_REPORT_PUBLIC=true` —
    the old `?token=`/admin-Bearer paths are gone. The signed-URL HMAC key
    moved from `OVERLAY_MANAGER_PASSWORD` to `SESSION_SECRET`.
  - Report deletion is now owner-only via `DELETE /api/v1/matches/{id}`; the
    `MATCH_REPORT_PUBLIC_DELETE` flag is removed.
  - `METRICS_REQUIRE_ADMIN` now gates `GET /metrics` behind the
    machine-to-machine `OVERLAY_SERVER_TOKEN` (Prometheus scrapers can't carry
    a cookie) instead of the admin password.
  - Webhook dead-letter replay moved to the cookie-admin
    `POST /api/v1/admin/webhooks/replay`.
  - Dropped the now-unused `OVERLAY_MANAGER_PASSWORD(+_HASH)`,
    `MATCH_REPORT_PUBLIC_DELETE`, `PREDEFINED_OVERLAYS`, and
    `HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED` entries from `.env.example` /
    `docker-compose.yml`.

### Fixed

- **The batch logo-import dialog no longer wipes its results right after
  a successful import.** Finishing an import refreshes the teams list,
  which re-rendered the dialog and reset it back to the checklist (with
  everything re-checked, inviting a duplicate run) before the per-team
  outcome could be read. The outcome list now stays visible until the
  dialog is closed.

- **A transient network error no longer logs you out of the UI.** The
  auth-context refresh treated any fetch failure as "not signed in" and
  redirected to the login page even when the session cookie was still
  valid. An established session is now kept through network blips; only
  the initial load falls back to the logged-out state (with registration
  shown as closed, matching the backend default).

- **Icon uploads reject over-budget images before decoding, and failed
  saves no longer leave orphaned files.** The pixel budget
  (`ICONS_MAX_PIXELS`) is now checked from the image header before any
  pixel data is decoded — previously an image between 1× and 2× the
  budget slipped past Pillow's bomb guard and was fully materialized in
  memory. And when the database write for an upload or batch-imported
  icon fails after the WebP file was written, the file is now removed
  instead of accumulating invisibly under `/media/icons`.

- **Database timestamps are timezone-aware on SQLite.** Timestamp columns
  now normalize to UTC-aware datetimes in both directions (SQLite returns
  naive values for `timezone=True` columns), removing the per-call-site
  `tzinfo` patching in the session resolver and the latent
  `TypeError: can't compare offset-naive and offset-aware datetimes`
  waiting for the next code that compares a model timestamp against
  `datetime.now(UTC)`. No schema migration is needed.

- **Concurrent duplicate submissions no longer surface as server errors.**
  Registering a username, creating an overlay, or saving a preset that a
  simultaneous request just created used to slip past the duplicate
  pre-check and crash with an unhandled database constraint violation
  (HTTP 500). These paths now translate the constraint violation into the
  same "already exists" error a normal duplicate gets (400/409). The
  first-admin claim is also serialized, so two simultaneous claims with
  the valid bootstrap token create exactly one administrator — the loser
  receives the regular 410.

- **The auth pages are translated.** Sign-in, registration, the forced
  password change and the claim-first-admin page now follow the detected
  UI language (all six languages) instead of always rendering in English —
  previously a non-English browser hit an English-only wall at the front
  door before ever reaching the translated app. The language is
  auto-detected from the browser (or the saved preference); the auth pages
  intentionally have no language picker.

- **Invalid match-rules points are called out inline.** Entering 0, a
  negative number, or clearing the points fields previously did nothing
  silently (the value just reverted on the next refresh); an inline
  message now explains the constraint.

- **Catalog JSON imports surface the server's error detail** instead of a
  generic "Import failed.", and a *Replace existing* import now requires a
  danger-confirm before wiping the catalog; import/export buttons disable
  while a request is in flight.

- **Config-panel accessibility.** Every colour swatch announces its field
  (and team) instead of nine identical "Pick color" buttons; range sliders
  are label-associated; the icon-only chrome buttons (back, fullscreen,
  theme, logout) and team-card icon buttons gained aria-labels; the
  save-error banner can be dismissed and shows the clean API error message.

- **Account settings feedback.** Profile/password/delete buttons disable
  while submitting (no more accidental double submissions), success is a
  single toast instead of a duplicate banner+toast, and profile errors
  render as errors rather than in the info banner.

- **A revoked control link now explains itself instead of dumping the
  operator on the owner-only connect screen.** Opening a `/board?c=…` link
  whose token was regenerated (or a disabled `?u=` public bookmark) used to
  fall back to the OID-entry InitScreen, whose overlay picker calls the
  cookie-gated `/api/v1/overlays` route and just 401s for a no-login
  operator. Capability-mode failures now render a dedicated panel ("This
  control link is no longer valid… ask the scoreboard owner for a new
  link"), and board error surfaces show the API's human-facing `detail`
  instead of the raw `API POST /session/init failed (403): {json}` string.

- **The board's show/hide-controls handle had untranslated tooltips and
  screen-reader labels** — it referenced i18n keys (`ctrl.hideControls` /
  `ctrl.showControls`) that existed in no language, so assistive tech
  announced the literal key string. The keys now exist in all six languages;
  `config.openManage` was also added to the four languages that were missing
  it. A new Vitest guard (`i18n-keys.test.ts`) enforces key parity across
  languages and that every static `t('…')` key used in the source resolves,
  so this class of leak cannot recur.

- **Sign-in failures are no longer all reported as "Invalid username or
  password."** A deactivated account (403), a rate-limit lockout (429) and a
  server/network outage each show their real cause now; only a 401 keeps the
  invalid-credentials message.

- **The account dashboard no longer shows the "create your first
  scoreboard" call-to-action when the overlay list simply failed to load** —
  a transient API error now renders an error banner instead of a false empty
  state. The admin global-presets section likewise surfaces a load failure
  as a toast instead of silently rendering empty.

- **A mid-session admin password reset now routes the affected user to the
  change-password page.** Any API call answering `409 password_change_required`
  flips the auth context (mirroring the existing 401 handling), so the user
  lands on `/change-password` instead of a stuck page with a raw error.
  Registration and claim-admin forms also gained the `autocomplete`
  attributes password managers need to capture new credentials.

- **Match-report charts stay readable for light team colours.** The per-set
  score charts picked the team's polyline colour with a bare luminance cap that
  waved through light-but-not-white brand colours (e.g. a light grey), which
  then sat at ~1.3:1 against the report's grey `#fafafa` surface — the points
  evolution was effectively invisible. The picker now measures a real WCAG
  contrast ratio against the surface and, when a brand colour falls below the
  3:1 floor, uses the team's text colour or **darkens the brand colour while
  keeping its hue** so a pale-green team stays green and a white/grey team
  becomes a visible neutral. Strong brand colours are unchanged. (Report
  screenshot refreshed.)

- **Reports list now shows the real winner / team names.** The account Reports
  page (and the public match-history list) showed the literal "Team 1" / "Team 2"
  placeholder for matches whose team names were stored under a non-canonical
  customization key (e.g. seeded from a preset or predefined team), even though
  the match report itself rendered the correct names. The list summary now
  resolves names through the same multi-key fallback the printed report uses
  (`Team N Name` → legacy `Team N Text Name` → `team_N_name` → `nameN`), so the
  list and the report always agree. This is a read-time fix — existing archived
  matches display correctly too, with no data migration.

- **Branch code-review correctness pass.** A batch of bug fixes surfaced by the
  multi-user branch review:
  - **Table-tennis timeout cap** now returns a failed `ActionResponse` (with a
    message) instead of a silent success when the one-per-match cap is hit.
  - **Rules change now persists the served side.** Switching rules recomputes
    the table-tennis server; it is now saved (not just WS-broadcast), so the OBS
    overlay reflects it immediately rather than only after the next point.
  - **Deleting a user evicts runtime state.** The admin delete now revokes the
    user's sessions and removes their overlays' in-process session/state/archives
    instead of leaving them until the hourly reaper.
  - **Overlay first-touch race.** `create_overlay` holds the store's lock across
    the existence check and the write, so two concurrent first-touches can't both
    write default state.
  - **Remote-config cache** is now refetched under a lock (no duplicate fetches /
    transient empty-cache races), and **migrations** enable the SQLite foreign-key
    PRAGMA like the app engine does.
  - **Serve-switch pill** no longer flashes "serve changes now" at 0-0 in the
    degenerate `points_limit=1` case.
  - **Position inputs** no longer persist `null` when a field is cleared (NaN is
    ignored), and switching the anchor back to **Free** restores the absolute
    coordinate defaults instead of leaving a 0/0 nudge that jumps the overlay to
    centre.
  - **Control board reconnect/links.** The board WebSocket now treats 4xxx close
    codes (revoked token, bad request) as terminal instead of reconnect-looping,
    resets its backoff per overlay, and the share dialog drops its cached links
    when the overlay changes (no stale URLs). The overlay rename panel guards
    against double-submit, and the Overlays/Reports pages no longer show the
    "nothing here" empty state on top of a load error.

- **The Reports page filter row lines up.** The match-type dropdown carried a
  stacked label that made it taller than the day-filter button and the count
  beside it, so the row looked ragged on a phone. The type filter is now a
  compact inline control aligned with the rest of the row.

- **The match-mode selector fits one row in phone portrait.** The
  indoor / beach / table-tennis toggle used a two-column grid, so the third
  mode dropped onto its own half-width second row. It is now a single row of
  three equal buttons, with a slightly smaller label so even the longest names
  ("Table tennis" / "Tenis de mesa" / "Tennis de table") stay on one line.

- **The Share menu's "match history" link no longer dead-ends on the account
  dashboard.** It pointed at a `/matches/index.html` listing page that was
  removed in the multi-user refactor, so it fell through to the SPA and landed
  on the dashboard. It now opens the new public match-history page (see Added).

- **The control HUD now expands the moment a match finishes.** If the bar had
  auto-hidden during the final rally, the operator no longer has to un-hide it
  to reach Reset or the **Match report** button — it reveals itself and stays
  pinned while the finished match is on screen.

- **Disabled team logos no longer leak into the set-score columns or the
  points-history strip.** They now follow the same "show logos" toggle as the
  score buttons, instead of being read straight from the customization.

- **Disabled team logos no longer show in the portrait score column.** The
  portrait per-team history column read the logo straight from the
  customization, so it stayed visible next to the score buttons even with the
  "show logos" toggle off; it now follows the same toggle as every other
  scoreboard surface.

- **Set-point / match-point markers point to the correct side after a court
  switch.** The triangle now tracks each team's *physical* side, so when the
  teams swap ends the arrow flips with them instead of pointing at the wrong
  half of the court.

- **Mobile usability pass on the account pages.** Several fixes after reviewing
  every account screen at phone width:
  - The off-canvas menu now opens from a hamburger in the **top-left** (next to
    where the drawer slides in), matching the usual convention — it used to sit
    top-right while the drawer came from the left.
  - **Data tables now label their stacked cells on mobile.** With the header row
    hidden, a value like "yes" or "admin" was meaningless; the Admin **Users**
    list, **Presets**, and **Reports** tables now show the column name above
    each value (Role / Active / Scope / Covers / Winner / Duration …).
  - Admins get an **Admin** tile on the dashboard, for parity with the other
    sections (it was only in the nav).
  - The Teams catalog shows a correct "The catalog is empty." message when there
    are no catalog teams (instead of "already in your list"), and section
    headings got a little more breathing room.

- **Teams lists no longer strand the checkbox on its own line on phones.** The
  mobile "stack each table cell onto its own line" rule turned every team into a
  tall card with the select checkbox floating alone above the team name. The
  selectable Teams lists (My teams / Catalog) now use a compact single-line row
  on mobile — checkbox + crest + name inline, with the Edit action at the end.

- **Account pages now scroll.** The fullscreen control board's global
  `overflow: hidden` (and `user-select: none`) leaked onto every account page,
  so a list taller than the viewport (e.g. a long Teams list) couldn't be
  scrolled and text couldn't be selected. The account shell is now its own
  scroll container with text selection restored.

### Security

- **The icon batch-import download pins the connection to the validated
  IP (DNS-rebinding fix).** `fetch_guarded` used to resolve a
  user-supplied logo URL to check it against the private-address
  blocklist and then let the HTTP client resolve the name again for the
  actual request — a host with a short-TTL record could answer the check
  with a public IP and the fetch with `169.254.169.254` or `127.0.0.1`.
  Hostname targets are now resolved once, every address validated, and
  the request sent to that exact IP with the original hostname preserved
  in the `Host` header and in TLS SNI/certificate verification. Every
  redirect hop is re-planned the same way, and a name that fails to
  resolve is refused instead of passed through. Deployments behind an
  egress proxy keep working: when a proxy applies to the URL, the
  original hostname is sent to the proxy (which does its own resolving)
  after the same validation.

- **Request bodies are capped at the ASGI layer.** The icon-upload size
  check keyed off the `Content-Length` header, which a chunked-transfer
  request simply omits — and the framework spooled the whole body to disk
  before any handler check ran. A new middleware fast-fails oversized
  declared lengths and stops reading once `REQUEST_MAX_BODY_BYTES`
  (default: icon upload cap + framing, ≥ 8 MiB) is crossed, answering 413.
  Per-route checks remain as the earlier, friendlier guard.

- **Public registration now auto-closes once the first admin is claimed.**
  Previously a fresh install accepted anonymous sign-ups at `/register`
  indefinitely until an admin explicitly turned them off. Now, when
  `REGISTRATION_OPEN` is not configured, registration stays open only
  during the bootstrap window and is closed automatically the moment the
  first administrator account is created (the admin can reopen it from
  the Users page at any time). Setting `REGISTRATION_OPEN=true`/`false`
  pins the behaviour explicitly and is never overridden; an empty value
  (docker-compose's passthrough for "unset") counts as unset. The
  default docker-compose seed changed from `true` to unset accordingly.

- **Branch code-review hardening pass.** Fixed a cluster of authorization /
  hardening gaps found reviewing the multi-user branch:
  - **Webhook SSRF via redirect.** Outbound webhook POSTs now use
    `allow_redirects=False`, so a public target can no longer 30x-redirect the
    client to a private/loopback/cloud-metadata address past the host guard.
  - **Admin group routes could reach a user's private group.** The admin
    `/admin/team-groups/*` delete / set-active / add-member / remove-member
    paths now resolve groups through a shared-only helper (`owner_user_id IS
    NULL`), so an admin can no longer mutate or delete a user's *private* group
    by id (read paths were already scoped; this closes the write-path gap).
  - **Audit endpoint leaked the internal storage key.** `GET /api/v1/audit`
    now returns the human-facing `oid`, not the `"<user_id>:<oid>"` skey, so a
    shared control-link operator can't read the owner's internal user id.
  - **Last-admin self-delete lockout.** `DELETE /api/v1/auth/me` now refuses
    when the caller is the only active administrator (mirroring the admin
    delete/demote/deactivate guards), so an instance can't be locked out of
    administration.
  - **Login timing.** The account-not-found path now verifies against a
    structurally-real dummy scrypt record (full-cost derive) instead of a
    1-byte stub, keeping login timing uniform.

- **Patched three transitive dev-dependency advisories (build-time only).**
  Bumped `js-yaml` to ≥ 4.2.0 — via an npm `override`, since
  `@redocly/openapi-core` pinned the vulnerable 4.1.1 — and `@babel/core` to
  7.29.7, and let `npm audit fix` patch `brace-expansion`. This clears a
  quadratic-complexity YAML DoS, an arbitrary-file-read via `sourceMappingURL`,
  and a `max`-bypass DoS. None of these ship to users (they are eslint /
  openapi-typescript / vite-plugin-pwa build dependencies); `npm audit` now
  reports 0 vulnerabilities.
