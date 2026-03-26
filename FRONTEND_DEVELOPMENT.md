# Frontend Development Guide

This guide provides everything you need to build a custom frontend for Volley Overlay Control using any JavaScript framework (React, Vue, Svelte, vanilla JS, etc.) or any HTTP-capable client.

## Architecture Overview

```
┌──────────────────────────┐     ┌──────────────────────────┐
│   NiceGUI Frontend       │     │  Your JS Frontend        │
│   (built-in)             │     │  (React, Vue, etc.)      │
└──────────┬───────────────┘     └──────────┬───────────────┘
           │ Python calls                   │ HTTP + WebSocket
           ▼                                ▼
┌──────────────────────────────────────────────────────────┐
│              Game Service Layer (app/api/)                │
│  ┌──────────────────┐  ┌──────────┐  ┌───────────────┐  │
│  │  REST API         │  │  WS Hub  │  │ Session Mgr   │  │
│  │  /api/v1/*        │  │  /api/v1 │  │               │  │
│  │                   │  │  /ws     │  │               │  │
│  └──────────────────┘  └──────────┘  └───────────────┘  │
└──────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────┐
│         Core Business Logic (unchanged)                   │
│   GameManager  │  State  │  Backend  │  Customization    │
└──────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────┐
│         External Overlay APIs                             │
│   overlays.uno (cloud)  │  Custom overlay (self-hosted)  │
└──────────────────────────────────────────────────────────┘
```

## Getting Started

### 1. Start the Backend

```bash
# Clone and install
git clone <repo-url>
pip install -r requirements.txt

# Configure (minimal)
export UNO_OVERLAY_OID=C-my-overlay   # or a cloud overlay OID

# Start the server
python main.py
```

The server starts on port `8080` by default (`APP_PORT` env var).

### 2. Initialize a Session

Before using any game endpoint, you must initialise a session:

```bash
curl -X POST http://localhost:8080/api/v1/session/init \
  -H "Content-Type: application/json" \
  -d '{"oid": "C-my-overlay"}'
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
  "oid": "C-my-overlay",
  "points_limit": 21,
  "points_limit_last_set": 15,
  "sets_limit": 3
}
```

---

## Authentication

If the server has `SCOREBOARD_USERS` configured, all API endpoints (except the WebSocket handshake) require a Bearer token:

```bash
curl -X POST http://localhost:8080/api/v1/game/add-point?oid=C-my-overlay \
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

---

## WebSocket — Real-Time Updates

Connect to `ws://localhost:8080/api/v1/ws?oid=<OID>` to receive live state updates.

### Connection

```javascript
const ws = new WebSocket('ws://localhost:8080/api/v1/ws?oid=C-my-overlay');

ws.onopen = () => {
  console.log('Connected! Initial state will arrive automatically.');
};
```

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
    const OID = 'C-my-overlay';
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

If your JavaScript frontend is served from a different origin (e.g., `http://localhost:3000` during development), you need to configure CORS. Add to your environment:

```bash
export APP_CORS_ORIGINS="http://localhost:3000"
```

Or configure directly in your deployment. The API endpoints are standard FastAPI routes, so standard FastAPI CORS middleware applies.

---

## Development Workflow

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
