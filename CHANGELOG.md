# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**This file covers the current major (7.x) and the unreleased work in
progress.** Older releases are in
[`docs/CHANGELOG-archive.md`](docs/CHANGELOG-archive.md); the release
workflow moves a superseded major there automatically. Every change is
written into `## [Unreleased]` below; nothing is ever appended to the
archive by hand.

## [Unreleased]

### Security

- **The published image now applies Debian security updates at build time.**
  The runtime stage inherited whatever OS packages `python:3.14-slim`
  happened to ship, so a Debian fix published between base-image rebuilds
  stayed unapplied — most recently the `util-linux` cluster
  (CVE-2026-53613, CVE-2026-53614, CVE-2026-53615, fixed in
  `2.41.5-0+deb13u1`), which turned the Trivy gate red on every pull
  request. An `apt-get upgrade` in the runtime stage takes those fixes
  instead of suppressing the finding, matching how the image already drops
  `pip`/`setuptools` rather than allow-listing their advisories.

### Dependencies

- **Backend runtime:** `uvicorn[standard]` `>=0.52.1` → `>=0.52.3`,
  `sentry-sdk[fastapi]` `>=2.66.1` → `>=2.68.0`, `sqlalchemy` `>=2.0.51`
  → `>=2.0.52` and `python-dotenv` `1.2.2` → `1.2.3`. Dependabot only
  moves the declared ranges, so `requirements.lock` was recompiled in the
  same change to keep the lock-satisfies-`requirements.txt` gate green;
  it moves exactly those four pins (`uvicorn` resolves to `0.52.4`) with
  no transitive churn.
  [#502](https://github.com/JacoboSanchez/volley-overlay-control/pull/502),
  [#503](https://github.com/JacoboSanchez/volley-overlay-control/pull/503),
  [#504](https://github.com/JacoboSanchez/volley-overlay-control/pull/504),
  [#505](https://github.com/JacoboSanchez/volley-overlay-control/pull/505)
- **Frontend (dev-only):** `@vitejs/plugin-react` `6.0.4` → `6.0.5`
  (restores a linear react-compiler preset filter after the 6.0.3
  regression), `rollup-plugin-visualizer` `7.0.1` → `7.1.1` (drops the
  deprecated `source-map` `0.8.0-beta.0` in favour of `0.8.0`) and
  `@testing-library/user-event` `14.6.3` → `14.6.4` (keyboard event
  `repeat` property fix).
  [#506](https://github.com/JacoboSanchez/volley-overlay-control/pull/506),
  [#507](https://github.com/JacoboSanchez/volley-overlay-control/pull/507),
  [#508](https://github.com/JacoboSanchez/volley-overlay-control/pull/508)

## [7.1.1] - 2026-08-16

### Changed

- **The Config panel opens on Teams, and Presets moved below Position &
  Size.** The section list now reads Teams → Overlay Style → Position & Size
  → Presets → …, so the fields an operator touches before every match come
  first and the saved-configuration entry point sits with the appearance
  settings it restores. Teams is also the section the panel opens on, in both
  the landscape sidebar and the portrait accordion; the preset list is now
  fetched only once that section is opened. The config-panel README
  screenshot was regenerated for the new section order.

## [7.1.0] - 2026-08-15

### Added

- **Revision-safe multi-operator control and privacy-preserving presence.**
  Every control-state response and WebSocket broadcast now carries a persisted
  monotonic revision. Bundled-client mutations conditionally send their last
  rendered revision; stale writes return `409 state_revision_conflict` and the
  UI reloads authoritative state instead of silently overwriting another
  operator. Browser tabs use ephemeral ids for an aggregate connected-
  controller indicator and optional audit attribution. A tab duplicated from
  a live one claims a fresh id instead of inheriting its opener's, so two
  real controllers are never counted (or attributed) as one. Presence and
  audit metadata never disclose the overlay owner's account identity, while
  clients that omit the new headers remain backward compatible. Background
  writes — the overlay locale sync that follows the operator's UI language — go
  through the same serialized mutation queue as scoring actions, so they can
  no longer send a stale revision alongside a point and lose one of the two
  to a conflict. The match-rule controls (mode, limits, auto side switch) and
  the config panel's Save use that queue too, and a change rejected by a
  conflict now says so instead of silently snapping back.
- **A usability, functionality and performance roadmap** now records the
  post-7.0 delivery order, user outcomes and measurable completion criteria in
  `docs/USABILITY_FUNCTIONALITY_PERFORMANCE_ROADMAP.md`.
- **Owner-scoped match calendar and bulk-delete APIs.**
  `GET /api/v1/matches/days` returns lightweight local calendar-day keys, and
  `POST /api/v1/matches/bulk-delete` removes up to 100 selected reports in one
  transaction without allowing ids from another account to cross the owner
  boundary. Selections survive paging, so the reports page splits a larger
  selection into requests the endpoint accepts, and refreshes the calendar
  after a deletion empties a day. Switching overlay, filter, sort or page
  while a list request is still open no longer lets the older response
  repopulate the table, and the shared history page treats an impossible
  date (`?day=2026-02-30`) as no filter instead of failing the request.

### Changed

- **Browser preferences and the recent overlay are isolated by account.**
  Language, board workflow settings, recent colours and the last owner OID now
  use the authenticated user id as their local-storage namespace. Existing
  unscoped values migrate once to the first account that reads them; later
  accounts start independently. Control links and public bookmarks use a
  separate guest namespace and no storage key contains their credential.
- **Overlay background work now uses one bounded, process-wide executor.**
  Creating or evicting a game session no longer creates or shuts down a
  private five-thread pool. Tasks remain FIFO within each per-user overlay
  key, different overlays can progress concurrently, and the bounded queue
  applies backpressure instead of retaining unlimited pending payloads.
  Unlabelled Prometheus metrics expose queue depth plus wait and run latency;
  worker and queue limits are operator-configurable. Scoring, display and
  customization endpoints run their work on a worker thread, so a saturated
  pool applies backpressure to that request alone instead of stalling every
  other request and live overlay update in the process. The WebSocket
  registry is lock-guarded for those cross-thread reads: a tab connecting
  while a mutation builds its response can no longer fail the request that
  was already applied.
- **Match-history browsing now stays bounded as archives grow.** The React
  reports page sends its mode/day/sort/page filters to SQL instead of fetching
  at most 500 matches and filtering them in memory. Summary queries omit the
  potentially large `audit_log` JSON column, sort ties deterministically, and
  the server-rendered history page uses the same filtered page queries. The
  post-restart latest-report lookup is now a one-row scalar query.

### Removed

- **Python 3.11 support. The minimum supported interpreter is now 3.14.**
  `requires-python` moves to `>=3.14`, ruff targets `py314`, and mypy
  type-checks against 3.14. CI drops the second interpreter with it: the
  backend job is no longer a matrix (a single 3.14 job replaces the
  `py3.11` / `py3.14` pair, so its coverage artifact is plain
  `coverage-xml`), and the frontend and security-scanner jobs — plus the
  release workflow, previously on 3.12 — now set up 3.14 as well.
  The Docker image already builds on `python:3.14-slim`, so container
  operators are unaffected; anyone running from source on 3.11
  must upgrade their interpreter before taking this release. With the
  floor raised, forward references that only existed to satisfy pre-3.14
  annotation evaluation are plain annotations again (PEP 649 defers them),
  and `SECURITY.md`'s out-of-scope note now names the base images the
  Dockerfile actually builds on.

## [7.0.0] - 2026-08-09

### Security

- **Request correlation and observability surfaces are now bounded and
  operator-controlled.** Client-provided `X-Request-ID` values are accepted
  only from a safe 64-character alphabet before being echoed or logged;
  malformed values are replaced. The request middleware now participates in
  W3C `traceparent`/`tracestate`, emits trace IDs in text and JSON logs, and
  propagates context through webhook and guarded outbound HTTP calls.
  `/metrics` remains open by default for compatibility, but can require a
  constant-time-compared `METRICS_TOKEN` bearer credential or be hidden with
  `METRICS_ENABLED=false`. Match-report HMACs now use a separately persisted
  `MATCH_REPORT_SIGNING_SECRET`; an upgraded installation seeds it from the
  current cookie key once so existing links survive, while later
  `SESSION_SECRET` rotation no longer affects report links.
  Fixes [#447](https://github.com/JacoboSanchez/volley-overlay-control/issues/447).

- **The remote-config fetch is now SSRF-guarded and never follows
  redirects.** `REMOTE_CONFIG_URL` was the only outbound `requests` call in
  the codebase with neither a `net_guard` check nor `allow_redirects=False`,
  even though whatever answers gets to set most of the app's configuration:
  the match-report signing key, `METRICS_TOKEN`, the `MATCH_REPORT_PUBLIC`
  gate, the webhook destination match state is POSTed to, and the
  `OVERLAY_PUBLIC_URL` origin that widens the CSP `frame-src`. It now runs the same
  `is_target_safe` check webhook delivery uses: a config host resolving to a
  private / loopback / link-local address is refused before the request
  fires, and a `30x` is reported rather than followed to whatever the
  redirect names. Deployments whose config source *is* internal (a Compose
  sidecar, an intranet file server) opt back in with the new
  `REMOTE_CONFIG_ALLOW_PRIVATE_IPS=true`; a refused fetch logs an error and
  falls back to the local environment. Part of [#441](https://github.com/JacoboSanchez/volley-overlay-control/issues/441).

- **The default Content Security Policy no longer permits string
  evaluation or arbitrary HTTPS iframes.** `script-src` drops the unused
  `'unsafe-eval'`; `frame-src` now allows only `'self'` and, for split-host
  deployments, the exact HTTP(S) origin configured by
  `OVERLAY_PUBLIC_URL`, using browser-compatible UTS #46 normalization
  for internationalized hostnames and WHATWG parsing for legacy IPv4 forms.
  The broad `img-src https:` source remains intentional because operators can
  configure external team-logo URLs.
  Fixes [#431](https://github.com/JacoboSanchez/volley-overlay-control/issues/431).

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

- **Cleared two of the three open Dependabot advisories on the frontend
  dev toolchain (build-time only).** `js-yaml` moves to 4.3.0 — the npm
  `override` floor was still `^4.2.0`, which pinned the tree to the last
  release affected by [GHSA-52cp-r559-cp3m](https://github.com/advisories/GHSA-52cp-r559-cp3m)
  (quadratic CPU on YAML merge-key chains). That also clears the
  `@redocly/openapi-core` alert, which was flagged only for depending on
  it. `brace-expansion` moves 5.0.6 → 5.0.9 in the modern `minimatch@10`
  chain, patching [GHSA-mh99-v99m-4gvg](https://github.com/advisories/GHSA-mh99-v99m-4gvg)
  (unbounded expansion → OOM) and
  [GHSA-3jxr-9vmj-r5cp](https://github.com/advisories/GHSA-3jxr-9vmj-r5cp).
  `npm audit` goes from 3 high to 1 high; nothing here ships to users.

  The remaining `brace-expansion` alert has **no upstream fix available**
  and is deliberately left alone rather than papered over. It is patched
  only in 5.0.8+, which changed its CommonJS export from the bare
  function to `{ expand, … }`. `minimatch` 3.x and 5.x do
  `const expand = require('brace-expansion')` and call it directly, so
  forcing 5.x on them throws `expand is not a function` and breaks
  `eslint` outright — and `eslint-plugin-react` (7.37.5) and
  `eslint-plugin-jsx-a11y` (6.10.2) are both already at their latest
  release and still depend on `minimatch@^3.1.2`. The 1.x/2.x/3.x/4.x
  maintenance backports do not clear the advisory either. Pinning those
  chains to their newest in-line release buys nothing and makes `npm
  audit` report 15 findings instead of 1, so the override is scoped to
  `minimatch@10` where 5.x actually loads. The exposure is a DoS on
  attacker-supplied glob patterns; these run at lint/build time over
  patterns from this repo's own config, and none of it reaches runtime.

### Added

- **The “My overlays” page now supports account-persisted favorites and
  fast filtering for long lists.** Favorite overlays sort first on every
  device, can be isolated with a one-click filter, and lists of six or more
  overlays gain name/id search with an explicit result count and empty state.

- **A property test for the live audit protocol, replacing five one-off
  regression tests with one invariant.** Review of the audit push protocol
  found five defects in the seam between the `GET /audit` read, the
  `audit_append` / `audit_invalidate` frames and the per-OID log lock —
  including one introduced while fixing another of the same shape. Both
  halves of that seam are now driven by randomised, seeded interleavings of
  log mutations (append, undo, rapid-pair tombstone/restore, clear, delete,
  rotation), transport faults (dropped, duplicated, reordered frames,
  disconnect/reconnect), transient read failures and board switches, and
  checked against one property: a client that believes it is current shows
  exactly what the log holds at the version it holds, and never shows a row
  the board never logged. `tests/test_audit_convergence_property.py` drives
  the real `action_log` — lock, tombstone filter, record cache and real
  rotation included — against a port of the client reducer, and
  `frontend/src/test/useAuditFeed.property.test.tsx` drives the real
  `useAuditFeed` hook against a model of the log; only the wire between them
  is faked. Each of the five reviewed defects is pinned as an injectable
  regression seed with a test asserting the property fails under it, so the
  next defect of that shape is caught by the property rather than by
  remembering to write its one-off test.
  Fixes [#488](https://github.com/JacoboSanchez/volley-overlay-control/issues/488).

- **Backfilled tests for the three highest-risk untested surfaces.**
  `frontend/src/test/useDoubleTap.test.tsx` covers the press-gesture state
  machine behind every score, timeout and set button — single tap, double
  tap, long press and their documented priority, the touch/mouse and
  keyboard-repeat guards, the cancel paths, the browser defaults the hook
  suppresses, and timer cleanup on unmount.
  `frontend/src/test/useScoreActions.test.tsx` covers the scoring handlers
  and the point-type-picker gate, including the referential stability that
  keeps a WebSocket state push from re-rendering the board's action context.
  `tests/test_match_report_access.py` covers the authorization gate on
  `/match/{id}/report` directly: public mode, signed capability URLs, the
  owner cookie, and every path that denies access.
  Fixes [#442](https://github.com/JacoboSanchez/volley-overlay-control/issues/442).

- **Opt-in privacy-scrubbed Sentry reporting and live operational gauges.**
  Setting `SENTRY_DSN` enables FastAPI error reporting and optional
  transaction sampling without sending request bodies, cookies, query strings,
  or capability-bearing URL paths. Errors and sampled transactions — including
  their spans, breadcrumbs, and transaction names — go through the same
  scrubber. `voc_rate_limit_blocked_buckets{surface}`
  reports buckets blocked right now, and the existing dead-letter gauge is
  refreshed from persistent storage at scrape time so restart does not reset
  the observed queue depth.

- **The backend typing gate now rejects every unannotated function.**
  All remaining application signatures are typed, including the
  `GameSession`/`Backend` game-service path and ASGI middleware boundaries;
  mypy now enables `disallow_untyped_defs` and disables implicit optionals,
  with Ruff `RUF013` enforcing the same optional-parameter syntax.
  Fixes [#443](https://github.com/JacoboSanchez/volley-overlay-control/issues/443).

- **The JavaScript and CSS that render the on-air overlays now pass the same
  automated quality gates as the React SPA.** ESLint checks every first-party
  script in `overlay_static/js/` with browser globals plus blocking
  `no-undef`/`no-unused-vars`; Prettier covers those scripts and all 35 overlay
  stylesheets; and Stylelint checks the CSS for invalid, duplicated, or
  deprecated declarations. Vendored `gsap.min.js` remains explicitly
  excluded. CI and pre-commit both enforce the expanded scope, with regression
  tests guarding the paths and commands. The first pass removed two dead
  JavaScript helpers and fixed duplicated selectors, viewport fallbacks, and
  deprecated wrapping declarations without changing overlay behavior.
  Fixes [#435](https://github.com/JacoboSanchez/volley-overlay-control/issues/435).

- **`limit` / `offset` paging on every account list endpoint**, closing
  the last unbounded reads
  ([#433](https://github.com/JacoboSanchez/volley-overlay-control/issues/433)).
  `GET /teams/catalog`, `/my/groups`, `/overlays`, `/icons`,
  `/customization/presets`, `/admin/team-groups`, `/admin/presets` and
  `/admin/users` all take the two parameters and push them into SQL. **Response bodies are unchanged** — a bare JSON array
  is still a bare JSON array; the full in-scope total travels in a new
  `X-Total-Count` header (exposed through CORS), so a client can tell a
  complete page from a truncated one without every existing consumer
  learning a new envelope. A caller that sends nothing gets
  `LIST_DEFAULT_LIMIT` rows — set well above any realistic catalog, so
  existing clients see no change — and no caller can ask for more than
  `LIST_MAX_LIMIT`. Both defaults live in `.env.example`.
  `GET /icons` pages the *global* library only — `mine` is already capped
  by `ICONS_MAX_PER_USER`. `GET /teams/catalog` gained a `scope` parameter:
  `global` (the default, the admin catalog) or `all` (every global team plus
  the caller's own customs), which gives the "All teams" roster embedded in
  `GET /my/groups` a pageable home of its own. The two export endpoints
  (`/admin/teams/export`, `/admin/presets/export`) deliberately do **not**
  page: they are backup surfaces where a silently truncated page would
  mean silently losing data on the next import.

  The bundled SPA walks every page. Its overlays, team catalog, groups,
  icon library and preset screens all render the complete listing, so the
  client follows `X-Total-Count` until it has everything rather than
  showing a silently truncated first page. A response without the header
  (an older server) is treated as a single complete page.

  Every paged `ORDER BY` ends in a unique key. `teams.name`, `icons.name`
  and `presets.name` carry no uniqueness constraint, so ordering by name
  alone would let the database return tied rows in a different order per
  query — and a client walking pages would then see some rows twice and
  miss others.

- **A background sweeper for expired login sessions.** `auth_sessions`
  rows were only ever deleted when their own token was presented again, so
  a user who logged in and then cleared their cookies left a row behind
  permanently (`SESSION_TTL_HOURS` defaults to 14 days). A periodic purge
  now runs alongside the existing in-memory session cleanup, on its own
  `AUTH_SESSION_SWEEP_INTERVAL_SECONDS` interval (6 h; `0` disables it for
  operators running an external janitor).

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

### Changed

- **Common overlay actions are now available directly from every collapsed
  card.** Operators can control the scoreboard or inspect its visual output in
  one click; creation, share/OBS links, naming, and destructive actions use a
  clearer progressive hierarchy with larger touch targets. Newly-created
  overlays are briefly highlighted, and the mobile layout keeps multiple
  boards within the first viewport. The account-page screenshots were
  regenerated to match the new interface.

- **The config panel's structure now matches its concerns.** The 675-line
  `ConfigPanel.tsx` mixed six of them: the form model, four independent
  remote lookups, history/back interception, save orchestration, the section
  registry and two full alternate layouts. It is now a ~250-line composition
  over `useConfigModel`, `useConfigOptions`, `useUnsavedChangesGuard`, a
  single `CONFIG_SECTIONS` registry (replacing four parallel structures a new
  section had to be added to in lockstep) and per-surface components for the
  top bar, bottom bar, section nav and section body. The dead `actions` prop
  is gone, and the five `setSetting as XSectionProps['setSetting']` casts —
  type holes with the same effect as `as any`, invisible to
  `no-explicit-any` — are replaced by the shared `SetSetting` type.
  Refs [#438](https://github.com/JacoboSanchez/volley-overlay-control/issues/438).

- **The SPA's API client is split by domain.** `api/client.ts` was a single
  909-line module with 139 exports that every consumer imported wholesale,
  so the login page reached the entire admin surface through the same module
  object. It is now `api/http.ts` (the transport: `fetch`, `ApiError`, the
  paginated-listing walk, the board credential mode) plus one module per
  route family — `board`, `auth`, `admin`, `teams`, `icons`, `presets`,
  `overlays`, `reports`, `app`. Every consumer imports only the domain it
  uses; the request behaviour is unchanged.
  Refs [#438](https://github.com/JacoboSanchez/volley-overlay-control/issues/438).

- **Shared hooks replace the SPA's copy-pasted list and action
  scaffolding.** `useAsyncAction` gains an `onError` option and is joined by
  `useAsyncRunner` (one pending flag and one error slot for a screen's whole
  set of actions) and `useToastAction`, replacing roughly fifty hand-rolled
  `useState(false)` busy flags and twenty-five repetitions of the same
  ApiError-detail ternary. `useTeamSelection` — hardcoded to numeric team ids,
  which is why the reports page grew its own near-identical copy — is now the
  generic `useSelection<K>`, shared by the reports, teams and admin-teams
  screens. No behaviour change.
  Refs [#438](https://github.com/JacoboSanchez/volley-overlay-control/issues/438).

- **The unsaved-changes prompt uses the app's own dialog.** Leaving the
  config panel with unsaved edits raised a browser `window.confirm` —
  unstyled, untranslated and ignoring the `ConfirmProvider` already mounted
  around the board. It now uses the same styled, translated confirmation as
  the reports and admin pages, on the back button, a swipe-back gesture, the
  dashboard link and an overlay switch alike.
  Refs [#438](https://github.com/JacoboSanchez/volley-overlay-control/issues/438).

- **The control SPA now loads account pages on demand instead of all at
  once.** `AppRouter` statically imported all thirteen pages, so anyone
  sitting on the login screen downloaded the admin, teams, reports,
  overlays and presets pages — and their transitive dependencies (icon
  library and picker, match calendar, JSON import/export, the colour
  picker) — before the login form could render. The eight signed-in
  account pages are now lazily loaded behind a Suspense boundary in
  `AccountLayout`, and the build splits React/Router and `react-colorful`
  into their own vendor chunks. The router chunk drops from 128 kB to
  16.8 kB; the unauthenticated front door and the board stay eager, since
  they are the first paint. No behaviour or layout change.
  Refs [#446](https://github.com/JacoboSanchez/volley-overlay-control/issues/446).

- **The control SPA no longer polls the audit log.** The momentum strip and
  the history drawer each re-fetched `GET /api/v1/audit` after every
  confirmed point — roughly 150–200 extra round trips over a five-set match,
  each racing the request that caused it. The backend now streams audit
  rows over the control WebSocket (`audit_append` / `audit_invalidate`, see
  [FRONTEND_DEVELOPMENT.md](FRONTEND_DEVELOPMENT.md)), and the board reads
  the log twice per board — once on mount and once when the socket opens,
  which closes the gap where an action by another client lands before the
  handshake — then follows it live. `GET /api/v1/audit` gains a `version`
  field and remains authoritative; it now answers **503** when the log
  cannot be read, rather than an empty page whose version would tell a
  following client it was up to date. A dropped message costs one extra
  fetch, never a wrong history. Verified end to end: scoring issues no
  audit request at all.
  Refs [#446](https://github.com/JacoboSanchez/volley-overlay-control/issues/446).

- **Material Icons is subsetted to the icons the app actually draws.** The
  SPA loaded the full ~2,200-glyph font — 125 kB of WOFF2 on first paint —
  to render 74 icons. It now ships a 5 kB subset built from the canonical
  list in `frontend/src/icons.ts` by
  `scripts/icons/build_font_subset.py`. A test fails the build if an icon is
  used without being listed, so a missing glyph surfaces in CI rather than
  as a blank box on an operator's screen. `material-icons` moves to
  devDependencies, leaving four runtime dependencies.
  Refs [#446](https://github.com/JacoboSanchez/volley-overlay-control/issues/446).

- **The HUD show/hide-controls handle is a real button.** It was a `div`
  with `role="button"`, `tabIndex` and a hand-written Enter/Space key
  handler — the last such element in the source tree. It now uses a native
  `<button>`, which brings correct keyboard and disabled semantics from the
  platform, and gains the `aria-expanded` state it never exposed. Appearance
  is unchanged.
  Refs [#446](https://github.com/JacoboSanchez/volley-overlay-control/issues/446).

- **Frontend type checking is stricter.** `tsconfig` adds
  `exactOptionalPropertyTypes`, `verbatimModuleSyntax` and
  `noFallthroughCasesInSwitch`, and ESLint now enforces the matching
  `consistent-type-imports` rule. This is a contributor-facing change with
  no runtime effect: the resulting fixes were type annotations and import
  statements only. `useGameState` also narrows the overlay id once rather
  than asserting it non-null at fourteen call sites, so an action fired
  without a board reports a failure instead of requesting a `null` one.
  Refs [#446](https://github.com/JacoboSanchez/volley-overlay-control/issues/446).

- **A slow remote config can no longer stall a request.** The background
  revalidation held `EnvVarsManager._lock` across its HTTP round-trip, so
  once a fetch outlived the 10s cache TTL any reader — the per-response CSP
  header lookup, the metrics token, the report gate — blocked on the socket
  inside an async handler. The fetch now runs outside the lock, which is
  taken only to swap the finished payload in, so stale-while-revalidate
  delivers what its name promises.
  [#441](https://github.com/JacoboSanchez/volley-overlay-control/issues/441).

- **Six more settings now honour `REMOTE_CONFIG_URL`.** The auth rate
  limiter (`AUTH_RATE_LIMIT_MAX_FAILURES`, `_WINDOW_SECONDS`,
  `_BLOCK_SECONDS`), the security-header knobs (`SECURITY_CSP`,
  `SECURITY_HSTS_SECONDS`), the Sentry settings, `OVERLAY_LOCALE` and
  `DEFAULT_TEAM_LOGO` read through `EnvVarsManager` instead of
  `os.environ`, so a remote config can set them rather than being silently
  ignored. That retires three more private parsers — including a fourth
  `_env_int` clone in the rate-limiter. The readers that stay on
  `os.environ` are the ones needed *before* the fetch can happen
  (`DATABASE_URL`, the cookie `SESSION_SECRET`, `ADMIN_BOOTSTRAP_TOKEN`,
  `TRUSTED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `LOG_REDACT`); a new
  `tests/test_env_read_path.py` keeps that list exhaustive instead of
  aspirational. One behaviour change: a rate-limit knob set to `0` or a
  negative number now falls back to its documented default with a warning
  rather than being silently clamped to `1`.
  [#441](https://github.com/JacoboSanchez/volley-overlay-control/issues/441).

- **Environment configuration has one read path again, and it validates
  where the value is read.** Three mutually inconsistent mechanisms had
  grown up around 54 variables: `EnvVarsManager` (the only one honouring
  `REMOTE_CONFIG_URL`), module-level `_env_int`/`_env_float` helpers in
  `app/constants.py` reading `os.environ` directly at import time, and a
  third integer parser in `app/conf.py` — with `app/config_validator.py`
  as a fourth layer that clamped values by **mutating `os.environ`** at
  startup. Everything now goes through `EnvVarsManager`, which gained typed
  accessors — `get_int_env`, `get_float_env` (with inclusive `minimum` /
  `maximum` and an `exclusive_minimum` for timeouts) and `get_enum_env`
  alongside the existing `get_bool_env`. A malformed or out-of-range value
  degrades to the caller's default with one warning naming the variable and
  the constraint it broke, instead of being clamped in a startup pass that
  the actual reader could not see. `app/constants.py` still resolves its
  tunables once at import — several are baked into FastAPI route signatures
  — but it now reads them through the same path, so remote-config
  deployments configure them like anything else. [#441](https://github.com/JacoboSanchez/volley-overlay-control/issues/441).

### Fixed

- **The config panel no longer fails its option lookups silently.** The team
  groups, output links, overlay styles and per-style capabilities were each
  fetched with a bare `.catch(console.warn)`, so a failure left the operator
  looking at an empty dropdown with no explanation and no way to try again —
  while the save path beside it had a proper error banner. A failed lookup now
  raises a retryable banner, and one dead lookup no longer blanks the other
  three.
  Refs [#438](https://github.com/JacoboSanchez/volley-overlay-control/issues/438).

- **The config panel's section list is now announced correctly.** Accordion
  headers carried no `aria-expanded`/`aria-controls` and sidebar entries no
  `aria-current`, so a screen reader could not tell which section was open —
  unlike the team rows, overlay switcher, preset picker and match calendar,
  which all do this already.
  Refs [#438](https://github.com/JacoboSanchez/volley-overlay-control/issues/438).

- **A failed customization refresh no longer passes silently.** After a save
  from the config panel, the SPA re-reads customization from the server; that
  read discarded every error into an empty `catch`, so a network failure left
  the panel showing values the server had never confirmed with nothing on
  screen to say so. The failure now raises an error toast, and the last
  known-good customization is kept rather than cleared. The background
  overlay-locale sync uses the same call and stays quiet, as before.
  Refs [#446](https://github.com/JacoboSanchez/volley-overlay-control/issues/446).

- **Group listings no longer issue a query per group.** Every board load
  ran `GET /board/team-groups`, which spent `1 + 3N` queries — and
  materialised every `Team` row of every group — purely to compute a
  `count`. It now answers from two aggregate queries and reads no team
  rows at all. `GET /my/groups` similarly cost four queries per group, one
  of them a duplicate (`group_effective_teams` and `user_group_team_ids`
  each re-ran the same per-user membership lookup); it now costs a fixed
  two, and `/admin/team-groups` fetches its members in one batched query
  instead of one per group. Part of
  [#433](https://github.com/JacoboSanchez/volley-overlay-control/issues/433).

- **Indexes on the columns every listing filters and orders by**
  (migration `0005_perf_indexes`, which skips any index already present so a
  large PostgreSQL deployment can create them with `CREATE INDEX
  CONCURRENTLY` beforehand — see README, *Upgrading a large PostgreSQL
  deployment*): `teams.is_global`, `teams.name`,
  `team_groups.is_active`, `icons.is_global`, `presets.scope`,
  `presets.is_active`, and `auth_sessions.expires_at` — the last of which
  is what keeps the new session sweeper from being a full-table scan. The
  migration test now compares model indexes against the migrated schema in
  the same way it already compared columns, so an `index=True` added
  without a migration fails CI instead of only ever existing on a freshly
  `create_all`-ed test database.

- **`DELETE /matches/{id}` and `POST /matches/{id}/sign-url` no longer
  load the whole match snapshot to check ownership.** Both read
  `final_state`, `customization` and the entire `audit_log` JSON column
  solely to compare one integer, and neither uses the payload afterwards.
  They now select just the owning `user_id`.

- Stale credential-transport and reconnect documentation no longer describes
  the control WebSocket as cookie-only or claims capability signatures and
  tokens never travel in URLs. It now follows the implemented cookie,
  `?c=`, and `?u=&oid=` modes and the client's backoff behaviour.

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

- **Match-rule validation no longer silently skips remote-config
  deployments.** `validate_config()` clamped `MATCH_GAME_POINTS`,
  `MATCH_GAME_POINTS_LAST_SET` and `MATCH_SETS` in `os.environ` at startup,
  but `Conf` reads them through `EnvVarsManager`, which prefers the remote
  config cache over `os.environ` — so a remote `MATCH_GAME_POINTS=-5`
  reached the match rules unvalidated and produced a set that could never
  be won. The bound now travels with the read (`minimum=1`), so it applies
  to every source. `APP_PORT` is likewise validated (1–65535) where it is
  read, so a typo can no longer yield an overlay output URL of
  `http://localhost:notaport`, and `WEBHOOKS_TIMEOUT_S` — previously read
  with no validation at all, and missing from its own module's env-var
  docstring — must now be greater than zero. Fixes [#441](https://github.com/JacoboSanchez/volley-overlay-control/issues/441).

- **Docker Compose no longer drops unlisted application settings from
  `.env`.** Both the host-port and Traefik deployment files now pass the full
  optional `.env` through to the container, including security headers, auth
  rate limits, request caps, icon limits, webhook retries, WebSocket limits,
  and future settings. This optional-file support requires Docker Compose
  2.24.0 or newer. Environment documentation guards now also catch stale
  example entries and indirect `_env_*` readers. Fixes
  [#445](https://github.com/JacoboSanchez/volley-overlay-control/issues/445).

### Deprecated

- **The legacy `C-id[/style]` OID prefix is now dated for removal in
  `7.0.0`.** Nothing has produced it since the multi-user refactor — the UI,
  the docs and overlay CRUD all use the bare id — but five files still carry
  the shim so an OBS source or bookmark saved before that refactor keeps
  resolving. It stays accepted (and stripped) until 7.0.0; `_LEGACY_PREFIX`
  in `app/overlay_backends/utils.py` lists every call site to drop then.

### Removed

- **`app/config_validator.py`, `REST_USER_AGENT`, and the unreachable
  championship-layout branch.** The startup validator is gone with the
  read-time validation that replaces it (above), and with it the
  hand-maintained duplicate of `logging_config`'s default level. `Backend`
  kept a configured `requests.Session` (`REST_USER_AGENT`, a retrying
  HTTP adapter) and a `process_response` helper from the era when it
  called a cloud overlay service; it has made no outbound HTTP request
  since that backend was removed, so all three are deleted along with the
  env var, its `.env.example` entry and its Compose pass-through.
  `Conf.id` was a hardcoded legacy UUID whose only reader compared it
  against `State.CHAMPIONSHIP_LAYOUT_ID` — a different hardcoded UUID, so
  the `Sets Display` branch it guarded could never execute; both constants
  and the branch are gone. Part of [#441](https://github.com/JacoboSanchez/volley-overlay-control/issues/441).

- **The legacy flat team roster and its routes.** Groups replaced the flat
  per-user list as the unit of team selection, but the old model, service
  helpers and seven endpoints stayed behind it: `GET /api/v1/teams`,
  `GET|POST /teams/mine`, `POST /teams/mine/remove`, `GET /team-groups` and
  `POST /team-groups/{id}/copy-to-mine` are gone, along with the
  `user_team_list` table (dropped by migration `0004`). Nothing is lost with
  it — a team's own `owner_user_id` already determined what the virtual "All"
  group showed, so the table only ever mirrored a fact the schema could
  answer without it, and the SPA had already moved to `/my/groups*`. Two
  `teams_service` readers left without a caller (`list_active_groups`,
  `list_user_custom_teams`) went with them.

  **Migration `0004` carries the roster forward before dropping it.** A roster
  row for a *global* team is the only record that a user ever picked it, so
  those memberships are copied into that user's private **"My teams"** group
  (created if they have none) rather than discarded — which is the copy the
  code comments have attributed to a "0007 migration" that the migration
  squash lost. Custom teams need no copy; `teams.owner_user_id` already
  implies them. If your users added global teams through the old
  `POST /teams/mine` and never put them in a group, those teams now appear in
  their "My teams" group. Downgrading past `0004` reconstructs the table from
  those same two sources, so a rollback serves a populated `GET /teams`
  instead of an empty one.

  **One behaviour change:** `DELETE /api/v1/teams/mine/{team_id}` now deletes
  a custom team the caller owns and returns `404` for anything else. It
  previously also unlinked a *global* team from the caller's roster; with no
  roster, a global team is dropped from a single group via
  `DELETE /my/groups/{group_id}/teams/{team_id}` instead. The SPA only ever
  called it for custom teams.

- **Four dead modules and a compatibility shim** (~700 LOC total):
  `app/overlay/models.py` (Pydantic models with no reference anywhere),
  `app/api/presets_store.py` (the pre-DB on-disk preset store — `slugify`
  moved to `app/presets_service.py`, the rest deleted), `app/app_storage.py`
  (NiceGUI-era in-memory UI state, kept alive only by a `@patch` target),
  and `app/api/oid_validation.py` (a re-export of `app/id_validation.py`
  whose three in-tree callers now import from the canonical module).
  The unreferenced `PRESETS_MAX_RECORDS` env var goes with the preset store.
  Closes [#434](https://github.com/JacoboSanchez/volley-overlay-control/issues/434).

### Documentation

- **The two ways to control a board without logging in are finally
  documented.** An overlay's `control_token` (the shareable
  `/board?c=<token>` operator link) and the `public_control` flag (the
  stable `?u=<username>&oid=<oid>` bookmark) both grant *full board
  control with no login*, and neither appeared anywhere in the
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
  gated `/matches/{public_token}` history listing). A document calling itself the
  per-route auth inventory while omitting 43% of the API is worse than
  none: a reader takes absence for "not an access path".

  The legend also gained a `G` class for routes that use hand-written,
  multi-mode access checks rather than a uniform route dependency — the two
  match-report routes and the
  `/matches/{public_token}` history listing, which were
  listed as `—` ("always public") under a section that closes by calling
  everything in it intentionally public, while `check_read_access` in fact
  returns `401` to an anonymous caller. Marking a protected route public in
  the document whose job is being unambiguous about access is the worst
  single error this file can contain. The history listing carried a second
  trap: a `{public_token}` in the path does not make the token the
  credential — there it only selects the overlay, and access still needs
  the owner's cookie or `MATCH_REPORT_PUBLIC`. Every remaining `—` row was
  audited against its handler.

  The guard now compares **`(method, path)` pairs across the whole schema**,
  in both directions. Path-only comparison had let rows advertise methods
  that 405 — `GET /api/v1/admin/teams` among seven such claims, all from
  over-compressed rows that listed two methods against two paths where each
  method belonged to only one. Schema-exempt WebSockets, hidden routes, and
  static mounts are also checked as exact operations, and mount coverage is
  exercised in both backend-only and built-frontend layouts.

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

- **The largest backend coordinators are now split by responsibility.**
  `GameService` remains the stable route-facing facade while state
  presentation, scoring/lifecycle actions, display toggles, and customization
  live in focused services; overlay payload assembly and style discovery no
  longer live in `Backend` or `OverlayStateStore`; PWA/static/system-route
  policy no longer lives in the app factory; and the flat `match_report_*`
  cluster is now an `app.match_report` package with separate color, chart,
  and card renderers plus focused access, signing, export, stats, and template
  modules.
  Route request/response models also moved into the central API schema module,
  while team-group presentation and overlay-link policy moved into focused
  services.
  Compatibility facades preserve existing imports and runtime behavior.
  Fixes [#439](https://github.com/JacoboSanchez/volley-overlay-control/issues/439).

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

### Dependencies

- **Backend runtime:** `sentry-sdk[fastapi]` `>=2.66.0` → `>=2.66.1`
  (upstream fix for exceptions raised inside `traces_sampler` and other
  callbacks) and `uvicorn[standard]` `>=0.52.0` → `>=0.52.1`. Only the
  `uvicorn` floor moved a pin in `requirements.lock` (`0.52.0` →
  `0.52.1`); the lock already resolved `sentry-sdk` to `2.66.1`.
  [#483](https://github.com/JacoboSanchez/volley-overlay-control/pull/483),
  [#484](https://github.com/JacoboSanchez/volley-overlay-control/pull/484)
- **Frontend:** `vite` `8.1.0` → `8.2.0` (patch-level bug fixes, then the
  8.2 minor; pulls `rolldown` `1.1.3` → `1.2.3` and `lightningcss`
  `1.32.0` → `1.33.0`).
  [#469](https://github.com/JacoboSanchez/volley-overlay-control/pull/469),
  [#486](https://github.com/JacoboSanchez/volley-overlay-control/pull/486)
- **Frontend types:** `@types/react` `19.2.17` → `19.2.18` and
  `@types/react-dom` `19.2.3` → `19.2.4`.
  [#485](https://github.com/JacoboSanchez/volley-overlay-control/pull/485)
- **Frontend (transitive, dev-only):** `brace-expansion` `1.1.14` →
  `1.1.18` and `2.0.3`/`2.1.0` → `2.1.4`.
  [#481](https://github.com/JacoboSanchez/volley-overlay-control/pull/481)
- **CI (GitHub Actions):** `docker/login-action` `4.4.0` → `4.6.0`
  (still pinned by commit SHA).
  [#464](https://github.com/JacoboSanchez/volley-overlay-control/pull/464)
