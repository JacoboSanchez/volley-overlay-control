# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once a first tagged release ships.

## [Unreleased]

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

### Changed

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

### Security

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

### Fixed

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

### Added

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

### Changed

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

### Added

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

- **New set-summary recap style "Scoresheet" (`ledger_diff`).** A
  comparative box-score — one row per stat with the home value, a bar
  tinted toward whichever side leads, and the away value — sitting above
  a full-width "point difference" area graph that swings up toward the
  home team and down toward the away team as the lead changes through the
  set (with timeout ticks and a set-point marker). When the set carries
  per-point scouting tags the stats split into two columns (general |
  point types); otherwise a single centred column shows and the graph
  gets the extra room. Responsive from a 1280×720 up to a 2560×1440 OBS
  canvas, with live/finished states, hot-swap and i18n in all six overlay
  locales.

### Removed

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

- **Set-summary "Podium" (`podium`) style.** Replaced by the new
  `ledger_diff` scoresheet. The built-in catalogue keeps six set-summary
  styles. Any overlay still configured with `"podium"` falls back to the
  default recap style automatically (the renderer already collapses
  unknown styles to `brand_ledger`), so no operator action is required.

### Fixed

- **Stale per-point breakdown carried over between matches.** The
  audit-derived `point_types_by_set` stats were deep-merged into the
  persisted overlay state instead of replacing it, so a match scored
  *without* per-point tags inherited the previous match's serve / attack
  / block / opponent-error tallies — the set-summary recap (and any
  other consumer of `overlay_control.stats`) kept showing e.g. "3 aces /
  2 kills" when only one point had been played. `point_types_by_set` now
  joins the other per-set buckets in the state store's force-replace
  list, so an empty broadcast (no tags this match) correctly clears the
  old breakdown.
- **Glass set-summary recap clipped its lower stats.** When the
  point-type breakdown band was shown, it ate into the fixed-height
  stage and pushed the score tile's bottom rows (timeouts / total
  points) off-screen. The band is now a compact single-line chip strip,
  and the glass score tile tightens its hero scores only while the band
  is present, so all four stat rows stay visible from a 1280×720 up to a
  2560×1440 OBS canvas. The roomy no-band layout is unchanged.

## [5.8.0] - 2026-06-19

### Added

- **"Corners" overlay family — four horizontal, corner-docked styles.**
  `corner_tags`, `corner_gradient`, `corner_jersey` and `corner_wedge` are
  horizontal cousins of `pylons`: one self-contained chip per team docked to a
  corner of the frame (home → left edge, away → right edge), with horizontal
  team names instead of the rotated pylons names. They reuse the edge-pinned
  machinery — `data-fixed-geometry` (so they ignore the free x/y geometry and
  expose the **top / center / bottom** vertical-anchor knob; designed for the
  top/bottom corners) and the per-edge hide animation — and ship a light/dark
  theme. The three live markers are split so they never read as one cluster:
  sets-won pips sit by the score on the court side, while the serve lamp and
  timeout bars sit by the team icon on the screen-edge side. Both chips are
  width-equalised to the longer of the two team names (no truncation).
  `corner_gradient` washes each chip in the team colour; `corner_jersey` leads
  with the team-kit jersey icon; `corner_wedge` is an angular variant with a
  live set-progress underline. This brings the built-in catalogue to 27
  selectable styles (also restores the previously undocumented `pylons_gradient`
  to the README list).

### Changed

- **Edge-pinned overlays fold to the screen edges when swapping sides.**
  Swapping the home/away sides while a `pylons`- or `corners`-family overlay
  is on screen used to collapse the whole frame toward the centre and snap
  back, which read as an abrupt vanish-and-return. Each panel now folds to
  its own screen edge and unfolds again on the swapped side, reusing the
  same choreography as the show/hide animation. Other styles keep the quick
  horizontal card-flip.

### Fixed

- **The in-app preview no longer reloads when swapping sides.** Clicking
  "swap sides" reordered the control-UI panels in the DOM, which made React
  move the centre panel's node — reloading its embedded preview iframe and
  flashing the scoreboard (replaying the hide animation) on every swap. The
  panels now keep a fixed DOM order and trade visual places via CSS flex
  `order`, so the preview iframe is never torn down and the swap is seamless.
  (Control UI only — the OBS browser source was unaffected.)
- **Swapping sides no longer flashes a hidden scoreboard on screen.** When
  the main scoreboard was hidden, a side swap briefly animated the panels
  into view before hiding them again (most visible on the edge-pinned
  `pylons` / `corners` families). The swap now re-renders silently while
  hidden, so the scoreboard stays off screen.
- **Edge-pinned overlays no longer flash for a frame when they render while
  hidden.** The `pylons` and `corners` panels had no resting hidden state in
  CSS, so a scoreboard configured hidden — or shown in the in-app preview
  while hidden — painted the panels at full opacity for a frame before the
  hide animation ran. They now default to `opacity: 0` until the reveal
  animation raises them.
- **Overlay pages can no longer be frozen by a proxy/CDN.** The `/overlay`
  and `/follow` pages embed a per-render `?v=` cache-buster on their JS/CSS,
  but if an intermediary cached the HTML itself that `?v` froze and stale
  assets kept being served — the overlay looked stuck on old code after a
  deploy even though the bare `/static` URLs were fresh. These dynamic pages
  now send `Cache-Control: no-cache, no-store, must-revalidate`.

### Dependencies

- Bump ``starlette`` from ``1.0.1`` to ``1.3.1`` to clear
  ``CVE-2026-48817``, ``CVE-2026-48818``, ``CVE-2026-54282`` and
  ``CVE-2026-54283`` (flagged by ``pip-audit --strict`` against the
  runtime ``requirements.lock``). ``starlette`` is a transitive
  dependency of FastAPI, so the pin is expressed as a
  ``starlette>=1.3.1`` security floor in ``requirements.txt``.
  Regenerating the lock also re-synced drift left over from earlier
  ``requirements.txt`` floor bumps — ``fastapi`` ``0.136.1`` →
  ``0.137.2``, ``uvicorn`` ``0.47.0`` → ``0.49.0`` and ``httptools``
  ``0.7.1`` → ``0.8.0``.

## [5.7.0] - 2026-06-14

### Added

- **Vertical-anchor control for edge-pinned overlays.** The `pylons` and
  `pylons_gradient` styles dock to the screen edges and ignore the free
  x/y/scale geometry knobs, so only their vertical placement is meaningful.
  The Overlay config section now offers a **top / center / bottom** selector
  (persisted as `verticalAnchor`) that docks the panels to the chosen edge of
  the frame. A `?anchor=top|center|bottom` URL parameter overrides it for a
  fixed OBS browser-source URL. Localised in all six UI languages.

### Changed

- **Style-specific overlay knobs only appear where they have an effect.** A new
  `GET /api/v1/style-capabilities` endpoint reports, per style, whether the
  dark/light **theme** selector and the vertical-anchor control change anything
  (scanned from the on-disk templates/CSS). The control UI now hides the theme
  selector for styles without a `body.overlay-theme-*` override and only shows
  the vertical-anchor control for edge-pinned styles, instead of showing the
  theme selector for every custom overlay with more than one style.

### Fixed

- **Pylons hide animation now collapses each panel to its own screen edge.**
  Hiding the scoreboard slid the whole frame sideways, which read wrong for the
  edge-pinned `pylons` / `pylons_gradient` styles (the two panels drifted off in
  the same direction). They now exit symmetrically — the home panel collapses to
  the left edge, the away panel to the right — while other styles keep the
  existing slide-and-fade.

- **Vertical-anchor selection is now persisted.** `verticalAnchor` was missing
  from the `ALLOWED_CUSTOMIZATION_KEYS` allow-list, so `PUT /customization`
  silently dropped it — the operator could pick top/center/bottom and save, but
  the overlay never moved. Added it to the allow-list (and the `style` preset
  category) so the choice round-trips to the overlay and into saved presets.

## [5.6.1] - 2026-06-12

### Added

- **New `pylons_gradient` overlay style.** Team-colored glass panels pinned to
  the screen edges — the team's primary colour fades from the top into a dark
  translucent base with backdrop-filter blur. Points and pips stay white for
  contrast. Supports dark/light themes and compact mode.

- **Compact mode (simple mode) for `pylons` and `pylons_gradient`.** When the
  operator enables "show only current set", both pylons styles now hide team
  names and tighten the panel — collapsing to a minimal strip (logo, score,
  set pips, serve lamp) similar to the `micro` overlay aesthetic. The
  transition animates smoothly.

## [5.6.0] - 2026-06-12

### Fixed

