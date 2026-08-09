# Usability, Functionality, and Performance Roadmap

This roadmap records the improvement opportunities identified after the 7.0.0
release. It is deliberately outcome-oriented: each proposal states the user or
operator problem, the intended change, and a measurable completion criterion.

## Delivery order

The first implementation sequence is:

1. Make match-history browsing genuinely scalable.
2. Replace per-scoreboard worker pools with one bounded shared executor.
3. Isolate browser preferences and the last-opened overlay by account.
4. Add state revisions and operator presence as the concurrency foundation for
   safe degraded/offline scoring.

The remaining proposals stay in the backlog until those foundations have
landed.

## 1. Scalable match history

### Problem

The account UI requests one maximum-size page, then filters, sorts, paginates,
and bulk-deletes in the browser. A library above the request ceiling is only
partially visible. Summary queries also materialize the large archived audit
and state JSON fields even though the listing only renders a handful of scalar
values.

### Proposal

- Project only summary fields in list queries.
- Filter by overlay, match mode, and date range in SQL.
- Sort and page in the backend with a deterministic tie-breaker.
- Preserve the existing offset contract while returning the effective filters
  and page metadata.
- Add an owner-scoped bulk-delete endpoint.
- Resolve the latest report with a one-row query rather than loading the full
  history.
- Apply the same server-side filtering and paging to the public history page.

### Completion criteria

- A user can reach every archived match, including match 501 and later.
- Listing a report never loads its `audit_log` JSON column.
- Filtering and sorting do not require loading the complete library.
- Bulk deletion uses one API request and one database transaction.

## 2. Shared bounded background executor

### Problem

Every live scoreboard owns a `ThreadPoolExecutor` capable of growing to five
threads. Idle game sessions live for hours, so a multi-court installation can
accumulate far more worker threads than useful concurrent work.

### Proposal

- Use one process-wide, bounded executor for overlay broadcast preparation and
  delivery.
- Keep each overlay's mutation order deterministic.
- Shut the shared executor down once at application shutdown, not once per
  game session.
- Expose queue depth and wait/execute latency if the existing metrics surface
  can do so without per-overlay labels.

### Completion criteria

- Creating additional game sessions does not create additional executor
  instances.
- Session eviction cannot shut down workers used by other sessions.
- Rapid updates for one overlay remain ordered.

## 3. Account-scoped preferences and recent overlay

### Problem

Browser settings currently use global `volley_*` keys, and the most recently
opened overlay uses a single `volley_oid` key. Different accounts sharing one
browser can therefore inherit each other's interface preferences and stale
overlay selection.

### Proposal

- Namespace local browser state by authenticated user id.
- Keep anonymous capability-link state separate without persisting the secret
  control token.
- Migrate existing unscoped keys once for the first signed-in user that reads
  them.
- Clear or re-evaluate the active overlay when the account changes.
- In a later iteration, sync account-level choices (language, theme, scoring
  workflow) through a database-backed user-preferences API while keeping true
  device capabilities such as haptics local.

### Completion criteria

- Two accounts in one browser retain independent settings and recent overlays.
- An old account's OID cannot auto-open or auto-create an overlay for the next
  account.
- Existing users keep their current preferences after the migration.

## 4. State revisions and multi-operator presence

### Problem

Control links allow several people to operate one scoreboard, but connected
controllers are anonymous. Game state has no monotonic revision that a client
can use to detect a stale write, and audit records do not identify the client
that issued an action.

### Proposal

- Add a monotonic revision to every game-state response and broadcast.
- Accept an optional expected revision on mutating requests and reject stale
  writes with a conflict response.
- Give each browser tab an ephemeral client id and optional display label.
- Broadcast aggregate controller presence and surface it unobtrusively on the
  board.
- Attach the non-sensitive client id/label to audit records.
- Never expose owner account identity through a public control capability.

### Completion criteria

- Clients can distinguish their own acknowledgement from a newer remote
  update.
- A stale conditional action cannot silently overwrite newer state.
- Operators can see when another controller is connected.
- Presence disappears after disconnect or heartbeat expiry.

