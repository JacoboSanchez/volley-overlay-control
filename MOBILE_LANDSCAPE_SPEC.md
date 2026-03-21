# Mobile UX Specification

**Project:** Volley Overlay Control
**Scope:** Optimized experience for phones in landscape and portrait orientations, plus full overlay connectivity contract
**Status:** Draft

---

## 1. Context and Goals

The application already ships as a PWA and detects orientation via `GUI.is_portrait()`. However, the landscape layout currently has several friction points when operated from a phone during a live match:

- Score buttons are sized relative to `page_width / 4.5`, which produces buttons that are too small on a 375 pt-wide phone screen.
- The center panel (sets history, set selector, live preview) takes horizontal space that crowds the scoring buttons.
- The undo mode is a separate toggle that requires two actions (enable undo, then tap score button).
- The options/customization dialogs use desktop-oriented forms that are difficult to interact with one-handed.
- There is no visual lock to prevent accidental taps while a phone is being passed to a co-scorer.

The goal of this specification is to define a layout, interaction model, configuration surface, and overlay connectivity contract that makes the app **fully operable with one thumb on a phone-sized screen (≥ 360 × 640 dp) in both orientations** without degrading the experience on tablets or desktop browsers.

---

## 2. Target Screen Classes

| Class | Width (dp) | Height (dp) | Typical Device |
|---|---|---|---|
| Phone portrait (small) | 320 – 375 | 568 – 667 | iPhone SE, Galaxy A series |
| Phone portrait (standard) | 375 – 390 | 667 – 844 | iPhone 14/15, Pixel 7 |
| Phone portrait (large) | 390 – 430 | 844 – 932 | iPhone 14/15 Plus/Pro Max |
| Phone landscape (small) | 568 – 667 | 320 – 375 | iPhone SE, Galaxy A series |
| Phone landscape (standard) | 667 – 844 | 375 – 390 | iPhone 14/15, Pixel 7 |
| Phone landscape (large) | 844 – 932 | 390 – 430 | iPhone 14/15 Plus/Pro Max |
| Tablet landscape | 1024 + | 768 + | iPad, Galaxy Tab |
| Desktop | 1280 + | 800 + | browser window |

**Phone landscape** is the primary scoring layout (operator holds the phone sideways during play). **Phone portrait** is the secondary layout used when first setting up a match or reviewing scores between sets. Tablet and desktop layouts must continue to work as today with no regressions.

---

## 3. Orientation Detection

**Current rule** (in the orientation detection module):
```
return height > 1.2 * width and not width > 800
```

This correctly identifies portrait for narrow phones but should be updated to explicitly distinguish all three layout classes:

```
is_phone_landscape = width <= 932 and height <= 430
is_phone_portrait  = height > width and width <= 430
# Everything else → tablet/desktop landscape (existing behavior)
```

Devices wider than 932 dp (tablets, desktops) use the existing landscape layout unchanged.

Hysteresis thresholds remain at 1.1 (exit portrait) / 1.3 (enter portrait) as today. The rebuild-on-orientation-change logic already handles this correctly and needs no structural change.

---

## 4. Layout: Phone Landscape Mode

### 4.1 Grid Structure

Use a single-row, three-column layout that fills 100 vw × 100 vh with no scrolling.

```
┌──────────────┬──────────────────┬──────────────┐
│              │                  │              │
│   TEAM A     │   CENTER STRIP   │   TEAM B     │
│   COLUMN     │                  │   COLUMN     │
│  (38% width) │   (24% width)    │  (38% width) │
│              │                  │              │
└──────────────┴──────────────────┴──────────────┘
```

Team columns each receive **38% of the viewport width**. The center strip receives **24%**. This allocation ensures the score buttons remain large enough to be tapped reliably while giving the center panel enough room to display set history legibly.

### 4.2 Team Column

Each team column is a flex column with three rows:

```
┌────────────────────┐
│  SCORE BUTTON      │  ← fills ~65% of column height
│  (tap = +1 point)  │
├────────────────────┤
│  SET BADGE  SERVE  │  ← ~20% height
├────────────────────┤
│  TIMEOUT DOTS      │  ← ~15% height
└────────────────────┘
```

**Score button sizing:**
- Width: 100% of column (≈ 38 vw)
- Height: `min(65vh, 38vw)` so it remains square-ish on very wide screens
- Font size: `button_height * 0.45`

At 667 × 375 dp (standard phone landscape) this produces a score button of approximately 253 × 244 dp, meeting the 48 dp minimum touch target by a large margin.

**Score button interaction (unchanged from current behavior):**
- Single tap → +1 point for that team (or −1 in undo mode)
- Double-tap within 350 ms → undo last point for that team
- Long press (≥ 1 000 ms) → open custom value input dialog
- Haptic feedback on every tap (existing implementation)

### 4.3 Center Strip

The center strip renders vertically from top to bottom:

1. **Set badges row** — two small circular badges (one per team) showing sets won. Tap a badge to increment/decrement sets directly. Height: `~22% of viewport height`.
2. **Per-set scores table** — compact grid showing scores for each completed set. Condensed to `text-xs`. Height: `~40% of viewport height`. Scrollable vertically if more than 5 sets are configured.
3. **Set selector** — a compact pagination row (← N →) to navigate between active sets. Height: `~18% of viewport height`.
4. **Match status indicator** — a small text label ("Set 3 · 21 pts") or "Match finished" banner. Height: `~20% of viewport height`.

The live preview iframe is **not shown** in phone landscape mode (it would be too small to be useful). Toggling preview is still available from the options dialog.

### 4.4 Control Bar

The existing control buttons (undo toggle, simple mode, visibility, save/reset, options, fullscreen, dark mode) are moved into a **collapsible control bar** that overlays the bottom of the screen.

- **Collapsed state (default):** a single 44 dp handle / grip icon centered at the bottom edge. Semi-transparent background.
- **Expanded state:** a horizontal pill that rises up ~56 dp from the bottom showing all control buttons at 36 dp size each, with equal horizontal spacing.
- Tapping anywhere outside the expanded bar collapses it.
- The control bar does not push the main layout up; it overlays it.

This removes the control buttons from the competing for height with the score buttons.

---

## 5. Touch Interaction Improvements

### 5.1 Swipe-to-Undo

In addition to the existing double-tap and undo toggle, introduce a **swipe-left gesture** on a score button as an alternative undo path:

- Swipe left ≥ 40 dp on the score button → undo last point for that team.
- Visual feedback: the button briefly shows a leftward slide animation and displays the decremented score.
- Swipe right on the button → (no action; reserved for future use).

Implementation: add `touchstart` / `touchend` listeners in `button_interaction.py`. Only fires if horizontal delta ≥ 40 dp and vertical delta < 30 dp (to avoid conflicts with scroll).

This means three undo paths exist: swipe-left, double-tap, and the undo toggle. All three remain active simultaneously.

### 5.2 Accidental Tap Guard

Add a **tap-lock mode** that disables score buttons to prevent accidental scoring when the phone changes hands:

- Accessible from the expanded control bar via a lock icon button.
- When locked: score buttons are visually dimmed (opacity 0.4) and show a lock overlay icon.
- Tapping a locked button shows a brief notification ("Tap lock active") instead of scoring.
- Unlocking: tap the lock icon in the control bar again, or perform a two-finger tap anywhere on the screen.
- Lock state is not persisted across sessions (resets on page reload).

### 5.3 Serve Toggle

Serve indicator is already a tappable icon per team. In phone landscape mode the serve icon is **enlarged to 44 × 44 dp** and repositioned to the bottom-left (Team A) / bottom-right (Team B) of the score button so it does not overlap with score text.

### 5.4 Timeout Action

Currently a round button in the team panel. In phone landscape mode:

- The timeout button is **replaced by three small circular dots** (filled = used, empty = available) below the score button.
- Tapping any dot calls `add_timeout` for that team (same as before).
- Long-pressing the dot area undoes the last timeout (equivalent to undo + add_timeout).
- Maximum 2 timeouts per team per set; dots reset at set change (existing `add_set` behavior).

---

## 6. Configuration Surface

The options dialog (`options_dialog.py`) is already two-column on wide screens. For phone landscape, the dialog should adapt:

### 6.1 Drawer Pattern

Replace the modal dialog with a **bottom drawer** that slides up from the bottom of the screen to 85% of viewport height when opened. This avoids the virtual keyboard shifting issues and feels native on mobile.

- Drawer slides in with a 200 ms ease-out transition.
- A drag handle at the top allows dragging down to dismiss.
- The existing two-column layout is kept for content, but columns reflow to single-column if viewport width < 480 dp.

### 6.2 Sections Visible in Phone Landscape

Organize the drawer into three tabs or accordion sections:

| Section | Contents |
|---|---|
| **Display** | Auto-hide (switch + slider), Simple mode (switch), Timeout-resets-simple (switch) |
| **Buttons** | Font selector, Follow team colors (switch), Team A color picker, Team B color picker, Text color picker, Reset colors button |
| **Match** | Points limit (number input), Points last set (number input), Sets to win (number input), Reset scores button, Reload from backend button |

The **Match** section exposes game configuration that currently requires environment variables. Changing these values overrides the conf values for the current session only (not persisted) unless a "Save as default" option is enabled (out of scope for this spec).

---

## 7. Visual Design

### 7.1 Score Button Appearance

No change from current implementation. Button color, font, and icon overlay continue to be configured via options. Haptic on tap is preserved.

### 7.2 Minimum Touch Targets

All interactive elements in phone landscape mode must meet 44 × 44 dp minimum. Elements that would be smaller (e.g., set badge, serve icon) get a 44 dp invisible touch area via padding or an overlay tap zone.

### 7.3 Safe Area Insets

On devices with a notch or a home indicator (iPhone X and later), the layout must respect CSS `env(safe-area-inset-*)`:

- Left/right paddings on the outer row: `max(8px, env(safe-area-inset-left))` and `max(8px, env(safe-area-inset-right))`.
- Bottom padding of the control bar: `max(8px, env(safe-area-inset-bottom))`.

These can be injected via the framework's head HTML injection API or as inline styles on the root container element.

### 7.4 Status Bar / PWA Theme

When running as a PWA in fullscreen mode (already configured with `display: fullscreen` in manifest.json), no changes needed. When running in the browser, the existing dark/light mode toggle is preserved.

---

## 8. Layout: Phone Portrait Mode

Portrait is the natural orientation when a phone is handed to someone, used while setting up before a match, or when the device cannot be rotated. The layout must be scorable in portrait too, though it is optimized less aggressively for one-handed use than landscape.

### 8.1 Grid Structure

A single-column vertical stack that fills 100 vw × 100 vh with no scrolling:

```
┌─────────────────────────────┐
│  TEAM A ROW                 │  ← 40% height
│  (score button + sidebar)   │
├─────────────────────────────┤
│  CENTER BAND                │  ← 22% height
│  (sets, set selector)       │
├─────────────────────────────┤
│  TEAM B ROW                 │  ← 38% height
│  (score button + sidebar)   │
└─────────────────────────────┘
```

Team A sits at the top, Team B at the bottom. The center band separates them.

### 8.2 Team Row (Portrait)

Each team row is a horizontal flex row:

```
┌──────────────────────────┬────────────┐
│                          │  SERVE ●   │
│   SCORE BUTTON           │            │
│   (tap = +1 point)       │  SETS  0   │
│                          │            │
│                          │  ● ○  TOs  │
└──────────────────────────┴────────────┘
```

- **Score button**: 70% of row width, full row height. Font size: `button_width * 0.45`.
- **Sidebar** (30% width): vertical stack of serve icon (top), sets badge (middle), timeout dots (bottom). Each element gets equal height.
- At 375 × 667 dp the score button is approximately 263 × 267 dp — well above minimum.

