# Volley Overlay Control

![License](https://img.shields.io/badge/license-Apache%202-blue)
![Python](https://img.shields.io/badge/python-3.x-blue.svg)
![FastAPI](https://img.shields.io/badge/built%20with-FastAPI-009688.svg)

**Volley Overlay Control** is a powerful, self-hostable application for controlling volleyball scoreboards. It bundles a touch-friendly React frontend, a FastAPI backend, and a **built-in overlay engine** into a single deployable service.

It includes 16 overlay style templates served directly to OBS browser sources — no external overlay server required. It also works with *overlays.uno* cloud overlays and with fully custom, external overlay engines. Complete match control — scores, sets, timeouts, and serving teams. Highly customizable and built for versatility, it supports multiple users, overlays, and personalized themes.

---

## Features

### Complete Match Control
*   **Score Management**: Manage points, sets, and timeouts for both teams via REST API.
*   **Service Indicator**: Track the serving team.
*   **Undo Capability**: Reverse any scoring action.
*   **Game Modes**: Support for both **Indoor** (25 points, 5 sets) and **Beach Volleyball** (21 points, 3 sets).

### Advanced Customization
*   **Team Identity**: Customize team names, logos, and colors.
*   **Scoreboard Layout**: Adjust dimensions (height, width) and position (horizontal, vertical).
*   **Visual Effects**: Apply glossy/gradient effects.
*   **Themes**: Create, save, and load custom themes.

### User and Overlay Management
*   **Multi-User Support**: Secure access with password-based API key authentication.
*   **Multi-Overlay Control**: Manage multiple overlays from a single instance.
*   **Overlay Library**: Select from predefined overlays for quick setup.
*   **Custom Overlay Manager Page**: Dedicated, password-protected page at `/manage` to create, delete and clone custom (built-in engine) overlays at runtime — no need to use the `/create/overlay`, `/list/overlay` or `/delete/overlay` endpoints directly.

### REST + WebSocket API
*   **Session management** — initialise and manage game sessions
*   **Game actions** — add points, sets, timeouts, change serve, reset matches
*   **Display controls** — toggle overlay visibility and simple mode
*   **Customization** — read and update team names, colors, logos
*   **Real-time WebSocket** — receive instant state updates at `ws://<host>/api/v1/ws?oid=<OID>`
*   **Internationalization**: Available in **English** and **Spanish**.

Authentication uses Bearer tokens (reusing `SCOREBOARD_USERS` passwords). If no users are configured, the API is open.

For the full endpoint reference, request/response schemas, and WebSocket protocol, see [**FRONTEND_DEVELOPMENT.md**](FRONTEND_DEVELOPMENT.md).

### Built-In Overlay Engine
*   **16 Overlay Styles**: Includes pre-built HTML overlay templates (esports, glass, compact, ribbon, shield, and more) rendered via Jinja2 and served directly to OBS/vMix browser sources.
*   **Real-Time Updates**: OBS browser sources connect via WebSocket (`/ws/{overlay_id}`) and receive 50ms-debounced state pushes — no polling needed.
*   **Manage Overlays in One Place**: Create, copy and delete overlays from the `/manage` page (protected by `OVERLAY_MANAGER_PASSWORD`). Overlay IDs created there can be used directly as OIDs in the control UI; state is persisted to disk and served immediately.
*   **Preset Themes**: Apply dark, light, esports, neo_jersey, split_jersey, or clear_jersey themes with one click.

### Single-App Deployment
*   **All-in-one**: The React control UI, Python backend, and overlay engine run as a single process from a single Docker image.
*   **Local Execution**: Run locally as a standard Python application (with optional Vite dev server for frontend hot-reload).
*   **Docker Support**: Deploy easily using a single Docker container — no nginx or reverse proxy required.

---

## Getting Started

### Prerequisites

*   **Python 3.x**
*   **Node.js 20+** and **npm** (for building the frontend)
*   *(Optional)* An account on **[overlays.uno](https://overlays.uno)** for cloud overlays. Not needed when using the built-in overlay engine.

### Creating an Overlay

1.  **Login** to your *overlays.uno* account.
2.  Navigate to [this overlay](https://overlays.uno/library/437-Volleyball-Scorebug---Standard) and click **Add to My Overlays**.
3.  **Open your overlay** to get the necessary tokens:
    *   **Control URL**: Copy the URL. The part after `https://app.overlays.uno/control/` is your **`UNO_OVERLAY_OID`**.

### Using the Built-In Overlay Engine

The fastest way to get started is with the built-in overlay engine. Open the `/manage` page (protected by `OVERLAY_MANAGER_PASSWORD`) to create an overlay — say, `mybroadcast` — then use that ID directly as the OID in the control UI. The system serves 16 style templates at `/overlay/{id}` and broadcasts state updates to OBS via WebSocket at `/ws/{id}`. No external server or account is required.

> **Backward compatibility:** the legacy `C-<id>` prefix (e.g. `C-mybroadcast`) is still accepted when the overlay already exists, but it is no longer required and is omitted from the documentation and UI from now on.

### Building a Custom External Overlay

If you need a fully custom overlay engine (e.g., built in React, Vue, or Godot), you can point Remote-Scoreboard at an **external overlay server** by setting `APP_CUSTOM_OVERLAY_URL`. Refer to the [Custom Overlay Documentation](CUSTOM_OVERLAY.md) for the API contract.

---

## Usage

### Running Locally

1.  **Clone the repository** and install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Build the frontend**:
    ```bash
    cd frontend && npm ci && npm run build && cd ..
    ```

3.  **Configure Environment Variables**:
    Create a `.env` file in the root directory or export variables in your terminal. `UNO_OVERLAY_OID` is required when using overlays.uno.

    ```env
    # .env file
    UNO_OVERLAY_OID=XXXXXXXX
    SCOREBOARD_USERS={"user1": {"password": "password1"}}
    ```

4.  **Start the Application**:
    ```bash
    python main.py
    ```
    The FastAPI server starts on port 8080 (configurable via `APP_PORT`). The control UI is available at `http://localhost:8080/`.

5.  **Use a Custom Overlay** — Create an overlay from the `/manage` page (set `OVERLAY_MANAGER_PASSWORD` first) and use its ID as the OID in the control UI. The overlay is accessible at `http://localhost:8080/overlay/{id}` for OBS browser sources. If you want to use an *external* overlay server instead, additionally set `APP_CUSTOM_OVERLAY_URL`. See [CUSTOM_OVERLAY.md](CUSTOM_OVERLAY.md) for details.

> **Tip:** For frontend development with hot-reload, run `cd frontend && npm run dev` alongside `python main.py`. Vite serves on port 3000 and proxies API calls to the backend on port 8080.

### Running with Docker

The Dockerfile uses a multi-stage build: Node.js builds the React frontend, then the result is copied into the Python image. No separate frontend container or nginx is needed.

1.  Create a `.env` file:
    ```env
    EXTERNAL_PORT=80
    APP_TITLE=MyScoreboard
    UNO_OVERLAY_OID=<overlay_control_token>
    ```
2.  Run Docker Compose:
    ```bash
    docker-compose up -d
    ```

---

## Configuration

Configure the application using the following environment variables:

| Variable | Description | Default Value |
| :--- | :--- | :--- |
| `UNO_OVERLAY_OID` | The control token for your overlays.uno overlay. | |
| `APP_PORT` | The TCP port where the application will run. | `8080` |
| `APP_TITLE` | Application title shown in the browser tab, the init screen heading and the PWA manifest. | `Volley Scoreboard` |
| `APP_CUSTOM_OVERLAY_URL` | *(Optional)* Base URL of an external custom overlay server. When set, custom overlays use the external server instead of the built-in engine. | *(unset — built-in engine)* |
| `APP_CUSTOM_OVERLAY_OUTPUT_URL` | *(Optional)* Public-facing base URL for overlay links. Used to replace the host in output URLs when the overlay server is behind a proxy. | |
| `OVERLAY_PUBLIC_URL` | *(Optional)* Public base URL for overlay output links served by the built-in engine. If unset, URLs are constructed from the request's host. | |
| `MATCH_GAME_POINTS` | Points needed to win a set. | `25` |
| `MATCH_GAME_POINTS_LAST_SET` | Points needed to win the last set. | `15` |
| `MATCH_SETS` | Total sets in the match (best of N). | `5` |
| `ORDERED_TEAMS` | If `true`, the team list will be displayed in alphabetical order. | `true` |
| `ENABLE_MULTITHREAD` | If `true`, overlay API calls run in a thread pool. | `true` |
| `LOGGING_LEVEL` | Log level (`debug`, `info`, `warning`, `error`). | `warning` |
| `SCOREBOARD_LANGUAGE` | Language code (e.g., `es` for Spanish). | `en` |
| `REST_USER_AGENT` | User-Agent to avoid Cloudflare bot detection. | `curl/8.15.0` |
| `APP_TEAMS` | JSON with the list of predefined teams. | |
| `SCOREBOARD_USERS` | JSON with the list of users and passwords (also used as API keys). | |
| `PREDEFINED_OVERLAYS` | JSON with a list of preconfigured overlays. | |
| `HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED` | If `true`, hides the option to manually enter an overlay. | `false` |
| `OVERLAY_MANAGER_PASSWORD` | Password that unlocks the custom overlay manager page at `/manage` (also required to read `/list/overlay`). Leave empty to disable the page. | |
| `OVERLAY_SERVER_TOKEN` | *(Recommended)* Bearer token required by the built-in overlay server's mutation and config endpoints (`/api/state/{id}`, `/api/raw_config/{id}`, `/api/config/{id}`, `/create/overlay/{id}`, `/delete/overlay/{id}`, `/api/theme/{id}/{name}`). When unset the endpoints stay open and a warning is logged at startup. If you also run the control app against an **external** overlay server via `APP_CUSTOM_OVERLAY_URL`, set the same value on both sides. See [AUTHENTICATION.md](AUTHENTICATION.md) (F-3, F-5). | |
| `APP_THEMES` | JSON with a list of customization themes. | |
| `REMOTE_CONFIG_URL` | URL to a remote JSON file with the configuration. | |
| `SINGLE_OVERLAY_MODE` | If `true`, restricts the app to a single active overlay at a time. | `true` |
| `MINIMIZE_BACKEND_USAGE` | If `true`, caches customization responses to reduce API round-trips. | `true` |
| `UNO_OVERLAY_OUTPUT` | Custom output URL override for the overlay display link. | |

<br>

### JSON Configuration Examples

#### `APP_TEAMS`
List of predefined teams.
```json
{
    "Local": {
        "icon": "https://cdn-icons-png.flaticon.com/512/8686/8686758.png",
        "color": "#060f8a",
        "text_color": "#ffffff"
    },
    "Visitor": {
        "icon": "https://cdn-icons-png.flaticon.com/512/8686/8686758.png",
        "color": "#ffffff",
        "text_color": "#000000"
    }
}
```

#### `SCOREBOARD_USERS`
List of allowed users. Passwords double as API Bearer tokens.
```json
{
    "user1": {"password": "password1"},
    "user2": {
        "password": "password2",
        "control": "CONTROLTOKEN"
    }
}
```

#### `PREDEFINED_OVERLAYS`
List of predefined overlay configurations.
```json
{
    "Overlay for user 1": {
        "control": "CONTROLTOKEN",
        "allowed_users": ["user1"]
    },
    "Overlay for all users": {
        "control": "CONTROLTOKEN"
    }
}
```

#### `APP_THEMES`
List of themes.
```json
{
    "Change position and show logos theme": {
        "Height": 10,
        "Left-Right": -33.5,
        "Logos": true
    },
    "Change only game status colors": {
        "Game Status Color": "#252525",
        "Game Status Text Color": "#ffffff"
    }
}
```

### Custom Overlay Manager Page

Navigate to **`/manage`** (e.g. `http://localhost:8080/manage`) to open the
custom overlay manager. It is independent from the scoreboard UI: it has
its own URL and its own password prompt.

From this page you can:

*   **Create** a new custom overlay by name — the overlay's OID is
    automatically `C-<name>`, and the built-in overlay engine persists its
    state to `data/overlay_state_<name>.json`.
*   **Clone** an existing custom overlay into a new one — the clone inherits
    the source's colors, layout, preferred style and current state.
*   **Delete** custom overlays no longer needed.

You no longer need to call the `/create/overlay`, `/list/overlay` or
`/delete/overlay` endpoints by hand for day-to-day management.

Predefined overlay catalogues (for populating the scoreboard UI's overlay
picker) are still configured exclusively through the `PREDEFINED_OVERLAYS`
environment variable or the remote configurator (`REMOTE_CONFIG_URL`).

#### Enabling the page

Set the `OVERLAY_MANAGER_PASSWORD` environment variable to any non-empty
value. When the variable is unset or empty, the page shows a "management
disabled" notice and every admin endpoint returns HTTP 503.

```env
OVERLAY_MANAGER_PASSWORD=change-me
```

> **Security note**: `OVERLAY_MANAGER_PASSWORD` is a single shared password.
> Treat it the same way you treat `SCOREBOARD_USERS` — do not expose the
> service directly to the public internet without additional protection.

### Overlay server token (`OVERLAY_SERVER_TOKEN`)

When the built-in overlay server is mounted (i.e. the `overlay_templates/`
directory is present), its mutation and config endpoints can be gated behind
a Bearer token. Set `OVERLAY_SERVER_TOKEN` to any non-empty value and every
request to the following routes must include
`Authorization: Bearer <token>`:

- `POST /api/state/{id}`
- `GET` / `POST /create/overlay/{id}`
- `GET` / `POST` / `DELETE /delete/overlay/{id}`
- `GET` / `POST /api/raw_config/{id}`
- `GET /api/config/{id}`
- `POST /api/theme/{id}/{name}`

When the variable is unset the routes stay open and a warning is logged at
startup — existing deployments keep working unchanged.

If the control app is pointed at an **external** overlay server via
`APP_CUSTOM_OVERLAY_URL`, set `OVERLAY_SERVER_TOKEN` to the same value on
both sides. The control app's `CustomOverlayBackend` forwards the token in
every request it makes to the overlay server.

The OBS capability URLs (`/overlay/{output_key}` and `/ws/{output_key}`) are
intentionally **not** gated by this token — they are the public-by-design
entry points that OBS loads.

See [AUTHENTICATION.md](AUTHENTICATION.md) for the full route inventory.

### Remote Configuration
Import configuration from an external resource via `REMOTE_CONFIG_URL`. The application fetches this JSON file on startup. Useful for centralized management.
*   **Example Source**: [volleyball-scoreboard-configurator](https://github.com/JacoboSanchez/volleyball-scoreboard-configurator/)

### Available Endpoints

| Endpoint | Description |
| :--- | :--- |
| `/` | Control UI (React SPA) |
| `/manage` | Custom overlay manager page (password-protected via `OVERLAY_MANAGER_PASSWORD`). |
| `/api/v1/...` | REST API (see [FRONTEND_DEVELOPMENT.md](FRONTEND_DEVELOPMENT.md)) |
| `/api/v1/ws?oid=X` | WebSocket for real-time state updates (frontend) |
| `/api/v1/admin/custom-overlays` | List/create/delete custom overlays (Bearer = `OVERLAY_MANAGER_PASSWORD`). |
| `/overlay/{id}` | Overlay HTML for OBS browser sources (built-in engine) |
| `/ws/{id}` | WebSocket for OBS browser sources (overlay state broadcast) |
| `/api/config/{id}` | Overlay config (output URL, available styles) |
| `/api/themes` | List preset overlay themes |
| `/health` | Health check endpoint. Returns `200 OK` with a timestamp. |

For a full audit of every route and its authentication requirements
(including the overlay server endpoints consumed by OBS and
`CustomOverlayBackend`), see [AUTHENTICATION.md](AUTHENTICATION.md).

---

## Troubleshooting

| Issue | Solution |
| :--- | :--- |
| App won't start | Verify `UNO_OVERLAY_OID` is set correctly. Check logs for errors. |
| Overlay not updating | Ensure the overlay control token is valid. Try calling `POST /api/v1/session/init` again. |
| Docker container crashes | Check logs with `docker-compose logs app`. Ensure all environment variables in `.env` are properly formatted (especially JSON values). |
| "Outdated overlay version" error | Your overlay was created before March 2025. Create a new overlay from the [overlays.uno library](https://overlays.uno/library/437-Volleyball-Scorebug---Standard). |
| Custom overlay not receiving updates | Overlay IDs must start with `C-`. For built-in overlays, check that `overlay_templates/` exists. For external overlays, verify `APP_CUSTOM_OVERLAY_URL` is reachable. See [Custom Overlay docs](CUSTOM_OVERLAY.md). |

---

## Contributing

Contributions are welcome! Here's how to get started:

1.  **Fork** the repository and create a feature branch.
2.  **Install dependencies** and ensure tests pass:
    - Backend: `pip install -r requirements.txt && pytest tests/`
    - Frontend: `cd frontend && npm ci && npm test`
3.  **Follow existing patterns** — see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) for architecture and conventions.
4.  **Submit a Pull Request** against the `dev` branch with a clear description of your changes.

For custom overlay development, see [CUSTOM_OVERLAY.md](CUSTOM_OVERLAY.md).

---

## License

This project is licensed under the **Apache License 2.0**. See the [LICENSE](LICENSE) file for details.

---

## Disclaimer

This software was developed as a personal project and is provided **as-is**. It was built iteratively and may lack comprehensive error handling.

> [!CAUTION]
> **Security Warning:** The authentication feature is intended only for distributing overlays among trusted users and is **not secure**. **Do not expose this application directly to the internet without additional security measures.**

**Use at your own risk.**
