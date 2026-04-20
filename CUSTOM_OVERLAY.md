# Custom Overlays

## Built-In Overlay Engine

Remote-Scoreboard includes a **built-in overlay engine** that serves custom overlays in-process — no external server is needed. Overlays must be created up-front from the `/manage` page (protected by `OVERLAY_MANAGER_PASSWORD`); the system never auto-creates overlays from the control UI. Once an overlay named e.g. `mybroadcast` exists, the system:

1. Persists state to `data/overlay_state_mybroadcast.json`
2. Serves 16 overlay style templates at `/overlay/{id}` (for OBS browser sources)
3. Broadcasts real-time updates to OBS via WebSocket at `/ws/{id}`

The overlay's name is used directly as the OID in the control UI.

> **Backward compatibility:** the legacy `C-<id>` syntax (e.g. `C-mybroadcast`) is still accepted when the overlay already exists, but it is no longer the recommended form and is omitted from the documentation and UI.

### 🖼️ Style Preview Grid (`?style=mosaic`)

To compare every overlay style side-by-side — useful when deciding which layout fits your broadcast — open:

```
/overlay/{id}?style=mosaic
```

The page renders every selectable style in a responsive grid of iframes, each cropped to the actual overlay bounds, so differences in layout and color are easy to spot. Live state changes propagate to every cell via the same WebSocket used by individual overlays.

`mosaic` is a **meta-style**: it is never returned in `availableStyles` from `/api/config/{id}`, so it cannot be selected as an overlay's `preferredStyle` and does not appear in the style picker. It is only reachable via the explicit `?style=mosaic` query parameter.

---

## Building a Custom External Overlay Server

If you need a fully custom overlay engine (e.g., built in React, Vue, Godot, or another framework), you can point Remote-Scoreboard at an **external overlay server** by setting `APP_CUSTOM_OVERLAY_URL`. This disables the built-in engine for custom overlays and instead communicates with your server via HTTP/WebSocket.

This document outlines the API contract that your external custom overlay must implement.

> [!TIP]
> **Quick Start Checklist** — Your custom overlay server must:
> 1. Implement `GET /api/config/{id}` returning `{ "outputUrl": "...", "availableStyles": [...] }`
> 2. Implement `POST /api/state/{id}` accepting the full match state JSON
> 3. Implement `GET /api/raw_config/{id}` and `POST /api/raw_config/{id}` for state persistence
> 4. Return `200 OK` within 2 seconds on POST requests
> 5. *(Optional)* Implement `/ws/control/{id}` WebSocket endpoint and return `controlWebSocketUrl` in `/api/config` for low-latency persistent connections

---

## 🔗 The Connection Protocol

When the user enters an overlay ID that resolves to a custom overlay **and** `APP_CUSTOM_OVERLAY_URL` is set, Remote-Scoreboard identifies this as a **Custom External Overlay**.

It will then communicate directly with your custom overlay server using the Base URL defined in the `APP_CUSTOM_OVERLAY_URL` environment variable.

> [!NOTE]
> If `APP_CUSTOM_OVERLAY_URL` is **not** set, custom overlays use the built-in overlay engine (see above) and none of the endpoints described below need to be implemented.

**Output URL resolution**

Remote-Scoreboard determines the final output URL shown in the "Links" dialog using the following logic:

1.  It fetches the `outputUrl` from your `/api/config/{id}` endpoint.
2.  If `APP_CUSTOM_OVERLAY_OUTPUT_URL` is set, Remote-Scoreboard replaces the host and port of the fetched `outputUrl` with the value from this environment variable, but preserves the path (which should contain the `outputKey`). This is useful when the overlay server is behind a proxy or on a different network.
3.  If `APP_CUSTOM_OVERLAY_OUTPUT_URL` is **not** set, Remote-Scoreboard uses the `outputUrl` from your server as-is. Ensure your overlay server returns a publicly accessible URL in this case (e.g., by configuring its own `OVERLAY_PUBLIC_URL`).

The `custom_id` passed to your server is the bare overlay ID (the legacy `C-` prefix, when present, is stripped before forwarding).

**Styling Support**
Users can append a specific style constraint to their overlay ID using the `/` separator (e.g., `mybroadcast/line`). This specifies to the system exactly which layout template to use.
Alternatively, users can change the current layout directly from the Remote-Scoreboard controller UI using the "Preferred Style" dropdown options fetched from your `/api/config/{custom_id}` endpoint.
Remote-Scoreboard will send `preferredStyle` inside the `overlay_control` block of the JSON payload, and custom overlays can default to this style when the output URL has no explicit `?style` query constraint.

---

## 📡 Required Endpoints

Your custom overlay HTTP server must expose the following three REST endpoints:

### 1. The Output Configuration Endpoint

**Endpoint:** `GET /api/config/{custom_id}`

This endpoint is polled by Remote-Scoreboard when the user attempts to view the overlay link or preview it in the controller.