### 8.3 Center Band (Portrait)

Left-to-right inside the band:

1. **Team A sets badge** (circular, tappable) — left-aligned.
2. **Set scores table** — compact `text-xs` grid in the center showing past set scores.
3. **Set selector** (← N →) — right-aligned.

The set scores table and selector scroll horizontally if there are more sets than fit (up to 5 sets).

### 8.4 Control Bar (Portrait)

Same collapsible control bar as landscape (§4.4), anchored to the bottom edge. The handle and expanded bar behave identically.

### 8.5 Portrait-Specific Behavior

- **Live preview** is not shown in portrait phone mode (same rule as landscape).
- **Options drawer** (§6) works identically in portrait; columns reflow to single-column automatically since portrait width is narrow.
- All touch interactions (double-tap undo, swipe-left undo, long press, tap-lock) apply identically.

---

## 9. Overlay Connectivity

This section documents the full overlay backend contract so that the UI can be rebuilt without reading the existing `backend.py` implementation.

### 9.1 Configuration Entry (OID Dialog)

On first launch, or when the user taps "Change Overlay" in the Links dialog, the app shows a single text input for the **Overlay Control OID**. The OID is a string that determines which backend the app talks to:

| OID format | Backend type |
|---|---|
| UUID or alphanumeric string (e.g. `abc123xyz`) | overlays.uno cloud |
| Prefixed with `C-` (e.g. `C-mybroadcast`) | Custom / self-hosted overlay |
| `C-mybroadcast/line` | Custom overlay with locked style `line` |

**Validation flow:**
1. If the OID is empty → show `Messages.EMPTY_OVERLAY_CONTROL_TOKEN` and block.
2. Call `validate_and_store_model_for_oid(oid)`:
   - Returns `VALID` → proceed to the main scoring screen.
   - Returns `DEPRECATED` → show `Messages.OVERLAY_DEPRECATED` warning and allow proceeding.
   - Returns `INVALID` → show `Messages.INVALID_OVERLAY_CONTROL_TOKEN` and stay on the OID screen.

The OID is persisted in `AppStorage` so the user does not need to re-enter it on reload.

### 9.2 overlays.uno Protocol

All communication uses HTTPS PUT to:

```
https://app.overlays.uno/apiv2/controlapps/{oid}/api
```

Request body shape:

```json
{ "command": "<CommandName>", "id": "<overlay_id>", "content": <payload> }
```

or for customization:

```json
{ "command": "SetCustomization", "value": <customization_object> }
```

The `overlay_id` (separate from the OID) is fetched once on startup via `GetOverlays` and cached in `conf.id`. A mismatch between the stored `conf.id` and the real overlay causes silent failures, so the fetch must happen before the first state save.

**Required commands:**

| Command | Direction | Purpose |
|---|---|---|
| `GetOverlays` | GET-equivalent | Fetch the actual overlay UUID (`conf.id`) |
| `GetOverlayContent` | read | Fetch initial match state on startup |
| `SetOverlayContent` | write | Push updated match state after every score change |
| `GetCustomization` | read | Fetch team names, colors, logos on startup |
| `SetCustomization` | write | Push updated customization |
| `ShowOverlay` / `HideOverlay` | write | Toggle scoreboard visibility |
| `GetOverlayVisibility` | read | Sync visibility state on startup |

**Output URL resolution (overlays.uno):**

Call `GET https://app.overlays.uno/apiv2/controlapps/{oid}` to retrieve the `outputUrl` field. Extract the token from the path segment after `/output/` and use it to construct the browser-source URL shown in the Links dialog.

