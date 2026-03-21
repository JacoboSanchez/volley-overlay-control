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
| `SCOREBOARD_USERS` | No | — | JSON string mapping usernames to passwords and OIDs (see §9.6) |
| `APP_TEAMS` | No | — | JSON string of predefined team presets for the customization picker |
| `APP_THEMES` | No | — | JSON string of named color themes available in the customization panel |
| `APP_DEFAULT_LOGO` | No | CDN volleyball icon | Default logo URL applied when no team logo has been configured |
| `HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED` | No | — | Hide the manual OID text field when predefined overlays are configured |
| `PREDEFINED_OVERLAYS` | No | — | JSON list of pre-configured OID entries shown in the OID selection dialog |
| `REMOTE_CONFIG_URL` | No | — | URL of a remote JSON endpoint that overrides env vars; polled with a 10 s cache |
| `LOGGING_LEVEL` | No | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

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

### 10.4 AppStorage Key Reference

The complete set of `AppStorage` category keys used across the application. New keys introduced by this spec are marked *(new)*.

**Session-scoped keys** (shared across all tabs of the same authenticated session):

| Key | Type | Default | Purpose |
|---|---|---|---|
| `USERNAME` | `str` | — | Authenticated user's name |
| `AUTHENTICATED` | `bool` | `false` | Whether the current session has passed login |
| `CONFIGURED_OID` | `str` | — | Active overlay control OID for this session |
| `CONFIGURED_OUTPUT` | `str` | — | Active overlay output URL for this session |
| `CURRENT_MODEL` | `dict` | — | Cached game state model (overlays.uno only; custom overlays use their own server) |
| `REDIRECT_PATH` | `str` | `/` | Path to redirect to after successful login |
| `SIMPLE_MODE` | `bool` | `false` | Whether the scoreboard is in simple (current-set-only) mode |
| `DARK_MODE` | `str` | `auto` | Dark mode preference for this session: `on`, `off`, or `auto` |
| `AUTOHIDE_ENABLED` | `bool` | env var | Session override for auto-hide enabled flag |
| `AUTOHIDE_SECONDS` | `int` | env var | Session override for auto-hide delay in seconds |
| `SIMPLIFY_OPTION_ENABLED` | `bool` | env var | Session override for auto-simple-mode flag |
| `SIMPLIFY_ON_TIMEOUT_ENABLED` | `bool` | env var | Session override: revert to full view when timeout is called |
| `SHOW_PREVIEW` | `bool` | env var | Session override for live preview iframe visibility |
| `LOCK_TEAM_A_ICONS` | `bool` | `false` | Prevent Team A logo from being changed (per-OID) |
| `LOCK_TEAM_B_ICONS` | `bool` | `false` | Prevent Team B logo from being changed (per-OID) |
| `LOCK_TEAM_A_COLORS` | `bool` | `false` | Prevent Team A colors from being changed (per-OID) |
| `LOCK_TEAM_B_COLORS` | `bool` | `false` | Prevent Team B colors from being changed (per-OID) |
| `TAP_LOCK_ACTIVE` *(new)* | `bool` | `false` | Per-session tap lock state (resets on page reload) |

**Browser-local keys** (isolated per browser tab — never broadcast to other clients):

| Key | Type | Default | Purpose |
|---|---|---|---|
| `BUTTONS_FOLLOW_TEAM_COLORS` | `bool` | `false` | Score buttons inherit team colors from customization |
| `TEAM_1_BUTTON_COLOR` | `str` | `#2196f3` | Team 1 score button background color |
| `TEAM_1_BUTTON_TEXT_COLOR` | `str` | `#ffffff` | Team 1 score button text color |
| `TEAM_2_BUTTON_COLOR` | `str` | `#f44336` | Team 2 score button background color |
| `TEAM_2_BUTTON_TEXT_COLOR` | `str` | `#ffffff` | Team 2 score button text color |
| `SELECTED_FONT` | `str` | `Default` | Score button font family name |
| `BUTTONS_SHOW_ICON` | `bool` | `false` | Show team logo icon overlaid on score button |
| `BUTTONS_ICON_OPACITY` | `float` | — | Opacity of the team logo icon overlay |
| `CONTROL_BAR_EXPANDED` *(new)* | `bool` | `false` | Remember whether the control bar is pinned open |

---

## 11. Affected Files

### 11.1 Modified Files

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

### 11.2 New Files (this spec)

- `app/components/tap_lock.py` — manages tap lock state and the lock overlay element.
- `app/components/control_bar.py` — collapsible bottom bar extracted from `ControlButtons`.

### 11.3 Complete File Inventory (existing codebase)