#### Expected Response (JSON):
```json
{
  "outputUrl": "http://127.0.0.1:8000/overlay/a1b2c3d4e5f6",
  "outputKey": "a1b2c3d4e5f6",
  "availableStyles": ["default", "line", "minimal"],
  "controlWebSocketUrl": "ws://127.0.0.1:8000/ws/control/mybroadcast"
}
```

*   `outputUrl` **(Required)**: The absolute URL where the actual graphical view of the overlay can be accessed (the link that gets pasted into OBS/vMix). This URL should use the `outputKey` (see below) instead of the raw overlay name so that the public URL is not easily guessable.
*   `outputKey` *(Recommended)*: A short deterministic hash of the overlay name that acts as an alias in the `/overlay/` output path. Remote-Scoreboard uses this key when composing the output URL shown to users. The overlay server must accept both the overlay name and the output key as valid identifiers in `/overlay/{id}`.
*   `availableStyles` *(Optional)*: A list of strings representing different visual themes or styles your overlay supports.
*   `controlWebSocketUrl` *(Optional)*: A WebSocket URL for the persistent control channel. When present, Remote-Scoreboard will open a WebSocket connection for low-latency state pushes instead of polling via HTTP POST. If absent, HTTP-only mode is used (fully backward-compatible).

### 2. The State Update Endpoint

**Endpoint:** `POST /api/state/{custom_id}`

This is the core communication channel. Whenever a score changes, a timeout is called, or a color is modified in the Remote-Scoreboard UI, the backend will issue a POST request to this endpoint containing the complete state of the match.

#### Request Body (JSON Payload):
```json
{
  "match_info": {
    "tournament": "Superliga Masculina",
    "phase": "Playoffs",
    "best_of_sets": 5,
    "current_set": 2,
    "show_only_current_set": false
  },
  "team_home": {
    "name": "Home Team Name",
    "short_name": "HOM",
    "color_primary": "#E21836",
    "color_secondary": "#FFFFFF",
    "logo_url": "https://url-to-logo.png",
    "sets_won": 1,
    "points": 24,
    "serving": true,
    "timeouts_taken": 1,
    "set_history": {
      "set_1": 25,
      "set_2": 24,
      "set_3": 0,
      "set_4": 0,
      "set_5": 0
    }
  },
  "team_away": {
    "name": "Away Team Name",
    "short_name": "AWA",
    "color_primary": "#0047AB",
    "color_secondary": "#FFD700",
    "logo_url": "",
    "sets_won": 0,
    "points": 22,
    "serving": false,
    "timeouts_taken": 2,
    "set_history": {
      "set_1": 23,
      "set_2": 22,
      "set_3": 0,
      "set_4": 0,
      "set_5": 0
    }
  },
  "overlay_control": {
    "show_main_scoreboard": true,
    "show_bottom_ticker": false,
    "ticker_message": "Match delayed by 5 minutes",
    "show_player_stats": false,
    "player_stats_data": null,
    "geometry": {
      "width": 30.0,
      "height": 0.0,
      "xpos": -45.0,
      "ypos": 40.0
    },
    "colors": {
      "set_bg": "#333333",
      "set_text": "#FFFFFF",
      "game_bg": "#111111",
      "game_text": "#FFFFFF"
    },
    "preferredStyle": "line"
  }
}
```

### 3. The Raw Configuration Pass-Through Endpoint

**Endpoints:** `GET /api/raw_config/{custom_id}` and `POST /api/raw_config/{custom_id}`

For performance and stateless architecture reasons `remote-scoreboard` no longer stores custom overlay state files on its own local disk. Instead, it expects the custom overlay server to host an arbitrary storage bucket per overlay ID.
When `remote-scoreboard` boots up or users click save, it will heavily utilize these endpoints to read and persist its own raw underlying JSON models alongside the custom overlay instance without parsing them.

* **GET**: Must return `{ "model": { ... }, "customization": { ... } }`.
* **POST**: Must accept the same shape (or just one key at a time) and persist it against `{custom_id}`.

#### Payload Field Descriptions

*   `match_info`: General global match attributes.
    *   `show_only_current_set` *(Boolean)*: High-level hint driven by the "Simple Mode" toggle in the backend. When true, you should hide previous set history rendering.
*   `team_home` / `team_away`: Represents the two sides of the net.
    *   `short_name`: First 3 characters of the name by default.
    *   `color_primary` / `color_secondary`: Used for backgrounds and text.
    *   `serving` *(Boolean)*: True if this team is currently serving.
    *   `set_history`: A dictionary mapping `set_1` through `set_5` to the points scored by this team in those respective sets.
*   `overlay_control`: Parameters meant to orchestrate layout, visibility, and UI-specific overrides.
    *   `show_main_scoreboard` *(Boolean)*: Controls the visibility of the entire graphic (toggled via the "eye" icon in the controller).
    *   `geometry`: The width scaling, X position, and Y position variables configured in the layout settings. Note that these are historically percentage or abstract coordinate numbers, requiring subjective mathematical mapping within your graphics engine.
    *   `colors`: Fallback or override colors for specific areas (Sets Box and Game Points Box).
    *   `preferredStyle`: The layout style identifier that the user has selected from the remote-scoreboard UI dropdown based on your `availableStyles`.