**Network requirements:**
- All requests must include a `User-Agent` header (configurable via `REST_USER_AGENT` env var; default `curl/8.15.0`).
- All requests must include `Content-Type: application/json` and `Accept: application/json, text/plain, */*`.
- Timeout per request: 5 s for reads, 5 s for writes.
- On `status >= 300` log a warning but do not crash; the app must remain operational when the overlay cloud is unreachable.
- Use a persistent HTTP session (keep-alive) to avoid TCP setup overhead on every score update.
- Multithreaded write: score-update saves should be dispatched to a thread pool (max 5 workers) so the UI is never blocked waiting for network.

### 9.3 Custom Overlay Protocol

When the OID starts with `C-`, the app communicates with a local server whose base URL is set via the `APP_CUSTOM_OVERLAY_URL` environment variable (default: `http://127.0.0.1:8000`). The `custom_id` used in URLs is the OID with the `C-` prefix removed and any `/style` suffix stripped.

**Required HTTP endpoints:**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/config/{custom_id}` | Fetch `outputUrl`, `availableStyles`, optional `controlWebSocketUrl` |
| `POST` | `/api/state/{custom_id}` | Push full normalized match-state payload (see §9.4) |
| `GET` | `/api/raw_config/{custom_id}` | Fetch raw model + customization blobs on startup |
| `POST` | `/api/raw_config/{custom_id}` | Persist raw model + customization blobs |

Timeouts: 5 s for GET `/api/config`, 2 s for all other calls.

**Output URL resolution (custom):**

1. Fetch `outputUrl` from `GET /api/config/{custom_id}`.
2. If `APP_CUSTOM_OVERLAY_OUTPUT_URL` is set, replace the host+port of the fetched URL with the value of that variable while keeping the path (which contains the output key). This is required when the overlay server is behind a reverse proxy.
3. If the env var is not set, use the fetched URL as-is.

**Initial state loading:**

On startup, call `GET /api/raw_config/{custom_id}`. The response must be `{ "model": {...}, "customization": {...} }`. If `model` is absent or empty, initialize with the default reset model. If `customization` is absent, initialize with the default customization state.

**Style locking:**

If the OID contains a `/style` suffix (e.g. `C-mybroadcast/line`), extract the style string and write it into the customization object as `preferredStyle: "line"`, then immediately persist it back via `POST /api/raw_config`.

### 9.4 Normalized State Payload

Every score or customization change that targets a custom overlay sends the following JSON body to `POST /api/state/{custom_id}`. This is also the format used over WebSocket `state_update` messages.

```jsonc
{
  "match_info": {
    "tournament": "Superliga Masculina",   // static placeholder
    "phase": "Playoffs",                   // static placeholder
    "best_of_sets": 5,                     // from conf.sets
    "current_set": 2,                      // 1-based active set index
    "show_only_current_set": false         // present only when simple mode is active
  },
  "team_home": {
    "name": "Home Team Name",
    "short_name": "HOM",                   // first 3 chars of name, uppercased
    "color_primary": "#2196f3",
    "color_secondary": "#ffffff",
    "logo_url": "https://...",
    "sets_won": 1,
    "points": 24,                          // current-set points only
    "serving": true,
    "timeouts_taken": 1,
    "set_history": {                       // all 5 sets always included
      "set_1": 25, "set_2": 24,
      "set_3": 0, "set_4": 0, "set_5": 0
    }
  },
  "team_away": { /* same shape as team_home */ },
  "overlay_control": {
    "show_main_scoreboard": true,          // present only when visibility changes
    "show_bottom_ticker": false,
    "ticker_message": "",
    "show_player_stats": false,
    "player_stats_data": null,
    "geometry": {
      "width": 30.0, "height": 0.0,
      "xpos": -45.0, "ypos": 40.0        // configured in customization panel
    },
    "colors": {
      "set_bg": "#333333", "set_text": "#ffffff",
      "game_bg": "#111111", "game_text": "#ffffff"
    },
    "preferredStyle": "line",             // from customization.preferredStyle
    "show_logos": true
  }
}
```

**Visibility-only updates** (eye icon toggle) include `show_main_scoreboard` in `overlay_control` and re-send the last known state. The WebSocket path sends a `visibility` message type instead (see §9.5).

### 9.5 WebSocket Control Channel (Custom Overlay, Optional)

If `GET /api/config/{custom_id}` returns a `controlWebSocketUrl` field, the app must open a persistent WebSocket to that URL on startup and use it in preference to HTTP for all subsequent state pushes.

**Message types the app sends:**

| Type | When | Payload |
|---|---|---|
| `state_update` | Every score/customization change | `{ "type": "state_update", "payload": <normalized state> }` |
| `visibility` | Eye icon toggle | `{ "type": "visibility", "show": true/false }` |
| `raw_config` | Save/reset actions | `{ "type": "raw_config", "payload": { "model": {...}, "customization": {...} } }` |
| `get_state` | On demand (e.g. after reconnect) | `{ "type": "get_state" }` |
| `ping` | Every ~25 s (heartbeat) | `{ "type": "ping" }` |

**Message types the app expects to receive:**

| Type | Action |
|---|---|
| `connected` | Validate `protocol == 1`; log warning on mismatch but continue. Parse `obs_clients` count. |
| `ack` | Confirm the last message was received; update `obs_clients` count from `ack.obs_clients` |
| `state` | Response to `get_state`; forwarded to the event callback |
| `pong` | Heartbeat acknowledged; no action needed |
| `obs_event` | Update the OBS client count shown in the UI |

**Connection setup:** `create_connection` uses a 10 s socket timeout. The heartbeat loop uses a 25 s recv timeout (inside the server's 30 s keepalive window); if recv times out, a `ping` is sent immediately.

**Reconnection:** uses exponential backoff — initial delay 1 s, doubling on each failure, capped at 30 s. The delay resets to 1 s on a successful connection. Reconnection continues indefinitely; there is no automatic fallback to HTTP after a fixed number of retries. The HTTP path is only used if `controlWebSocketUrl` was never present in the first place.

**HTTP fallback:** if `GET /api/config/{custom_id}` returns no `controlWebSocketUrl`, use the HTTP endpoints from §9.3 for all writes. Both modes must produce identical overlay behavior.

### 9.6 User Authentication and Per-User Overlay Configuration

When the `SCOREBOARD_USERS` environment variable is set, the app requires a login before showing the scoring screen. If the variable is absent or empty, authentication is skipped and the app runs open-access.

**`SCOREBOARD_USERS` format** — a JSON string (set as an env var):

```json
{
  "alice": {
    "password": "s3cret",
    "control": "abc123xyz",
    "output": "a1b2c3d4e5f6"
  },
  "bob": {
    "password": "hunter2",
    "control": "C-mybroadcast"
  }
}
```

- `password` — plain-text password checked at login.
- `control` — OID automatically stored on successful login. Bypasses the manual OID entry screen.
- `output` *(optional)* — overlays.uno output token. Stored as `https://app.overlays.uno/output/<token>` and used as the browser-source URL shown in the Links dialog. If absent, the output URL is auto-fetched from the backend as normal.

