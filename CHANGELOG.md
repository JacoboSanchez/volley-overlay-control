# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once a first tagged release ships.

## [Unreleased]

### Added

- React control UI: when the overlay preview is hidden, the centre
  column now renders a "points history strip" in the slot the
  preview would have occupied — a two-row table (one row per team)
  with the team's coloured logo marker on the left and a
  chronological sequence of action chips to the right. Each
  audit-log event becomes a chip on its team's row only, so the
  column visually maps to the moment the action happened. Lets
  operators read momentum and recent corrections at a glance
  without the bandwidth / visual cost of the live preview iframe.

  Chip vocabulary:
  * ``+1`` / ``−1`` for an ``add_point`` forward / undo entry.
  * Star icon when a team's ``sets`` count advances by 1
    without ending the match. Detected via the post-state diff
    in the audit response, so it covers both the explicit
    ``add_set`` action and — far more common — the set-winning
    ``add_point`` (which the backend logs as ``add_point``
    only, with the new ``sets`` count carried in the result
    block). Struck-star variant when the operator undoes the
    set-winning point: detected via a React state diff
    (``team_X.sets`` drops between refetches), since the
    audit log alone can't reconstruct the popped forward.
  * Trophy icon when the same sets diff also flips
    ``match_finished`` to ``true``. Struck-trophy variant when
    ``match_finished`` flips back to ``false`` (operator undoes
    the match-winning point).
  * Clock icon for ``add_timeout``; struck-clock for any undo
    of a timeout — same rule as ``point_undo`` so the strip is
    visually consistent across action types. When the undo is
    non-adjacent (some action happened in between), the
    classifier additionally synthesizes the missing forward
    chip from the post-state timeout diff (the forward record
    was physically removed by ``pop_last_forward`` so we never
    see it directly) and places it before the first in-between
    record that observed the bumped count, recovering the
    timeline the operator saw before clicking undo.
  * Pencil icon plus the absolute new score (e.g. ``15``,
    ``0``) for a ``set_score`` manual correction. No-op
    corrections (typed value matches the current value) are
    suppressed via a per-(set, team) running cache.

  Chips render at ``opacity: 0.7`` so they recede behind the
  score buttons and alert pills they sit next to instead of
  competing with them.

  Implementation:
  * New ``frontend/src/hooks/useRecentEvents.ts`` (replaces the
    earlier ``useRecentPoints``) fetches ``GET /api/v1/audit``
    only while the preview is hidden, and refetches when the
    match scoring key (sum of all set scores + sets won +
    timeouts per team) changes — so unrelated state pushes
    (visibility toggles, simple-mode changes) don't trigger
    redundant network calls, but a timeout immediately surfaces
    its clock chip rather than waiting for the next scoring
    event. Audit fetch limit derives from the requested window
    (``Math.max(40, max * 3)``). Failed fetches clear the strip
    rather than leave stale chips.
  * ``frontend/src/components/PointsHistoryStrip.tsx`` renders
    two rows × N cells with inline-SVG icons for clock,
    clock-undo, trophy and pencil. Hairline divider between
    the team marker and the action cells, plus a row-to-row
    separator between the two team rows. Receives team
    colours, logos and names from ``App.tsx`` via
    ``ScoreboardView`` and ``CenterPanel``, so the marker
    honours ``followTeamColors`` and the per-team customisation
    overrides; absent logos fall back to a flat coloured
    circle. ``max`` is set to ``8`` on desktop / portrait and
    ``5`` on landscape phones (compact layout) so the strip
    never overflows the centre slot.

---

## [5.1.0] - 2026-05-02

### Security

- `/match/{match_id}/report` is no longer unauthenticated by default.
  Match snapshots bundle the audit log and full team customization,
  which is strictly more sensitive than live overlay state. The route
  now requires `OVERLAY_MANAGER_PASSWORD` (Bearer header *or*
  `?token=` query string) unless the operator explicitly opts in to
  open access via `MATCH_REPORT_PUBLIC=true`. When neither is
  configured the route returns 503.
- `app/match_report._team_color` validates customization-supplied
  hex colours against a strict `^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$`
  regex before interpolating into the CSS template, closing a CSS
  injection vector where a malformed value (e.g. `#a;}b`) could
  inject styles or break the page.

### Fixed

- `app/api/match_archive` filenames now include microseconds
  (`%Y%m%dT%H%M%S_<μs>Z`), so two archives in the same wall-clock
  second produce distinct `match_id` values instead of silently
  overwriting. Tests no longer need `time.sleep` workarounds.
- `app/api/action_log` per-OID writer serialization now goes
  through a fixed-size pool of 256 locks indexed by `hash(oid)`,
  replacing an LRU dict. The LRU could evict a lock while one
  thread was still inside the critical section, letting a
  concurrent caller for the same OID mint a fresh lock and enter
  the read/append/pop section at the same time — corrupting the
  JSONL audit file. The pool gives bounded memory without that
  race; unrelated OIDs that hash-collide just see negligible
  spurious serialization.
- Match report timeline drops "orphan" undo rows. Under the
  unified undo, `action_log.pop_last_forward` physically removes
  the original forward record and the caller appends a new
  `undo=True` audit entry. `_collapse_undos` then could not pair
  it with any prior forward and was leaving the orphan visible
  as an unanchored row referencing an action that no longer
  exists in the log. The collapse pass now drops those orphans
  entirely; paired collapses (forwards still followed by their
  explicit undo, e.g. legacy snapshots) keep working as before.
- `WebhookDispatcher` is now drained on application shutdown via
  `router_lifespan` calling `webhook_dispatcher.shutdown()` with
  `cancel_futures=True`, so a hung outbound delivery cannot keep
  the process alive past exit. Previously the executor was left
  to Python's default `atexit` cleanup, which waits for in-flight
  workers — usually fast (5 s per-target timeout) but visible in
  systemd unit shutdown latency.
- The cached `GameSession.undoable_forward_count` (source of truth
  for `GameStateResponse.can_undo`) now updates *only* after the
  audit-log append succeeds. A filesystem error during `_audit`
  used to leave the counter overstating the on-disk truth; now
  the counter and `count_undoable_forwards` always agree.