All files that make up the full application, for reference when rebuilding from scratch:

| File | Role |
|---|---|
| `main.py` | Entry point; starts the server via `startup()` |
| `app/startup.py` | Registers all routes, static files, PWA assets, and middleware |
| `app/gui.py` | Main scoring UI; orientation detection; multi-tab broadcast registry |
| `app/gui_update_mixin.py` | `UIUpdateMixin` base class providing update methods called by broadcasts |
| `app/game_manager.py` | Game logic (points, sets, timeouts, serve, win detection) |
| `app/state.py` | `State` data model and `simplify_model` helper |
| `app/backend.py` | All overlay HTTP/WS communication (overlays.uno + custom) |
| `app/ws_client.py` | Persistent WebSocket client for custom overlay servers |
| `app/conf.py` | `Conf` configuration object populated from env vars + session storage |
| `app/app_storage.py` | `AppStorage` abstraction (session store + browser-local store) |
| `app/authentication.py` | `AuthMiddleware` + `PasswordAuthenticator` (login flow) |
| `app/customization.py` | `Customization` data model and accessors |
| `app/customization_page.py` | Configuration tab UI (team names, colors, logos, geometry) |
| `app/options_dialog.py` | Options/settings dialog (auto-hide, simple mode, fonts, colors) |
| `app/oid_dialog.py` | OID entry dialog (first-launch and "Change Overlay" flow) |
| `app/preview_page.py` | Standalone `/preview` route with scale/dark-mode controls |
| `app/preview.py` | `create_iframe_card` helper used by preview page and inline preview |
| `app/env_vars_manager.py` | Environment variable resolution with optional remote config override |
| `app/conf.py` | Runtime `Conf` object; reads env vars + per-session storage overrides |
| `app/messages.py` | Localised string constants (`en` / `es`) |
| `app/logging_config.py` | Logging setup controlled by `LOGGING_LEVEL` env var |
| `app/theme.py` | UI style constants, color names, font scaling multipliers |
| `app/components/score_button.py` | Score button widget |
| `app/components/button_style.py` | Button visual style helpers |
| `app/components/button_interaction.py` | Tap / double-tap / long-press / swipe gesture detection |
| `app/components/team_panel.py` | Team column/row layout (score button + serve + sets + timeouts) |
| `app/components/center_panel.py` | Center strip / band (set history table, set selector, status) |
| `app/components/control_buttons.py` | Collapsible control bar (undo, lock, visibility, options, …) |
| `app/pwa/manifest.json` | PWA manifest (fullscreen display, icons, theme color) |
| `app/pwa/sw.js` | Service worker for offline caching |
| `app/pwa/icon-*.png` | PWA icons (192 × 192, 512 × 512) |
| `font/` | Optional custom font files (TTF/OTF/WOFF/WOFF2) loaded at runtime |

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

---

## 14. Data Models

This section documents all internal data models so the application can be rebuilt without reading the existing implementation.

### 14.1 Game State Model (`State`)

The game state is a flat string-keyed dictionary. All values are stored as strings. The reset (initial) state is:

```json
{
  "Serve":                    "None",
  "Team 1 Sets":              "0",
  "Team 2 Sets":              "0",
  "Team 1 Game 1 Score":      "0",
  "Team 1 Game 2 Score":      "0",
  "Team 1 Game 3 Score":      "0",
  "Team 1 Game 4 Score":      "0",
  "Team 1 Game 5 Score":      "0",
  "Team 2 Game 1 Score":      "0",
  "Team 2 Game 2 Score":      "0",
  "Team 2 Game 3 Score":      "0",
  "Team 2 Game 4 Score":      "0",
  "Team 2 Game 5 Score":      "0",
  "Team 1 Timeouts":          "0",
  "Team 2 Timeouts":          "0",
  "Current Set":              "1"
}
```

**Serve values:** `"None"` (no server), `"A"` (Team 1 serving), `"B"` (Team 2 serving).

**Special constant:** `CHAMPIONSHIP_LAYOUT_ID = "446a382f-25c0-4d1d-ae25-48373334e06b"` — when `conf.id` matches this value, a `"Sets Display"` key is injected into the payload sent to the overlay, set to the current set number as a string.

**OID validation statuses:** `VALID`, `INVALID`, `DEPRECATED`, `EMPTY`.
- `DEPRECATED` is returned when the fetched model contains a `game1State` key (legacy schema).

**`simplify_model` transformation:** collapses all set history to Set 1 only. Copies the current-set scores into `Team 1 Game 1 Score` / `Team 2 Game 1 Score`, then zeroes out all other set score keys. Used when simple mode is active to send a one-set view to the overlay.

