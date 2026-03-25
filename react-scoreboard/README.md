# Volley Scoreboard — React GUI

A React-based scoreboard controller for [Volley Overlay Control](https://github.com/JacoboSanchez/volley-overlay-control). This frontend provides a responsive, touch-friendly interface for managing live volleyball match overlays.

## Quick Start

```bash
# Install dependencies
npm install

# Start the dev server (proxies API to localhost:8080)
npm run dev

# Build for production
npm run build
```

The dev server runs at `http://localhost:3000` and proxies all `/api` requests to the backend at `http://localhost:8080`.

## Architecture

```
src/
├── App.jsx                  # Root component, tab routing, responsive layout
├── App.css                  # All styles (single CSS file, no framework)
├── theme.js                 # Color constants
├── main.jsx                 # Entry point
├── api/
│   ├── client.js            # REST API client (session, game actions, customization)
│   └── websocket.js         # WebSocket client for real-time state updates
├── components/
│   ├── TeamPanel.jsx        # Score button, timeout, serve indicator per team
│   ├── CenterPanel.jsx      # Sets display, score history table, set pagination
│   ├── ControlButtons.jsx   # Bottom bar: visibility, simple mode, undo, config nav
│   ├── ConfigPanel.jsx      # Customization panel: team names, colors, geometry
│   ├── ScoreButton.jsx      # Tap + long-press button (score/set values)
│   ├── ScoreTable.jsx       # Per-set score history table
│   └── SetValueDialog.jsx   # Number input dialog for custom values
└── hooks/
    └── useGameState.js      # Central state hook (session init, WebSocket, actions)
```

## Features

- **Responsive layout** — adapts between landscape and portrait orientations
- **Real-time sync** — WebSocket connection with automatic reconnection and keepalive
- **Tap & long-press** — tap score buttons to increment, long-press to set a specific value
- **Undo mode** — toggle undo to reverse the last action
- **Simple mode** — switch between full and simplified scoreboard display
- **Overlay visibility** — show/hide the overlay on the broadcast output
- **Configuration panel** — edit team names, colors, logos, and overlay geometry
- **Overlay preview** — live iframe preview of the scoreboard output, auto-refreshed on OID change
- **Set pagination** — navigate between sets in multi-set matches

## Tabs

The app has two main views, switched via arrow buttons in the bottom control bar:

| Tab | Description |
|-----|-------------|
| **Scoreboard** | Score buttons, sets, timeouts, serve indicators, and control bar |
| **Configuration** | Team customization (names, colors, logos), overlay geometry, save/refresh/reset |

The scoreboard bottom bar shows `→` on the right to open configuration.
The configuration bottom bar shows `←` on the left to return to the scoreboard.

## API Integration

All communication goes through the backend REST API and WebSocket:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/session/init` | POST | Initialize a session for an Overlay ID (auto-resolves output URL) |
| `/api/v1/state` | GET | Get current game state |
| `/api/v1/customization` | GET | Get overlay customization model |
| `/api/v1/customization` | PUT | Save customization changes |
| `/api/v1/game/add-point` | POST | Add/undo a point |
| `/api/v1/game/add-set` | POST | Add/undo a set |
| `/api/v1/game/add-timeout` | POST | Add/undo a timeout |
| `/api/v1/game/change-serve` | POST | Switch serving team |
| `/api/v1/game/set-score` | POST | Set exact score for a set |
| `/api/v1/game/set-sets` | POST | Set exact sets won |
| `/api/v1/game/reset` | POST | Reset the match |
| `/api/v1/display/visibility` | POST | Show/hide overlay |
| `/api/v1/display/simple-mode` | POST | Toggle simple mode |
| `/api/v1/ws` | WebSocket | Real-time state updates |

Authentication is optional — set a Bearer token via `setApiKey()` in `api/client.js`.

## Development

### Prerequisites

- Node.js 18+
- The Volley Overlay Control backend running on port 8080

### Dev Server

```bash
npm run dev
```

Open `http://localhost:3000` in a browser. Enter your Overlay Control ID (OID) to connect. The Vite dev server proxies `/api` requests to the backend automatically.

### Production Build

```bash
npm run build
```

Output goes to `dist/`. Serve it from the backend or any static file server — just ensure the API is accessible at `/api/v1/`.

## Tech Stack

- **React 19** — UI library
- **Vite 6** — Build tool and dev server
- **Material Icons** — Icon font (loaded from Google Fonts CDN)
- No CSS framework — plain CSS with custom properties

## Notes

- **Team name keys** — The backend customization model may use either the legacy key
  `"Team N Text Name"` or the newer `"Team N Name"`. The team selector in `ConfigPanel`
  checks for both formats automatically.
- **Output URL** — The backend auto-resolves the overlay output URL during session
  init, so the React app does not need to supply it explicitly.
- **Preview data** — Preview and overlay links are re-fetched whenever the OID changes.
  Stale preview data from a previous session is cleared automatically.