## 5. Degraded/offline scoring

### Problem

When a score request fails, the current optimistic update is rolled back. That
is safe but disruptive in venues with unreliable Wi-Fi, where an operator may
lose several rallies before noticing the connection indicator.

### Proposal

- Add an idempotent `client_action_id` to mutations.
- Queue a small, explicit set of pending actions locally.
- Replay only against the expected server revision.
- Require operator reconciliation when another controller changed the match
  during the outage.
- Show pending-action count and never imply that an unacknowledged score is
  already on air.

### Completion criteria

- Retrying a request cannot score the same rally twice.
- Pending work survives a page refresh but remains scoped to one account and
  overlay.
- Conflicting offline actions are never applied silently.

This work depends on proposal 4 and should not be implemented as a blind FIFO
queue before revisions exist.

## 6. Match preparation and operational dashboard

### Problem

The account dashboard is primarily navigation, while overlay creation asks
only for an id and description. Preparing a match requires visiting several
separate configuration sections before the operator can verify the OBS output.

### Proposal

- Add a "Prepare match" flow covering teams, mode/rules, visual preset, preview,
  and OBS connectivity.
- Offer "Create and open", "Duplicate configuration", and "Test overlay"
  actions.
- Show favourite/recent overlays, active matches, on-air state, and the latest
  result on the dashboard.
- Add reusable scheduled match setups for recurring competitions.

### Completion criteria

- A first-time user can create, configure, verify, and open a scoreboard in one
  guided flow.
- Returning operators can resume the relevant live scoreboard in one action.

## 7. Real frontend pagination for catalogues

### Problem

The API bounds list responses, but the bundled SPA walks every page and joins
the complete result in memory. This preserves the old UI contract but cancels
most of the scaling benefit for large team, icon, preset, overlay, and user
catalogues.

### Proposal

- Add server-side search and stable sort parameters.
- Render real paging or incremental loading in account screens.
- Virtualize only lists that demonstrate a rendering bottleneck; avoid adding
  virtualization complexity to small lists.
- Retain full, intentionally unpaged export endpoints for backups.

### Completion criteria

- Initial account-page requests remain bounded as catalogues grow.
- Searching does not first download the full catalogue.

## 8. Smaller initial frontend payload

### Problem

All six translation dictionaries are imported into one eager i18n chunk. The
current built chunk is roughly 257 KB uncompressed (47 KB Brotli), even though a
session normally uses one language.

### Proposal

- Split one translation module per locale and dynamically load the selected
  language plus the English fallback.
- Preload a newly selected language before switching the UI.
- Add compressed initial-route size budgets to CI.
- Keep route-level lazy loading and the existing dependency chunk split.

### Completion criteria

- Opening the login page or board does not download unused locale dictionaries.
- CI fails on an accidental material increase in the initial payload.

## 9. Optional horizontal-scaling architecture

### Problem

Overlay state, WebSocket registries, and parts of rate limiting are process
local. Multiple replicas can therefore disagree unless traffic is pinned to a
single instance and all runtime files are shared carefully.

### Proposal

- Introduce a runtime-state interface independent of local JSON files.
- Use Redis Pub/Sub or Streams for cross-process state and presence broadcasts.
- Store durable runtime/audit data in the database or an explicitly configured
  shared store.
- Document sticky sessions as an interim deployment constraint.
- Move authentication throttling to a shared edge layer for multi-replica
  deployments.

### Completion criteria

- Two replicas can serve control and output connections for the same overlay
  without divergent state.
- Losing one process does not lose acknowledged match actions.

This proposal is intentionally conditional. The single-process design remains
simpler and preferable for ordinary self-hosted installations.

## Validation principles

Every delivery should include focused regression tests, update the OpenAPI
contract when the API changes, and pass the complete backend and frontend
quality gates documented in `AGENTS.md`. Performance changes should be guarded
by query-count, allocation-count, or payload-shape assertions rather than
fragile wall-clock thresholds.