### 14.2 Customization Model (`Customization`)

The customization state is a flat string-keyed dictionary. Default (reset) values:

| Key | Default | Type | Purpose |
|---|---|---|---|
| `"Team 1 Text Name"` | `""` | string | Team 1 display name (legacy key; new key is `"Team 1 Name"`) |
| `"Team 2 Text Name"` | `""` | string | Team 2 display name (legacy key; new key is `"Team 2 Name"`) |
| `"Logos"` | `"true"` | bool-string | Show team logos on the overlay |
| `"Gradient"` | `"true"` | bool-string | Apply gloss/gradient effect on the overlay |
| `"Height"` | `10` | float | Overlay height as a percentage of the scene |
| `"Left-Right"` | `-33` | float | Horizontal position (negative = left of center) |
| `"Up-Down"` | `-41.1` | float | Vertical position (negative = above center) |
| `"Width"` | `30` | float | Overlay width as a percentage of the scene |
| `"Team 1 Color"` | `"#060f8a"` | hex | Team 1 primary/background color |
| `"Team 1 Text Color"` | `"#ffffff"` | hex | Team 1 text/secondary color |
| `"Team 1 Logo"` | CDN URL | URL | Team 1 logo image URL |
| `"Team 1 Logo Fit"` | `"contain"` | string | CSS `object-fit` for Team 1 logo (`"contain"` or `"cover"`) |
| `"Team 2 Color"` | `"#ffffff"` | hex | Team 2 primary/background color |
| `"Team 2 Text Color"` | `"#000000"` | hex | Team 2 text/secondary color |
| `"Team 2 Logo"` | CDN URL | URL | Team 2 logo image URL |
| `"Team 2 Logo Fit"` | `"contain"` | string | CSS `object-fit` for Team 2 logo |
| `"Color 1"` | `"#2a2f35"` | hex | Set-wins background color |
| `"Text Color 1"` | `"#ffffff"` | hex | Set-wins text color |
| `"Color 2"` | `"#ffffff"` | hex | Game-score background color |
| `"Text Color 2"` | `"#2a2f35"` | hex | Game-score text color |
| `"Color 3"` | `"0055ff"` | hex | Additional accent color |
| `"Text Color 3"` | `"FFFFFF"` | hex | Additional accent text color |
| `"preferredStyle"` | `null` | string or null | Overlay style variant key (e.g. `"line"`) |

**Team name backward compatibility:** both `"Team 1 Text Name"` (legacy) and `"Team 1 Name"` (new) are accepted. Reads prefer the legacy key if present.

**Logo URL normalization:** URLs beginning with `"//"` are prefixed with `"https:"` before use.

**Predefined teams** (`APP_TEAMS` env var): a JSON object where each key is a team name and the value is `{ "icon": "<url>", "color": "<hex>", "text_color": "<hex>" }`. If not set, defaults to two entries labelled with the configured language's "Local" and "Visitor" strings.

**Themes** (`APP_THEMES` env var): a JSON object where each key is a theme name and the value is a partial customization object applied as an overlay on top of the current state when selected.

### 14.3 Configuration Object (`Conf`)

Runtime configuration loaded from env vars at startup, with some properties overridable by session storage:

| Property | Source | Default | Notes |
|---|---|---|---|
| `id` | `UNO_OVERLAY_ID` env var | `"8637cb0f-df01-45bb-9782-c6d705aeff46"` | Auto-updated after `GetOverlays` call |
| `oid` | `UNO_OVERLAY_OID` env var | `null` | Set to URL param / storage value before use |
| `output` | `UNO_OVERLAY_OUTPUT` env var | `null` | Output URL; auto-fetched if absent |
| `rest_user_agent` | `REST_USER_AGENT` env var | `"curl/8.15.0"` | Sent as HTTP `User-Agent` |
| `darkMode` | `APP_DARK_MODE` env var | `"auto"` | `"on"`, `"off"`, or `"auto"` |
| `multithread` | `ENABLE_MULTITHREAD` env var | `true` | Dispatch saves to thread pool |
| `cache` | `MINIMIZE_BACKEND_USAGE` env var | `true` | Cache model in session to avoid re-fetching |
| `orderedTeams` | `ORDERED_TEAMS` env var | `true` | Lock home team to left/top position |
| `points` | `MATCH_GAME_POINTS` env var | `25` | Points to win a regular set |
| `points_last_set` | `MATCH_GAME_POINTS_LAST_SET` env var | `15` | Points to win the deciding set |
| `sets` | `MATCH_SETS` env var | `5` | Best-of sets count |
| `single_overlay` | `SINGLE_OVERLAY_MODE` env var | `true` | Disable multi-overlay switcher |
| `show_overview` | `SHOW_PREVIEW` env var | `false` | Show inline preview iframe |
| `auto_hide` | session → `AUTO_HIDE_ENABLED` | `false` | Session value takes priority over env var |
| `hide_timeout` | session → `DEFAULT_HIDE_TIMEOUT` | `5` | Session value takes priority over env var |
| `auto_simple_mode` | session → `AUTO_SIMPLE_MODE` | `false` | Session value takes priority over env var |
| `auto_simple_mode_timeout` | session → `AUTO_SIMPLE_MODE_TIMEOUT` | `false` | Session value takes priority over env var |
| `show_preview` | session → `SHOW_PREVIEW` | `false` | Session value takes priority over env var |
| `lock_teamA_icons` | session (per-OID) | `false` | Stored under the OID namespace |
| `lock_teamB_icons` | session (per-OID) | `false` | Stored under the OID namespace |
| `lock_teamA_colors` | session (per-OID) | `false` | Stored under the OID namespace |
| `lock_teamB_colors` | session (per-OID) | `false` | Stored under the OID namespace |