#### Expected Response:
The backend does strict synchronous timeouts (usually 2.0 seconds) for overlay POST requests to minimize UI lag.
**You must return a `200 OK` response as fast as possible.**

---

## 🔌 Optional: WebSocket Control Endpoint

**Endpoint:** `WS /ws/control/{custom_id}`

If your overlay server supports it, you can implement a persistent WebSocket control channel. When `controlWebSocketUrl` is included in your `/api/config/{id}` response, Remote-Scoreboard will open this connection on startup and use it for all state pushes, visibility toggles, and raw_config syncs — eliminating per-update HTTP overhead.

### Protocol (v1)

**Handshake:** On connection, your server should immediately send:
```json
{
  "type": "connected",
  "protocol": 1,
  "overlay_id": "mybroadcast",
  "obs_clients": 2,
  "current_state": { "...full state object..." }
}
```

**Incoming message types from Remote-Scoreboard:**

| Type | Payload | Description |
|------|---------|-------------|
| `state_update` | `{ "payload": { ...match state... } }` | Partial or full state update (deep-merged) |
| `visibility` | `{ "show": true/false }` | Toggle overlay visibility |
| `raw_config` | `{ "payload": { "model": {...}, "customization": {...} } }` | Persist raw model/customization data |
| `get_state` | *(none)* | Request current state |
| `ping` | *(none)* | Heartbeat (sent every ~25s) |

**Response messages your server should send:**

| Type | When | Payload |
|------|------|---------|
| `ack` | After `state_update`, `visibility`, `raw_config` | `{ "type": "ack", "ref": "<message_type>", "obs_clients": N }` |
| `state` | After `get_state` | `{ "type": "state", "payload": { "model": {...}, "customization": {...} } }` |
| `pong` | After `ping` | `{ "type": "pong" }` |
| `obs_event` | When OBS browser clients connect/disconnect | `{ "type": "obs_event", "event": "connected"/"disconnected", "obs_clients": N }` |

**Backward compatibility:** This endpoint is entirely optional. If your server does not implement it or omits `controlWebSocketUrl` from `/api/config`, Remote-Scoreboard falls back to HTTP-only mode with no loss of functionality.

---

## 🏛️ Real-Time Implementation Strategy

While Remote-Scoreboard pushes state updates *to your server*, your broadcasting software (OBS, vMix, etc.) loads a web page interface that cannot be directly reached by the POST request.

**The Recommended Architecture:**

1.  **FastAPI/Express Server**: Receive the `POST /api/state/...` payload and immediately keep it in memory.
2.  **WebSockets**: Your server maintains WebSocket connections with the actual web clients (the OBS browser source).
3.  **Broadcast**: Instantly push the new JSON state down the WebSocket to the browser.
4.  **Frontend State Diffing**: In the browser, compare the new JSON payload with a cached `previousState` to identify specifically what changed (e.g., only the away team's score changed), and run CSS/GSAP animations targeting just that HTML element to prevent screen flickering.

---

## 📺 Controller Preview Integration

When users configure their overlay inside the Remote-Scoreboard UI, a preview card is rendered so they can view their design live. For your custom overlay to perfectly fit and scale within this preview card, your frontend code MUST report its render bounding box bounds back to the controller via the `postMessage` API.

**How it works:**
1. Remote-Scoreboard will load your `outputUrl` into a hidden `1920x1080` iframe container.
2. It expects your web page to execute `window.parent.postMessage(...)` with a specific payload summarizing the exact position and dimensions of the actual scoreboard graphic.
3. Upon receiving this message, the preview container dynamically applies CSS `scale()` and `translate()` properties to perfectly center your scoreboard within the 250px-wide UI preview card.

**Expected `postMessage` Payload:**
```javascript
window.parent.postMessage({
    type: 'overlayRenderArea',
    bounds: {
        x: elementRect.x,
        y: elementRect.y,
        width: elementRect.width,
        height: elementRect.height
    }
}, '*');
```

**Implementation Tip:** Attach this `postMessage` call to a `ResizeObserver` or `MutationObserver` mapped to your main scoreboard `<div>`. Whenever your overlay scales, moves, or changes dimensions (like when expanding to show additional set history), the observer will automatically dispatch updated boundaries ensuring the controller's preview always stays perfectly framed!

---

## 📎 Reference Implementation

The built-in overlay engine (`app/overlay/`) implements the same API contract described above and can serve as a reference for building your own external overlay server. The overlay templates in `overlay_templates/` and the frontend JavaScript in `overlay_static/js/app.js` demonstrate the OBS browser source side of the protocol.

A machine-readable **OpenAPI 3.0 specification** for the full contract is available at [CUSTOM_OVERLAY_API.yaml](CUSTOM_OVERLAY_API.yaml). It can be imported into tools like Swagger UI, Postman, or Insomnia for interactive exploration and automatic mock generation.

For general application architecture and development guidance, see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md).