- `action_log.pop_last_forward` rewrites the audit file atomically
  via mkstemp + `os.replace` (matching `match_archive`'s pattern).
  Previously a crash mid-write would truncate the file and lose
  every preceding record.
- The `set_end` webhook now reports the set that just ended, not
  the set the session has advanced to. Both `add_point`'s
  set-winning point and `add_set` were reading
  `session.current_set` *after* it was incremented, so consumers
  saw `set_number=2` when set 1 just ended (or `set_number=4`
  after set 3 ended, etc.). The match-winning case is unchanged
  because `current_set` doesn't advance past the deciding set.
- The audit log now records the *final* score of the set the
  action operated on. Previously, set-winning add_point and
  add_set entries showed `team_1.score=0, team_2.score=0` because
  the snapshot was taken after `current_set` advanced to the new,
  empty set. Each entry gains a `score_set` field so a reader can
  see the set the score belongs to (usually equal to
  `current_set`, but lower on set-winning actions).
- HUD: show the Reset button on finished matches; primary
  controls relaid out on the left; match timer centred in its
  spacer.
- Match report: fall back to the rally axis when timestamps are
  non-monotonic so the score-evolution charts still render.
- Match report: prefer the team-identity colour over the per-team
  accent; set-winning points are now grouped under the set they
  completed.
- Match report: exclude `set_score` events from the longest-rally
  computation.
- Match report: respect the explicit Start-match anchor on the
  report side so the time axis matches the HUD timer.
- Layout: shrink the overlay preview on landscape phones; reverted
  the inline score-history experiment that broke alignment on
  small screens.
- PWA: exempt `/match` and `/matches` from the service-worker
  navigation fallback so the report and matches index render
  server-side instead of falling back to `index.html`.
- Match-end: respect the per-session `sets_limit` so best-of-1
  ends after one set instead of waiting for the configured
  best-of-N target.
- Rules UI: hide the "Points / final set" input when best-of-1 is
  selected (the field is irrelevant without a deciding set).
- Rules: keep the midpoint alert visible after the leader scores
  past the trigger point so operators don't miss it on a fast
  rally cluster.

### Changed

- Match report set-by-set table now annotates timeouts inline next
  to each score: a cell renders ``25 (2)`` when the team called
  two timeouts in that set and bare ``25`` when none. The
  previous separate "Timeouts (final set)" row has been removed —
  the per-set view is more useful and survives across sets, where
  the old row only showed the deciding-set count (timeout
  counters reset on each set transition).
- Match report "Biggest comeback" highlight reads more clearly.
  English copy was ``"down {n}, won {set}"`` — easy to misread as
  "won by 1" when ``{set}`` was a small number. Now reads
  ``"down {n} in set {set}"``. Romance-locale strings tightened
  similarly so the trailing ``{set}`` always sits behind the word
  for "set" (German already did this).
- Unified the two undo entry points behind one audit-log stack.
  Previously ``add_*(undo=True)`` and ``POST /game/undo`` had
  divergent stack semantics: the per-type flag only reverted state
  and appended an undo record, leaving the original forward record
  in the log. A follow-up generic undo would then pop the fantasma
  forward and double-revert. Now both paths pop the matching
  forward before applying the state-level inverse, so the two
  cannot drift.
  - ``action_log.pop_last_forward`` accepts a new ``team`` filter
    used by the per-type branches; ``action_log.peek_last_forward``
    is the read-only sibling used by ``GameService.undo_last`` to
    locate the next undoable record without consuming it (the
    dispatched per-type call performs the actual pop).
  - ``GameStateResponse.can_undo`` is a new boolean derived from a
    cached ``GameSession.undoable_forward_count``. Lets frontends
    drive the global Undo button from the server-side stack
    instead of maintaining their own LIFO. The counter is
    rehydrated from the audit log on session creation.
  - The bundled React control UI now calls
    ``actions.undoLast()`` (POST ``/game/undo``) for the bottom-bar
    Undo button and consumes ``state.can_undo`` for the disabled
    flag. Per-team double-tap gestures continue to use the per-type
    flag — the unification means they pop from the same stack.
    ``useActionHistory`` is no longer wired into ``App.tsx``.
  - Behaviour change for callers of the per-type
    ``add_*(undo=True)`` API: when no matching forward record
    exists in the log, the call still falls through to the
    state-level undo (preserving backward compatibility for
    callers manipulating state via ``set_score``/etc.), but it
    will not bump the undo counter — so ``can_undo`` only flips
    based on real audit-log activity.

### Added

- Operators can now delete archived match snapshots from the
  ``/matches/index.html`` page. New checkbox column with select-all
  in the header, a "Delete selected" button in the toolbar, and a
  per-row "Delete" button. Backed by a new
  ``DELETE /matches/{match_id}`` route gated by a stricter
  ``_check_admin_access`` helper that ignores
  ``MATCH_REPORT_PUBLIC=true`` — public mode grants read-only
  access, deletion always requires the admin token. Helper:
  ``match_archive.delete_match(match_id)``.
- Match-rules configuration is now editable per-session. New
  config-panel section "Match rules" exposes:
  * Indoor / Beach mode toggle (defaults: 25/15/5 indoor, 21/15/3
    beach). Switching mode applies the canonical preset; per-field
    overrides in the same call still win.
  * Sets selector (1 / 3 / 5).
  * Points-per-set and points-per-final-set inputs.
  * "Reset defaults for mode" button.

  Backend additions: ``app/api/match_rules.py`` (presets +
  side-switch helpers), ``GameSession.mode`` (persisted via
  ``session_meta``), new ``POST /api/v1/session/rules`` endpoint
  with ``mode``/``points_limit``/``points_limit_last_set``/
  ``sets_limit``/``reset_to_defaults`` body. ``GameStateResponse``
  carries ``config.mode`` so frontends can render the active
  preset.
- Beach side-switch tracker (§2.3). Beach matches switch sides
  every 7 combined points in non-tiebreak sets and every 5 in the
  tiebreak. ``GameStateResponse.beach_side_switch`` now surfaces
  ``{interval, points_in_set, next_switch_at, points_until_switch,
  is_switch_pending}`` for consumers; the field is ``null`` for
  indoor matches so existing payloads are unaffected. The control
  UI renders an inline indicator below the set pagination ("Side
  switch in N" → orange "Switch sides now" pulse on the boundary
  point), with i18n strings in all six locales.
- `GET /api/v1/links` returns a `latest_match_report` URL pointing
  at the most recent archived match snapshot for the session — but
  only when `MATCH_REPORT_PUBLIC=true`. The control UI's "Links"
  configuration section surfaces it as a clickable / copyable entry
  ("Latest match report" / "Último informe de partido" in 6
  locales). The token is intentionally never embedded in the URL,
  so gated deployments can keep their match reports private without
  the link section ever leaking the admin token.
- New browseable HTML match-history index at
  `GET /matches/index.html?oid=<OID>`. Lists every archived match
  for the OID with sets, duration, end-date, and a per-row link to
  the full report. Same auth gate as `/match/{id}/report`
  (`OVERLAY_MANAGER_PASSWORD` Bearer header / `?token=`, or open
  via `MATCH_REPORT_PUBLIC=true`). The page propagates the token
  to the per-match report links so a click-through doesn't
  re-prompt for credentials. `GET /api/v1/links` surfaces it as
  `match_history` (only when `MATCH_REPORT_PUBLIC=true` and the
  session has at least one archive), and the React control UI's
  Links section renders it alongside `latest_match_report` in 6
  locales ("Match history" / "Historial de partidos" / …).
- Session-level state survives process restarts. Per-OID flags
  (`simple` mode, custom `points_limit`, `points_limit_last_set`,
  `sets_limit`) used to live only in memory and were silently dropped
  on deploy/crash. They are now persisted to
  `data/session_meta_<sha256[:20]>.json` on every state mutation and
  rehydrated by `SessionManager.get_or_create` before any caller-supplied
  override is applied. Match data (scores, sets, current set, serve,
  timeouts) was already round-tripped through the overlay state store
  for local overlays and through the cloud for `overlays.uno`, so this
  closes the last in-memory gap. Deleting a custom overlay from
  `/manage` now also removes the session and the meta file.
- Outbound webhooks fired on game events. The new
  `WebhookDispatcher` reads
  `WEBHOOKS_URL`/`WEBHOOKS_SECRET`/`WEBHOOKS_EVENTS` (single endpoint)
  or `WEBHOOKS_JSON` (list of endpoints, optionally per-event-filtered)
  and POSTs `{event, oid, ts, state, details}` payloads on `set_end`,
  `match_end`, `timeout`, and `serve_change`. Bodies are signed with
  HMAC-SHA256 (`X-Webhook-Signature: sha256=<hex>`) when a secret is
  configured. Delivery is fire-and-forget on a small thread pool with
  a configurable timeout — failures are logged but never break the
  triggering action.
- Per-OID action audit log at
  `data/audit_<sha256[:20]>.jsonl`. Every state-mutating
  `GameService` call appends `{ts, action, params, result}` where
  `result` is a compact post-state snapshot. Exposed read-only via
  `GET /api/v1/audit?oid=...&limit=100`. Cleared on `reset()` and
  bundled into per-match snapshots on match end (see below).
- Match history archive. When a session transitions to
  `match_finished`, the final state, customization, audit log, and
  match config are bundled into a snapshot at
  `data/matches/match_<sha256(oid)[:20]>_<UTC-ISO8601>.json`.
  Two new read endpoints: `GET /api/v1/matches[?oid=…]` returns
  summaries newest-first, `GET /api/v1/matches/{match_id}` returns
  the full snapshot. `GameSession` now tracks `match_started_at`
  (persisted, reset on `reset()` and after every successful archive)
  so durations are accurate.
- Server-side undo stack. New `POST /api/v1/game/undo` pops the most
  recent forward `add_point` / `add_set` / `add_timeout` from the
  audit log and applies the inverse. Non-undoable forward records
  (e.g. `change_serve`, `set_score`, `reset`) stay in the log so
  the timeline is preserved; undo just walks past them. Returns
  `success=false, message="Nothing to undo."` when no eligible
  record exists. The per-type `undo=True` flag continues to work
  and now shares the same stack — see the **Changed** section
  above for the unification details.
- Print-friendly match report at `GET /match/{match_id}/report`.
  Server-rendered self-contained HTML page with hero scoreboard
  (team names, sets won, winner badge, team colours from the
  archived customization), set-by-set scores table, match facts
  (start/end timestamps, format, audit count), and an action
  timeline. A `@media print` block makes the page render cleanly
  via the browser's built-in "Save as PDF" workflow. Auth model:
  by default the route requires `OVERLAY_MANAGER_PASSWORD`
  (Bearer header or `?token=` query); set
  `MATCH_REPORT_PUBLIC=true` to make it openly addressable by
  hash-prefixed `match_id` instead — see the **Security** section
  above.
- OS-aware light/dark theme for the React control UI. The
  `darkMode` setting now accepts `'auto'` (default) in addition to
  `true` / `false` — when `'auto'`, the UI follows the OS
  `prefers-color-scheme` media query and updates live as the
  preference changes. The theme button in the bottom HUD now cycles
  through `auto → dark → light → auto`, with a `brightness_auto`
  icon and a localised "Theme: follow system" tooltip in the auto
  state. Existing localStorage values continue to work unchanged.
- Explicit match start. The HUD gains a "Start match" button that
  anchors the live match timer (rendered in the centre HUD spacer)
  and the report-side time axis. Theme and fullscreen buttons
  moved out of the scoreboard toolbar into the bottom HUD to
  declutter the bar.
- Match report enhancements layered on top of the initial
  print-friendly report:
  * Richer print layout with hero, set-by-set table, and action
    timeline polish; pregame records trimmed and unplayed sets
    hidden so finished best-of-3s don't render four empty
    columns.
  * Score-evolution charts can plot a time-elapsed X-axis (with
    automatic fallback to the rally index when timestamps aren't
    monotonic), and Highlights / chart axes / contrast / print
    dialog received a polish pass.
  * `MATCH_REPORT_PUBLIC_DELETE` env flag lets operators expose
    the delete affordance on `/matches/index.html` without
    handing out the admin token; OIDs in archived snapshots are
    redacted before render so a public report URL never leaks
    the session identifier.
- In-match alert system. The control UI now surfaces match-finished,
  set-point, and match-point indicators in the centre HUD, and an
  indoor deciding-set midpoint alert (frontend-driven, fires when
  the leader reaches half of the deciding-set target). Alerts
  display the relevant team via a directional triangle icon
  instead of an `[T1]` / `[T2]` label suffix, with i18n strings in
  all six locales.

### Removed

- Deleted the orphan `frontend/src/hooks/useActionHistory.ts` hook
  and its tests, plus the `ACTION_HISTORY_LIMIT` constant in
  `frontend/src/constants.ts`. The bundled React UI now drives the
  global Undo button straight off `state.can_undo` and
  `actions.undoLast()`, so the client-side LIFO stack the hook
  used to maintain is no longer needed. Pure cleanup — no
  externally visible behaviour change.

### Documentation

- README endpoint table lists `/api/v1/audit`, `/api/v1/matches`,
  `/api/v1/matches/{id}`, `/api/v1/game/undo`,
  `/api/v1/session/rules`, and `/match/{id}/report`. Configuration
  table documents the new `MATCH_REPORT_PUBLIC` env var.
- `FRONTEND_DEVELOPMENT.md` gains a dedicated section for
  `POST /api/v1/game/undo` plus a "Two undo APIs, one stack" note
  explaining that `add_*(undo=true)` and the new generic endpoint
  consume from the same audit-log stack and can be mixed safely;
  also flags the deliberate footgun that `state.can_undo` reflects
  audit-log truth (not raw scoreboard state).
- `AGENTS.md` source-tree reflects the new modules
  (`app/api/match_rules.py`, `app/api/action_log.py`,
  `app/api/match_archive.py`, `app/api/webhooks.py`,
  `app/api/session_persistence.py`, `app/match_report.py`).

---

## [5.0.4] - 2026-04-30

### Changed

- The `mosaic` overlay style (`/overlay/{id}?style=mosaic`) now scales to
  fit the current viewport without scrolling. The grid picks the best
  cols × rows split for the number of available styles, and each
  preview iframe is cropped to its reported render bounds and centred
  inside its cell, so all styles are visible at once and re-fit on
  window resize. Previously the page used a fixed 580px-min column with
  a 200px height cap, producing a vertically scrolling list once more
  than a few styles were available. Mobile viewports are pinned to
  `100dvh` so the grid stays inside the visible area when browser
  chrome shrinks/expands, and the iframe sizing handshake was
  rewritten around the resize observer's content-box plus a single
  `requestAnimationFrame` to remove the brief flicker on first paint
  and on resize (`#222`).

### Dependencies

- Bump `fastapi` floor from `>=0.115.0` to `>=0.136.1` (`#218`).
- Bump `uvicorn` floor from `>=0.32.0` to `>=0.46.0` (`#216`).
- Bump `httpx` (dev) floor from `>=0.27.0` to `>=0.28.1` (`#214`).
- Bump `pytest` (dev) floor from `>=9.0.2` to `>=9.0.3` (`#219`).
- Bump `pytest-asyncio` (dev) floor from `>=0.23.0` to `>=1.3.0` (`#213`).
- Bump base Docker image `python` from `3.12-slim` to `3.14-slim` (`#220`).
- Bump base Docker image `node` from `20-alpine` to `25-alpine` (`#221`).
- Bump `actions/setup-node` from `4` to `6` (`#217`).
- Bump `actions/upload-artifact` from `4` to `7` (`#212`).
- Bump `docker/setup-buildx-action` from `3` to `4` (`#215`).

---

## [5.0.3] - 2026-04-30

### Added

- Keyboard activation on the score and timeout buttons in the React
  control UI: Enter and Space now trigger the same single-tap / rapid
  double-tap / long-press gestures previously only reachable by mouse
  or touch, closing a WCAG 2.1.1 (Keyboard) gap. Implemented in the
  shared `useDoubleTap` hook and covered by new keyboard test cases.
- Frontend coverage gate in CI. `vitest run --coverage` is now enforced
  on every PR via `npm run test:coverage`; thresholds are pinned tightly
  below current coverage to act as a regression floor and the lcov
  report is uploaded as a CI artifact alongside the existing backend
  coverage artifact.

### Changed

- Centralised frontend timing and capacity tunables into a new
  `frontend/src/constants.ts` (`ACTION_HISTORY_LIMIT`, `DOUBLE_TAP_MS`,
  `LONG_PRESS_MS`, `HUD_AUTO_HIDE_MS`, `WS_PING_INTERVAL_MS`,
  `WS_RECONNECT_MS`). Previously these magic numbers lived inline in
  `App.tsx`, `useDoubleTap.ts`, `api/websocket.ts` and `useGameState.ts`;
  call sites now import from one place so future tuning is discoverable.
- Bumped the client-side undo history cap from 200 to 300 so a 5-set
  match with extended deuces is fully covered without truncation.
- Refactored the client-side undo state out of `App.tsx` into a
  dedicated `useActionHistory` hook (`frontend/src/hooks/useActionHistory.ts`).
  The hook owns the bounded stack, exposes a small testable API
  (`push`, `undoLast`, `popMatching`, `clear`) and uses a ref-mirrored
  state so rapid undo dispatches see the latest history even between
  React batches. Behaviour is unchanged; the hook now has dedicated
  unit tests covering the truncation path and the rapid-undo case.
- Internationalization is now correctly described in `README.md` as the
  React control UI being available in six locales (English, Spanish,
  Portuguese, Italian, French, German), and the bullet has been moved
  from the REST API section to "User and Overlay Management" where it
  belongs.
- README screenshots are now captured at `deviceScaleFactor: 1` instead
  of `2`, cutting the in-tree screenshot bundle from ~2.9 MB to ~1.1 MB
  with no loss of legibility. Regenerated every PNG under
  `docs/screenshots/` against the new setting.
- README screenshot section refreshed to reference the current mosaic
  outputs (`06-overlay-mosaic-full.png`, `07-overlay-mosaic-simple.png`)
  produced by `scripts/screenshots/capture.mjs`, replacing the stale
  `06-overlay-default.png` / `07-overlay-clear-jersey.png` /
  `08-overlay-mosaic.png` entries.
- `AGENTS.md` now mandates regenerating screenshots
  (`bash scripts/screenshots/run.sh`) on any change that affects the
  look of an operator-facing surface, and mandates a `CHANGELOG.md`
  entry on every user-visible change.

### Fixed

- Doc drift: directory-tree blocks in `AGENTS.md` and `DEVELOPER_GUIDE.md`
  still referenced pre-TypeScript-migration filenames (`App.jsx`,
  `i18n.jsx`, `theme.js`, `api/client.js`). Updated to the actual `.tsx`
  / `.ts` files and added the generated `api/schema.d.ts` entry.
- `ControlButtons` declared a `matchFinished` prop that no consumer ever
  read; it was forwarded `App.tsx` → `ScoreboardView` → `ControlButtons`
  for no effect. Removed across all three layers (and from the test
  fixture). Docstring also refreshed to match the current button set
  (visibility, preview, simple-mode, undo, fullscreen, dark-mode).

---

## [5.0.2] - 2026-04-28

### Added

- Double-tap to undo on the timeout button in the React control UI, mirroring
  the existing double-tap-to-undo gesture on the score button. The shared
  press-gesture detector has been extracted into a `useDoubleTap` hook so both
  buttons stay in sync (`frontend/src/hooks/useDoubleTap.ts`) (`#208`).

### Changed

- Undo behaviour in the React control UI: the bottom-bar undo button no longer
  toggles an "undo mode" — clicking it immediately reverts the most recent
  action, and clicking it again reverts the action before that, walking back
  through a bounded history (200 entries) of points, sets, and timeouts. The
  button is disabled when the history is empty. Reset and logout clear the
  history. Translations updated across all six locales (`ctrl.undoOn` /
  `ctrl.undoOff` replaced with `ctrl.undoLast`) (`#208`).

### Fixed

- Undoing a set-winning point now works correctly. Previously, after a winning
  point advanced the session to the next set, both the score-button double-tap
  and the undo button silently no-opped because the backend was looking at the
  new (empty) set's score. `GameManager.add_game(undo=True)` now falls back to
  the prior set when the current one has no score for the requested team,
  allowing the existing un-win cascade to fire as intended. Note: timeouts are
  a single per-team counter (not historical per-set), so undoing a set-winning
  point cannot restore the prior set's timeouts — the limitation is unchanged
  (`#208`).

---

## [5.0.1] - 2026-04-28

### Added

- Swipe navigation between scoreboard and configuration in the React control
  UI: a horizontal left-swipe on the scoreboard opens the config panel and a
  right-swipe returns to the scoreboard. The gesture is suppressed when the
  touch starts on an interactive element (buttons, inputs, sliders, switches,
  links, contenteditable) so taps, long-presses, and slider drags keep their
  default behavior. Implemented in `frontend/src/hooks/useSwipeNavigation.ts`
  (`#197`, `#198`).
- `?control=<id>` is now accepted as a backward-compatible alias for `?oid=<id>`
  on every API endpoint that takes the OID via query string (REST routes, the
  `/ws` WebSocket, and the request-logging middleware) and on the React
  control UI's initial-OID lookup. Either parameter resolves to the same
  overlay; passing both prefers `oid` (`#196`).

### Changed

- Config panel save UX: the "Save" button is now disabled (kept visible)
  until a setting that needs to be persisted to the overlay actually changes,
  making it visually obvious which controls apply directly versus which
  require an explicit save without the bottom bar reflowing. Leaving the
  panel via the back arrow, a browser back/edge-swipe gesture, or the in-app
  right-swipe now prompts the user before discarding pending edits
  (`config.unsavedChangesConfirm` translated for EN/ES/PT/IT/FR/DE)
  (`#200`, `#201`).

### Fixed

- Disabled config-panel bottom buttons now render with a clearly greyed-out
  style so it is obvious when an action is unavailable (`#202`, `#203`).
- Scoreboard control bar stays pinned on tablets and desktops; the auto-hide
  effect was split so the manual toggle keeps working on tablet form factors
  (`#204`).

### Dependencies

- Bump `postcss` from 8.5.8 to 8.5.12 in `frontend/` (`#206`).

---

## [5.0.0] - 2026-04-24

### Added

- In-process overlay engine: `LocalOverlayBackend` serves Jinja2 overlay
  templates and broadcasts state to OBS via WebSocket entirely in-process — no
  external overlay server required. Persists overlay state to JSON files, debounces
  WS broadcasts at 50 ms, and exposes 16 bundled templates out of the box
  (`#145`, `#143`).
- Custom overlay manager: password-protected `/manage` admin page (vanilla JS,
  no React) with CRUD for custom overlays. `GET`/`POST /api/v1/admin/custom-overlays`
  and `DELETE /api/v1/admin/custom-overlays/{name}`; optional `copy_from` param
  deep-clones an existing overlay's config on creation (`#146`, `#160`).
- Standalone `/preview` page: full-screen preview SPA route with a low-opacity
  toolbar for zoom −/+, dark/light backdrop toggle, and native fullscreen. Preview
  URL encoded in `/api/v1/links` for both custom and overlays.uno OIDs (`#163`).
- Per-session style override in preview: discreet style `<select>` in the
  `/preview` toolbar lets a remote viewer render with a different template via the
  existing `?style=` param without changing the session's saved `preferredStyle`
  used for streaming. Selector appears only when the server advertises more than
  one style; preview URL gains a `styles=` hint from `/api/v1/links` (`#183`).
- Mosaic preview grid: `?style=mosaic` on `/overlay/{id}` renders all overlay
  layouts side-by-side in a responsive iframe grid for at-a-glance style selection.
  A new `get_renderable_styles()` list on `OverlayStateStore` is a superset of the
  user-selectable list to keep `mosaic` out of the style picker (`#173`).
- OID resolution by file existence: `resolve_overlay_kind()` in
  `app/overlay_backends/utils.py` determines `CUSTOM` (overlay JSON exists on disk),
  `UNO` (22-char alphanumeric format), or `INVALID` — eliminating the required `C-`
  prefix. Legacy `C-` IDs continue to work (`#164`).
- `APP_TITLE` env var: configures the browser tab title, SPA `<title>`, PWA
  manifest `name`/`short_name`, and `/manage` page heading without rebuilding the
  frontend (default: `Volley Scoreboard`) (`#165`).
- Frontend error reporting: `window.onerror` / `unhandledrejection` pipeline
  ships errors to `POST /api/v1/log` so JavaScript exceptions surface in the
  backend log stream. `ErrorBoundary` wraps `ScoreboardView` and `ConfigPanel` and
  forwards React-caught errors through the same reporter (`#171`, `#176`).
- Logging — JSON output + correlation IDs: `dictConfig`-based logging pipeline
  (`app/logging_config.py`) with two formatters: `text` (ANSI, default) and `json`
  (one object per line, suitable for Loki/Datadog/CloudWatch). Every request gets a
  `X-Request-ID` correlation header and `request_id` injected into log records by
  `CorrelationMiddleware`. Uvicorn's access log is routed into the same pipeline
  (`#170`).
- Secret scrubbing: `RedactFilter` on the root logger scrubs `Bearer …` tokens
  and `password=`/`api_key=`/`token=`/`secret=` key-value pairs from every log
  record, complementing the existing `redact_url`/`redact_oid` helpers (`#171`).
- WS zombie detection: `WSControlClient` tracks `_last_inbound_ts`; `is_connected`
  returns `False` and the read loop breaks to trigger reconnect when no inbound
  traffic arrives within 55 s, preventing a hung socket from silently failing sends
  while blocking the HTTP fallback (`#167`).
- Per-OID session creation locks: each overlay ID now gets its own `asyncio.Lock`
  for the first-init path, preventing duplicate backend initialisation under
  concurrent requests (`#167`).
- Observability timing spans: `perf_counter` spans wrap `Backend.save_model`
  (split into `.model` and `.push` phases), `get_current_model`,
  `get_current_customization`, and `GameService.get_state`. Logs at DEBUG below
  threshold (500 ms remote / 50 ms in-process), WARNING above (`#180`).
- HTTP compression: `GZipMiddleware(minimum_size=1024)` attached outermost in
  `app/bootstrap.py` so it compresses final response bodies after observability
  middlewares (`#180`).
- Static asset caching: `CachedStaticFiles` subclass stamps
  `Cache-Control: public, max-age=31536000, immutable` on `/fonts` and the
  Vite-fingerprinted `/assets` mount. `index.html` gets `no-cache, must-revalidate`
  so clients always pick up new hashed asset URLs after a frontend rebuild (`#180`).
- `STRICT_OID_ACCESS` env var: flips the default so any authenticated user
  without an explicit `control` field is denied with `403`. Off by default to
  preserve single-tenant setups; see `AUTHENTICATION.md` (`#174`).
- Frontend a11y: score buttons gained `aria-label` / `aria-live="polite"` so
  assistive tech announces score changes (`#176`).
- DX — ruff + mypy expansion: ruff `select` now includes `I` (isort) and `B`
  (flake8-bugbear); mypy checks cover `app/api/routes` and `app/api/middleware` in
  addition to the existing `app/api` service layer (`#176`).
- OpenAPI snapshot + TypeScript tooling: `frontend/openapi.json` snapshot and a
  CI schema-drift guard ensure the generated API types stay in sync with the backend
  (`#147`).
- `?oid=` URL param: documented in `FRONTEND_DEVELOPMENT.md` — passing `?oid=`
  in the control URL pre-selects an overlay and persists it, replacing any previously
  stored value (`#178`).
- Additional UI languages: European Portuguese, Italian, French and German
  translations for the React frontend, using volleyball-specific terminology per
  locale (e.g. `desconto de tempo` PT, `time-out` IT, `temps mort` FR, `Auszeit`
  DE for the volleyball timeout; `marcador` / `tabellone` / `tableau de score` /
  `Anzeigetafel` for the scoreboard). Language picker labels each option with
  its native name.

### Changed

- Architecture — NiceGUI fully removed: the remaining NiceGUI UI layer
  (~6 000 lines) is deleted, completing the migration started in v4.0.0. The
  React frontend is now the sole operator interface; `main.py` becomes pure
  FastAPI + Uvicorn glue with no NiceGUI dependency (`#139`).
- Architecture — overlay server merged in: the standalone overlay server is
  folded into the backend, eliminating the double-hop latency (Backend → Overlay
  Server → OBS) and an entire service deployment (`#143`).
- Frontend — full TypeScript migration: all `.js`/`.jsx` files under
  `frontend/src/` converted to `.ts`/`.tsx`. Typed prop interfaces, exported API
  types, OpenAPI-generated `GameState` schema, and type-safe test mocks across eight
  incremental PRs (`#150`–`#156`).
- Backend factory: `create_app()` extracted into `app/bootstrap.py` so tests
  build an isolated app via `TestClient(create_app())` without relying on `main.py`
  import side effects (`#147`).
- `overlay_backends/` split: the 721-line monolith split into a per-strategy
  package (`uno.py`, `local.py`, `base.py`, `utils.py`), mirroring the routes split
  pattern (`#147`).
- `app/api/routes.py` split: the 394-line routes file split into domain
  submodules under `app/api/routes/` — `lifespan`, `session`, `state`, `game`,
  `display`, `customization`, `overlays`, `links`, `admin` (`#157`).
- Docker image slimmed: stage 2 switches from `COPY . .` to an explicit whitelist
  (`main.py`, `app/`, `font/`, `overlay_static/`, `overlay_templates/`,
  `frontend/dist`). `.dockerignore` expanded to exclude docs, tests, scripts, and
  compose files from the build context (`#158`).
- Service worker unified: the legacy hand-written `app/pwa/sw.js` removed;
  `vite-plugin-pwa`'s Workbox-generated worker is the single service worker.
  `/sw.js` endpoint and `app/pwa/` directory deleted (`#159`).
- Typed state model: `State`'s internal `dict[str, str]` replaced with a `Serve`
  enum and `GameState` dataclass. Legacy dict format preserved at system boundaries
  via `_from_dict()`/`_to_dict()` — no changes in `GameManager`, `GameService`,
  backends, or overlay code (`#166`).
- Logger hygiene: all loggers switched to `getLogger(__name__)` (replaces
  hardcoded strings like `"Storage"`, `"APIRoutes"`). Log calls use lazy `%`-style
  args; OID values redacted from URLs before logging (`#169`).
- Backend HTTP client: `Backend.session` mounts an `HTTPAdapter` with
  `pool_connections=10`, `pool_maxsize=20`, and
  `Retry(total=2, backoff_factor=0.3, status_forcelist=(502,503,504))` on both
  `http://` and `https://` (`#180`).
- Backend customization cache: `GameService.refresh_customization` now has a 5 s
  TTL read-through cache per session, coalescing bursts of identical fetches.
  Writes prime the timestamp so the next read is immediately consistent (`#175`).
- `ConfigPanel` lazy sections: the six config sections (Teams / Overlay /
  Position / Buttons / Behavior / Links) are `React.lazy` chunks behind a `Suspense`
  boundary with a shimmer skeleton fallback. Production build emits a separate JS
  bundle per section (~14 kB deferred from initial open) (`#175`).
- Score tap debounce: single-tap debounce drops from 400 ms to 220 ms, halving
  perceived latency for a normal point while still distinguishing double-taps (~150 ms
  typical) (`#172`).
- Neumorphic CSS tokens deduped: shared token variables extracted into
  `jersey_shared.css`, eliminating repetition across jersey overlay stylesheets
  (`#168`).
- Fonts: all 10 scoreboard `@font-face` rules use `font-display: swap` so scores
  stay visible during font fetch instead of hiding under FOIT (`#180`).
- Noisy log lines demoted: INFO logs on `Backend.save_model`, `save_json_model`,
  `save_json_customization`, `get_current_model`, `get_current_customization` demoted
  to DEBUG so timing WARNINGs are not drowned out during a match (`#180`).
- Backend i18n removed: `app/messages.py` `Messages` class and
  `SCOREBOARD_LANGUAGE` env var dropped. The Spanish placeholder defaults (`Local` /
  `Visitante`) are replaced with empty strings; users set team names via `APP_TEAMS`
  or the runtime Teams config panel (`#177`).
- Set buttons respect the button font: the center-panel set counters now
  render in the same `fontFamily` selected for the score buttons (via
  `FontSelector` / `settings.selectedFont`), instead of the browser default.
  `CenterPanel` gained an optional `fontStyle` prop that `ScoreboardView`
  forwards through; the `.set-button` CSS `font-size` is unchanged.

### Fixed

- Overlay WebSocket URL: after capability-URL hardening, `serve_overlay` now
  passes the SHA-256 `output_key` into the template context so `wsUrl` is built
  from the correct key. The prior raw `target_id` caused `/ws/` to close with code
  4004 and no state to reach the page (`#161`).
- Preview initial load: `usePreview` now waits for the session to be ready before
  firing `GET /api/v1/links`. The prior race with `initSession` caused the preview to
  be blank on first load and appear only after a manual refresh (`#162`).
- `/manage` service worker bypass: `/manage` added to `navigateFallbackDenylist`
  in the Workbox config so the PWA no longer intercepts navigation to the overlay
  manager and serves `index.html` instead of the FastAPI-rendered page (`#182`).
- `GameService.set_score` bounds: `set_number` is now validated against both
  lower (`< 1`) and upper (`> sets_limit`) bounds. Previously only the upper bound
  was enforced (`#174`).
- WSHub concurrent broadcast: per-socket `_BROADCAST_SEND_TIMEOUT` prevents a
  stuck subscriber from stalling updates to the rest; the cleanup pass no longer
  pops an OID whose set was replaced by a concurrent reconnect (`#174`).
- Customization cache sentinel: initial call always hits the backend even on
  systems where `time.monotonic()` starts near zero — sentinel defaults to `None`
  instead of `0.0` (`#175`).

### Security

- Authentication audit: `AUTHENTICATION.md` documents full route/mount coverage
  with findings F-1–F-5. `/list/overlay` now requires `OVERLAY_MANAGER_PASSWORD`
  (F-4) — previously unauthenticated (`#148`).
- Capability URL hardening: `resolve_overlay_id` now supports SHA-256 output
  keys for `/overlay/{…}` and `/ws/{…}` capability URLs, enabling unguessable
  public links. Dead pass-through `AuthMiddleware` removed (`#149`).
- Overlay-id sanitizer: `OverlayStateStore._sanitize_id` replaced the prior
  `os.path.basename` stripping with a strict allow-list regex
  (`^(?!\.{1,2}$)[A-Za-z0-9._-]{1,64}$`). Invalid IDs raise `ValueError` at the
  single choke point between user input and on-disk paths (`#180`).
- Iframe src validation: `OverlayPreview` runs `overlayUrl` through a scheme
  check that only accepts `http:`/`https:`. The Uno-overlay hostname match tightened
  from substring to exact hostname/subdomain so `evil-overlays.uno` cannot ride the
  Uno code path (`#180`).
- `secrets.compare_digest`: constant-time comparison used in `require_admin`,
  `check_api_key`, and the overlay server token check to prevent timing attacks
  (`#149`).

---

## [4.1.0] - 2026-04-08

### Changed

- Uno and Custom overlay backends decoupled into separate strategy classes
  sharing a common base interface; `oid` parameter threaded through all
  backend interface methods (`#136`).
- nicegui bumped to 3.10.0 (`#138`).

---

## [4.0.0] - 2026-04-04

### Added

- React scoreboard GUI: new `volley-control-ui` SPA replaces the NiceGUI
  operator interface. Includes scoreboard view, config panel, overlay preview,
  links/theme dialogs, and button font selector matching the old frontend.
- REST API + WebSocket layer: full decoupling of frontend from backend.
  Session management, OID authorization, and WebSocket authentication added.
  `GET /api/v1/overlays` returns the list of predefined overlays.
- `preferredStyle` in REST API: the overlay style preference is now
  readable and writable through the API, not only stored in-process.
- Uno/Custom backend decoupling: `UnoBackend` and `CustomOverlayBackend`
  extracted into separate strategy classes, sharing a common base interface
  (`#136`).

### Fixed

- WebSocket reconnect loop on session loss.
- `preferredStyle` no longer overwritten by the OID default on reconnect.
- `extract_oid` regex aligned with `validate_oid` so all valid OID characters
  are accepted uniformly.
- Customization refreshed from the overlay server on every page load.
- Custom overlay output URL resolved correctly after backend split.
- Session race conditions under concurrent init requests.
- Customization refresh and `get_styles` calls moved into `ThreadPoolExecutor`
  to avoid blocking the async event loop.

### Changed

- `requests` bumped from 2.32.5 to 2.33.1.
- Alternative NiceGUI frontend subproject removed from the repository.

---

## [3.3.1] - 2026-03-20

### Added

- Test coverage skeleton for seven priority areas (preview page, WebSocket
  client, custom overlay manager, auth, API routes, state model, broadcast hub)
  with inline comments identifying what each suite should verify (`#125`).

### Fixed

- Dockerfile base image pinned to the same nicegui version as `requirements.txt`
  so `docker build` and `pip install` stay in sync. Dependabot docker ecosystem
  added so future nicegui releases keep both files aligned (`#126`).

### Changed

- nicegui bumped from 3.8.0 to 3.9.0.

---

## [3.3.0] - 2026-03-19

### Added

- `show_logos` in custom overlay API: the "Logos" toggle from the
  customization page is now forwarded to custom overlays via the `show_logos`
  boolean in `overlay_control`, allowing overlays to hide/show team logos
  dynamically. Field added to `CUSTOM_OVERLAY_API.yaml` (`#123`).

---

## [3.2.2] - 2026-03-17

### Added

- Output key aliases: overlay output URLs now use a deterministic hash
  (output key) so public URLs are not easily guessable. The remote-scoreboard
  URL is preserved across renames (`#122`).

### Fixed

- WebSocket connection timeout was not triggering reconnect; `recv()` timeout
  now correctly handled to keep the heartbeat loop alive (`#122`).

---

## [3.2.1] - 2026-03-16

### Fixed

- `_listen()` was catching `TimeoutError` but `websocket-client` raises
  `WebSocketTimeoutException` — a separate class that does not inherit from
  `TimeoutError`. Timeouts fell through to the generic handler, breaking the
  listen loop and triggering reconnects every ~25 s instead of sending
  heartbeats. Fixed by catching `self._ws_lib.WebSocketTimeoutException`
  (`#121`).

---

## [3.2.0] - 2026-03-16

### Added

- WebSocket-first state sync for custom overlays: `Backend` now opens a
  persistent WebSocket control channel (`/ws/control/{id}`) to custom overlay
  servers. Replaces per-update HTTP POSTs, reducing latency and overhead.
  Auto-discovers the endpoint via `/api/config/{id}` on startup (`#120`).
- **`WSControlClient`** (`app/ws_client.py`): background daemon thread,
  thread-safe sends, message dispatching. Protocol v1 supports `state_update`,
  `visibility`, `raw_config`, `get_state`, `ping/pong`, `obs_event`.
  Auto-reconnect with exponential backoff (1 s → 30 s max) and heartbeat
  pings every 25 s. 19 unit and integration tests (`#120`).
- Transparent HTTP fallback: if the WebSocket is unavailable all operations
  fall back to HTTP with no loss of functionality (`#120`).
- `controlWebSocketUrl` field added to `CUSTOM_OVERLAY_API.yaml` and
  `CUSTOM_OVERLAY.md` (`#120`).
- `websocket-client >= 1.6.0` and `python-dotenv 1.2.2` added to dependencies.

### Changed

- `gui.py` modularised into `app/components/button_interaction.py`,
  `button_style.py`, and `gui_update_mixin.py` (`#113`).
- Visual-only button settings (font, colors, icon opacity) isolated per
  browser tab — changes no longer propagate to other connected browsers via
  score broadcasts (`#116`).
- Improved multi-browser scoreboard synchronisation (`#115`).

---

## [3.1.0] - 2026-03-13

### Fixed

- Font, button colors, and icon opacity/visibility settings no longer
  propagate from one browser tab to another when a score broadcast fires.
  Each GUI instance now caches its visual preferences at connection time and
  refreshes only on explicit user change (`#116`).

---

## [3.0.3] - 2026-03-13

### Fixed

- Scoreboard synchronisation improved: state is now synced in memory before
  broadcasting, eliminating a race that could cause tabs to show stale scores
  (`#114`, `#115`).

---

## [3.0.2] - 2026-03-11

### Fixed

- `Client has been deleted but is still being used` warning eliminated.
  `_broadcast_to_others` now checks `Client.instances` before calling
  `update_ui`, skipping stale clients from closed browser tabs (`#112`).

---

## [3.0.1] - 2026-03-10

### Fixed

- `AssertionError` in `AppStorage._get_storage()` when NiceGUI user session
  storage has not been initialised yet — now falls back to in-memory storage
  gracefully, preventing 500 errors on page load (`#111`).
- Recursive call chain `get_current_customization` → `save_json_customization`
  → `update_local_overlay` → `get_current_customization` broken, eliminating
  maximum-recursion-depth crashes on custom overlay updates (`#111`).
- Customization cached on `Backend` instance after first fetch, removing a
  redundant `GET /api/raw_config` on every score press (3 requests → 2) (`#111`).
- `update_local_overlay` uses `self.session.post` instead of bare
  `requests.post`, reusing the connection pool for the `/api/state` call (`#111`).

---

## [3.0.0] - 2026-03-09

### Added

- PWA support: manifest, service worker, app icons, fullscreen display
  mode, Screen Wake Lock to keep display active during matches, and haptic
  feedback on score buttons (`#110`).
- Double-tap to undo: double-tapping a score button reverses the last
  score action; long-press timer raised to 1.0 s to avoid conflict (`#110`).
- Custom overlay support: `APP_CUSTOM_OVERLAY_URL` and
  `APP_CUSTOM_OVERLAY_OUTPUT_URL` env vars; dynamic overlay ID fetching;
  multiple schema payload support; `preferredStyle` for custom overlays;
  secure URL reconstruction with proxy-headers support (`#110`).
- **OpenAPI 3.0 spec** for the custom overlay contract
  (`CUSTOM_OVERLAY_API.yaml`) and full integration guide (`CUSTOM_OVERLAY.md`)
  (`#110`).
- Multi-user state broadcast: GUI instance registry synchronises state
  across multiple concurrent browser sessions (`#110`).
- `/health` endpoint: HTTP readiness check integrated with Docker
  healthcheck (`#110`).
- Startup configuration validation: all configuration validated at startup
  with early error reporting (`#110`).
- Adaptive layouts: adaptive layout options for CHAMPIONSHIP mode; explicit
  current-set mapping to Sets Display for layout `446a382f` (`#110`).
- GitHub Actions CI pipeline with Playwright and pytest (`#110`).

### Changed

- UI components extracted into `app/components/` module (`#110`).
- `Messages` class added for i18n-ready UI strings (`#110`).
- `constants.py` introduced to centralise repeated literals (`#110`).
- Thread pool and timeouts added for all backend operations (`#110`).
- Custom font scales normalised with exact flexbox metrics (`#110`).
- `.dockerignore` added for smaller Docker images (`#110`).
- `requirements-dev.txt` separated from `requirements.txt`; all dependency
  versions pinned (`#110`).
- nicegui bumped to 3.8.0.

---

## [2.3.0] - 2026-02-27

### Added

- Adaptive CHAMPIONSHIP layout: layout options for CHAMPIONSHIP mode that
  disable team color fields and rename labels to match the broadcast format
  (`#106`).

---

## [2.2.1] - 2026-02-24

### Changed

- nicegui bumped from 3.7.x to 3.8.0 (`#105`).

---

## [2.2.0] - 2026-02-24

### Added

- PWA: full Progressive Web App support with manifest, service worker, and
  app icons merged from dev branch (`#103`, `#104`).
- Screen Wake Lock: keeps the display on during a match (`#103`).
- Double-tap to undo: reverses the last score action; long-press timer
  adjusted to 1.0 s to avoid conflicts with double-tap (`#103`).
- Haptic feedback: vibration on score button presses (`#104`).

### Changed

- Custom font offset/scaling normalised using exact algorithmic flexbox metrics
  so all fonts are centred correctly and padding is bounded precisely (`#99`).
- GitHub Actions updated: `actions/checkout` → v6, `actions/setup-python` → v6
  (`#100`, `#101`).

---

## [2.1.1] - 2026-02-20

### Changed

- Dark/Light theme toggle and fullscreen button moved from the scoreboard
  toolbar into the customization page for a cleaner main layout (`#98`).

---

## [2.1.0] - 2026-02-16

### Fixed

- Overlay preview broken after nicegui upgrade due to issue
  zauberzeug/nicegui#5749; downgraded to nicegui 3.6.1 as a workaround (`#96`).

### Changed

- Resize trigger refactored to debounce minor size changes, preventing
  redundant layout recalculations (`#96`).

---

## [2.0.1] - 2026-02-06

### Changed

- nicegui bumped to 3.7.1 (`#94`).

---

## [2.0.0] - 2026-02-02

### Changed

- Scoreboard, score buttons, and configuration pages fully refactored with
  updated color scheme for timeout and serve buttons (`#92`).

---

## [1.8.2] - 2026-01-29

### Fixed

- Dismissed-notification regression introduced by the nicegui upgrade fixed
  (`#90`).

### Changed

- nicegui upgraded to 3.6.1 (`#90`).

---

## [1.8.1] - 2026-01-08

### Changed

- nicegui upgraded to 3.5.0.

---

## [1.8.0] - 2025-12-21

### Added

- `DEVELOPER_GUIDE.md`: comprehensive guide covering project architecture,
  directory structure, core logic (`State`, `GameManager`, `Backend`), and
  common modification scenarios (`#88`).

### Fixed

- Race condition on page load where set scores were not synchronised correctly;
  a delayed update in the initialisation phase ensures the UI reflects stored
  state (`#88`).

### Changed

- Dockerfile migrated to `uv pip install` to align with the latest
  `zauberzeug/nicegui` base image (`#88`).
- UI text centering on score buttons improved via updated
  `GAME_BUTTON_CLASSES` (`#88`).

---

## [1.7.3] - 2025-12-09

### Changed

- nicegui bumped from 3.3.1 to 3.4.0 (`#87`).

---

## [1.7.2] - 2025-12-06

### Changed

- Font selector moved to its own section with an internationalised default
  entry (`#86`).
- Options panel redesigned and redistributed for better usability (`#86`).

---

## [1.7.1] - 2025-12-06

### Added

- Font preview rendered inline in the font selector (`#85`).

### Fixed

- Storage bug where different users shared the same browser storage fixed
  (`#85`).

---

## [1.7.0] - 2025-12-05

### Added

- Font configuration: per-button font selection for scoreboard text (`#84`).
- Auto-resize buttons: button size scales automatically based on screen
  dimensions (`#84`).

---

## [1.6.1] - 2025-11-28

### Added

- Button colour customisation: point buttons can now be given explicit
  colours or set to follow the teams' overlay colours (`#82`).

---

## [1.6.0] - 2025-11-25

### Changed

- Output URL configuration made optional; output URL is now derived from the
  control token automatically when not supplied (`#81`).

---

## [1.5.0] - 2025-11-24

### Added

- Responsive layout: scoreboard adapts to portrait and landscape
  orientations and different screen sizes (`#80`).

---

## [1.4.3] - 2025-11-04

### Fixed

- Unit tests updated to work with the NiceGUI 3.2.0 API changes (`#76`).

---

<!-- Versions below v1.4.3 predate formal GitHub releases and git tags.
     Entries are reconstructed from merged pull requests. -->

## [1.4.2] - 2025-10-08

### Added

- Overlay preview: inline preview panel showing the live overlay output
  inside the scoreboard UI. Auto-simplifies the scoreboard variant to the full
  board on timeouts (`#66`).
- Dedicated `/preview` link in the links section (`#72`).

### Fixed

- Overlay preview initial size incorrect on first render (`#69`, `#73`).

### Changed

- nicegui upgraded from 2.x to 3.0.0, then through 3.0.3, 3.0.4, and 3.1.0
  (`#68`, `#72`, `#74`, `#75`).

---

## [1.4.1] - 2025-09-10

### Added

- UI tests: Playwright-based UI test suite covering the main scoreboard
  flows (`#59`).
- **Long-press UI tests** and custom-value flow tests (`#60`).
- OID selection logic refactored to have clear priorities and persist
  selections across page reloads (`#61`).
- `REMOTE_CONFIG_URL` env var: loads environment variables from a remote JSON
  config file at startup (`#64`).
- `SINGLE_OVERLAY_MODE` env var: disables the `UNO_OVERLAY_OID` preference so
  a single custom overlay always takes precedence (`#64`).

### Fixed

- Long press on game/set buttons not triggering set/match win conditions
  (`#62`).
- Setting a custom value via long press no longer blocks the next single tap
  from registering (`#60`).

### Changed

- Long-press feature refactored; nicegui bumped to 2.24.1 (`#63`).

---

## [1.4.0] - 2025-08-29

### Added

- Long press to set custom value: long-pressing a score button opens a
  numeric input to set an arbitrary value directly (`#55`).
- **Unit tests for state management** (non-UI) (`#55`).

### Changed

- Complete code overhaul decoupling GUI rendering from model mutations; `State`
  and `GameManager` now operate independently of NiceGUI callbacks (`#55`).
- Light interface refactor (`#55`).

---

## [1.3.0] - 2025-08-08

### Added

- Behavior dialog: new options dialog covering auto-hide HUD, auto-simple
  mode, fullscreen, and dark/light toggle — consolidated from scattered toolbar
  buttons (`#43`).
- Theme support: light and dark themes selectable at runtime (`#52`).
- Project renamed to **volley-overlay-control** (`#52`).

### Fixed

- Dark mode setting not persisted correctly across reloads (`#44`).

### Changed

- Session cookie sent with backend requests to preserve server-side session
  (`#51`).
- Backend code refactored; reset links no longer require two redirects (`#51`).

---

## [1.2.0] - 2025-05-02

### Added

- Dynamic layout: scoreboard size adapts to the device's screen dimensions
  and orientation (`#29`).
- Persistent dark mode: dark/light preference saved and restored across
  page reloads (`#24`).
- Sort teams list: overlay team names displayed in alphabetical order in
  the configuration combo box (`#26`).
- More compact layout variant for small screens (`#28`).
- Reload dialog for triggering a page refresh from within the UI (`#30`).

### Fixed

- Reset dialog messages improved for clarity (`#30`).
- Resize extended to portrait orientation, not only landscape (`#31`).
- Uninitialised button reference no longer causes errors on startup (`#30`).

### Changed

- Lock icon on team selector prevents accidental team colour changes (`#34`).
- nicegui bumped through 2.15.0 → 2.16.1 (`#25`, `#31`, `#32`).

---

## [1.1.0] - 2025-04-04

### Added

- User authentication: optional password protection for the scoreboard
  control page (`#17`).
- Internationalisation: UI strings available in English and Spanish via
  `SCOREBOARD_LANGUAGE` env var (`#17`).
- Custom overlay control URL: operator can supply a custom overlay's
  control and output URLs directly in the UI (`#17`).
- Predefined overlay selections: list of known overlay IDs selectable from
  a dropdown (`#17`).
- Overlay API updated to the March 2025 version — breaks compatibility with
  earlier overlay schemas (`#14`, `#17`).
- Multiple overlays: control more than one overlay from a single session
  (`#14`).
- `?control=` and `?output=` URL parameters to pre-fill overlay URLs on load
  (`#14`).
- Option to launch without defining a default overlay (`#14`).

---

## [1.0.0] - 2025-02-20

### Added

- Initial release of the NiceGUI-based volleyball scoreboard control
  application.
- Score buttons for points, sets, timeouts, and serve direction.
- Real-time state push to the connected overlay server via HTTP.
- Docker image with CI publish to Docker Hub.
- Basic overlay integration using the overlays.uno API.