---

## 15. Game Logic

### 15.1 GameManager

`GameManager` owns all mutable game state and exposes the following operations:

| Method | Description |
|---|---|
| `add_game(team, current_set, points_limit, points_limit_last_set, sets_limit, undo)` | Add or remove a point; triggers `add_set` if the set is won/un-won. Returns `True` if set state changed. |
| `add_set(team, undo)` | Add or remove a set won. On new set: resets both teams' timeouts to 0 and clears serve. |
| `add_timeout(team, undo)` | Increment or decrement a team's timeout count (clamped 0–2). |
| `change_serve(team, force)` | Set the serving team. Passing `team=0` clears serve. If `force=False` and the team is already serving, serve is cleared (toggle). |
| `set_game_value(team, value, current_set)` | Directly set a team's score for the current set. |
| `set_sets_value(team, value)` | Directly set a team's sets-won count. |
| `match_finished()` | Returns `True` when either team has won ⌈sets/2⌉ sets. |
| `check_set_won(team, current_set, points_limit, points_limit_last_set, sets_limit)` | Re-check win condition after a direct score update; triggers `add_set` if met. |
| `save(simple, current_set)` | Persist state to backend (with optional simplification). |
| `reset()` | Reset state to `State.reset_model` and persist. |

**Win condition:** a score wins a set when `score >= limit AND score − rival_score > 1` (standard rally-point with deuce).

**Points limit selection:** the deciding set (set index equals `sets_limit`) uses `points_limit_last_set`; all other sets use `points_limit`.

**Match win:** `⌈conf.sets / 2⌉ + 1` sets required (soft ceiling: a best-of-5 requires 3 sets).

### 15.2 OID Resolution Priority

When a scoring page loads, the OID is resolved in this priority order:

1. **URL query parameter** `?control=<oid>` — validated immediately; if valid, used and stored.
2. **Session storage** (`CONFIGURED_OID`) — validated; if valid, used as-is.
3. **Environment variable** `UNO_OVERLAY_OID` — only checked when `SINGLE_OVERLAY_MODE=true` and no URL param was provided.
4. **OID dialog** — shown when all above sources yield no valid OID.

After resolving, if no output URL is available from the same source, `fetch_output_token(oid)` is called automatically to obtain the browser-source URL.

---

## 16. Application Routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Main scoring screen (uses `MATCH_*` env var defaults) |
| `GET` | `/indoor` | Scoring screen preset: 25 pts / 15 last-set / best-of-5 |
| `GET` | `/beach` | Scoring screen preset: 21 pts / 15 last-set / best-of-3 |
| `GET` | `/login` | Login page (shown when `SCOREBOARD_USERS` is set) |
| `GET` | `/preview` | Standalone overlay preview with geometry and scale controls |
| `GET` | `/health` | Health check endpoint; returns `{ "status": "ok", "timestamp": <unix>, "service": "volley-overlay-control" }` |
| `GET` | `/manifest.json` | PWA web app manifest |
| `GET` | `/sw.js` | Service worker script |
| `GET` | `/fonts/*` | Static font files from the `font/` directory |
| `GET` | `/pwa/*` | Static PWA assets (icons, etc.) |

**Query parameters supported on `/`, `/indoor`, `/beach`:**
- `control=<oid>` — pre-populate and auto-validate the OID (skips dialog).
- `output=<token-or-url>` — override the output/browser-source URL.
- `logout=true` — clear session storage and reload.

