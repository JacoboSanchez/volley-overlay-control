# Building a Custom Overlay for Remote-Scoreboard

The **Remote-Scoreboard** system is capable of driving completely custom, third-party overlay engines instead of relying on the default `overlays.uno` cloud system. This allows developers to build high-performance, strictly local, or highly customized broadcast graphics (e.g., in React, Vue, Vanilla HTML/JS, or Godot).

This document outlines the API contract that your custom overlay must implement to be fully compatible with Remote-Scoreboard.

---

## 🔗 The Connection Protocol

When the user configures an overlay ID starting with `C-` (e.g., `C-mybroadcast`), Remote-Scoreboard identifies this as a **Custom Overlay**.

It will then communicate directly with your custom overlay server using the Base URL defined in the `APP_CUSTOM_OVERLAY_URL` environment variable (which defaults to `http://127.0.0.1:8000`).

The `custom_id` passed to your server will be the user's overlay ID **without** the `C-` prefix. For `C-mybroadcast`, the `custom_id` passed in URLs is `mybroadcast`.

**Styling Support**
Users can append a specific style constraint to their overlay ID using the `/` separator (e.g., `C-mybroadcast/line`). This specifies to the system exactly which layout template to use.
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
  "outputUrl": "http://127.0.0.1:8000/overlay/mybroadcast",
  "availableStyles": ["default", "line", "minimal"]
}
```

*   `outputUrl` **(Required)**: The absolute URL where the actual graphical view of the overlay can be accessed (the link that gets pasted into OBS/vMix).
*   `availableStyles` *(Optional)*: A list of strings representing different visual themes or styles your overlay supports.

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