- **Remote config (`REMOTE_CONFIG_URL`) now accepts the configurator's
  `{"configuration": {...}}` envelope.** The
  [volleyball-scoreboard-configurator](https://github.com/JacoboSanchez/volleyball-scoreboard-configurator/)
  exports the config wrapped in a top-level `configuration` key, but the
  app read the JSON as a flat env-var mapping — so every setting
  (`APP_TEAMS`, `APP_THEMES`, `PREDEFINED_OVERLAYS`, …) was looked up at
  the wrong level, silently fell through to defaults, and the configured
  teams never appeared. The loader now unwraps a lone `configuration`
  envelope transparently while still accepting a plain flat object.

- **Score digits now centre vertically in every font.** The ten
  selectable score-button fonts ship wildly inconsistent vertical
  metrics (declared ascents from 0.58em to 1.03em), which browsers
  resolve differently per platform — so the numbers sat visibly high
  or low depending on the font and device, and a hand-tuned offset
  table only papered over it on some platforms. Every score-font
  ``@font-face`` (and the LED overlay's digit font) now carries
  ascent/descent overrides computed from the actual digit glyph
  geometry, which centres the digits identically on Android, desktop
  and OBS; the manual offsets are zeroed. Horizontal centring is
  corrected the same way: some fonts centre the glyph *advance* but
  not the visible ink (LED board's digits sit a uniform 0.07em left
  of centre), so the measured imbalance is compensated per font with
  a proportional shift of the rendered digits.

### Added

- **Overlay output scale + outer margin (custom overlays).** Two new
  per-overlay knobs in the config panel's Position section, persisted in
  presets under the existing *position* category: **Scale** zooms the
  whole rendered output (base 100%), and **Margin** adds or removes a
  symmetric outer border expressed as a percentage of the canvas
  (positive shrinks the overlay toward centre leaving a uniform border;
  negative pushes it past the edges to compensate for stream overscan).
  Both apply to the built-in overlay engine as a single global transform
  on the overlay body, so they affect *every* style uniformly —
  including edge-pinned layouts that opt out of per-element geometry.

- **Documented streaming position presets in `.env.example`.** The
  `APP_THEMES` env var (already surfaced read-only under Config →
  Presets) now ships a documented example of six position-only
  presets for a 1080p stream — four screen corners plus centred
  top/bottom single-line placements — alongside an explanation of the
  `Width` / `Height` / `Left-Right` / `Up-Down` coordinate system.
  Config-only; no code change.

- **Side switching across every live view.** A swap button in the
  scoreboard centre column flips which team renders left/right on
  the operator UI, on all 22 OBS overlay styles (behind a quick
  horizontal fold transition) and on the public spectator page —
  presentation only, so team identity in the API, stats and audit
  log never changes. An optional **auto switch sides** setting in
  the Match Rules section follows the physical court: one switch per
  set change, every 7 combined points in beach mode (5 in short
  sets), and at the deciding-set midpoint (8 of 15) indoors —
  including the mid-set switches of already-completed beach sets, so
  the orientation always matches where the teams actually stand. The
  orientation is a pure function of the live score, so undo rewinds
  it; the manual button stays usable as a correction in auto mode,
  and toggling auto never visually jumps the current picture. New
  endpoints: ``POST /api/v1/display/swap-sides`` and
  ``POST /api/v1/display/auto-swap-sides``; the effective orientation
  ships as ``sides_swapped`` in the game state and the broadcast.

- **Three more scoreboard overlay styles.** `led` is a retro
  gym-scoreboard homage — black bezel cabinet, dot-matrix texture,
  glowing amber LED points (rendered with the repo's own "LED board"
  font), red set counters, green serve lamp and amber timeout lamps;
  its LED palette is the style's identity; the theme toggle swaps the
  cabinet between the dark default and a light aluminium face while
  the recessed digit windows keep their dark glass and glow. `pylons` docks one slim panel per team to the
  left/right screen edges (rotated name, points, set pips, timeouts,
  serve lamp), keeping the whole top and bottom of the frame clean —
  placement is the design, so it opts out of operator geometry via
  the new data-fixed-geometry container attribute. `micro` is the
  smallest footprint in the catalogue: a logo+points capsule with a
  serve ring around the serving team's logo and a detached pill with
  the set pips and localized set label. pylons and micro ship light
  themes and use the contrast-safe accents.

- **Overlay dark/light theme + contrast-safe team accents.** A new
  three-state appearance setting (default / dark / light) in the
  overlay config flips the card surface on styles that define the
  matching palette — `neon` and `baseline` gain a light variant,
  `broadcast` and the light-native jersey family (`neo_jersey`,
  `clear_jersey`, `split_jersey`) dark ones; "default" keeps every
  style's native look. Styles whose card surface is the team colour
  itself (e.g. `glass`) intentionally ignore the toggle, and the
  jersey kit icons keep their raw team colours on either surface.
  The theme rides the customization (`overlayTheme`), is included in
  style presets, and can be pinned per browser source with a
  `?theme=` URL parameter (the mosaic forwards it to every preview).
  Independently of the theme, the engine now derives contrast-safe
  per-team accents — the team colour nudged toward white (dark
  surfaces) or black (light surfaces) until it clears WCAG's 3:1
  non-text ratio — so a navy team colour stays legible on the dark
  neon/baseline cards and a pale yellow on the white broadcast card,
  with no operator action needed.

- **Three new scoreboard overlay styles.** `broadcast` is a TV-network
  score bug with per-team colour spines and set *pips* (one dot per
  set needed to win, filled per set won) instead of a numeric set
  count; `baseline` is a bottom-centre lower third with mirrored team
  wings, per-set history chips and a per-team progress bar toward the
  current set's point target (rule-aware: 21 beach / 15 deciding set);
  `neon` is a dark smoked-glass card with team-colour glow underlines
  and glowing monospace digits. All three are deliberately text-free
  apart from the current-set label, which is now localized through the
  shared overlay label bundle (en/es/pt/it/fr/de) — previously the
  dormant `current-set-label` hook in app.js hardcoded English "SET".
  The new set-pip and set-progress renderers in app.js are opt-in by
  element ID, so existing styles are untouched.

- **Set-summary empty state.** Opening the between-set recap before
  the first rally of a set used to show blank chart axes (or bare
  placeholder chips). The chart variants (`brand_columns`, `glass`,
  `podium`) now overlay a localized "No points yet this set" note on
  the chart area, and `brand_ledger` shows it inline in its centre
  column. The string already shipped in all six locales but was never
  rendered.
- **One-click release workflow.** A new manual **Cut release** GitHub
  Actions workflow (`.github/workflows/release.yml`) renames the
  changelog's `[Unreleased]` section to the new version, commits and
  tags `vX.Y.Z`, creates the GitHub release with the cut section as
  notes, and chains the Docker image build. A `dry_run` input previews
  the notes without committing. The changelog transform lives in
  `scripts/release/cut_changelog.py` (unit-tested) and the procedure
  is documented in `CONTRIBUTING.md`.

### Changed

- **Pylons panels are now always the same height.** The two
  edge-docked panels of the *pylons* overlay used to size
  independently from their own team name, so a long name on one
  side made that panel visibly taller than the other. Both panels
  now stretch to the height of the longer name and the shorter name
  centres in the freed space, so the pair reads symmetrically and
  the bottom cluster (points, set pips, timeouts, serve lamp) lines
  up across both sides.
- **Set-summary recap polish.** The recap stage now rises subtly into
  place alongside the existing cross-fade (disabled under
  `prefers-reduced-motion`); very long club names are capped at two
  lines in every variant so they can no longer overflow the fixed
  16:9 stage; and the point-progression chart scales its vertical
  axis to the active rules' set target (21 for beach, 15 for a
  deciding set) instead of a fixed 25, so short-format sets fill the
  chart height.
- **Frontend coverage gate raised.** 13 new test files (94 tests)
  cover the previously untested components (`Dialog`, `AppDialogs`,
  `InitScreen`, `FontSelector`, `ConfigSkeleton`,
  `SetSummaryActiveNotice`, `SetSummaryStylePicker`, `ShortcutsHelp`,
  `TeamCard`) and hooks (`useAsyncAction`, `useHudVisibility`,
  `useStaleSetPrompt`, `useShareLinks`). The vitest coverage
  thresholds ratchet accordingly: lines 72→82, statements 70→80,
  functions 57→69, branches 60→71.
- **Backend module decomposition; complexity lint gate now applies
  everywhere.** ``app/match_report.py`` (2,094 lines) is split into
  sibling modules — ``match_report_access.py`` (auth ladder),
  ``match_report_stats.py`` (pure audit-log reducers, now also the
  import home for ``app/api/live_stats.py``) and
  ``match_report_render.py`` (HTML/SVG builders) — leaving only the
  three routes in the original module. ``app/overlay/routes.py``
  likewise sheds its auth dependency (``app/overlay/auth.py``, still
  re-exported), locale resolution (``app/overlay/locale.py``) and
  Pydantic models (``app/overlay/models.py``), and registers routes
  through two helper functions. The over-complex functions
  (``_compute_stats``, ``_render_highlights``, ``_render_score_chart``,
  ``create_overlay_router``) were decomposed below the mccabe cap, so
  the two long-standing per-file ``C901`` suppressions in
  ``pyproject.toml`` are gone. No route paths, operation IDs or
  behaviour changed (OpenAPI snapshot is byte-identical).

- **Environment variable docs synced with the code.** Documented
  previously missing tunables across `README.md`, `.env.example` and
  `docker-compose.yml`: `METRICS_REQUIRE_ADMIN`, `STRICT_OID_ACCESS`,
  `CUSTOMIZATION_CACHE_TTL_SECONDS`, `MATCH_REPORT_PUBLIC_DELETE`,
  `MINIMIZE_BACKEND_USAGE`, `REMOTE_CONFIG_URL`, `WEBHOOKS_EVENTS`,
  `WEBHOOKS_TIMEOUT_S`, `WEBHOOKS_ALLOW_PRIVATE_IPS`, `APP_DEFAULT_LOGO`,
  `DEFAULT_TEAM_LOGO`, `OVERLAY_LOCALE`, `SET_SUMMARY_DEFAULT_STYLE`,
  `UNO_OVERLAY_ID` and `APP_RELOAD`. A new test
  (`tests/test_env_docs.py`) now fails CI whenever a backend env-var
  read is missing from the operator docs, so the lists can no longer
  drift.

### Removed

- **Dead `DEFAULT_HIDE_TIMEOUT` / `APP_DARK_MODE` startup validation.**
  Both env vars were validated and normalised at startup but never read
  anywhere else in the codebase (NiceGUI-era leftovers); the validator
  blocks and their tests are gone. Setting either variable was — and
  remains — a no-op.

## [5.5.0] - 2026-05-31

### Added

- **New `beach_twoline` overlay style.** A two-line variant of the beach
  board: each team's tall white score card sits on the outer edge and
  spans both of the two stacked name bars (home on top, away on bottom).
  Per team, from its own score outward to the centre, the bar reads
  sets (a large numeral) → logo → name. Expanded mode shows the team
  name only; simple mode (the operator's "show only current set" toggle)
  shows the logo only — or just the sets numeral when a team has no
  logo. Serving is shown by the coloured line decorating that team's
  score card (the card is otherwise fully white), and a short
  transparent "fade tail" on each bar's inner end (toward the other
  team's score) detaches it from the wrong card so the score↔bar pairing
  stays unambiguous even in the symmetric simple/no-logo case. Long names
  grow both bars symmetrically and shrink the font rather than truncating
  (shared measuring logic with the classic beach board). Auto-discovered
  by the overlay engine (`overlay_templates/beach_twoline.html` +
  `overlay_static/css/beach_twoline.css`), so it appears in the style
  picker and is selectable per overlay like any other style.
- **New `beach` overlay style.** A scoreboard layout tailored for beach
  volleyball, mirrored around the centre: the two teams sit on the left
  and right with their logos on the outer edges and their live scores
  toward the middle. The current-set score is rendered as two tall,
  raised white cards with large black numerals (a coloured cap ties each
  card to its team) — the focal point of the board — visually separated
  from the shorter team sections, which carry the team name (both name
  bars are a fixed equal width so the board stays symmetric), a compact
  sets-won badge, a sun-yellow serving indicator and timeout pips.
  Logos are optional. In simple mode (the operator's "show only current
  set" toggle) the team names are dropped and the sets-won counter is
  promoted onto the name line as a large numeral (no "SETS" label), with
  the timeout markers moved out beside the logo and stacked vertically to
  stay compact — keeping the big live-score cards as the focus. Auto-discovered by the
  overlay engine (`overlay_templates/beach.html` +
  `overlay_static/css/beach.css`), so it appears in the style picker and
  is selectable per overlay like any other style.

### Changed

- **Beach overlay: team-name bars now expand to fit the longest name (both sides symmetric) and shrink the font instead of truncating; the SETS label, timeout dots and serving indicator now use each team's name colour for contrast.**

### Fixed

- **Set-summary recap overlay overflowed with point-type stats.** The
  per-point breakdown was added to the recap as one stat row per type,
  which overran the fixed-size stat panels (services wrapped, the
  opponent-errors row was clipped off the bottom). It now renders as a
  bounded compact chip strip — short label + count per type, zeros
  dimmed, team-coloured, headed by the team logo — that can't overflow
  no matter how many types were tagged. Ledger/columns render it as a
  per-team strip under each column; bento/bumper as a two-row block
  below the core stats; glass as a full-width band spanning both tiles.

### Added

- **Per-point classification (opt-in scouting tags).** `POST
  /api/v1/game/add-point` now accepts an optional `point_type` (`ace`,
  `kill`, `block`, `opp_error`) and, for opponent errors, an optional
  `error_type` sub-classification (`serve_error`, `attack_error`,
  `reception_error`, `ball_handling`, `net_fault`, `position_fault`,
  `other`) — the latter is rejected (422) unless `point_type ==
  "opp_error"`. Tags ride along in the per-OID audit log `params`, are
  ignored on undo, and are fully optional (omitting them records an
  untyped point exactly as before). Live stats
  (`/api/v1/matches/live/stats`) and the printed match report now expose
  a per-team breakdown of point
  types, with opponent errors further broken down by cause; the report
  block is localized across all six supported locales. The match report
  additionally shows each type as a percentage of the team's points
  (point composition) and an "own errors" card attributing points given
  away to the faulting team (count, cause breakdown, and share of the
  opponent's points).
- **Control-UI point-type picker (opt-in).** Two new Behavior settings
  — "Track point types" and "Detailed opponent errors" (both off by
  default) — gate a score-button picker: with tracking on, tapping a
  team's score opens a quick chooser (ace / kill / block / opponent
  error / quick point), and with detailed errors on, an opponent error
  expands into a cause step (serve / attack / reception / ball-handling
  / net / position / other). The fast tap-to-score flow is unchanged
  when tracking is off. Tagged points show a compact glyph in the
  points-history strip. Picker labels are localized across all six
  locales.
- **Point-type stats on the spectator page and overlay recap.** The
  public `/follow/{id}` spectator page now shows a per-team breakdown
  (aces / kills / blocks / opponent errors) and a "last point" badge
  indicating how the most recent rally was won (including the error
  cause for tagged opponent errors). The set-summary recap overlay (the
  ledger, columns, bento, glass and bumper variants) shows the same
  breakdown scoped to the displayed set. All rows are gated to non-empty,
  so a match scored without tags is visually unchanged. The backend now
  ships `point_types_by_set` and `last_point` in
  `/api/v1/matches/live/stats` and the overlay broadcast. New labels are
  localized across all six locales.

### Fixed

- **Type errors surfaced by the wider `mypy` scope (below).** Bringing the
  whole package under the type checker exposed two genuine gaps that the
  old allowlist hid: a return-type widening in ``app/api/match_archive.py``
  (the heterogeneous payload dict widened the inferred return type — the
  ``match_id`` is now a typed local) and three numeric-vs-``None`` typing
  gaps in ``app/match_report.py`` (the streak/rally accumulator dicts and
  ``effective_duration`` now carry explicit annotations). No runtime
  behaviour changes.
- **Keyboard access for the scoreboard wake-handle and serve toggle.** The
  show/hide-controls handle (`ScoreboardView`) and the per-team serve icon
  (`TeamPanel`) were click-only `<div>`/`<span>` elements; they now expose
  `role="button"`, are focusable (`tabIndex`), carry an `aria-label` (and
  `aria-pressed` on the serve toggle), and respond to Enter/Space — so the
  controls are operable without a pointer. Both also gain a
  `:focus-visible` outline so keyboard focus is clearly indicated
  (WCAG 2.4.7).

### Changed

- **Config: the Behavior section was split into focused sections.** The
  single, long "Behavior" settings list is replaced by four top-level
  sections that plug into the existing accordion/sidebar navigation:
  **Display** (auto-hide, auto simple mode), **Statistics** (point-type
  tracking, detailed opponent errors), **Set summary** (recap overlay,
  default style, auto-show timing), and **General** (haptic feedback,
  keyboard shortcuts, language). Every individual setting is unchanged —
  only its grouping moved — so operators can scan and find options more
  easily. New section labels are localized across all six locales.
- **Live-stats are memoized against the audit-log version.**
  ``compute_live_stats`` reads and re-parses the entire per-OID audit log
  and runs ~9 aggregation passes over it. A single scoring action fans
  out to a control-UI state response, an overlay push, and one broadcast
  per connected client — each previously recomputing the identical stats
  from scratch. The result is now cached per OID keyed by a new
  ``action_log.version`` counter (bumped on every append / tombstone /
  clear / delete), so the work runs at most once per audit mutation and
  idle polling (spectator ``/live-stats``, control-UI ``/state``) hits
  the cache for free. No change to the returned values.
- **`mypy` now type-checks the whole `app` package + `main.py`.** Coverage
  was previously maintained as an explicit module-by-module allowlist;
  with the backend fully clean it is checked wholesale so new modules can
  no longer escape the gate silently. The conditional ``prometheus_client``
  import shim in ``app/metrics.py`` now carries explicit
  ``# type: ignore[…, unused-ignore]`` codes so it passes whether or not
  ``prometheus_client`` (and its real type stubs) is installed — CI has it,
  the pre-commit hook env does not.
- **Pinned `ruff` and `mypy` in CI to match the pre-commit hooks.** CI
  previously installed the floating "latest" of each while
  ``.pre-commit-config.yaml`` pinned much older versions, so local
  pre-commit and CI could disagree (the root cause of the type-check
  drift above). Both now run `ruff==0.15.8` / `mypy==1.19.1`; bumping
  them is a deliberate change that should land in its own PR.

### Documentation

- Corrected stale paths in ``AGENTS.md``: ``app/overlay_backends`` and
  ``app/api/routes`` are packages (directories), not single modules.
- Added a README screenshot (`docs/screenshots/11-point-type-picker.png`)
  of the opt-in per-point classification picker open over the
  scoreboard, plus a capture step for it in `scripts/screenshots/`. The
  capture pipeline now honours an optional `SCREENSHOT_CHROMIUM_PATH`
  to use a pre-provisioned Chromium where the managed-browser download
  is blocked.

## [5.4.4] - 2026-05-24

### Added

- **Auto-trigger set-summary recap on set end.** New operator opt-in in
  the Behavior section: when a set closes, the recap overlay appears
  automatically after a configurable delay (default 5 s, range 0–30) so
  the broadcast camera can linger on the players' reaction before the
  overlay covers them, then auto-dismisses after a configurable duration
  (default 15 s, range 5–60). The dismiss yields to live play
  immediately if a point lands in the next set, and the show is
  suppressed entirely if a point lands during the pre-show delay (the
  rally already resumed). Undoing the set-winning point clears any
  pending timers and force-hides the recap. End-of-match transitions
  show the recap but skip the auto-dismiss so the operator clears the
  final recap on their own.
- **Configurable abandoned-match prompt threshold.** The 1-hour
  stale-set detection that surfaces the "match looks abandoned" dialog
  on control-UI load is now configurable via the
  ``STALE_SET_THRESHOLD_MINUTES`` environment variable (default
  ``60``). Set it to ``0`` to disable the prompt entirely — long
  all-day tournaments can opt out without losing the dialog for
  shorter recreational matches. The frontend reads the value from
  ``GET /api/v1/app-config`` on boot, so changing the env var only
  needs a container restart (no client refresh required after that).

### Fixed

- **Per-set timeout history (closes the previous undo-across-set-
  boundaries limitation).** Timeouts used to live in a single per-team
  counter that was zeroed on every forward set transition, so undoing
  a set-winning point couldn't restore the prior set's timeout state.
  Storage now keeps a per-(team, set) array; ``State.get_timeout`` /
  ``set_timeout`` gain an optional ``set_num`` argument (defaulting to
  the current set, so existing call sites are untouched). ``add_set``
  no longer zeroes the counters — the new set starts at 0 naturally
  because no entry has been written yet, and the previous set's
  history survives. ``TeamState`` gains a ``timeouts_by_set`` field
  (current-set ``timeouts`` is preserved for backwards compatibility).
  Legacy state files using only the flat ``Team N Timeouts`` key load
  transparently: the legacy value lands in the current set's slot, and
  the next save writes the new per-set keys alongside.

### Dependencies

- Bump ``starlette`` from ``1.0.0`` to ``1.0.1`` to clear
  ``PYSEC-2026-161``. The runtime ``requirements.lock`` was also
  re-synced with the ``requirements.txt`` drift left over from
  v5.4.3 — ``uvicorn`` ``0.46.0`` → ``0.47.0`` and ``requests``
  ``2.33.1`` → ``2.34.2`` (both already advertised in the v5.4.3
  changelog as ``requirements.txt`` floor bumps; only the lockfile
  pins were stale).

## [5.4.3] - 2026-05-21

### Added

- **Set-summary overlay follows the operator's UI language live.** The
  OBS browser-source URL is fixed in the streaming app, so the
  ``?lang=`` strategy used by the spectator (follow) page cannot
  reach an embedded overlay once OBS is configured. The control UI
  now syncs the operator's locale onto the overlay's
  ``raw_remote_customization.locale`` whenever it changes, and
  ``set_summary.js`` re-reads ``window.OVERLAY_LOCALE`` on each
  WebSocket update — so the recap re-renders in the operator's
  chosen language without touching OBS. ``locale`` is also seeded
  into the served overlay HTML so the first render boots in the
  right language before any WS message arrives.

### Changed

- README badges refreshed (license / CI / Docker / React / TypeScript
  badges added, Python badge bumped to ``3.11+``) and the Prerequisites
  section now states Python 3.11+ explicitly.

### Dependencies

- Backend: ``uvicorn[standard]`` minimum bumped from ``>=0.46.0`` to
  ``>=0.47.0``; ``requests`` pinned from ``2.34.1`` to ``2.34.2``.
- Frontend: ``react-colorful`` from ``5.6.1`` to ``5.7.0``,
  ``@types/react`` from ``19.2.14`` to ``19.2.15``, and
  ``@vitest/coverage-v8`` from ``4.1.6`` to ``4.1.7``.

## [5.4.2] - 2026-05-20

### Added

- Unified overlay/API identifier validation in ``app/id_validation.py`` with
  cross-layer matrix tests.
- CI: Prettier format check on the frontend, Docker image build job, and
  shared ``CUSTOMIZATION_CACHE_TTL_SECONDS`` env knob for backend caches.

### Changed

- Split ``GameService`` broadcast/audit/rapid-pair helpers and the match
  report HTML shell into dedicated modules; ``require_admin`` now lives in
  ``app/auth_utils`` (overlay routes no longer import from admin).
- Frontend: dialog/modal UI extracted to ``AppDialogs.tsx``; locale strings
  moved to ``frontend/src/i18n/translations.ts``.
- Documentation: README/AGENTS/DEVELOPER_GUIDE aligned on bare overlay OIDs,
  lockfile-based installs, and current test counts; AUTHENTICATION.md §9
  documents secure-by-default operator choices.
- Regenerated README screenshots (spectator page, match report, set summary
  overlay, scoreboard phone view) to reflect the spectator/comeback fixes
  below.

### Fixed

- README troubleshooting no longer claims custom overlay IDs must use the
  legacy ``C-`` prefix.
- **Spectator page surfaced in the config Links section.** The follow
  URL was already in the HUD share dialog but missing from the config
  panel's Links list; it now renders alongside the other share links.
- **Spectator share links preserve the operator's locale.** Both the
  HUD share dialog and the config Links section now append
  ``?lang=<active-locale>`` to the follow URL, so a Spanish operator
  sharing the link no longer drops the spectator into English.
- **Comeback stat ends at the tie (spectator + match report).**
  ``perSetStreakAndComeback`` (spectator) and ``_compute_stats``
  (post-match HTML report) both clamp the post-peak deficit at ``0``
  so a team that recovered from ``-5`` to a tie reads as a 5-point
  comeback instead of continuing to count their subsequent lead as
  part of the recovery. Matters most for a losing side that briefly
  took the lead mid-set.
- **Spectator streak/comeback rows show both teams' max.** ``Racha``,
  ``Racha más larga`` and ``Remontada`` now render per-team values
  side by side instead of collapsing to only the leading team's
  number. The longest-streak row is suppressed when it would only
  repeat the same number already shown one row up under ``Racha``.

### Removed

- Unused ``MatchFinishedError`` exception in ``game_service``.

## [5.4.1] - 2026-05-18

### Changed

- **Original overlay — larger score digits.** Bumped the font size of
  the three number cells (current points, sets won, set history) from
  ``18px`` to ``28px`` via a dedicated ``--score-font-size`` CSS
  variable so the score reads clearly on stream. Team name keeps the
  existing ``--font-size``. Cell width nudged from ``40px`` to ``44px``
  to comfortably fit two-digit scores at the new size. The set-history
  GSAP animation in ``overlay_static/js/app.js`` now reads the
  ``--cell-w`` CSS variable from the container instead of a hardcoded
  ``40``, so the grow-in transition stays in sync with whichever
  overlay style is rendering.

## [5.4.0] - 2026-05-17

### Added

- **Set summary overlay (opt-in).** New operator-toggled overlay that
  replaces the scoreboard between sets with a recap panel — chart of
  the point progression, score, duration and key stats. Six visual
  styles ship as candidates (``brand_ledger``, ``brand_columns``,
  ``bento``, ``glass``, ``podium``, ``bumper``), all fully
  implemented end-to-end (per-variant HTML markup in
  ``overlay_static/js/set_summary.js`` + scoped CSS in
  ``overlay_static/css/set_summary.css``, ported from
  ``docs/mockups/set-summary/*.html``). Two more variants
  (``split_screen`` and ``jumbotron``) were prototyped during the
  cycle and dropped before merge for being visually weaker than
  the rest. The panel renders into a centred 16:9 stage sized to
  roughly two thirds of the viewport height (with equal margins
  above/below) — fully transparent over the live stream so only
  the data regions get ``rgba()`` fills + ``backdrop-filter:
  blur(…)`` and any OBS scene underneath stays legible. Chart-
  based variants generate their SVG polylines from the live
  ``points_by_set`` payload (not hard-coded mockup data). Wired
  end-to-end: new endpoints ``POST /api/v1/display/set-summary
  {,-style}``, payload fields ``match_info.{show_set_summary,
  set_summary_style,summary_set_num}`` picked up by
  ``set_summary.js``, plus a React control button (icon
  ``summarize``), centre-panel "Set summary is live" notice with
  inline style picker, and matching i18n strings in all six
  locales. A WCAG-aware ``resolveTeamColour`` helper falls back to
  a saturated mockup-palette accent when an operator's team
  ``color_primary`` is too close to white, so the variants that
  paint a full coloured panel (glass score tile, podium pillar,
  brand columns) don't render white-on-white. **Off by default**:
  the feature lives behind a ``setSummaryEnabled`` toggle in the
  Behavior config section so existing setups don't get a surprise
  extra button. Mockup gallery for the six styles lives at
  ``docs/mockups/set-summary/index.html``.

- **Set-summary variants now scale with the stage, not the
  viewport.** The 149 ``clamp(min, X vw, max)`` rules across the
  six variant stylesheets had their ``vw``/``vh`` swapped for
  ``cqw``/``cqh`` (with ``container-type: size`` added to the
  ``.ss-stage``) and their pixel minimums halved. With the old
  setup the "ideal" term of ``clamp()`` bottomed out at its pixel
  floor on small viewports, so a 480p preview kept full-HD font
  sizes while the stage itself shrank — team names wrapped onto
  three lines, ledger chips overflowed, scores cramped against
  the column edges. Switching the scaling unit makes the inner
  content track the stage size (which is itself derived from the
  viewport via ``min(95vw, calc(67vh * 16/9))``) so every variant
  preserves its proportions and information density at 480p,
  720p and 1080p alike.
- **Cross-fade between scoreboard and set-summary recap.** The
  scoreboard → recap toggle used to be an instant DOM swap
  (``display: none`` slammed the scoreboard, ``hidden`` attribute
  slammed the recap panel). Both surfaces now animate via a 450ms
  ``opacity`` transition and keep their layout slot at all times,
  so flipping the toggle produces a real cross-fade. The set-
  summary panel manages its own ``opacity`` + ``pointer-events``
  via inline styles so the transition has a guaranteed "from"
  value when the panel is freshly created on the very first
  activation.
- **Quieter INFO log level.** Restructured per-call-site levels so
  ``LOGGING_LEVEL=info`` gives a readable picture of what the
  server is doing without drowning the operator in per-request
  noise. Successful (HTTP 2xx / 3xx) ``uvicorn.access`` records
  are demoted to ``DEBUG`` by the
  ``HealthEndpointFilter`` — only client / server errors surface
  at the default level, but the full access log comes back when
  the operator enables ``DEBUG``. Per-interaction routes (display
  toggles, session-reuse, customization saves, visibility
  changes, per-broadcast 2xx response logs in
  ``Backend.process_response``) and routine WS client/handshake
  events also drop to ``DEBUG``. One-shot lifecycle events
  (server boot, overlay create/delete/copy, theme applied,
  preset created/deleted, WS heartbeat startup, WS zombie
  eviction, session expiry, ``WSControlClient`` start/stop)
  stay at ``INFO``.
- **"Match looks abandoned" prompt on control-UI load.** When the
  operator opens the React control UI on a session whose current
  set has been live for more than an hour, a confirm dialog now
  surfaces asking whether to reset the match (the scoreboard
  was probably left running by mistake) or keep going. Fires
  once per page load — refusing it doesn't re-trigger on the
  next WS broadcast. Backed by a new ``current_set_started_at``
  timestamp on ``GameStateResponse``, derived from the first
  scoring event of the operator's current set.

### Removed

- **Live-stats panel and points-history strip dropped from the
  in-broadcast overlay.** The two opt-in widgets used to sit on
  top of the live scoreboard in the OBS browser source. Their
  config toggles had already been removed from the operator UI,
  and stale ``show_stats`` flags persisted on existing overlays
  would still surface the panel — which on every non-``original``
  variant rendered as raw black text in the top-left corner
  because each variant's CSS (``pill.css``, ``ribbon.css``, …)
  never carried the rules for ``.live-stats-panel`` or
  ``.points-history-strip``. The elements are gone from
  ``overlay_templates/base.html`` so the live broadcast shows
  only the scoreboard (or the set-summary recap when activated).
  The same stats keep flowing in ``overlay_control.stats`` for
  the spectator (``/follow/{id}``) page and the set-summary
  recap, both of which already render them through their own
  markup.

### Dependencies

- Bump `vite` from 6.4.2 to 8.0.13 and `@vitejs/plugin-react` from
  4.7.0 to 6.0.2 in `frontend/`. The two upgrades are coupled because
  `@vitejs/plugin-react@6` requires `vite@^8` as a peer, so neither
  Dependabot PR (`#319`, `#320`) could land alone — they must ship
  together. `vite-plugin-pwa@1.3.0` and `vite-plugin-compression2@2.5.3`
  already advertise vite 8 compatibility.

### Fixed

- **Set summary clock now ticks every second on a live set.** The
  server-computed ``set_durations`` only refreshes when a new
  audit event lands (each point triggers a broadcast), so the
  duration shown in the recap panel used to visibly freeze
  between rallies. ``set_summary.js`` now anchors a client-side
  ``setInterval`` to the first scoring event's timestamp and
  updates every node tagged with ``data-live-duration`` once per
  second. The tick stays disabled when the displayed set has
  already finished (recap shown during a set break or after match
  end), so the rendered total never climbs past the real set
  length.
- **Set summary recap no longer pins to an unplayed set after
  historical edits.** When the operator backfills earlier sets via
  ``set_score`` after advancing the match, those audit records get
  tagged with ``result.current_set`` and a running score of ``[0,
  0]`` for the active set. Both the resolver
  (``GameService._resolve_summary_set`` / the backend broadcast)
  and the overlay's ledger renderer now ignore ``set_score`` events
  when deciding "did this set actually see a rally?" — so the
  recap rolls back to the previously played set, and the in-set
  ledger no longer renders ghost ``0`` chips.
- **Team-coloured icons stay readable on the panel surface.** The
  timeout dots, timeout button, serve icon, and points-history
  marker in the React control UI now run their colours through a
  WCAG-aware helper that lifts (or lowers) the HSL lightness only
  when the contrast against the current ``--surface`` falls below
  the threshold (4.5:1 for text/icons, 3:1 for UI shapes). The
  hue and saturation are preserved so the two teams remain
  visually distinct, and the helper re-evaluates automatically on
  light/dark theme toggles. The default indigo accent
  (``#5c6bc0``) — which only reached 3.27:1 against the dark
  navy panel — is now lifted to a tone that clears 4.5:1 on dark
  mode while staying recognisably indigo.
- **Match timer no longer ticks past match end.** The HUD timer in
  the React control UI and the match/set counters on the
  `/follow/{id}` spectator page now freeze at the actual end-of-
  match value as soon as the set-winning point or set lands,
  instead of continuing to count up until the operator reloads.
  Backed by a new ``match_finished_at`` timestamp on
  ``GameStateResponse`` and on the overlay broadcast payload's
  ``match_info`` block.
- **Spectator page now shows a "match finished" indicator.** Once
  the match transitions to finished, the alerts strip renders a
  localized ``Match finished`` / ``Partido finalizado`` badge and
  hides the now-stale set-point / match-point / side-switch pills.
  The match/set timer pill also tints green to make the frozen
  state visually distinct from a paused-between-rallies live
  match.
- **Reset on the operator UI now clears the spectator's stats and
  time history.** The overlay state-store deep-merge previously
  left per-set entries in ``overlay_control.points_by_set`` /
  ``timeouts_by_set`` / ``stats.set_durations`` behind because an
  empty dict from the post-reset broadcast is a no-op for a deep
  merge. The store now force-replaces those audit-derived
  subtrees on every update so a Reset wipes the spectator chart,
  history, and per-set durations alongside the scoreboard.
- **Bumper score digits no longer kiss the team-block edges.** The
  oversized scores in the ``bumper`` set-summary variant were
  rendered flush against the home/away team block borders (``align-
  items: flex-start`` / ``flex-end`` with no horizontal padding),
  and the 20px drop-shadow blur on each digit was being clipped by
  the ``.ss-bumper-core`` ``overflow: hidden``. Both digits now sit
  on ``clamp(4px, 1.4cqw, 16px)`` of internal padding, the negative
  letter-spacing was relaxed from ``-0.06em`` to ``-0.04em``, and
  the drop-shadow blur was tightened so the glyphs read fully
  even at 480p.
- **Chart polylines stay distinguishable when both teams share a
  colour.** When the operator picks near-identical primaries (e.g.
  two navy clubs), the home and away polylines used to overlap
  into a single confused trace. A weighted RGB-distance check in
  ``set_summary.js`` now flags ``colorsAreSimilar`` pairs (≈80
  units, captures same-hue/lightness variants) and tags the away
  polyline with a ``ss-line-away--dashed`` class so CSS renders
  it as a dashed stroke — preserving the colour intent while
  keeping the two series readable.
- **"Final" pill no longer lies when the recap is shown mid-set.**
  The ``glass`` and ``brand_columns`` headers hard-coded a green
  "Set N · Final" pill regardless of whether the displayed set had
  actually concluded. Now ``deriveViewModel`` exposes a
  ``setFinished`` flag (true only when the team's ``set_history``
  has a final score recorded for that set) and the renderers swap
  to an amber ``Set N · Live`` pill with a pulsing indicator when
  the set is still in play. Green/Final stays for sets the backend
  has actually closed.

### Changed

- **``match_started_at`` is no longer cleared when a match is
  archived.** The session keeps the start anchor in place after
  match end so the HUD timer and the spectator page can render the
  final elapsed duration (``match_finished_at - match_started_at``)
  until the operator hits Reset — which is now the only path that
  returns the session to the pre-match idle state.

## [5.3.0] - 2026-05-13

### Added

- **Live stats + points-history in the overlay WebSocket broadcast.**
  Every overlay state push now carries a stats summary (current
  streak, longest streak, partial comeback, total points) and a
  30-point trajectory in `overlay_control.stats` and
  `overlay_control.points_history`. The two per-overlay Config-panel
  toggles ("Show live stats" / "Show points history") gate whether
  the OBS overlay app.js *renders* the panels (default OFF so
  existing overlays look unchanged after upgrade); the data itself
  is always present so the `/follow/{id}` spectator page and other
  consumers can read it regardless of operator display preferences.
  The data is computed from the per-OID audit log via the new
  `app.api.live_stats.compute_live_stats` helper, so the live
  numbers reconcile with the printed match report — no second
  source of truth to drift.
- **`GET /api/v1/matches/live/stats?oid=X&limit=N` endpoint.**
  Returns the same stats payload powering the overlay panel, plus
  per-set durations and the longest-rally proxy. External
  integrators (coach apps, dashboards, secondary panels) can read
  the live report block without polling the audit log directly.
- **Public spectator page at `/follow/{overlay_id}`.** Mobile-first
  read-only follow view that consumes the same `/ws/{output_key}`
  feed as the OBS templates. Surfaced via the operator's share
  dialog (`/api/v1/links` now returns a ``follow`` URL alongside
  control / overlay / preview) so the operator never has to
  hand-build the URL. Resolves by either the raw overlay id or
  its short output key and is excluded from the PWA
  ``navigateFallback`` denylist so a shared URL hits the backend
  Jinja route instead of the SPA shell. Marked
  ``noindex,nofollow`` so the page doesn't leak into search
  engines.
  - **Serve indicator** is an absolutely-positioned pulsing
    volleyball icon docked at the inner edge of the serving
    team's cell (toward the centre divider). Position is fixed,
    so toggling the indicator no longer reflows the layout the
    way the previous under-name badge did.
  - **Set progression chart** has explicit per-team stroke
    colours pulled from the brand palette (no
    ``currentColor`` collapse), a dark plot background
    distinct from the surrounding panel, and dashed grid lines
    with high-contrast tick labels. Up to 5 evenly-spaced Y
    ticks render the running score scale, deduped when the set
    is fresh so the axis never repeats ``0``. The X axis is
    real-time elapsed (``m:ss`` labels at start / mid / end)
    so long sideout streaks and short ace bursts occupy
    visibly different spans. Each scoring event is marked
    with a team-coloured dot; each timeout is a dashed
    vertical line in the calling team's colour with a small
    ``T`` badge at the top.
  - **Scoreboard timeouts indicator.** Two pip dots per
    team next to the sets counter fill in as the operator
    burns timeouts (FIVB max 2/set), so the viewer reads
    available timeouts at a glance.
  - **Serve ball** shrunk so it lives comfortably inside the
    team cell without crowding the score.
  - **Live stats reordered** with total points first, plus a
    new ``Services won`` row showing services-won / served per
    team derived from the audit log's serve transitions.
  - **Set-point / match-point indicator.** A pulsing badge on
    each side of the alert strip flags when the next point
    would close out the set or the entire match. Match point
    takes visual priority over set point on the same side.
  - **Beach side-switch indicator.** A central yellow badge
    counts down points until the next mandatory side switch
    ("Cambio en 2 pts"), flipping to a pulsing
    "Cambiar de campo" the moment the boundary lands. Only
    surfaces for beach mode (indoor uses a client-side
    deciding-set midpoint alert in the operator UI). The
    countdown is driven by ``compute_side_switch`` so it
    matches what the operator sees.
  - **Match-rules quick-reference badge** in the header
    ("Beach · Best of 3 · 21 · 15 in deciding set ·
    Side switch every 7 pts") so a viewer can confirm the
    ruleset without leaving the page.
  - **Scoreboard centre column** now hosts the shared
    indicators (both teams' set wins as a single ``2 – 1``
    pair at the top, with the current ``SET N`` pill pushed
    lower toward the score line). Per-team meta rows dropped
    the redundant "Sets X" label — only the timeouts pips
    remain there — so the central column has visible content
    instead of empty vertical space. The serve indicator
    inside each team cell slid from the column's mid-line
    down to ``top: 64%`` so the volleyball icon lines up with
    the score the viewer is reading rather than floating over
    the team name.
  - **Per-team stats grid.** The stats panel is now a 3-column
    layout (home value · label · away value) instead of single
    rows that mixed team names into the value text. Total
    points are split per team (summed from ``set_history``
    rather than the audit aggregate). Services-won, current
    streak, longest streak and partial comeback render in the
    column of the team they belong to; the opposite column
    shows a muted "—". Rows where neither team has data
    collapse via ``data-empty="true"``.
  - **Chart colour-collision fallback.** When both teams'
    primary colours are within ~60 RGB units the chart's away
    line switches to a high-contrast fallback (mirroring the
    print report's ``_ensure_distinct_chart_colors``) AND
    picks up a dashed stroke pattern, so even pathological
    cases (two reds + a red fallback) still render as two
    distinct traces. The legend swatches mirror the resolved
    colours.
  - **Alert badges use fixed semantic colours.** Set point is
    amber (warning), match point is red with a pulsing glow
    (critical), side-switch is amber (info / pulses when
    pending). Team affiliation is implicit from the alert
    strip's three-column grid (home left, switch centre, away
    right) so the team colour is no longer needed inside the
    badge — matches the React control UI's chip palette.
  - **OID is no longer rendered into the spectator HTML.**
    The page title, footer line and ``window.OVERLAY_TARGET_ID``
    now omit the raw overlay id (it's the secret an operator
    types into the control UI). Only the SHA-derived
    ``output_key`` reaches the browser. The route's
    ``test_follow_*`` regression suite was updated to assert
    this invariant.
  - **Per-set streak, longest streak, and comeback.** The
    stats panel rescopes these to the *viewed* set instead of
    the whole match, computed client-side from
    ``overlay_control.points_by_set`` so the panel
    recomputes when the viewer steps through previous sets.
  - **Page title is i18n'd.** The Jinja template emits a
    neutral English ``<title>`` for crawlers/share previews;
    the spectator JS replaces ``document.title`` with the
    localised version once the language is resolved.
  - **Set + match elapsed counters** in the page header
    (between the rules badge and the connection status) as a
    single inline pill ``MATCH 1:24 · SET 0:32``. Match clock
    ticks live from the new ``match_info.match_started_at``
    field in the broadcast; the set clock derives from the
    viewed set's audit timestamps and adds the wall-clock
    delta when the viewed set is the live one. A 1 Hz
    ``setInterval`` re-renders only the two text nodes so
    the counters move between rallies. Past sets render
    their frozen duration from ``stats.set_durations``.
    Format auto-switches to ``H:MM:SS`` once a counter
    crosses the hour mark; the timer pill reserves enough
    width for that longer string so the layout doesn't
    reflow every second past 60 min.
- **README screenshot for the public spectator page.**
  ``scripts/screenshots/capture.mjs`` now drives a phone-portrait
  full-page capture of ``/follow/{id}`` against the demo overlay,
  written to ``docs/screenshots/09-spectator-page.png`` and embedded
  in the README screenshot grid. The capture pipeline also seeds
  ``volley_gestureTourSeen=true`` via ``context.addInitScript`` so
  the first-use gesture coachmark does not cover the scoreboard /
  config-panel shots after upgrade.

### Changed

- **Backend rules hook is now an explicit setter.** Replaced the
  monkey-patched ``backend._rule_overrides_getter = ...`` from
  ``GameSession.__init__`` with ``Backend.set_rule_overrides_getter``
  so the dependency is part of Backend's public surface. Addresses
  Gemini's coupling concern from the PR review.
- **Defensive ``except Exception`` blocks in
  ``_build_overlay_payload`` and the ``/links`` route now log via
  ``logger.exception`` so the full traceback reaches operator
  logs instead of just the exception's repr.
  - **Backend rules hook.** ``GameSession`` now exposes its
    live mode + per-set limits via a getter the Backend's
    overlay-payload builder consults on every broadcast, so
    the OBS-side WS stream carries the actual session rules
    instead of falling back to env-default ``conf`` values
    (which can diverge after the operator edits rules from
    the React control UI).
  - **Set navigation** lets the viewer step back through past
    sets via prev / next buttons or by clicking any cell in the
    set-history table. The chart freezes on the chosen set
    until the operator advances back to "live"; the active set
    is highlighted in the history table and the header reads
    ``Set N · live`` when tracking the current set.
  - **Per-set data** is now broadcast as
    ``overlay_control.points_by_set`` (full per-set arrays,
    capped at 60 events per set) so the spectator chart can
    render historical sets without a second fetch. The
    existing ``points_history`` (last-30 flat list) is
    preserved for the OBS overlay strip.
  - **Internationalisation:** every string on the spectator
    page is translated for en / es / pt / it / fr / de. The
    page reads the locale from ``?lang=`` first, then
    ``navigator.language``, then falls back to English.
  - The previous bottom "points trajectory" chip strip was
    removed: the set-progression chart covers the same
    information with context (which set, what scale, who's
    leading).
- **Keyboard shortcuts for the operator.** New `useKeyboardShortcuts`
  hook + `ShortcutsHelp` dialog covering the high-frequency
  actions: `A` / `B` add point, `Z` undo, `1` / `2` change serve,
  `Q` / `P` timeout, Space start match, `H` toggle overlay
  visibility, `S` toggle simple mode, `?` open the help cheatsheet.
  Defaults ON for fine-pointer devices (mouse + keyboard), OFF for
  coarse-pointer (touch-only) so the screen keyboard on tablets
  doesn't score phantom points. Toggleable from the Behavior
  section of the Config panel, and disabled while any modal /
  text input owns focus so it never fights the existing dialog
  flow. Translated into the six supported UI languages.

### Changed

- **Recent-actions strip now skips all undo records.** The strip is
  redefined as a pure "current state activity" indicator: it only
  renders chips for actions that still contribute to the live
  score (`point_add`, `set_won`, `match_won`, `timeout`, `manual`).
  Undo records (`point_undo`, `timeout_undo`) and the synthetic
  state-diff undoes (`set_undo`, `match_undo`) no longer surface,
  because the matching forward chip was tombstoned by
  `pop_last_forward` and a floating struck chip has no visible
  counterpart to invalidate. Operators can still consult the
  history drawer and the printable `/match/{id}/report` for the
  full forensic timeline, which keep showing undone actions as
  struck rows. As a consequence: clicking team A, then team B,
  then double-tap-undo on team A (>5 s after the click) now leaves
  the strip showing only `[+1 B]` — no orphan `-1` chip.
- **Internal cleanup.** Removed unused legacy `Backend` pass-through
  methods and the unreferenced `PasswordAuthenticator.compose_output`
  helper. Consolidated four duplicated truthy-env parsers into
  `EnvVarsManager.get_bool_env` / `is_truthy`, and the
  `_data_dir`/`_hashed_basename`/atomic-JSON-write idioms scattered
  across `app/api/*` + `app/overlay/state_store.py` into a new
  `app/api/_persistence_paths.py`. Auth helpers in `app/auth_utils.py`
  now expose shared `extract_bearer_token` and
  `get_hashed_or_plaintext_env` helpers used by the admin and
  overlay-server credential paths. No observable behavior change;
  full `pytest` (1019), `ruff`, `mypy`, and `vitest` (415) suites
  remain green.
- **Recent-actions strip rewritten as a pure projection of the
  tombstone-filtered audit log.** Dropped the `priorEventsRef`
  stickiness buffer in `useRecentEvents` and the
  `INVERSE_UNDO_KIND` suppression heuristic that went with it.
  Every fetch now fully replaces the chip list, so rapid-pair
  collapses (forward + undo within 5 s ⇒ audit empty), generic
  undoes, and resets all converge to the same view the history
  drawer and printable report render. Side-effects of the rewrite:
  * Rapid-pair Case A no longer leaves a ghost "alive" chip in
    the strip after the pair is collapsed at the audit level.
  * Chronological ordering is guaranteed by audit `ts` (server
    monotonic per-OID); the synthetic state-diff set/match-undo
    chips are anchored above the last audit chip, so they always
    render rightmost.
  * The strip no longer recovers chips that age out of the audit
    fetch window — but at `max(40, max*3) = 40` fetched and the
    strip capped at `max = 8` visible, aging out would require
    >32 intervening chips, which doesn't happen in practice.

### Fixed

- **Undo button no longer lags one action behind.** The
  `ActionResponse.state.can_undo` flag that the WebSocket broadcast
  and the HTTP reply carry now reflects the *post-action*
  `undoable_forward_count` for `add_point`, `add_set`,
  `add_timeout`, and `reset`. Previously `state_response` was
  captured before `_audit` bumped the counter, so the very first
  forward action broadcast `can_undo=false` (the undo button stayed
  disabled until the second action), and the final undo back to
  zero broadcast a misleadingly enabled button. The state response
  is now computed *after* the audit append in all four paths.
- **Recent-actions strip clears on match reset even when scores
  stayed at zero.** `scoringKey` in `useRecentEvents` now includes
  `match_started_at`, so a reset that lands on already-zero scores
  (typical after an operator undid everything back to 0:0) still
  refires the audit fetch, triggers the `matchBoundary` cleanup of
  `priorEventsRef`, and lets the empty audit log surface an empty
  strip. Previously the leftover undo chips lingered until the next
  scoring event changed the numeric portion of the key.
- **Recent-actions strip now drops the "alive" chip on undo** so it
  matches how history (`RecentAuditDrawer`) and the printable
  `/match/{id}/report` render the same event. Previously, when the
  preview was hidden and the operator undid an action, the strip
  surfaced both the original chip *and* the struck/undone chip side
  by side, even though the audit-backed views only show the undone
  entry once `pop_last_forward` tombstones the forward record. The
  classifier no longer synthesizes a forward `timeout` chip from
  the post-state diff for popped records, and the recovery buffer
  in `useRecentEvents` now suppresses any prior chip whose undo
  counterpart (point/timeout/set/match) is present in the fresh
  fetch or the snapshot diff.

## [5.2.0] - 2026-05-10

### Added

- **Cross-navigation between Config and `/manage`.** The config
  panel's top bar now shows a `dashboard` button on the right
  (mirroring the back-arrow on the left) that links to `/manage`,
  and the Custom Overlay Manager header gains a back-arrow on the
  left of its title that returns the operator to the scoreboard.
  Both surfaces previously required typing the URL by hand.
- **Rapid-pair undo correction (5 s window).** Two opposite
  ``add_point`` actions on the same team within
  ``RAPID_PAIR_WINDOW_S`` (5 s) now collapse to a no-op at the
  audit-log level — neither half surfaces in the report, the
  post-match drawer, or the live history strip. Both directions
  are handled:

  * **Case A** — tap to score, then double-tap-undo within 5 s:
    the just-added forward is tombstoned and no undo record is
    appended. Net audit: nothing for the pair.
  * **Case B** — double-tap-undo, then tap within 5 s: the
    fresh undo record is tombstoned and the forward the undo
    had originally hidden is **restored from its tombstone** via
    a new ``_restore`` audit marker so the timeline keeps the
    original ts. Net audit: as if neither the undo nor the
    recovery happened.

  Outside the 5 s window the actions remain separate (legacy
  unified-undo flow). On a different team the cache stays per-
  team so a deliberate forward on team 2 can't accidentally
  pair with a stray double-tap on team 1. Any non-``add_point``
  mutation (``add_set``, ``add_timeout``, ``change_serve``,
  ``set_score``, ``set_sets_value``, ``reset``) invalidates the
  cache so a follow-up tap can never trigger a false-positive
  recovery. State-level effects (set-end / match-end / serve-
  change webhooks) still fire on the recovery side — the
  underlying state transition really happened (the operator
  briefly closed the set, then reopened it).

  Implementation:

  * New ``RAPID_PAIR_WINDOW_S = 5.0`` module constant on
    ``app/api/game_service.py``.
  * New ``GameSession.rapid_pair_cache: dict[int, dict]`` —
    per-team trace of the most recent ``add_point`` (kind, ts,
    audit_ts, optional popped_ref_ts) used to detect the pair
    on the next call.
  * New ``action_log.tombstone_ts`` and
    ``action_log.restore_popped`` helpers plus
    ``_RESTORE_TOMBSTONE_ACTION = "_restore"``.
    ``_apply_tombstones`` now processes ``_pop`` and ``_restore``
    together so a restore cancels an earlier pop with the same
    ``ref_ts``. ``action_log.append`` returns the written record
    so the caller can capture its assigned ``ts`` for the cache.
  * ``GameService.add_point`` consults
    ``_consume_rapid_pair`` before the normal pop / state-mutate
    / audit-append cycle. On a rapid hit the audit half is
    handled by the cache (no ``_audit`` call); on a miss the
    seed is refreshed via ``_record_rapid_pair_seed``.

  Tests: 11 new in ``tests/test_rapid_pair_undo.py`` covering
  Case A collapse, Case B recovery (with mocked time so the
  prior forwards lie outside the window), different-team
  isolation, every cache invalidation path, and a set-winning
  recovery that re-advances ``current_set``. Pre-existing
  legacy-unified-undo tests (``tests/test_undo_stack.py``,
  ``tests/test_action_log.py``, ``tests/test_undo_unification
  .py``) were updated to mock time past the rapid-pair window
  so they continue exercising the legacy path. Full backend
  suite: 1021 passed (was 1009 + 12 new).

### Changed

- **Unified preset picker — env-driven themes now live alongside
  user-saved presets.** ``APP_THEMES`` entries used to surface as
  a separate "Preloaded Config" dropdown inside the Overlay
  section; user-saved presets lived in their own Presets section.
  Both selectors did exactly the same thing on click — shallow-
  merge the chosen patch into the in-memory edit model and wait
  for the operator to hit Save — but they looked and were located
  differently, so operators had to remember which selector held
  what. ``GET /api/v1/customization/presets`` now returns both
  sources in a single list, with a new ``source: "user" |
  "system"`` field on each ``PresetSummary``. System entries are
  derived from ``APP_THEMES`` at request time, are sorted first
  in the picker, render with a "System" badge, and have no
  delete button. The ``DELETE`` endpoint rejects any slug
  starting with the reserved ``system-`` prefix with a 403, and
  ``presets_store.slugify`` refuses to derive a user slug that
  collides with that prefix. The picker's action button is
  renamed from "Apply" to "Load" (and its translations: Cargar,
  Carregar, Carica, Charger, Laden) to reflect that the click
  stages the configuration without persisting — the existing
  Save button at the bottom of the panel is what writes to the
  backend. The redundant "Preloaded Config" dropdown and the
  ``overlay.preloadedConfigLabel`` / ``overlay.selectAndLoad``
  i18n strings are gone.

- **Match report comeback highlight split into "set-winning" and
  "partial" cards with new thresholds.** Used to: a single
  "Biggest comeback" card surfaced any deficit ≥ 2 pts erased by
  the eventual set winner — so a team that briefly trailed 0-2
  before cruising to 25-10 was still credited with a "comeback".
  Now:

  * **Biggest set-winning comeback** renders only when the erased
    deficit is **5 pts or more**, suppressing the trivial 2-4
    point swings that aren't really comebacks.
  * **Biggest partial comeback** is a new card that surfaces the
    largest deficit *reduction* (peak deficit minus the smallest
    subsequent deficit) achieved by a team that ultimately *lost*
    the set — useful for spotting near-comebacks. Threshold
    `> 3 pts` so a one-rally swing doesn't qualify.
  * When team 1 and team 2 share the same maximum on either card
    the value collapses to the magnitude alone and the per-team
    detail is replaced by "Tied between both teams" rather than
    arbitrarily picking one side.

  ``_compute_stats`` now returns ``set_win_comeback`` and
  ``partial_comeback`` per-team dicts (replacing the old
  single-team ``biggest_comeback``); ``_render_highlights``
  combines them with the new tie-detection logic. New i18n keys
  ``highlightPartialComeback``, ``partialDeltaValue`` and
  ``comebackTie`` across all six locales (en/es/pt/it/fr/de),
  and ``highlightComeback`` rewords to "set-winning". Pinned by
  six new tests in ``TestMatchReportComebacks`` covering the
  per-card threshold, the team-credited side, and both tie paths.

- **Match report timeline drops both halves of every ``undo``
  pair.** Used to: undo records were rendered as a struck-through
  line carrying an "↶ Undone" badge — visible but visually noisy.
  Now: ``_collapse_undos`` removes both the forward action and
  its undo so the timeline reads "as if the undone action never
  happened". Live unified-undo logs already had this shape (the
  forward was popped physically, leaving an orphan undo we
  dropped); legacy paired logs now collapse the same way.
  Removed: ``.undone`` / ``.undone-badge`` / ``.chip-undone``
  CSS, the ``undone`` entry in ``_CHIP_CATALOGUE``, the
  ``was_undone`` parameter on ``_chip_classifier``, and the
  ``undo`` / ``undoneBadge`` / ``legendUndone`` i18n keys across
  all six locales. Existing legacy tests
  (``test_undo_collapses_to_strikethrough``,
  ``test_undone_rows_carry_visible_badge``) replaced with
  ``test_undo_pairs_disappear_from_timeline`` and
  ``test_no_undone_artefacts_in_rendered_html`` that pin the new
  invisibility invariant. The frontend live operator drawer
  (``RecentAuditDrawer``) is unchanged: it still surfaces undo
  records as their own rows because that surface is a transcript
  of operator actions, not a final-state report.

- **Match-report set-by-set table grows a "Timeouts (T1/T2)"
  row.** The per-set timeout count was already shown inline as
  ``25 (2)`` next to the score, but the suffix is easy to miss
  on dense matches. The new row sits below "Set durations" and
  spells out both teams' counts side-by-side as ``2/0`` /
  ``0/1`` / ``—``. Reuses the existing ``_timeouts_per_set``
  audit reducer so a coach can scan timeout usage per set
  without trawling the timeline. New i18n key ``timeoutsRow``
  across all six locales (en/es/pt/it/fr/de). Pinned by
  ``test_set_byset_table_has_per_set_timeouts_row`` and the
  existing ``test_set_score_cell_appends_timeout_count`` was
  extended to assert the new row alongside the inline suffix.

  Full suites: backend 1008 passed, frontend 405 passed.

### Removed

- **``GET /api/v1/themes`` is gone.** ``APP_THEMES`` is now
  surfaced exclusively through the unified
  ``GET /api/v1/customization/presets`` endpoint with
  ``source="system"``. The frontend ``api.getThemes()`` helper is
  removed; the env var itself is unchanged. (The unrelated
  ``GET /api/themes`` endpoint that lists overlay-template render
  themes — used by the in-process overlay engine — is unaffected.)

### Fixed

- **Rapid-pair recovery could hide its own restored forward in the
  report.** Two follow-ups to the rapid-pair undo flow shipped in
  the previous release:

  * ``GameService._invalidate_rapid_pair_cache`` is now also called
    by ``set_rules`` and ``start_match`` (the docstring already
    listed ``set_rules``; the implementation in those methods was
    missing). A rule change or an explicit match start now wipes
    any stale per-team rapid-pair seed so a follow-up tap cannot
    trigger a false-positive recovery against an unrelated forward.
  * **Case B recovery** now gates ``action_log.restore_popped`` on
    the success of ``action_log.tombstone_ts``. Previously the
    restore ran unconditionally, so a failed undo-tombstone left
    the audit log in a state where the orphan undo was still
    visible alongside the restored forward; ``_collapse_undos`` in
    the match report would then pair the two and hide both,
    defeating the recovery. The counter bump (``undoable_forward_count
    += 1``) follows the same gate, matching Case A's atomicity.

  Three regression tests cover the new behaviour: the cache-
  invalidation parametrize now exercises ``set_rules`` and
  ``start_match``;
  ``test_case_b_skips_restore_when_undo_tombstone_fails`` patches
  ``tombstone_ts`` to fail and asserts ``restore_popped`` is never
  reached; and
  ``test_case_b_skips_restore_when_audit_ts_is_missing`` drops
  the cached ``audit_ts`` and asserts both writes bail out (mirroring
  Case A's ``audit_ts is not None and tombstone_ts(...)`` guard so
  a defective seed cannot recreate the orphan-undo state).

- **Match report rendered "Team 1" / "Team 2" instead of the real
  team names when the OID was UNO-backed.** ``app.match_report
  ._team_name`` only checked the canonical ``Team {n} Name`` key,
  but the rest of the codebase (``Customization.A_TEAM`` /
  ``B_TEAM``) and the overlays.uno cloud customization API both
  round-trip the legacy ``Team {n} Text Name`` alias. Custom
  overlays happened to land on the canonical key because the
  React control UI writes that one, so the bug was invisible in
  custom-overlay coverage. Added the legacy alias to the lookup
  list (and pinned the regression in
  ``test_renders_team_names_from_legacy_text_name_alias``).

- **Match report locale ignored the operator's app language —
  always followed ``Accept-Language``.** Sharing the report from
  a Spanish-set control UI to a browser that advertised English
  rendered in English. Reasonable when the report is a public
  permalink; surprising when the operator was the one shaping
  the link. Added a ``?lang=<code>`` query parameter to
  ``GET /match/{id}/report`` that wins over ``Accept-Language``
  when the value is one of the supported locales (en/es/pt/it/
  fr/de). Unknown ``?lang=xx`` values fall through to
  ``Accept-Language`` so the cap can't lock the report into the
  default. ``LinksSection`` in the React control panel appends
  ``?lang=<active-locale>`` to the ``latest_match_report`` and
  ``match_history`` URLs before display / copy; control /
  overlay / preview URLs are passed through unchanged. New
  helper ``frontend/src/components/config/LinksSection.tsx``
  ``withLang`` + a five-case ``LinksSection.test.tsx`` plus two
  backend regression cases (``test_lang_query_overrides_accept
  _language``, ``test_lang_query_falls_back_to_accept_language
  _when_unknown``).

### Added

- **Screen Wake Lock during a live match.** New
  ``frontend/src/hooks/useScreenWakeLock.ts`` holds a screen wake
  lock while ``state.match_started_at != null && !state
  .match_finished`` so the operator's phone doesn't dim or lock
  between rallies. Released deliberately on match end / reset
  and on unmount; transient releases driven by the platform
  (tab hidden, lock screen) re-acquire automatically when the
  page becomes visible again. Silent no-op on runtimes without
  ``navigator.wakeLock`` (desktop browsers, iOS Safari pre-16.4).
  Wired in ``App.tsx`` immediately after ``useMatchAlertHaptics``.
  Tests: ``useScreenWakeLock.test.tsx`` (8 cases: enable / disable
  / unmount / visibility round-trip / unsupported / permission
  rejection / hidden-on-mount / re-acquire).

- **UX Phase 4.2 — recent-audit drawer accessible from the
  scoreboard.** The per-OID action log was previously only
  reachable via the post-match HTML report; during a live match the
  operator had to detour through the config tab or wait for the
  match to finish to confirm "did I undo the right point?" /
  "when was that timeout?". A new ``RecentAuditDrawer`` slides in
  from the right (tablet/desktop) or up from the bottom (mobile)
  on demand, lists the latest 20 records, and stays in sync with
  state confirmations via the existing ``confirmedState`` channel
  from ``useGameState``. Intentionally **not** a modal — the
  team panels behind the drawer remain interactive so the operator
  can keep scoring while reading the drawer. Dismiss via the
  close button, ESC, or tapping the transparent backdrop. Honours
  ``prefers-reduced-motion``.

  * **`useAuditLog` hook.** New
    ``frontend/src/hooks/useAuditLog.ts`` lazily fetches
    ``GET /api/v1/audit?oid=…&limit=20`` when the drawer opens,
    refetches when the trigger key (sums of points + sets +
    timeouts + match-finished) changes, surfaces records
    newest-first. Cancels in-flight requests on OID change /
    drawer close.
  * **`ActionChip` primitive + shared catalogue.** New
    ``frontend/src/components/ActionChip.tsx`` paired with
    ``frontend/src/utils/chipCatalogue.ts``. The TS catalogue
    mirrors the Python ``_CHIP_CATALOGUE`` in
    ``app/match_report.py`` so the live operator drawer and the
    post-match HTML report share the same per-action palette
    (point-t1 / point-t2 / set / timeout / serve / edit / reset /
    undone). Both surfaces use the same glyphs and colours;
    drift between them is now a single-file change instead of
    two.
  * **HUD share cluster grows a history button.** New
    ``history`` icon (deep-purple-300) sits next to the share
    button. Theme constant ``HISTORY_COLOR`` exported alongside
    ``SHARE_COLOR``.

  i18n: 22 new frontend keys (``history.title``, ``history.close``,
  ``history.refresh``, ``history.empty``, ``history.loading``,
  ``history.relative.{justNow,seconds,minutes,hours}``,
  ``history.action.{point,set,timeout,serve,edit,reset,unknown
  ,undoSuffix}``, ``history.legend.{pointT1,pointT2,set,timeout
  ,serve,edit,reset,undone}``) translated across all six
  supported locales (en/es/pt/it/fr/de).

  Tests: ``ActionChip.test.tsx`` (7 cases),
  ``useAuditLog.test.tsx`` (7 cases),
  ``RecentAuditDrawer.test.tsx`` (6 cases),
  ``ControlButtons.test.tsx`` gains a history-button case. Full
  suites: backend 1004 passed, frontend 390 passed.

- **UX Phase 3 — broadcast-side visual hierarchy.** Closes the
  perceptual gap between the operator's "I just won this set"
  feeling and the spectator-facing match report and OBS overlays.
  Set-point and match-point glows on overlays were intentionally
  deferred — they need the points-to-win threshold which the
  overlay state does not currently carry, so a backend-side
  ``match_info.alert`` flag is the next step.

  * **Match-report timeline — typed chips per action.** Each
    ``<li>`` in ``app/match_report.py``'s timeline now carries a
    per-action chip modifier (``chip-point-t1`` /
    ``chip-point-t2`` / ``chip-set`` / ``chip-timeout`` /
    ``chip-serve`` / ``chip-edit`` / ``chip-reset`` /
    ``chip-undone``) plus a glyph cell on the left-hand accent
    strip. Replaces the previously flat ``<ol>`` rendering that
    treated every action identically. Glyphs stay ASCII / single
    emoji so the print stylesheet doesn't depend on an icon font.
  * **Mini legend at the bottom of the timeline.** Decodes the
    chip palette without forcing the spectator to dig through
    docs, with seven entries — points (per team), set, timeout,
    serve change, manual edit, undone — translated across the
    six report locales (``legendPointT1``, ``legendPointT2``,
    ``legendSet``, ``legendTimeout``, ``legendServe``,
    ``legendEdit``, ``legendUndone``).
  * **Enriched footer.** The previously single-line footer now
    spans three lines: existing localized "Generated by…" header,
    a canonical permalink (``/match/{id}/report``) the
    spectator can bookmark, and a "Generated at" timestamp via
    the existing ``_fmt_ts`` helper. New report-i18n keys:
    ``permalinkLabel`` and ``generatedLabel`` across all six
    locales.
  * **Overlay OBS coreography (light).** ``overlay_static/js
    /app.js`` now injects an ``alerts-style`` block into the
    template head on first DOMContentLoaded and dispatches
    transient ``alerts-set-won`` / ``alerts-match-finished``
    glows on team-set increments and rising-edge match
    completion. Match completion is detected from the existing
    ``best_of_sets`` + ``sets_won`` fields the overlay state
    already carries — no backend change required.
    Honours ``prefers-reduced-motion`` (animation disabled) and
    is opt-out via ``state.overlay_control.alerts_visual ===
    false`` for live broadcasts that don't want it.
  * **Unified ``pickAlert`` primitive.** ``MatchAlertIndicator
    .tsx`` now exports the alert resolver and its types
    (``AlertSpec``, ``AlertKind``) so future hooks (sound cues,
    coachmarks targeting alerts, etc.) reuse the same
    transition logic. ``useMatchAlertHaptics`` already does so;
    the export removes the existing private-import smell.

  Tests: 2 new in ``tests/test_match_report.py`` —
  ``test_timeline_emits_typed_chips_per_action`` and
  ``test_footer_carries_permalink_and_generated_at``. The
  existing undo strikethrough cases were retargeted to the new
  composite ``class="timeline-li chip-... undone"`` shape via
  regex matching. Full suites: backend 1004 passed, frontend 367
  passed.

- **UX Phase 2 — discoverability and onboarding.** Surfaces the
  power features that already shipped (gestures, presets, share
  links) so a new operator finds them on the first session instead
  of from the docs.

  * **First-run gesture coachmark.** New
    ``frontend/src/components/GestureCoachmark.tsx`` walks four
    steps — tap to score, double-tap to undo, long-press to edit,
    swipe / gear icon for config — once per browser/profile.
    Persists dismissal via a new ``gestureTourSeen`` setting.
    Keyboard-driven (ArrowLeft / ArrowRight / Enter / Escape) and
    skip / back / next buttons for pointer users. Auto-fires on
    the first authoritative ``state`` arrival; the Behavior config
    section gains a "Replay tour" affordance that flips the flag
    back to ``false`` so the operator can re-watch without
    refreshing. Honours ``prefers-reduced-motion``.
  * **HUD config button gets a discoverability hint.** The
    ``.top-right-config-btn`` now carries a longer ``title``
    ("Configuration — or swipe left") plus an explicit
    ``aria-label`` so screen-reader users hear the canonical
    action while pointer users learn about the gesture, and a
    ``focus-visible`` outline so keyboard navigation never lands
    on it invisibly.
  * **Share button in the HUD.** New cyan share button next to
    Undo opens the existing ``LinksDialog`` (control / overlay /
    preview links with copy buttons) without requiring the
    operator to detour through the configuration panel.
    ``api.getLinks`` is fetched lazily on first open and cached
    for the session.
  * **Active preset hint pill in `/manage`.** The drawer now
    surfaces a "Last applied: <slug>" pill when the operator has
    applied a preset to the overlay in this browser. Storage is
    intentionally client-side (``localStorage`` keyed by OID,
    cleared on overlay delete) — the backend doesn't currently
    pin a "last applied" marker on overlay state, so this is a
    per-browser memory aid rather than authoritative state. A ``×``
    affordance in the pill clears the memory.

  i18n: 17 new frontend keys (``tour.*`` × 12, ``share.title``,
  ``ctrl.configHint``, ``behavior.replayTour``, ``behavior
  .replayTourAction``) plus an extended ``ctrl.configHint``,
  translated across all six supported locales (en/es/pt/it/fr/de).

  Tests: ``GestureCoachmark.test.tsx`` (8 cases),
  ``ControlButtons`` gains a share-button case, ``test_admin
  .test_manage_page_served`` updated to allow client-side opaque
  ``localStorage.setItem`` calls (preset-pill memory) while
  keeping the password-leak guard expressed by name. Full suites:
  backend 1002 passed, frontend 367 passed.

- **UX Phase 0 — quick wins across the four operator surfaces.** Five
  small, low-risk fixes that close visible gaps in the control UI,
  the ``/manage`` admin page, the public match report and the
  preview iframe. Each is independently revertable.

  * **Realtime sync indicator (``ConnectionStatus``).** New pinned
    pill at the top-left of the control UI that surfaces an amber
    "Reconnecting…" badge whenever the WebSocket from
    ``hooks/useGameState.ts`` drops for more than 1.5 s
    (``graceMs`` configurable). Healthy connections render no
    visible chrome — only an off-screen ``role="status"`` /
    ``aria-live="polite"`` element so assistive tech still picks
    up the transition. Honours ``prefers-reduced-motion``.
  * **Stylised confirm dialogs (``ConfirmDialog``).** Replaces
    ``window.confirm`` in App reset and ConfigPanel logout with a
    focus-trapped modal layered on the existing ``Dialog`` primitive.
    Native confirm broke theme/zoom on mobile and skipped the focus
    trap that the rest of the app already depends on. The unsaved-
    changes ``confirm`` in ConfigPanel stays — its synchronous
    return value is what the popstate handler hangs off, and that
    flow is rebuilt in Phase 4 (history rework, not a Phase 0 swap).
  * **/manage create-overlay name length cap.** ``app/admin/static/
    overlays.html`` now enforces ``maxlength="64"`` on the create
    form's name input plus a JS-side guard for paste paths, with an
    inline help-text update. Pre-empts the table-layout breakage that
    arbitrarily long names produced.
  * **Preview iframe failure fallback.** ``OverlayPreview`` now binds
    ``onLoad`` / ``onError`` and starts a 6 s ``PREVIEW_LOAD_TIMEOUT_MS``
    timer per mount. If neither fires, an overlay placeholder
    ("Preview unavailable" + Retry button) covers the iframe so the
    operator can recover without unmounting. Retry busts cache via a
    new ``cacheBust`` token so the second attempt isn't served from
    the still-broken response.
  * **Match-report timeline ↶ Undone badge.** ``app/match_report.py``
    ``_render_li`` now appends a non-strikethrough chip to undone
    rows so the marker survives dense timelines and the print
    stylesheet (where the line-through alone is hard to read).
    Localised in all six report locales as ``undoneBadge``.

  i18n: 5 new keys (``conn.online``, ``conn.reconnecting``,
  ``confirm.title``, ``confirm.confirm``, ``confirm.cancel``,
  ``preview.unavailable``, ``preview.retry``) translated across all
  six frontend locales (en/es/pt/it/fr/de). 1 new backend report key
  (``undoneBadge``) translated across the same six locales.

  Tests: ``ConnectionStatus.test.tsx`` (4 cases), ``ConfirmDialog
  .test.tsx`` (6 cases), 3 new fallback cases in ``OverlayPreview
  .test.tsx``, 1 new ``test_undone_rows_carry_visible_badge`` in
  ``tests/test_match_report.py``. ConfigPanel logout tests rewritten
  to assert against the new ``confirm-dialog-ok`` /
  ``confirm-dialog-cancel`` test ids instead of mocking
  ``window.confirm``. Full suites: backend 1002 passed, frontend
  341 passed.

- **UX Phase 1 — sensory feedback and loading state.** Closes the
  perceptual loop so the operator knows *what just happened*
  without having to watch the scoreboard. Sound cues were
  intentionally deferred to a later phase to keep this PR
  focused on the silent-but-visible failure modes.

  * **`useHaptics` hook + per-event patterns.** New
    ``frontend/src/hooks/useHaptics.ts`` wraps ``navigator.vibrate``
    behind a 50 ms throttle, a settings toggle (``haptics``,
    default ``true``), and a feature detect that no-ops on
    runtimes without the Vibration API (desktop browsers, JSDOM,
    pre-18.4 iOS Safari). Five named patterns: ``tap`` (10 ms),
    ``confirm`` (10-30-10), ``alert`` (15-35-15), ``matchPoint``
    (5-pulse), ``finished`` (40-60-40).
  * **`useMatchAlertHaptics` transition watcher.** Hoisted
    ``pickAlert`` out of ``MatchAlertIndicator`` so the new hook
    in ``frontend/src/hooks/useMatchAlertHaptics.ts`` can subscribe
    to the same set / match / finished transitions the indicator
    pill reads. Re-broadcasts of the same alert kind/team are
    suppressed so a stable WS frame can't replay the cue.
  * **Wired into the existing operator gestures.** Server-side
    LIFO undo (HUD button) and per-team double-tap-undo
    (``handleDoubleTapScore`` / ``handleDoubleTapTimeout``) now
    fire the ``confirm`` pattern; the alert watcher lights up on
    set / match / finished transitions. New
    ``behavior.haptics`` toggle in the Behavior section of the
    config panel, translated across the six supported locales.
  * **`ScoreboardSkeleton` placeholder.** New
    ``frontend/src/components/ScoreboardSkeleton.tsx`` mirrors the
    scoreboard's three-pane layout (team A / centre / team B) so
    the "post-OID, pre-first-WS-frame" gap no longer flashes the
    InitScreen with a prefilled value before swapping to the real
    UI. Reuses the ``config-skeleton-shimmer`` keyframes for
    tonal consistency and honours ``prefers-reduced-motion``. The
    InitScreen path is now reserved for the no-OID and post-error
    cases. Carries the realtime-sync pill in its first frame so
    a slow connect is observable end-to-end.
  * **Persistent save-error banner with Retry.** The old
    transient ``.config-save-error`` banner now exposes a real
    Retry button bound directly to ``handleSave``; pending saves
    surface a ``cloud_upload`` "Saving…" pill next to the Save
    button (``role="status"``, ``aria-live="polite"``). The
    success path still navigates back as before, so happy-path
    behaviour is unchanged. New i18n keys: ``config.saving`` and
    ``config.retry`` across all six locales.
  * **Floating toast in the `/manage` admin page.** The inline
    ``.status`` panel was promoted to a fixed top-right pill with
    icon glyphs from Material Icons (``check_circle`` /
    ``error_outline`` / ``info``), a slide-in transition, and
    ``prefers-reduced-motion`` support. Modal-scoped errors opt
    out via the new ``.status-inline`` modifier so login / create-
    overlay / preset modals keep their existing in-flow panels.
    No JS contract change — ``showStatus`` callers (create,
    delete, bulk-delete, preset save, preset apply) emit toasts
    automatically via the styling switch.

  Tests: ``useHaptics.test.tsx`` (7 cases),
  ``useMatchAlertHaptics.test.tsx`` (5 cases),
  ``ScoreboardSkeleton.test.tsx`` (4 cases), 1 new
  ``surfaces a retryable error banner`` case in
  ``ConfigPanel.test.tsx``. ``App.test.tsx`` updated where the
  seeded-OID path no longer flashes an InitScreen input. Full
  suites: backend 1002 passed, frontend 358 passed.

- **Configuration presets — replaces the originally planned
  Fase 2 (themes editables).** Operators can now save subsets of an
  overlay's current state under a name and reapply them — to the
  same overlay or any other — without going through the legacy
  hardcoded ``PRESET_THEMES`` catalogue. Five scopes shipped:
  * ``team_home`` / ``team_away`` — name, short name, primary /
    secondary colors and logo URL. Live-match keys (``points``,
    ``sets_won``, ``set_history``, ``serving``, ``timeouts_taken``)
    are intentionally excluded so a preset apply can never
    silently rewind a match.
  * ``overlay_layout`` — ``overlay_control.geometry``.
  * ``overlay_colors`` — ``overlay_control.colors`` (set_bg /
    set_text / game_bg / game_text). These keys do reach the
    rendered overlay end-to-end via
    ``overlay_static/js/app.js:123-126`` — apologies for the earlier
    rollout note that flagged them as no-op; the original PR #281
    diagnosis missed the JavaScript layer that consumes them as CSS
    custom properties (``--set-bg`` / ``--game-bg`` / etc.). Twelve
    of the sixteen overlay templates render them.
  * ``overlay_style`` — ``overlay_control.preferredStyle`` (which
    Jinja template is served).

  Storage lives at ``data/presets/preset_<sha20(slug)>.json`` —
  same hex-only-basename pattern as overlay state, so a
  user-supplied name never flows into a filesystem path.
  ``PRESETS_MAX_NAME_LEN`` (default 80) and ``PRESETS_MAX_RECORDS``
  (default 500) cap slug length and catalogue size; both override
  via env. Duplicate slugs collide loudly on create (HTTP 409),
  but on re-import they suffix ``-2``, ``-3``... up to ``-99`` so a
  reimport of the same JSON does not silently overwrite the
  catalogue.

  Seven new admin endpoints under ``/api/v1/admin/presets``:
  ``GET`` (list), ``POST`` (create from a source OID's state),
  ``GET /{slug}`` (full record incl. snapshots), ``DELETE /{slug}``,
  ``POST /{slug}/apply`` (target_oid + optional scope subset),
  ``GET /{slug}/export`` (portable JSON), ``POST /import``
  (round-trips ``export`` + tolerates unknown future scopes).

  All apply paths coalesce: a single ``OverlayStateStore.update_state``
  per request, regardless of how many scopes ride along. Same
  one-write/one-broadcast invariant the M4 PATCH endpoint locked in.

  Manager UI ships two new buttons in the Info drawer ("Save as
  preset…" and "Apply preset…"), each backed by an a11y modal
  reusing the existing focus trap / ESC dismissal / opener-restore
  scaffolding. Save-modal pre-selects ``overlay_layout`` /
  ``overlay_colors`` / ``overlay_style`` (the most common
  "tournament template" combo); apply-modal pre-selects every
  scope the chosen preset carries and greys out the ones it
  doesn't.

  Tests: 38 new in ``tests/test_presets.py`` covering scope
  extract / apply / merge invariants, store CRUD with cap and
  collision suffixing, the seven endpoints and an export →
  import round-trip. ``team_home`` snapshot's no-leak guarantee
  is pinned by name (``test_team_home_excludes_match_state``)
  so a future scope edit cannot regress the live-match
  protection. Full suite: 999 passed (was 961 + 38 new).

### Changed

- **Haptic feedback default flipped to `false`.** A fresh install
  no longer surprises the operator with vibration on the first
  scoring tap; the toggle in BehaviorSection opts in. Existing
  operators with ``volley_haptics: true`` already saved in
  ``localStorage`` keep that — only new sessions land on the new
  default. Test scaffolds in ``useHaptics.test.tsx`` and
  ``useMatchAlertHaptics.test.tsx`` flip the flag on explicitly
  in their ``beforeEach`` so the active-path assertions still
  exercise the vibration code path.

### Removed

- **"Replay tour" button + ``behavior.replayTour`` /
  ``behavior.replayTourAction`` i18n keys.** The Behavior section
  no longer exposes a manual re-arm for the gesture coachmark.
  ``gestureTourSeen`` still gates the first-run trigger and
  persists across sessions; rerunning the tour now requires
  clearing the ``volley_gestureTourSeen`` localStorage entry
  (or installing in a fresh browser profile). Cleaner
  BehaviorSection UI: only autoHide / autoSimple / haptics +
  language live there now.

### Fixed

- **`/metrics` was being shadowed by the SPA catch-all when a
  ``frontend/dist`` was present.** ``include_router(metrics_router)``
  in ``app/bootstrap.py`` ran *after* ``_register_spa(application)``
  so any deployment that ships a built frontend (i.e. production)
  would see the SPA shell ``index.html`` returned for
  ``GET /metrics`` instead of the Prometheus exposition. CI runs
  built without the frontend and never tripped, but local +
  production setups did. Same symptom class as the ``/manage``
  bug fixed in PR #281: server-rendered route mounted after the
  catch-all. Moved the include to ``_register_api_routes`` next
  to admin / match-report so the metrics endpoint is reachable
  before the SPA fallback inspects the path.

### Removed

- **Theme selector pulled from the ``/manage`` detail drawer.**
  Validating against real overlay templates after merge revealed
  the colour keys the dropdown wrote (``set_bg``, ``game_bg``,
  ``set_text``, ``game_text``) are not consumed by **any** Jinja
  template in ``overlay_templates/`` — applying ``dark`` or
  ``light`` produced a silent no-op while ``esports`` /
  ``neo_jersey`` / ``split_jersey`` / ``clear_jersey`` happened to
  work only because they also flip ``preferredStyle``. Rather than
  ship a half-working surface the dropdown was removed; the drawer
  now exposes the live preview iframe and the Live-usage panel
  only, and the per-row button is renamed to **Info** to match
  the inspect-only nature of the panel.

  The backend ``PATCH /api/v1/admin/custom-overlays/{name}``
  endpoint is **kept**: it is still useful for automation
  (especially the ``preferred_style`` field, which does drive the
  template selection at render time and works end-to-end). The
  manager UI just no longer wires a button to it. ``GET
  /api/themes`` and the legacy ``POST /api/theme/{id}/{name}``
  carry on unchanged. A future iteration that genuinely consumes
  the colour keys in the templates can re-introduce the selector
  without further backend changes.

### Fixed

- **PWA service-worker no longer requires a force-reload after a
  release for routes like ``/manage``.** ``frontend/vite.config.js``
  now sets ``workbox.skipWaiting: true`` and
  ``workbox.clientsClaim: true``. The previous default kept the old
  service worker active until every tab closed, so on a fresh deploy
  operators would land on the SPA shell at ``/manage`` (a route that
  is in the ``navigateFallbackDenylist`` of the new SW but was not
  in the old one) until they hit Ctrl+Shift+R. Operators are
  internal users — there's no consumer-side flow that the immediate
  SW takeover would break — so claiming clients on activation is
  the right tradeoff for an admin app. Same SW config also adds
  ``/metrics`` to the ``navigateFallbackDenylist`` so manual
  inspection from a browser with the PWA installed hits the
  Prometheus exposition rather than the SPA shell.

- **Code-review follow-ups on Fase 4 (CR-3, CR-4, M-1).** Three
  issues surfaced in the post-fase code review:
  * **Webhook replay was a self-DoS waiting to happen.**
    ``POST /api/v1/admin/webhooks/replay`` ran synchronously and
    iterated every dead-letter record with up to ~25 s of blocking
    retries each — a fully-loaded DL would pin the handler for
    tens of minutes, well past any sensible HTTP timeout, and tie
    up an entire FastAPI thread. The endpoint now (a) accepts a
    ``max_records`` query param (default 50, cap 500) and replays
    only the oldest-eligible slice, (b) runs the blocking work
    via ``run_in_threadpool`` so the event loop stays free for
    other handlers, and (c) reports ``remaining_in_dl`` so the
    operator can iterate (``while remaining > 0: replay``)
    without guesswork. Records held back by ``since`` /
    ``max_records`` are preserved untouched.
  * **The dead-letter file had no size cap.** A misbehaving
    target during a multi-day outage could grow
    ``data/webhooks_dead_letter.jsonl`` without bound — the same
    anti-pattern Fase 4 just fixed for the audit log. ``append``
    now enforces ``WEBHOOK_DEAD_LETTER_MAX_RECORDS`` (default
    1000) by dropping the oldest entries via an atomic rewrite
    when the cap is breached, so even a runaway producer stays
    inside a bounded disk footprint. A new
    ``voc_webhook_dead_letter_size`` Prometheus gauge tracks the
    current count so dashboards can alert before the cap is
    reached.
  * **Heartbeat tick walked clients serially.** With
    ``WSHUB_HEARTBEAT_INTERVAL_SECONDS > 0`` and a busy OID, a
    200-client sweep could take 200 × ``BROADCAST_SEND_TIMEOUT``
    of wall time. ``_heartbeat_tick`` now classifies clients
    once, fans the zombie closes and healthy pings out via
    ``asyncio.gather`` (with ``return_exceptions=True`` so a
    single stuck socket cannot wedge the rest), and applies the
    bookkeeping after the gather lands — so 200 clients finish
    in roughly ``BROADCAST_SEND_TIMEOUT``.
  Tests: 7 new cases — DL ``count``/cap eviction/gauge updates
  in ``tests/test_webhooks.py``, ``max_records`` paginated
  replay + ``remaining_in_dl`` in ``tests/test_admin.py``, and
  the concurrent + mixed-zombie heartbeat sweeps in
  ``tests/test_api_routes.py``. Full suite: 960 passing.

### Added

- **Prometheus ``/metrics`` endpoint + instrumentation
  (Fase 4 / M15).** A new ``app.metrics`` module wires
  ``prometheus_client`` (now in ``requirements.txt``) into the
  hot paths and surfaces the result at ``GET /metrics``. The
  endpoint speaks the standard Prometheus text-exposition format
  (``text/plain; version=0.0.4``) and is mounted at the app
  root rather than under ``/api/v1`` so it lines up with every
  other Prometheus-instrumented service the operator might be
  scraping.

  Metrics emitted:
  * ``voc_http_request_duration_seconds`` — histogram of
    end-to-end HTTP latency, labelled by ``route`` (the FastAPI
    route template — bounded by the OpenAPI surface, not the
    raw path), ``method`` and ``status``. Wired through a new
    ``MetricsMiddleware`` placed inside ``ExceptionLogging``
    but outside ``RequestContext`` so the bucket reflects the
    full handler cost.
  * ``voc_webhook_delivery_total{event, status}`` — counter
    with ``status`` ∈ ``success`` / ``client_error`` /
    ``server_error`` / ``exception`` / ``ssrf_blocked`` /
    ``dead_letter``. ``dead_letter`` is incremented in
    addition to the per-attempt status so an alert can fire on
    "X events landed in the DL" without subtracting other
    buckets.
  * ``voc_ws_clients_total`` — total open frontend WebSocket
    connections across all OIDs (unlabelled).
  * ``voc_ws_oids_active`` — number of distinct OIDs with at
    least one open subscriber (unlabelled).
  * ``voc_active_sessions`` — live ``GameSession`` count
    tracked by ``SessionManager`` (unlabelled).

  The plan called for ``ws_clients_per_oid`` as a labelled
  gauge; that label would be unbounded in OID space (textbook
  Prometheus anti-pattern). The two unlabelled gauges above
  give the operator the same dashboard story (total fan-out
  plus breadth) without the cardinality risk.

  Auth ladder mirrors ``/manage``: by default the endpoint is
  unauthenticated (the exposed values are aggregates, no
  payloads, no per-OID labels — safe to scrape from the cluster
  service mesh). Operators that prefer to gate it set
  ``METRICS_REQUIRE_ADMIN=true``, which checks the same Bearer
  token as ``/api/v1/admin/*``. The auth check fires *before*
  the library-availability check so an unauthenticated probe
  cannot use the 503-vs-200 difference to fingerprint whether
  the metrics backend is loaded.

  Graceful degradation: if ``prometheus_client`` is missing
  (older deploys that have not run ``pip install -r
  requirements.txt``), every helper becomes a no-op, the rest
  of the app boots normally, and ``/metrics`` returns a 503
  with a clear "install prometheus-client" message instead of
  a confusing 404.

  Tests: 7 new in ``tests/test_metrics.py`` covering the
  exposition format + content, the route-template label, the
  default-no-auth path, ``METRICS_REQUIRE_ADMIN`` gate,
  503-when-password-unset, the webhook counter increment, and
  the WS gauges tracking ``WSHub.connect`` / ``disconnect``.
  Suite at 953 passing.

- **Webhook retries + dead-letter queue + operator replay
  (Fase 4 / M16).** The outbound webhook dispatcher used to be
  fire-and-forget: a single 503 from a flaky receiver dropped
  the event on the floor with nothing more than a log warning.
  Three changes:
  * **Retries with exponential backoff.** ``_attempt_with_retries``
    runs the configured ``WEBHOOK_RETRY_ATTEMPTS`` (default 3)
    additional POSTs after the first failure, sleeping
    ``WEBHOOK_RETRY_BASE_SECONDS * 2**(attempt-1)`` between them
    (capped at ``WEBHOOK_RETRY_MAX_SECONDS``). Defaults give the
    classic 1 / 2 / 4 / 8 progression. Retries fire on 5xx and
    on ``requests.RequestException`` (timeouts, connect errors);
    **4xx is treated as permanent client rejection** — no retry,
    no dead-letter, just a warning, because retrying a "bad
    request" never converges.
  * **Dead-letter queue.** When retries are exhausted on a
    transient failure, the delivery is appended to
    ``data/webhooks_dead_letter.jsonl`` with the URL, event,
    OID, body (as a UTF-8 string for human inspection), last
    error string and attempt count. The HMAC ``secret`` is
    deliberately **not** persisted — replay re-resolves the
    target's secret from the live config, so rotating
    ``WEBHOOKS_SECRET`` does not strand legacy entries with
    stale signatures and a leaked DL file does not leak signing
    keys. SSRF blocks and 4xx rejections are also kept out of
    the DL because they are not replay-recoverable. The DL file
    is rewritten atomically (tempfile + ``os.replace``) so a
    crash mid-write cannot leave it half-written.
  * **Operator replay endpoint.** New
    ``POST /api/v1/admin/webhooks/replay`` (gated by
    ``OVERLAY_MANAGER_PASSWORD``) reads the DL, optionally
    filters by ``since=<unix-seconds>``, redelivers each record
    against the current target config, and rewrites the file
    with only the entries that still failed (plus those whose
    URL no longer matches any configured target — kept so the
    operator can fix the config and retry). The response carries
    counts only (``considered`` / ``succeeded`` /
    ``still_failing`` / ``skipped_unknown_url``); the payloads
    themselves are never echoed through the admin surface.

  Tests: 8 new in ``tests/test_webhooks.py`` (first-attempt
  success, 5xx-then-success, 5xx-exhausts-retries, 4xx-no-retry,
  RequestException retries, ``replay_records`` happy path,
  unknown-URL preservation, attempts-counter increment) plus
  4 endpoint-level cases in ``tests/test_admin.py`` (auth,
  empty-DL no-op, success path pruning, ``since`` filter
  preserving older entries). Suite at 946 passing.

- **WebSocket connection cap + opt-in server heartbeat
  (Fase 4 / M14).** Two complementary defences against runaway
  ``WSHub`` registries:
  * **Connection cap.** ``WSHub.connect`` now refuses upgrades
    when an OID already has ``WSHUB_MAX_CLIENTS_PER_OID`` (default
    200) subscribers. The reject path raises a new
    ``WSHubFull`` exception **before** ``ws.accept()``, and the
    ``/api/v1/ws`` endpoint translates it into a WebSocket close
    with code ``1013`` ("Try Again Later") — the conventional
    server-side back-pressure signal. The cap protects the box
    from a runaway tab loop or a misconfigured load test eating
    file descriptors. Configurable via the
    ``WSHUB_MAX_CLIENTS_PER_OID`` env var.
  * **Server heartbeat (opt-in).** When the operator sets
    ``WSHUB_HEARTBEAT_INTERVAL_SECONDS > 0``, a background task
    started from ``router_lifespan`` sweeps every connection
    every ``INTERVAL`` seconds, sends an application-level
    ``{"type":"ping"}`` frame, and evicts any client whose
    ``mark_active`` timestamp is older than
    ``WSHUB_CLIENT_TIMEOUT_SECONDS`` (default 60 s) with a 1011
    close ("server error") and a clean ``disconnect``. Default
    interval is **0 (disabled)** because the existing browser
    client does not yet ack application-level pings — turning
    this on without first updating the frontend would churn live
    tabs every timeout. A new ``_env_float_nonneg`` helper in
    ``app.constants`` lets ``KEY=0`` survive the validation as a
    genuine "off" signal (the strict ``> 0`` filter on
    ``_env_float`` would otherwise upgrade it to the default).
  Tests: 6 new cases in ``tests/test_api_routes.py`` covering
  ``WSHubFull`` raise-before-accept, the endpoint's 1013 close,
  zombie eviction past the timeout, healthy-client ping
  dispatch, ``mark_active`` bumping ``_last_seen``, and the
  ``start_heartbeat`` no-op path. Suite at 934 passing.

- **Audit log rotation + cursor-based pagination
  (Fase 4 / M13).** The per-OID action audit
  (``data/audit_<hash>.jsonl``) used to grow without bound — a
  long tournament could leave a single file with hundreds of
  thousands of lines, every read of which (``match_archive``,
  ``GET /audit``, undo) walked the whole thing. Two changes:
  * **Logrotate-style rotation.** Once the active file exceeds
    ``AUDIT_LOG_MAX_BYTES`` (default 5 MiB), it rotates to
    ``audit_<hash>.jsonl.1``, bumping older rotations down by one
    suffix; anything past ``AUDIT_LOG_MAX_FILES - 1`` rotated
    slots (default 5 total files counting the active) is dropped.
    Rotation runs inside the existing per-OID lock so concurrent
    appends never see a torn rename. ``read_all`` /
    ``pop_last_forward`` / ``peek_last_forward`` walk the active
    file plus every rotated file in chronological order, so
    ``match_archive`` and the undo path keep seeing the full
    visible history regardless of how many rotations have
    occurred. ``clear`` and ``delete`` now sweep the whole family
    (active + rotated) so a match reset starts genuinely empty.
    Both knobs respect the same env-var override pattern as the
    other tunables in ``app.constants``.
  * **Cursor-based pagination on ``GET /audit``.** New optional
    ``before_ts`` query parameter; the response now carries a
    ``next_cursor`` field that the caller passes back to walk
    history one window at a time. Older calls without
    ``before_ts`` keep returning the most recent ``limit``
    records, so the existing dashboard contract is preserved —
    only new clients pay attention to ``next_cursor``. Tombstones
    are honoured by the cursor so an undo between two pages does
    not leak the cancelled record.
  Tests: ``tests/test_action_log.py`` adds 13 new cases covering
  no-rotation-under-threshold, single-rotation cross-file reads,
  cap eviction (oldest records dropped), ``clear``/``delete``
  sweeping the rotated set, undo tombstones spanning rotation,
  cursor walks across all records, null-cursor on final page,
  and pagination respecting tombstones. Suite at 928 passing.

- **`/manage` — bulk delete, filter and per-overlay detail drawer
  (Fase 1 — frontend half).** Three sizeable additions to the
  custom-overlay manager UI:
  * **Filter input** above the toolbar: live, case-insensitive
    substring match against the overlay's name, OID and output
    key. The result count (`23 of 50`) sits next to the input
    with `aria-live="polite"` so screen readers announce the
    new total when the operator types.
  * **Bulk delete.** A new "Select" column adds a checkbox per
    row, and a "Select all visible" checkbox in the header. The
    toolbar gains a "Delete `<N>` selected" button (disabled
    when nothing is checked); clicking it reuses the existing
    confirmation modal, which now switches between the original
    1-overlay layout and a list of up to 10 OIDs (with "… and N
    more" tail) for multi-deletes. Deletes run sequentially so a
    401 mid-run bounces back to login instead of fanning out N
    parallel failures, and the status line summarises partial
    successes ("`5 of 8 deleted; stopped at error: …`"). Selections
    that point at OIDs no longer present after a server-side
    refresh are dropped automatically.
  * **Detail drawer.** A new "Edit" button on every row opens a
    right-hand `<aside role="dialog">` that shows: a live
    preview iframe (`/overlay/<output_key>?style=mosaic`,
    `sandbox="allow-scripts allow-same-origin"`), a theme
    dropdown wired to `GET /api/themes` and the new
    `PATCH /api/v1/admin/custom-overlays/{name}` endpoint, and
    a "Live usage" panel fed by `GET /usage` with a green/grey
    dot ("Live" vs "Idle"), OBS viewer count, scoreboard tab
    count, active-session flag and human-readable
    "last activity 30s ago / 4m ago / 2h ago" string. The drawer
    uses `inert` + `aria-hidden` instead of `display: none` so
    the slide-in transition is meaningful, ESC closes it, and
    focus returns to the originating button. After a theme is
    applied, the iframe `src` is bumped with a cache-busting
    `t=<now>` query so the operator immediately sees the new
    look.

  ⚠️ Screenshot regeneration: the `/manage` page now shows three
  buttons in the toolbar (`+ New overlay`, `Refresh`, `Delete N
  selected`) and a checkbox column. Run
  `bash scripts/screenshots/run.sh` to refresh
  `docs/screenshots/05-manage-page.png`. Skipped in this commit
  because it needs Node + Playwright + a live server.

### Added

- **Admin endpoints for editing and inspecting custom overlays
  (Fase 1 — backend half).** Two new routes under
  ``/api/v1/admin/custom-overlays/{name}``:
  * **``PATCH``** — partial update of a custom overlay's appearance.
    The body accepts any combination of ``theme`` (preset name from
    ``GET /api/themes``), ``colors`` (dict deep-merged into
    ``overlay_control.colors``) and ``preferred_style`` (validated
    against the renderable templates plus ``default``). When both
    ``theme`` and explicit overrides are sent, the theme is applied
    first so user-supplied values win on the second merge — that's
    the operator's mental model. Empty patches are rejected with
    400 to flag accidental form submissions instead of silently
    no-op'ing. The mutation flows through
    ``OverlayStateStore.update_state`` so OBS browser sources
    receive the broadcast in real time (50 ms debounce).
  * **``GET /usage``** — snapshot of how many live consumers a
    custom overlay has: ``obs_clients`` (browser-source viewers),
    ``frontend_ws_clients`` (scoreboard control tabs subscribed via
    ``WSHub``), ``has_active_session`` (live ``GameSession``) and
    ``seconds_since_last_activity`` (clamped at the session TTL).
    The relative duration intentionally avoids confusing
    ``time.monotonic`` timestamps with epoch wall-clock —
    ``GameSession.touch`` uses monotonic and the operator's
    question is "is this still live?", not "when exactly".
  Both routes require ``OVERLAY_MANAGER_PASSWORD`` and feed the
  drawer/usage indicator scheduled for the frontend half of Fase 1.

### Refactored

- **``PRESET_THEMES`` extracted to ``app.overlay.themes``.** The
  static catalogue used to live inside ``app/overlay/routes.py``,
  which made it inaccessible to ``app/admin/routes.py`` without a
  circular import (overlay → admin already exists for
  ``require_admin``). Moving it to a dedicated module breaks the
  cycle, exposes a stable ``get_theme_names()`` helper to both
  routers, and prepares the seam M8 (Fase 2) will widen when
  themes become directory-backed under ``data/themes/``. The
  ``GET /api/themes`` and ``POST /api/theme/{id}/{name}`` public
  routes are unchanged on the wire — they now read through
  ``themes.PRESET_THEMES`` instead of the local dict.

### Changed

- **`/manage` — auth-error handling unified across every admin call.**
  The custom-overlay manager page previously only bounced the operator
  back to the login view when ``loadOverlays`` got a 401/403; the
  delete and create flows logged the raw error inside the dialog and
  left the now-stale password in memory. A shared ``handleAuthError``
  helper now clears the cached password, dismisses any open modal,
  shows the login view and re-focuses the password input from
  ``loadOverlays``, ``performDelete`` and the ``createForm`` submit
  alike. Symptom: rotating ``OVERLAY_MANAGER_PASSWORD`` while a
  manager tab was open used to leave the operator stuck inside a
  half-broken modal until they refreshed.

### Tests

- **Coverage for the new env-var overrides in ``app.constants``.**
  ``tests/test_constants.py`` (14 tests) reloads ``app.constants``
  under each ``monkeypatch.setenv`` and verifies the ``SESSION_TTL_*``
  / ``WS_*_SECONDS`` overrides honour the env, fall back to defaults
  on garbage / empty / non-positive input, and that the legacy
  re-exports in ``app.api.session_manager`` and ``app.ws_client`` see
  the same value after a matching reload. Without these the only
  thing protecting the override contract was the implicit "defaults
  match legacy values" coincidence; a regression in the ``_env_int``
  / ``_env_float`` parsers would have been silent.

### Changed

- **`/manage` quick wins (Fase 0 del roadmap de mejoras).** Three
  small but operator-visible improvements to the custom-overlay
  manager page (`app/admin/static/overlays.html`):
  * **Accessible delete confirmation.** The custom-overlay delete
    flow no longer uses `window.confirm`. It now opens a
    `role="dialog" aria-modal="true"` overlay that shows the
    overlay's name, OID and output key, traps TAB inside the
    dialog, restores focus to the originating button on close, and
    dismisses on ESC. The Cancel button is default-focused so a
    stray ENTER cannot delete by accident. The pre-existing "New
    custom overlay" modal received the same `aria-modal` /
    `aria-labelledby` annotations.
  * **Descriptive ARIA labels on the action buttons.** Screen-reader
    users now hear "Copy overlay `mybroadcast`" / "Delete overlay
    `mybroadcast`" instead of bare "Copy" / "Delete".
  * **Mobile-friendly overlay table.** Below 600 px the overlay
    list collapses into a stacked card layout (each row labelled
    via `data-label` `::before` pseudo-elements), so the manager
    is usable from a phone in a courtside operator workflow.

  No API contract changes; `tests/test_admin.py` keeps passing.

- **Centralised tunable constants in `app.constants`.** The
  hardcoded `SESSION_TTL_SECONDS` (idle session eviction),
  `WSHub._BROADCAST_SEND_TIMEOUT` (per-socket broadcast timeout)
  and the `WSControlClient` reconnect/heartbeat parameters
  (`_RECONNECT_BASE` / `_RECONNECT_MAX` / `_HEARTBEAT_INTERVAL` /
  `_ZOMBIE_DEADLINE`) now load from `app.constants` and accept
  env-var overrides (`SESSION_TTL_SECONDS`,
  `WS_BROADCAST_SEND_TIMEOUT_SECONDS`, `WS_RECONNECT_BASE_SECONDS`,
  `WS_RECONNECT_MAX_SECONDS`, `WS_HEARTBEAT_INTERVAL_SECONDS`,
  `WS_ZOMBIE_DEADLINE_SECONDS`). Non-numeric or non-positive values
  fall back to the previous defaults so a misconfigured environment
  degrades gracefully. The legacy module-level names
  (`app.api.session_manager.SESSION_TTL_SECONDS`,
  `app.api.ws_hub.WSHub._BROADCAST_SEND_TIMEOUT`,
  `app.ws_client._ZOMBIE_DEADLINE`…) are preserved as
  re-exports/initialisers so the existing monkeypatch in
  `tests/test_api_routes.py` and the deadline read in
  `tests/test_ws_client.py` keep working untouched.

## [5.1.4] - 2026-05-07

### Fixed

- **OverlayPreview iframe blocked by the strict default CSP (regression
  in v5.1.3).** The new ``SecurityHeadersMiddleware`` shipped a default
  ``Content-Security-Policy`` without a ``frame-src`` directive, so
  browsers fell back to ``default-src 'self'`` and silently blocked
  every cross-origin iframe in the React control UI. Two real-world
  paths broke:
  * UNO overlay previews loaded from ``https://overlays.uno`` (the
    iframe inside ``OverlayPreview.tsx`` for non-custom overlays).
  * Custom-overlay previews when ``OVERLAY_PUBLIC_URL`` points at a
    different host than the control UI itself — e.g. a Traefik
    deployment that serves the scoreboard on ``marcador.example.com``
    and the overlay on ``overlay.example.com``.

  ``_DEFAULT_CSP`` now includes ``frame-src 'self' https:``, which
  unblocks both cases without weakening the policy meaningfully:
  ``data:`` / ``javascript:`` / ``http:`` iframe sources remain
  forbidden, and the iframe content's own origin still governs what
  scripts run inside it (``sandbox="allow-scripts allow-same-origin"``
  in ``OverlayPreview.tsx`` is unchanged). Operators that already set
  a custom ``SECURITY_CSP`` should add ``frame-src 'self' https:`` to
  their override string.

## [5.1.3] - 2026-05-07

### Changed

- **Type-safer settings persistence.**
  ``frontend/src/hooks/useSettings.tsx::readAll`` no longer needs the
  ``as unknown as Record<string, unknown>`` double-cast to write
  parsed JSON back into the typed ``Settings`` object — it routes
  through ``Object.assign`` instead. The remaining ``as unknown as``
  cast in ``OverlayPreview.tsx`` is now documented inline (it is
  required because Chromium's iframe ``allowTransparency`` honours
  the string form more reliably than the boolean React types model).
- **Centralised TeamState re-imports.** ``TeamState`` now lives in
  ``frontend/src/api/client.ts`` alongside the other generated-schema
  type aliases. The four call sites
  (``useGameState.ts``, ``useRecentEvents.ts``, ``TeamPanel.tsx``,
  ``test/TeamPanel.test.tsx``) import from there instead of digging
  into ``./schema`` directly.
- **Expanded mypy coverage.** ``[tool.mypy] files`` in
  ``pyproject.toml`` grew from 6 to ~17 modules. ``app/state.py``,
  ``app/customization.py``, ``app/game_manager.py``,
  ``app/conf.py``, ``app/oid_utils.py``,
  ``app/env_vars_manager.py``, ``app/app_storage.py``,
  ``app/match_report_i18n.py``, ``app/match_report_signing.py``,
  ``app/password_hash.py``, ``app/auth_utils.py``,
  ``app/security_bootstrap.py``, and
  ``app/overlay/state_store.py`` are now type-checked. The
  expansion required minor cleanups: ``AppStorage`` and
  ``Customization`` static helpers got the ``@staticmethod``
  decorator they were missing, ``State.OIDStatus`` got the right
  enum name, and ``EnvVarsManager._remote_config_cache`` /
  ``Customization.predefined_teams`` /
  ``Customization.THEMES`` got explicit type annotations. No
  runtime behaviour change.
- **Stricter Ruff rule set.** ``pyproject.toml`` now selects ``UP``
  (pyupgrade), ``C90`` (mccabe complexity, capped at 18), ``RUF``,
  and ``SIM`` on top of the previous ``E/F/W/I/B``. The mass
  modernization sweep replaced legacy ``Optional[X]`` /
  ``Dict[X, Y]`` annotations with ``X | None`` / ``dict[X, Y]``,
  upgraded a handful of ``open(...)`` redundant modes, sorted
  ``__all__`` blocks, and dropped now-unused ``typing`` imports.
- **Stricter TypeScript flags.** ``frontend/tsconfig.json`` now
  enables ``noUncheckedIndexedAccess``, ``noUnusedLocals``,
  ``noUnusedParameters``, and ``noImplicitReturns``. Index-access
  callsites in ``useRecentEvents``, ``useSwipeNavigation``,
  ``i18n``, and the ``FONT_SCALES`` lookup in ``App.tsx`` were
  hardened. A new ``DEFAULT_FONT_SCALE`` export in
  ``frontend/src/theme.ts`` provides a fallback that doesn't
  flow through indexed access.

### Fixed

- **Material Icons no longer blocked by CSP.** The control UI used to
  load the icon font from ``https://fonts.googleapis.com/icon?family=Material+Icons``,
  which the security-headers CSP (``style-src 'self' 'unsafe-inline'``,
  ``font-src 'self' data:``) blocks on fresh page loads — leaving the
  timeout / serve / bottom-bar buttons rendered as text ligatures.
  The font is now bundled with the frontend via the ``material-icons``
  npm package (filled variant only) and served same-origin from
  ``/assets/``, so no third-party network request is made and the
  default CSP is unchanged. Side benefit: the UI now works in
  airgapped / firewalled deployments.
- **Overlay templates' Google Fonts allowed by CSP.** Several overlay
  styles (``clear_jersey``, ``neo_jersey``, ``split_jersey``,
  ``compact``, ``original``, ``esports``, ``glass``, ``mosaic``,
  ``pill``, ``ribbon``, ``shield``, ``vertical``, ``style``,
  ``style_reference``, ``split``, ``diagonal``) load Outfit / Inter /
  Roboto / Oswald / Montserrat / Rajdhani / Barlow Condensed / Chakra
  Petch / Rubik from ``fonts.googleapis.com``. The strict default CSP
  blocked them and OBS browser sources fell back to system sans-serif.
  ``SecurityHeadersMiddleware._build_html_csp`` now appends
  ``https://fonts.googleapis.com`` to ``style-src`` and
  ``https://fonts.gstatic.com`` to ``font-src`` **only on
  ``/overlay/*`` paths** (alongside the existing
  ``frame-ancestors *`` relaxation). The control UI, ``/manage``, and
  ``/match/{id}/report`` keep the strict 'self'-only CSP.
- **Dialog accessibility.** ``SetValueDialog`` and ``LinksDialog``
  now share a new ``frontend/src/components/Dialog.tsx`` primitive
  that renders ``role="dialog" aria-modal="true"``, focuses the
  card on open, listens for the ESC key to dismiss, and replaces
  the previous ``<div onClick>`` backdrop with a real ``<button>``
  so keyboard users can dismiss the dialog without a mouse. CSS is
  unchanged (same ``.dialog-overlay`` / ``.dialog-card`` classes
  plus a new transparent ``.dialog-backdrop`` button) so the
  visual appearance is identical and screenshot regeneration is
  not required.
- **Silent exception swallowing in overlay state I/O.**
  ``OverlayStateStore._read_state_sync``,
  ``save_persisted_state[_async]``, ``_iter_persisted_ids`` and
  ``_migrate_legacy_files_locked`` now narrow their previously
  blanket ``except Exception`` to the specific
  ``OSError | json.JSONDecodeError`` they actually recover from. A
  programming error inside the read path no longer gets logged as
  a warning and masked. Two new tests cover the corrupt-JSON and
  unreadable-file fallback paths.
- **Stale-client drop visibility.**
  ``ObsBroadcastHub._send_to_clients`` now logs the dropped client
  at debug level, and ``WSControlClient.disconnect`` /
  ``WSControlClient._listen`` log close/heartbeat failures so a
  disconnect storm shows up in the log instead of being silently
  swallowed.
- **Lost broadcast tasks.** ``WSHub.broadcast_sync`` and
  ``broadcast_payload_json_sync`` now keep a strong reference to
  the task they create via ``loop.create_task(...)``. Without it
  the asyncio loop could garbage-collect the task before it
  finished, silently dropping a state-update push to subscribed
  WebSocket clients (RUF006).

### Added

- **Backfilled tests for ``app.api.dependencies`` and
  ``app.bootstrap``.** ``tests/test_api_dependencies.py`` (24
  tests) covers ``_strict_oid_access_enabled`` env-var parsing,
  ``check_oid_access`` (auth disabled, missing header, invalid
  token, allowed OID, mismatched OID, lenient vs strict modes,
  malformed per-user config), and ``get_current_username``
  edge cases. ``tests/test_bootstrap.py`` (4 tests) verifies that
  ``create_app`` boots gracefully when ``frontend/dist`` and/or
  ``overlay_templates`` directories are missing, and exercises
  ``_split_csv_env``. Total backend tests grew from 853 → 883;
  ``--cov=app`` is at 82%.
- **Repository hygiene.** Added ``.editorconfig`` (LF endings,
  4-space Python, 2-space JS/TS/MD), ``.gitattributes`` (text=auto
  eol=lf with explicit binary classification and
  ``linguist-generated`` markers for lockfiles and the generated
  OpenAPI types), ``CONTRIBUTING.md`` summarising the dev loop and
  PR checklist, plus issue templates
  (``.github/ISSUE_TEMPLATE/{bug_report,feature_request,config}``)
  and a ``.github/pull_request_template.md``. ``dependabot.yml``
  now also tracks ``npm`` updates for ``frontend/`` (grouped by
  eslint / vitest / testing-library / react).
- **Frontend linting.** Added ESLint (flat config) with
  ``typescript-eslint``, ``eslint-plugin-react``,
  ``eslint-plugin-react-hooks``, and ``eslint-plugin-jsx-a11y``,
  plus Prettier and ``eslint-config-prettier``. New scripts in
  ``frontend/package.json``: ``lint``, ``lint:fix``, ``format``,
  ``format:check``. The ``lint`` step is now wired into
  ``.github/workflows/ci.yml`` (frontend job) and into
  ``.pre-commit-config.yaml`` as a ``local`` hook that runs
  ``npx eslint`` on changed ``.ts``/``.tsx`` files under
  ``frontend/src/``. Known dialog a11y findings and unused-import
  cleanups are intentionally kept as warnings so this lint baseline
  passes today; tightening lands in subsequent PRs.

### Security

- **Webhook SSRF guard.** ``app/api/webhooks.py`` now refuses to POST
  to URLs whose host resolves to a private (RFC 1918), loopback,
  link-local (including the ``169.254.169.254`` cloud-metadata
  endpoint), multicast, reserved (RFC 5737 / RFC 3849
  documentation), or unspecified address. Trusted-LAN deployments
  that legitimately call internal webhook receivers set
  ``WEBHOOKS_ALLOW_PRIVATE_IPS=true`` to opt out. Non-``http(s)``
  schemes are also rejected. DNS resolution failures pass through
  so flaky resolvers don't silently break valid webhook
  configurations.
- **`WWW-Authenticate` on 401 responses.** Per RFC 7235 §4.1, every
  401 from the auth ladders now carries a
  ``WWW-Authenticate: Bearer realm="<scoreboard|admin|overlay-server>"``
  header. The realm hint helps the OpenAPI / Swagger UI label the
  credential prompt and lets operators tell from access logs which
  ladder rejected a request. 403 semantics are preserved (invalid
  credential ≠ no credential).
- **Enriched unhandled-exception logging.** ``ExceptionLoggingMiddleware``
  now logs the request method, path, exception class, and request id
  in both the message text and as structured ``extra`` fields
  (``http_method``, ``http_path``, ``exc_class``) so JSON log
  consumers can query each axis without parsing the free-form
  message.

- **`TrustedHostMiddleware` (opt-in).** Set ``TRUSTED_HOSTS`` to a
  comma-separated list of public hostnames the deployment serves
  from; requests carrying a ``Host`` header outside the allow-list
  are rejected with HTTP 400 before any handler reads
  ``request.base_url``. Wildcard subdomains are honoured. Default:
  unset → no enforcement (backwards compatible).
- **CORS scaffolding (opt-in).** Set ``CORS_ALLOWED_ORIGINS`` to a
  comma-separated list of origins permitted to call the API
  cross-origin. ``*`` is deliberately rejected on this credentialed
  API; explicit origins only. ``Authorization``,
  ``Content-Type``, ``X-Request-ID``, and
  ``Sec-WebSocket-Protocol`` are forwarded so the existing auth
  flows and the new Bearer-subprotocol WebSocket handshake all keep
  working. Default: unset → same-origin only (backwards compatible).
- **CI security scanners.** New ``security-scan`` job in
  ``.github/workflows/ci.yml`` runs Bandit (MEDIUM+ severity) over
  ``app/``, ``pip-audit --strict`` against both
  ``requirements.lock`` and ``requirements-dev.lock``, and
  ``npm audit --omit=dev --audit-level=high`` against the frontend.
  Findings fail the job; suppression requires either a documented
  ``# nosec`` comment or an explicit advisory ignore.
- **`SECURITY.md`** — formal vulnerability-disclosure policy.
  Points reporters at GitHub's private vulnerability reporting,
  documents in-scope/out-of-scope surfaces, and links to the
  hardening reference (``AUTHENTICATION.md``).

- **Hashed credentials at rest.** New module ``app/password_hash.py``
  uses ``hashlib.scrypt`` (no new dependency) to mint salted hash
  records of the form ``scrypt$n=16384,r=8,p=1$<salt>$<hash>``. Three
  auth surfaces gained an opt-in hashed alternative — operators
  migrate without a flag day, since each surface accepts either the
  legacy plaintext or the new hash:
  - ``SCOREBOARD_USERS`` user entries may carry ``password_hash``
    instead of ``password``. When both are present, the hash wins
    so the migration doesn't leave both credentials valid.
  - ``OVERLAY_MANAGER_PASSWORD_HASH`` is honoured alongside the
    legacy ``OVERLAY_MANAGER_PASSWORD``. The match-report URL
    signing key follows whichever credential is configured, so
    rotating either one still invalidates outstanding signed URLs.
  - ``OVERLAY_SERVER_TOKEN_HASH`` is honoured alongside
    ``OVERLAY_SERVER_TOKEN``. When the hash is set, the security
    bootstrap skips auto-generation of the persisted plaintext
    file — a hash-only deployment keeps zero cleartext on the
    server side; the peer keeps the cleartext token.

  Mint a hash via ``python -m app.password_hash`` (interactive
  prompt) or ``echo -n 'pw' | python -m app.password_hash --stdin``.

  Hash verification with the default scrypt parameters costs ~50 ms
  per check, which would noticeably slow the React control UI's
  per-action API calls. ``PasswordAuthenticator`` now keeps a
  60-second per-process verify cache keyed on
  ``sha256(provided_token)`` so the hot path stays fast; the cache
  is automatically invalidated whenever ``SCOREBOARD_USERS`` is
  rotated.

- **Capability-style signed URLs for the gated match report.** New
  endpoint ``POST /api/v1/admin/match/{match_id}/sign-url`` (admin
  Bearer auth) returns a short-lived URL of the form
  ``/match/{id}/report?exp=<unix>&sig=<hmac>``. The legacy
  ``?token=<OVERLAY_MANAGER_PASSWORD>`` flow is preserved for
  backwards compatibility but operators should switch over: signed
  URLs do not embed the admin password, expire automatically (TTL
  bounded to ``[60, 30 days]``, default ``86 400 s``), and rotating
  the password invalidates every outstanding signature.
- **Bearer subprotocol auth on ``/api/v1/ws``.** The WebSocket route
  now prefers ``Sec-WebSocket-Protocol: bearer, <token>`` over the
  legacy ``?token=`` query parameter. The handshake echoes the
  selected subprotocol so browser clients accept the connection.
  Resolution order: subprotocol → ``Authorization`` header → legacy
  ``?token=`` query (deprecated). Tokens no longer need to appear
  in URL access logs or HTTP ``Referer`` headers for browser clients.

- ``OVERLAY_SERVER_TOKEN`` is now **auto-generated and persisted on
  first start** instead of leaving the seven overlay-server mutation
  endpoints (``POST /api/state/{id}``, ``/create/overlay/{id}``,
  ``/delete/overlay/{id}``, ``/api/raw_config/{id}``,
  ``/api/theme/{id}/{name}``) unauthenticated by default. Resolution
  order at startup:
  1. ``OVERLAY_SERVER_TOKEN_DISABLED=true`` keeps the legacy
     fail-open behaviour and logs a ``CRITICAL`` startup warning.
  2. ``OVERLAY_SERVER_TOKEN=<value>`` already set wins.
  3. Otherwise the bootstrap reads / mints a token at
     ``data/.overlay_server_token`` (mode ``0o600``) and injects it
     into ``os.environ`` so the rest of the app picks it up
     transparently. The same value is reused across restarts so an
     external ``CustomOverlayBackend`` peer does not need to be
     re-configured.

  **Operator action:** when an external overlay server points at this
  app via ``APP_CUSTOM_OVERLAY_URL``, both sides must use the same
  ``OVERLAY_SERVER_TOKEN``. Either set it explicitly on both, or read
  the auto-generated value from ``data/.overlay_server_token`` after
  the first start. To restore the previous unauthenticated behaviour
  on a trusted LAN, set ``OVERLAY_SERVER_TOKEN_DISABLED=true``.
- ``SCOREBOARD_USERS`` left unset now emits a startup ``WARNING``
  (previously silent) so the open-API posture is visible in the
  startup tail. ``SCOREBOARD_USERS_DISABLED=true`` silences the
  warning for trusted-LAN deployments.
- New ``SecurityHeadersMiddleware`` adds baseline response headers on
  every request: ``X-Content-Type-Options: nosniff``,
  ``Referrer-Policy: strict-origin-when-cross-origin``, and a
  ``Permissions-Policy`` that denies geolocation/microphone/camera by
  default. HTML responses additionally carry a ``Content-Security-Policy``
  (locked to ``'self'`` + inline scripts/styles to keep the existing
  match report rendering) and ``X-Frame-Options: SAMEORIGIN``. The
  ``/overlay/*`` routes get a relaxed ``frame-ancestors *`` so OBS
  browser sources can still embed them. Operators can override the
  CSP / referrer / permissions strings via ``SECURITY_CSP``,
  ``SECURITY_REFERRER_POLICY``, ``SECURITY_PERMISSIONS_POLICY`` and
  opt into HSTS by setting ``SECURITY_HSTS_SECONDS`` (off by default
  to avoid locking out non-HTTPS deployments).
- New ``AuthRateLimitMiddleware`` watches ``/api/v1/`` and ``/manage``
  for repeated 401/403 responses and blocks further requests from
  the same IP with HTTP 429 once a per-IP threshold is reached. This
  is a defence-in-depth backstop for brute-force attempts against
  ``/api/v1/admin/login`` and the ``verify_api_key`` /
  ``require_admin`` dependencies. Tunables:
  ``AUTH_RATE_LIMIT_MAX_FAILURES`` (default 10),
  ``AUTH_RATE_LIMIT_WINDOW_SECONDS`` (default 60),
  ``AUTH_RATE_LIMIT_BLOCK_SECONDS`` (default 60). The bucket is
  reset only by the sliding window — successful responses to public
  endpoints under the same prefix (``/api/v1/admin/status``,
  ``/manage`` itself) do not clear failures, so an attacker cannot
  launder login attempts by interleaving status requests. The
  client identifier is sourced from ``scope["client"]`` only;
  client-supplied ``X-Forwarded-For`` headers are ignored to defeat
  spoofing. Operators behind a reverse proxy must configure uvicorn
  with ``--proxy-headers`` / ``--forwarded-allow-ips`` so the ASGI
  scope reflects the real remote IP.
- ``/api/v1/`` JSON responses now carry ``Cache-Control: no-store``
  unless the handler explicitly sets a different policy, so
  intermediaries cannot cache authenticated payloads.
- ``PUT /api/v1/customization`` now caps payload size and validates
  every value:
  - At most 64 top-level keys per request.
  - Only scalar JSON types (string, boolean, number, null) are
    accepted — arrays and nested objects are rejected so the
    deep-merge into the broadcast state cannot be used to inflate
    the WebSocket payload.
  - String values capped at 256 characters (8 KiB for logo URLs to
    accommodate base64 ``data:image/...`` payloads).
  - Logo URLs must use ``http(s)://`` or ``data:image/...`` schemes.
    ``javascript:``, ``vbscript:``, ``data:text/html``, ``file://``,
    etc. are rejected before persistence and broadcast.

## [5.1.2] - 2026-05-06

### Changed

- React control UI: reversed the order of the four secondary toggles
  on the bottom HUD bar. New order, left → right (closest to the
  match timer first): undo, simple-mode, preview, visibility. Undo
  is the most reached-for action during play, so it now sits closest
  to the primary side of the bar.
- Docs: regenerated README screenshots to reflect the bottom-HUD
  toggle reorder and the recent control-UI / config-panel /
  match-report tweaks.
- Performance: audit-log undo (``POST /api/v1/game/undo`` and the
  per-type ``add_*(undo=True)`` flag) now appends a single tombstone
  record instead of rewriting the entire ``data/audit_<hash>.jsonl``
  file. Reads continue to expose the same logical view — tombstones
  and the records they reference are filtered out — and the file is
  still truncated on match end / ``reset`` so tombstones do not
  accumulate across matches. Brings undo cost down from O(N) to
  O(1) per call.
- Performance: ``GET /api/v1/matches`` now reads a compact
  ``data/matches/index.jsonl`` summary file (one line per archive)
  instead of opening and JSON-parsing every match snapshot on disk.
  The index is appended on each ``archive_match`` and rewritten on
  ``delete_match`` / ``delete_for_oid``; missing indices are
  rebuilt on demand from the on-disk files, so upgrades from
  earlier builds do not need a manual migration step.
- Performance: ``GameService`` action methods (``add_point``,
  ``add_set``, ``add_timeout``, ``change_serve``, ``set_score``,
  ``set_sets_value``, ``set_rules``, ``reset``, ``set_visibility``,
  ``set_simple_mode``, ``update_customization``) compute
  ``GameStateResponse`` once per call and reuse the same object for
  the broadcast, webhook fan-out, archive payload, and HTTP
  response. The previous code path called ``get_state`` 2-5 times
  per action, each call iterating ``sets_limit`` and recomputing
  side-switch / match-point info.
- Performance: ``WSHub`` gained a ``broadcast_payload_json`` path
  that accepts an already-encoded JSON string. ``GameService._broadcast``
  uses ``GameStateResponse.model_dump_json`` so the WebSocket
  payload is serialized in a single pass instead of going through an
  intermediate ``model_dump`` → dict → ``json.dumps`` round-trip.
- Performance: React control UI — ``TeamPanel`` and ``CenterPanel``
  are now wrapped in ``React.memo`` so a WebSocket state push no
  longer re-renders the full scoreboard subtree when only the
  relevant team's props changed. Button-colour derivations in
  ``App.tsx`` are collapsed into a single ``useMemo`` to keep
  referential identity stable across renders.
- Performance: React control UI — ``ConfigPanel`` tracks
  unsaved-changes via an explicit ``isDirty`` flag toggled by the
  mutation paths (``updateField``, theme apply) instead of running
  a double ``JSON.stringify`` comparison of the full customization
  object on every keystroke.

## [5.1.1] - 2026-05-04

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
    block). Struck-star variant added beside the original star
    when the operator undoes the set-winning point: detected
    via a React state diff (``team_X.sets`` drops between
    refetches), since the audit log alone can't reconstruct
    the popped forward.
  * Trophy icon when the same sets diff also flips
    ``match_finished`` to ``true``. Struck-trophy variant
    appended when ``match_finished`` flips back to ``false``
    (operator undoes the match-winning point).
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

  Forward chips are sticky across refetches. When
  ``pop_last_forward`` deletes the original forward record on
  an undo, the hook carries the prior chip forward (it remembers
  the last surfaced events) and appends the struck-undo chip
  beside it instead of letting the original silently vanish or
  morph into its struck variant. So undoing a set-winning point
  shows ``[+1, ★, −1, ⊘★]`` rather than just ``[⊘★]``, matching
  the way ``point_undo`` already laid out next to ``point_add``.

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

### Changed

- React control UI: replaced the horizontal set selector with a
  compact current-set indicator, freeing horizontal space in the
  centre column for the new points history strip.
- Points-history chips now use a stable composite key
  (``ts/team/kind/value``) instead of the array index, so the
  sliding window no longer remounts every chip when the oldest
  event drops off — preserves chip state and avoids unnecessary
  reconciliation.
- README screenshots regenerated; the portrait capture now shows
  the points history strip in the centre slot.

### Fixed

- UNO overlay preview size now matches the custom overlays
  (``cardHeight`` hoisted to the shared scope), so the iframe no
  longer renders at a different aspect than what the broadcast
  output will show.
- Points history strip occasionally missed the chip for the action
  that just happened — it would only surface together with the next
  action's chip. Root cause was a race between the optimistic state
  update in ``useGameState.addPoint`` and the audit ``GET`` that
  ``useRecentEvents`` fires when its ``scoringKey`` changes: the
  optimistic write bumped the key immediately, the GET often beat
  the in-flight ``POST``'s ``action_log.append``, and the follow-up
  WS broadcast carried the same state so the key didn't change
  again. Fixed by introducing a separate ``confirmedState`` slot in
  ``useGameState`` that only advances on authoritative updates
  (initial fetch, action response, WS push) and feeding *that* to
  ``useRecentEvents`` — so the audit refetch trigger no longer
  outruns the server's acknowledgement.

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