**Login flow:**

1. Any unauthenticated request (except `/login` and framework-internal routes) is redirected to `/login`.
2. The login page shows username + password fields.
3. On successful authentication: mark session as authenticated, store username, store `control` and `output` from the user's config entry, then redirect to the original requested path.
4. On failure: show `Messages.WRONG_USER_NAME` notification and stay on `/login`.
5. Logout clears all user session storage and navigates to `./`.

**Session isolation:** session state (`authenticated`, `configured_oid`, etc.) is stored in server-side session storage, keyed by session cookie. Two browser tabs belonging to the same user share the same session storage.

### 9.7 Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `UNO_OVERLAY_OID` | Yes (overlays.uno) | — | The overlay control OID for overlays.uno |
| `UNO_OVERLAY_ID` | No | fetched at startup | The internal UUID of the overlay layout (auto-fetched) |
| `UNO_OVERLAY_OUTPUT` | No | auto-fetched | Override the output/preview URL |
| `APP_CUSTOM_OVERLAY_URL` | Yes (custom) | `http://127.0.0.1:8000` | Base URL of the custom overlay HTTP server |
| `APP_CUSTOM_OVERLAY_OUTPUT_URL` | No | — | Public base URL for the overlay browser-source link |
| `REST_USER_AGENT` | No | `curl/8.15.0` | HTTP User-Agent sent with all backend requests |
| `MATCH_GAME_POINTS` | No | `25` | Points needed to win a regular set |
| `MATCH_GAME_POINTS_LAST_SET` | No | `15` | Points needed to win the deciding set |
| `MATCH_SETS` | No | `5` | Number of sets in the match (best-of) |
| `MINIMIZE_BACKEND_USAGE` | No | `true` | Cache model locally to reduce cloud API calls |
| `ENABLE_MULTITHREAD` | No | `true` | Dispatch backend writes to a thread pool |
| `AUTO_HIDE_ENABLED` | No | `false` | Auto-hide the scoreboard overlay after scoring |
| `DEFAULT_HIDE_TIMEOUT` | No | `5` | Seconds before auto-hide fires |
| `AUTO_SIMPLE_MODE` | No | `false` | Collapse to current-set-only view while playing |
| `AUTO_SIMPLE_MODE_TIMEOUT` | No | `false` | Switch back to full view when timeout is called |
| `SHOW_PREVIEW` | No | `false` | Show live overlay preview iframe in the control panel |
| `APP_DARK_MODE` | No | `auto` | Dark mode preference: `on`, `off`, `auto` |
| `SCOREBOARD_LANGUAGE` | No | `en` | UI language: `en` or `es` |
| `SINGLE_OVERLAY_MODE` | No | `true` | Disable multi-overlay switcher |
| `ORDERED_TEAMS` | No | `true` | Lock team order (home always left/top) |