**Query parameters supported on `/preview`:**
- `control=<oid>` — fetch geometry and output URL automatically from backend.
- `output=<token-or-url>` — output URL (used if `control` does not provide one).
- `x`, `y`, `width`, `height` — geometry overrides (floats; fetched from customization if omitted).
- `layout_id=<uuid>` — overlay layout UUID override.

---

## 17. PWA and Browser Integration

### 17.1 Service Worker

Registered at `/sw.js`. Provides offline caching so the control app remains usable when the network drops briefly during a match.

### 17.2 Screen Wake Lock

Acquired on page load using the `navigator.wakeLock.request('screen')` API. Re-requested whenever the page regains visibility (`visibilitychange` event). Falls back silently when the browser does not support the API. This prevents the phone from locking the screen during a match.

### 17.3 Resize Events

A `resize` event is emitted via the framework's client-side event bus whenever `window.innerWidth` or `window.innerHeight` changes. The server-side handler calls `set_page_size(width, height)` on the scoring page, which re-evaluates orientation and rebuilds the layout if the class boundary has been crossed.

For non-phone viewports (width < 650 px and not portrait), a CSS `transform: scale()` is applied to the main tab panel so the content fits without a scrollbar, preserving the desktop-designed layout on smaller non-phone windows.

### 17.4 Custom Font Loading

At page load, the server reads all files in the `font/` directory with extensions `.ttf`, `.otf`, `.woff`, or `.woff2`. For each file, a `@font-face` CSS rule is injected into the page head, making the font available under its filename (without extension) as a selectable option in the options dialog.

Font names with known visual sizing differences are listed in `theme.FONT_SCALES` with a `scale` multiplier and `offset_y` percentage applied to the score button text to normalize visual size across fonts.

### 17.5 PWA Manifest

The manifest configures the app as a `fullscreen` PWA with a `#1976d2` theme color and a 192 × 192 icon. When installed, the app launches without browser chrome.

---

## 18. Authentication System

### 18.1 Middleware

An HTTP middleware intercepts every request before routing. It exempts:
- Framework-internal routes (paths starting with the framework's internal prefix).
- The `/preview` route.
- The `/login` page itself.

All other requests from unauthenticated sessions are redirected to `/login`, with the original path saved to session storage as `REDIRECT_PATH`.

Authentication is only active when `SCOREBOARD_USERS` is set and non-empty. When absent, the middleware passes all requests through unchanged.

### 18.2 Login Page

A centered card with:
- Username text input
- Password text input (with toggle to reveal)
- Login button (also triggered by pressing Enter in the password field)

On successful login:
1. `AUTHENTICATED = true` and `USERNAME = <username>` are saved to session storage.
2. The `control` OID from the user's config is saved as `CONFIGURED_OID`.
3. If the user's config includes an `output` token, it is stored as `CONFIGURED_OUTPUT` with the prefix `https://app.overlays.uno/output/` prepended if not already a full URL.
4. The user is redirected to `REDIRECT_PATH` (defaulting to `/`).

On failure: a notification is shown and the form remains visible.

### 18.3 Logout

Clears all session storage (both user/session and browser-local scopes) and navigates to `./`.

---

## 19. Theme and Visual Style Constants

The following constants from `app/theme.py` are used throughout the UI and must be reproduced in any reimplementation:

**Team accent colors:**
- Team A: `blue` / light variants `indigo-5`
- Team B: `red` / light variants `indigo-5`

**Control button colors:**
- Undo mode active: `indigo-400`
- Normal mode: `indigo-700`
- Overlay visible: `green-600`
- Overlay hidden: `green-800`
- Full scoreboard mode: `orange-500`
- Simple scoreboard mode: `orange-700`

**Default score button colors:**
- Team 1 background: `#2196f3` (blue)
- Team 2 background: `#f44336` (red)
- Text: `#ffffff`

**Control button size:** `w-9 h-9 rounded-lg` (36 × 36 dp).

**Font scaling multipliers** (applied to score button font size to normalize visual weight):

| Font name | Scale | Vertical offset |
|---|---|---|
| Default | 1.00 | 0.00 |
| Digital Dismay | 1.16 | 0.01 |
| Aluminum | 1.06 | 0.02 |
| Atlas | 0.96 | 0.01 |
| Bypass | 0.96 | 0.00 |
| Catch | 1.17 | 0.01 |
| Devotee | 1.14 | 0.02 |
| Digital Readout | 1.39 | 0.00 |
| LED board | 0.79 | −0.01 |
| Open 24 | 1.14 | −0.02 |
| Alarm Clock | 1.01 | 0.01 |
