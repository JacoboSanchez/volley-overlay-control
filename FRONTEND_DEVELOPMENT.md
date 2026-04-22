# Frontend Development Guide

This guide covers the REST + WebSocket API exposed by Volley Overlay Control. Use it to build a custom frontend using any JavaScript framework (React, Vue, Svelte, vanilla JS, etc.) or any HTTP-capable client.

The bundled React control UI (`frontend/`) is a reference implementation that uses this API. You can also build a completely independent frontend.

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────────┐
│  Volley Overlay Control (single process, port 8080)               │
│                                                                   │
│  ┌──────────────────────────────┐                                 │
│  │  React Control UI (SPA)      │  served at /                    │
│  │  frontend/dist/              │                                 │
│  └──────────────────────────────┘                                 │
│                                                                   │
│  ┌──────────────────────────────────────────────────────┐         │
│  │          Game Service Layer (app/api/)                │         │
│  │  REST API  /api/v1/*  │  WS Hub  │  Session Manager  │         │
│  └──────────────────────────────────────────────────────┘         │
│                                                                   │
│  ┌──────────────────────────────────────────────────────┐         │
│  │       Core Business Logic                             │         │
│  │  GameManager  │  State  │  Backend  │  Customization  │         │
│  └──────────────────────────────────────────────────────┘         │
│                        │                                          │
│           ┌────────────┼────────────┐                             │
│           ▼                         ▼                             │
│  ┌─────────────────────┐   ┌──────────────────┐                  │
│  │  Built-in Overlay    │   │  overlays.uno    │                  │
│  │  Engine (app/overlay)│   │  (cloud API)     │                  │
│  │  /overlay/* /ws/*    │   └──────────────────┘                  │
│  └─────────────────────┘            │ (optional)                  │
│           │                ┌──────────────────┐                   │
│           ▼                │  External overlay │                   │
│     OBS browser sources    │  server (HTTP/WS) │                   │
│                            └──────────────────┘                   │
└───────────────────────────────────────────────────────────────────┘
```

## Getting Started

### 1. Start the Backend

```bash
# Clone and install
git clone <repo-url>
pip install -r requirements.txt

# Build the frontend (optional — backend works without it)
cd frontend && npm ci && npm run build && cd ..

# Configure (minimal)
export UNO_OVERLAY_OID=my-overlay   # or a cloud overlay OID

# Start the server
python main.py
```

The server starts on port `8080` by default (`APP_PORT` env var). The control UI is at `http://localhost:8080/`.

### 2. Initialize a Session

Before using any game endpoint, you must initialise a session:

```bash
curl -X POST http://localhost:8080/api/v1/session/init \
  -H "Content-Type: application/json" \
  -d '{"oid": "my-overlay"}'
```

Response:
```json
{
  "success": true,
  "state": {
    "current_set": 1,
    "visible": true,
    "simple_mode": false,
    "match_finished": false,
    "team_1": {
      "sets": 0,
      "timeouts": 0,
      "scores": {"set_1": 0, "set_2": 0, "set_3": 0, "set_4": 0, "set_5": 0},
      "serving": false
    },
    "team_2": {
      "sets": 0,
      "timeouts": 0,
      "scores": {"set_1": 0, "set_2": 0, "set_3": 0, "set_4": 0, "set_5": 0},
      "serving": false
    },
    "serve": "None",
    "config": {
      "points_limit": 25,
      "points_limit_last_set": 15,
      "sets_limit": 5
    }
  },
  "message": null
}
```

You can also override match rules when initialising:

```json
{
  "oid": "my-overlay",
  "points_limit": 21,
  "points_limit_last_set": 15,
  "sets_limit": 3
}
```

---

## Authentication

If the server has `SCOREBOARD_USERS` configured, all API endpoints (except the WebSocket handshake) require a Bearer token:

```bash
curl -X POST http://localhost:8080/api/v1/game/add-point?oid=my-overlay \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <password>" \
  -d '{"team": 1}'
```

The API key is any valid user password from the `SCOREBOARD_USERS` configuration. If no users are configured, authentication is not required.

---

## REST API Reference

All endpoints are under the `/api/v1/` prefix. State-changing endpoints require `oid` as a query parameter.

### Session Management

#### `POST /api/v1/session/init`

Initialise or re-use a game session.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `oid` | string | yes | — | Overlay control ID |
| `output_url` | string | no | auto | Output URL for overlay preview |
| `points_limit` | int | no | 25 | Points to win a set |
| `points_limit_last_set` | int | no | 15 | Points to win the last set |
| `sets_limit` | int | no | 5 | Total sets in the match |

When `output_url` is not provided, the backend automatically resolves it by calling
`fetch_output_token(oid)`. For cloud (overlays.uno) overlays this queries the
overlays.uno API; for custom overlays it fetches the `outputUrl` from
`/api/config/{id}`. If `APP_CUSTOM_OVERLAY_OUTPUT_URL` is set, the host portion is
replaced to avoid mixed-content issues.

### State Queries

#### `GET /api/v1/state?oid=<OID>`

Returns the full game state. See the [State Model](#state-model) section for the response structure.

#### `GET /api/v1/config?oid=<OID>`

Returns match configuration:
```json
{
  "points_limit": 25,
  "points_limit_last_set": 15,
  "sets_limit": 5
}
```

#### `GET /api/v1/customization?oid=<OID>`

Returns the overlay customization data (team names, colors, logos, geometry).

### Game Actions

All game actions return an `ActionResponse`:
```json
{
  "success": true,
  "state": { ... },   // Full GameStateResponse
  "message": null      // Error message if success=false
}
```

#### `POST /api/v1/game/add-point?oid=<OID>`

Add or undo a point.

```json
{"team": 1, "undo": false}
```

- Automatically handles set wins (when a team reaches the point limit with 2+ point lead)
- Automatically advances the serve
- Returns `success: false` when match is already finished (unless `undo: true`)

#### `POST /api/v1/game/add-set?oid=<OID>`

Add or undo a set win.

```json
{"team": 2, "undo": false}
```

- Resets timeouts for both teams on new set
- Resets serve on new set

#### `POST /api/v1/game/add-timeout?oid=<OID>`

Add or undo a timeout (max 2 per team).

```json
{"team": 1, "undo": false}
```

#### `POST /api/v1/game/change-serve?oid=<OID>`

Change the serving team.

```json
{"team": 1}
```

- Toggles serve: if the team already has serve, it's cleared

#### `POST /api/v1/game/set-score?oid=<OID>`

Set an exact score value.

```json
{"team": 1, "set_number": 2, "value": 15}
```

- `set_number` must be `>= 1` (no hard upper bound — the match's `sets_limit` is enforced by the service layer)
- Automatically detects set wins after setting the score

#### `POST /api/v1/game/set-sets?oid=<OID>`

Set exact sets won.

```json
{"team": 1, "value": 2}
```

#### `POST /api/v1/game/reset?oid=<OID>`

Reset the match to initial state. No body required.

### Display Controls

#### `POST /api/v1/display/visibility?oid=<OID>`

Toggle overlay visibility on the output display.

```json
{"visible": true}
```

#### `POST /api/v1/display/simple-mode?oid=<OID>`

Toggle simple mode (shows only current set scores).

```json
{"enabled": true}
```

### Customization

#### `PUT /api/v1/customization?oid=<OID>`

Update overlay customization. Send the full customization object:

```json
{
  "Team 1 Text Name": "Eagles",
  "Team 2 Text Name": "Hawks",
  "Team 1 Color": "#0000ff",
  "Team 2 Color": "#ff0000",
  "Team 1 Text Color": "#ffffff",
  "Team 2 Text Color": "#ffffff",
  "Team 1 Logo": "https://example.com/eagles.png",
  "Team 2 Logo": "https://example.com/hawks.png"
}
```

> **Note:** Team names may appear under the legacy key `"Team N Text Name"` or the
> newer key `"Team N Name"` depending on the overlay. The backend accepts both
> formats. When reading the customization model, check for both keys (the old key
> takes precedence when present).

### Overlay Info

#### `GET /api/v1/links?oid=<OID>`

Returns overlay-related URLs for the session.

```json
{
  "control": "https://app.overlays.uno/control/<OID>",
  "overlay": "http://localhost:8080/overlay/<output_key>",
  "preview": "http://localhost:8080/overlay/<output_key>?layout_id=auto"
}
```

- `control` — Only present for overlays.uno cloud overlays.
- `overlay` — The URL to paste into OBS/vMix as a browser source.
- `preview` — Only present for custom overlays (`C-` prefix). Used by the frontend to render a live preview card.

#### `GET /api/v1/styles?oid=<OID>`

Returns available overlay style names for the session's overlay backend.

```json
["default", "esports", "glass", "compact", "ribbon", ...]
```

The built-in engine returns the 14 selectable templates. The `mosaic` meta-style is intentionally excluded from this list — it can only be rendered via the explicit `?style=mosaic` query parameter on `/overlay/{id}`.

### SPA Bootstrap

#### `GET /api/v1/app-config`

Runtime configuration consumed by the SPA on load. Unauthenticated.

```json
{ "title": "Volley Scoreboard" }
```

Drives the browser tab title, init-screen heading and PWA manifest name. Set `APP_TITLE` to change it.

#### `POST /api/v1/_log`

Accepts a single error/warn record from the SPA. Rate-limited per peer IP (30 records / 60 s); unauthenticated by design, so the body caps and PII redaction do the safety work.

```json
{
  "level": "error",
  "message": "TypeError: cannot read properties of null",
  "stack": "...",
  "href": "https://host/?oid=abc",
  "user_agent": "Mozilla/5.0 ...",
  "oid": "abc"
}
```

Responses:
- `204 No Content` — accepted.
- `429 Too Many Requests` — rate limit hit; well-behaved clients should back off. Response body is empty so `navigator.sendBeacon` does not surface a JSON error payload.

`X-Forwarded-For` is honoured for rate-limit bucketing when the app sits behind a reverse proxy. Configure uvicorn with `--proxy-headers` to also rewrite `request.client.host`.

### Admin

The `/api/v1/admin/*` surface backs the custom-overlay manager page at `/manage`. Gated by `OVERLAY_MANAGER_PASSWORD`.

- `GET /api/v1/admin/status` — whether management is enabled (`{"enabled": true|false}`). Unauthenticated.
- `POST /api/v1/admin/login` — validates a `Authorization: Bearer <password>` header.
- `GET /api/v1/admin/custom-overlays` — list overlays backed by `LocalOverlayBackend`.
- `POST /api/v1/admin/custom-overlays` — create (optionally cloning from an existing overlay via `copy_from`).
- `DELETE /api/v1/admin/custom-overlays/{name}` — remove an overlay and its persisted state file.

All mutating routes require the same Bearer header. When `OVERLAY_MANAGER_PASSWORD` is unset, every route returns `503`.

---

## WebSocket — Real-Time Updates

Connect to `ws://localhost:8080/api/v1/ws?oid=<OID>` to receive live state updates.

### Connection

```javascript
const ws = new WebSocket('ws://localhost:8080/api/v1/ws?oid=my-overlay');

ws.onopen = () => {
  console.log('Connected! Initial state will arrive automatically.');
};
```

Browsers cannot set `Authorization` headers on `WebSocket`. When `SCOREBOARD_USERS` is configured, pass the user's password (same value used as the REST Bearer token) as a query parameter instead:

```javascript
const ws = new WebSocket(`ws://localhost:8080/api/v1/ws?oid=${OID}&token=${password}`);
```

The same `?token=<value>` escape hatch works on the built-in overlay server's `/ws/{id}` when it is gated by `OVERLAY_SERVER_TOKEN`. See [AUTHENTICATION.md](AUTHENTICATION.md) for the full dependency inventory.

### Message Format

All messages from the server are JSON with a `type` field:

```json
{
  "type": "state_update",
  "data": {
    "current_set": 1,
    "visible": true,
    "simple_mode": false,
    "match_finished": false,
    "team_1": { "sets": 0, "timeouts": 0, "scores": {...}, "serving": true },
    "team_2": { "sets": 0, "timeouts": 0, "scores": {...}, "serving": false },
    "serve": "A",
    "config": { "points_limit": 25, "points_limit_last_set": 15, "sets_limit": 5 }
  }
}
```

### Keepalive

Send `ping` to receive `pong`:

```javascript
setInterval(() => ws.send('ping'), 25000);
```

### Reconnection

The WebSocket will close if the session doesn't exist. Handle reconnection:

```javascript
ws.onclose = (event) => {
  if (event.code === 4004) {
    console.error('Session not found. Call /api/v1/session/init first.');
  } else {
    setTimeout(() => connectWebSocket(), 3000); // Reconnect after 3s
  }
};
```

---

## State Model Reference

This is the shape exposed by `/api/v1/state` and the WebSocket stream. It is **not** the same as the payload the server pushes to an external overlay (`POST /api/state/{id}` uses a different, human-readable schema like `"Serve": "A"`, `"Team 1 Sets": 0`). See [CUSTOM_OVERLAY.md](CUSTOM_OVERLAY.md) for that external contract — the translation lives inside the backend and alternate frontends never need to deal with it.

### GameStateResponse

| Field | Type | Description |
|-------|------|-------------|
| `current_set` | int (1–5) | Currently active set number |
| `visible` | bool | Whether the overlay is shown on output |
| `simple_mode` | bool | Whether only current set scores are shown |
| `match_finished` | bool | Whether a team has won the required number of sets |
| `team_1` | TeamState | Home team state |
| `team_2` | TeamState | Away team state |
| `serve` | string | `"A"` (team 1), `"B"` (team 2), or `"None"` |
| `config` | object | Match rules configuration |

### TeamState

| Field | Type | Description |
|-------|------|-------------|
| `sets` | int | Number of sets won (0–3) |
| `timeouts` | int | Timeouts taken in current set (0–2) |
| `scores` | object | Per-set scores: `{"set_1": 5, "set_2": 0, ...}` |
| `serving` | bool | Whether this team currently has serve |

### Customization Model

| Key | Type | Description |
|-----|------|-------------|
| `Team 1 Text Name` | string | Home team display name |
| `Team 2 Text Name` | string | Away team display name |
| `Team 1 Color` | string | Home team primary color (hex) |
| `Team 2 Color` | string | Away team primary color (hex) |
| `Team 1 Text Color` | string | Home team text color (hex) |
| `Team 2 Text Color` | string | Away team text color (hex) |
| `Team 1 Logo` | string | Home team logo URL |
| `Team 2 Logo` | string | Away team logo URL |
| `Logos` | string | `"true"` or `"false"` — show logos |
| `Width` | float | Overlay width percentage |
| `Height` | float | Overlay height percentage |
| `Left-Right` | float | Horizontal position offset |
| `Up-Down` | float | Vertical position offset |
| `Color 1` | string | Set indicator background color |
| `Text Color 1` | string | Set indicator text color |
| `Color 2` | string | Score background color |
| `Text Color 2` | string | Score text color |
| `preferredStyle` | string | Overlay rendering style name |

---

## Complete Example: Vanilla JavaScript Frontend

```html
<!DOCTYPE html>
<html>
<head>
  <title>Volley Scoreboard</title>
  <style>
    body { font-family: sans-serif; text-align: center; padding: 20px; }
    .score { font-size: 64px; font-weight: bold; }
    .sets { font-size: 24px; color: #666; }
    button { font-size: 18px; padding: 10px 20px; margin: 5px; cursor: pointer; }
    .team { display: inline-block; width: 45%; vertical-align: top; }
    .serve { color: green; font-size: 14px; }
    #status { color: #999; font-size: 12px; }
  </style>
</head>
<body>
  <h1>Volleyball Scoreboard</h1>
  <div id="status">Connecting...</div>

  <div class="team">
    <h2 id="team1-name">Team 1</h2>
    <div class="score" id="team1-score">00</div>
    <div class="sets">Sets: <span id="team1-sets">0</span></div>
    <div class="serve" id="team1-serve"></div>
    <button onclick="addPoint(1)">+ Point</button>
    <button onclick="addPoint(1, true)">- Point</button>
  </div>

  <div class="team">
    <h2 id="team2-name">Team 2</h2>
    <div class="score" id="team2-score">00</div>
    <div class="sets">Sets: <span id="team2-sets">0</span></div>
    <div class="serve" id="team2-serve"></div>
    <button onclick="addPoint(2)">+ Point</button>
    <button onclick="addPoint(2, true)">- Point</button>
  </div>

  <div style="margin-top: 20px;">
    <button onclick="resetMatch()">Reset Match</button>
    <button onclick="toggleVisibility()">Toggle Overlay</button>
  </div>

  <script>
    const BASE = 'http://localhost:8080';
    const OID = 'my-overlay';
    // Set this if authentication is enabled:
    const API_KEY = null; // e.g. 'my-password'

    function headers() {
      const h = { 'Content-Type': 'application/json' };
      if (API_KEY) h['Authorization'] = `Bearer ${API_KEY}`;
      return h;
    }

    // Initialize session on load
    async function init() {
      const res = await fetch(`${BASE}/api/v1/session/init`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ oid: OID }),
      });
      const data = await res.json();
      if (data.success) {
        updateUI(data.state);
        connectWebSocket();
      }
    }

    // WebSocket for real-time updates
    function connectWebSocket() {
      const ws = new WebSocket(`ws://localhost:8080/api/v1/ws?oid=${OID}`);
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'state_update') updateUI(msg.data);
      };
      ws.onopen = () => {
        document.getElementById('status').textContent = 'Connected (live)';
        setInterval(() => ws.send('ping'), 25000);
      };
      ws.onclose = () => {
        document.getElementById('status').textContent = 'Disconnected. Reconnecting...';
        setTimeout(connectWebSocket, 3000);
      };
    }

    // Track last known state from WebSocket for use in API calls
    let latestState = {};

    // Update the UI from state
    function updateUI(state) {
      latestState = state;
      const set = state.current_set;
      document.getElementById('team1-score').textContent =
        String(state.team_1.scores[`set_${set}`]).padStart(2, '0');
      document.getElementById('team2-score').textContent =
        String(state.team_2.scores[`set_${set}`]).padStart(2, '0');
      document.getElementById('team1-sets').textContent = state.team_1.sets;
      document.getElementById('team2-sets').textContent = state.team_2.sets;
      document.getElementById('team1-serve').textContent =
        state.team_1.serving ? 'SERVING' : '';
      document.getElementById('team2-serve').textContent =
        state.team_2.serving ? 'SERVING' : '';
    }

    // API calls
    async function addPoint(team, undo = false) {
      await fetch(`${BASE}/api/v1/game/add-point?oid=${OID}`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ team, undo }),
      });
    }

    async function resetMatch() {
      await fetch(`${BASE}/api/v1/game/reset?oid=${OID}`, {
        method: 'POST',
        headers: headers(),
      });
    }

    async function toggleVisibility() {
      // Use the last known state from WebSocket instead of fetching,
      // to avoid a race condition between GET and POST.
      await fetch(`${BASE}/api/v1/display/visibility?oid=${OID}`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ visible: !latestState.visible }),
      });
    }

    init();
  </script>
</body>
</html>
```

---

## CORS Considerations

The bundled React frontend is served from the same origin, so CORS is not needed. If you build an external frontend served from a different origin (e.g., `http://localhost:3000`), configure CORS via standard FastAPI middleware.

---

## Development Workflow

### Using the bundled React frontend

```bash
# Terminal 1: Start the backend
python main.py

# Terminal 2: Start the Vite dev server (hot-reload)
cd frontend && npm run dev
```

Vite serves on port 3000 and proxies `/api` requests to the backend on port 8080.

### Building a custom frontend

1. **Start the backend** on port 8080
2. **Initialise a session** via `POST /api/v1/session/init`
3. **Connect WebSocket** for live updates
4. **Build your UI** — call REST endpoints for actions, render state from WebSocket messages
5. **Test** — the backend validates all game rules (point limits, set wins, match completion)

### Tips

- The backend enforces all volleyball rules. Your frontend only needs to display state and send actions.
- Use the WebSocket for reactivity — don't poll the REST API.
- The `match_finished` field tells you when to disable scoring buttons.
- The `serve` field changes automatically when points are added.
- Set wins are detected automatically when a team reaches the point limit with a 2-point lead.
- Timeouts are capped at 2 per team. The backend silently ignores additional timeout requests.

### UX conventions in the bundled React UI

These behaviours are not part of the API contract — document them here so alternate frontends can match them intentionally.

- **HUD auto-hide** — the overlay controls fade out after 5 s of pointer inactivity (`resetHideTimer` in `frontend/src/App.tsx`). Any `pointerdown` resets the timer. Useful on touch devices where an always-visible toolbar occludes the scoreboard.
- **Score button gestures** — each side of the scoreboard uses a multi-gesture button (`frontend/src/components/ScoreButton.tsx`). Priority is **long-press > double-tap > single-tap**:
  - *Single tap*: `POST /api/v1/game/add-point`.
  - *Double tap*: undo the last point on that team.
  - *Long press*: open a numeric dialog that calls `POST /api/v1/game/set-score` to pick an exact value.
  Long-press cancels the pending single/double-tap timers so only the long-press handler fires.
- **Set-cell long press** — long-pressing a set counter in the centre panel opens the same dialog against `POST /api/v1/game/set-sets`.
- **Pre-select OID via URL** — the bundled UI resolves the initial OID from, in order, `?control=<oid>`, `?oid=<oid>`, and `localStorage.volley_oid`. Either query param auto-connects the session (skipping the picker) and replaces any previously stored OID. Use `?control=` from external control links to force-switch which overlay this tab is controlling.
- **WebSocket reconnect** — on close (other than `4004` "no session"), the bundled UI reconnects after 3 s. The `?token=` query param above is re-applied automatically.
- **Client error reporting** — uncaught errors and `window.onerror` traces are posted to `/api/v1/_log`, rate-limited and PII-redacted server-side.