---

## 10. State, Storage, and Multi-Browser Synchronization

### 10.1 Game and Customization State

No changes to the internal `State` or `GameManager` logic. The UI reads from and writes to these objects exactly as today.

### 10.2 Storage Scopes

The app uses two distinct storage scopes that must be kept separate:

| Scope | Storage Backend | Shared across tabs? | Purpose |
|---|---|---|---|
| **User/session storage** | Server-side session store | Yes — same session cookie | Authentication state, OID, current game model, display preferences (auto-hide, simple mode, show preview, lock flags) |
| **Browser-local storage** | Browser `localStorage` | No — per tab | Visual-only button settings that each scorer may want independently |

The following keys are **browser-local** and must never be included in any cross-tab broadcast:

- `buttons_follow_team_colors`
- `team_1_button_color` / `team_1_button_text_color`
- `team_2_button_color` / `team_2_button_text_color`
- `selected_font`
- `buttons_show_icon`
- `buttons_icon_opacity`

All other AppStorage keys use user/session storage and are shared across tabs of the same session.

### 10.3 Multi-Browser (Multi-Tab) Synchronization

Multiple browser tabs or devices can open the scoring screen simultaneously and control the same overlay. The app uses in-process in-memory broadcasting rather than polling or WebSockets between tabs.

**Instance registry:** every active UI instance (one per connected browser client) is held in a server-side registry. Instances are automatically removed when the browser disconnects.

**Broadcast on every state change:** after any action that modifies game or customization state, the acting instance:

1. Saves state to the backend (overlay push + local cache).
2. Iterates all other registered instances that are still connected.
3. For each, deep-copies the current game model and customization model directly into that instance's in-memory state — no HTTP re-fetch.
4. Calls that instance's UI update methods synchronously within its client context.

**Visibility broadcast:** visibility changes use a dedicated lighter broadcast that only propagates the boolean flag, not the full model.

**What is NOT broadcast:**
- Browser-local visual settings (button colors, font, icon — see §10.2). Each tab keeps its own.
- The `simple` mode toggle state (each tab tracks this independently for its own view).

**Failure handling:** if a registered instance's client context is stale or disconnected, that instance is skipped silently. The registry eventually drops it when it is cleaned up.

**Consequence for the UI spec:** the scoring buttons and all displayed values (score, sets, serve, timeouts) must be updatable by an external broadcast at any time, not just by local user action. All UI elements that reflect game state must be bound to or refreshable from the shared state object.

### 10.4 New AppStorage Keys

The following `AppStorage` category keys are added by this spec:

| Key | Scope | Type | Default | Purpose |
|---|---|---|---|---|
| `TAP_LOCK_ACTIVE` | session | `bool` | `false` | Per-session tap lock state (resets on page reload) |
| `CONTROL_BAR_EXPANDED` | browser-local | `bool` | `false` | Remember whether the control bar is pinned open |

---

## 11. Affected Files

| File | Change Type |
|---|---|
| `app/gui.py` | Update orientation detection, button sizing for both phone layouts |
| `app/components/team_panel.py` | Refactor for portrait row and landscape column layouts |
| `app/components/center_panel.py` | Compact set table, hide preview on phone, portrait center band |
| `app/components/control_buttons.py` | Extract into collapsible overlay bar (both orientations) |
| `app/components/button_interaction.py` | Add swipe-left gesture for undo |
| `app/options_dialog.py` | Convert to bottom drawer, add Match section |
| `app/theme.py` | Add breakpoint constants (portrait/landscape phone thresholds) |
| `app/app_storage.py` | Add `TAP_LOCK_ACTIVE` and `CONTROL_BAR_EXPANDED` categories |
| `app/backend.py` | No structural changes; env vars documented in §9.6 |
| `app/pwa/manifest.json` | No change |

New files:
- `app/components/tap_lock.py` — manages tap lock state and the lock overlay element.
- `app/components/control_bar.py` — collapsible bottom bar extracted from `ControlButtons`.

---

## 12. Testing Requirements

### 12.1 Viewport Tests (Playwright)

Extend the existing mobile viewport test suite (`tests/test_mobile_viewport.py`) with the following cases:

| Test | Viewport (w × h px) | Assertion |
|---|---|---|
| Score buttons fill majority of team columns (landscape) | 667 × 375 | Each score button height ≥ 200 px |
| Score buttons fill majority of team rows (portrait) | 375 × 667 | Each score button width ≥ 200 px |
| No horizontal scroll (landscape) | 568 × 320 | `document.body.scrollWidth <= 568` |
| No vertical scroll (portrait) | 375 × 667 | `document.body.scrollHeight <= 667` |
| Control bar hidden by default | 667 × 375 | Control bar element not visible |
| Control bar shows on handle tap | 667 × 375 | Control bar visible after tap on handle |
| Tap-lock prevents scoring | 667 × 375 | Score does not change when lock is active |
| Swipe-left triggers undo (landscape) | 667 × 375 | Score decrements on synthesized swipe-left |
| Swipe-left triggers undo (portrait) | 375 × 667 | Score decrements on synthesized swipe-left |
| Serve icon tap target ≥ 44 px | 667 × 375 | Computed touch area ≥ 44 × 44 px |
| Options drawer slides up | 667 × 375 | Drawer visible after options button tap |
| Tablet layout unchanged | 1024 × 768 | Layout matches current landscape behavior |
| Desktop layout unchanged | 1280 × 800 | Layout matches current landscape behavior |

### 12.2 Unit Tests

- `GameManager` and `State`: no new unit tests (no logic changes).
- `ButtonInteraction`: add tests for swipe-left detection and threshold conditions (≥ 40 dp horizontal, < 30 dp vertical).
- `AppStorage`: add tests for the two new categories.
- `Backend` overlay connectivity: existing tests cover the HTTP paths; add a test for WS reconnection fallback to HTTP.

---

## 13. Out of Scope

- Server-side rendering optimizations.
- Changes to the normalized state payload schema or custom overlay API contract.
- Internationalization of new UI strings (English first; Spanish strings can be added in a follow-up).
- Tablet-specific layout improvements.
- Multi-overlay switcher UI changes.
