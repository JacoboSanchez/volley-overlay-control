# Volley Overlay Control

![License](https://img.shields.io/badge/license-Apache%202-blue)
![Python](https://img.shields.io/badge/python-3.x-blue.svg)
![FastAPI](https://img.shields.io/badge/built%20with-FastAPI-009688.svg)

**Volley Overlay Control** is a powerful, self-hostable backend service for controlling volleyball scoreboards. It works with *overlays.uno* cloud overlays and with fully custom, self-hosted overlay engines.

It exposes a REST + WebSocket API that powers the [volley-control-ui](../volley-control-ui) React frontend, providing complete match control — scores, sets, timeouts, and serving teams. Highly customizable and built for versatility, it supports multiple users, overlays, and personalized themes.

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

### REST + WebSocket API
*   **Session management** — initialise and manage game sessions
*   **Game actions** — add points, sets, timeouts, change serve, reset matches
*   **Display controls** — toggle overlay visibility and simple mode
*   **Customization** — read and update team names, colors, logos
*   **Real-time WebSocket** — receive instant state updates at `ws://<host>/api/v1/ws?oid=<OID>`
*   **Internationalization**: Available in **English** and **Spanish**.

Authentication uses Bearer tokens (reusing `SCOREBOARD_USERS` passwords). If no users are configured, the API is open.

For the full endpoint reference, request/response schemas, and WebSocket protocol, see [**FRONTEND_DEVELOPMENT.md**](FRONTEND_DEVELOPMENT.md).

### Flexible Deployment
*   **Local Execution**: Run locally as a standard Python application.
*   **Docker Support**: Deploy easily using Docker containers.

---

## Getting Started

### Prerequisites

*   **Python 3.x**
*   An account on **[overlays.uno](https://overlays.uno)** (for cloud overlays), or a self-hosted overlay server.

### Creating an Overlay

1.  **Login** to your *overlays.uno* account.
2.  Navigate to [this overlay](https://overlays.uno/library/437-Volleyball-Scorebug---Standard) and click **Add to My Overlays**.
3.  **Open your overlay** to get the necessary tokens:
    *   **Control URL**: Copy the URL. The part after `https://app.overlays.uno/control/` is your **`UNO_OVERLAY_OID`**.

### Building a Custom Overlay

If you want to build and host your own completely custom graphical overlay (instead of using overlays.uno), refer to the [Custom Overlay Documentation](CUSTOM_OVERLAY.md).

---

## Usage

### Running Locally

1.  **Clone the repository** and install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Configure Environment Variables**:
    Create a `.env` file in the root directory or export variables in your terminal. `UNO_OVERLAY_OID` is required when using overlays.uno.

    ```env
    # .env file
    UNO_OVERLAY_OID=XXXXXXXX
    SCOREBOARD_USERS={"user1": {"password": "password1"}}
    ```

3.  **Start the Application**:
    ```bash
    python main.py
    ```
    The FastAPI server starts on port 8080 (configurable via `APP_PORT`).

4.  **Use the Built-in Overlay Engine (Optional)**:
    Instead of *overlays.uno*, you can use the built-in local overlay by configuring your overlay ID with the `C-` prefix (e.g., `C-mybroadcast`). The overlay is served directly from the backend — no separate server needed. Set `OVERLAY_PUBLIC_URL` if the backend is behind a reverse proxy.

### Running with Docker

Use the provided `docker-compose.yml`.

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
| `OVERLAY_PUBLIC_URL` | Public-facing base URL for overlay output links (when behind a reverse proxy). | |
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

### Remote Configuration
Import configuration from an external resource via `REMOTE_CONFIG_URL`. The application fetches this JSON file on startup. Useful for centralized management.
*   **Example Source**: [volleyball-scoreboard-configurator](https://github.com/JacoboSanchez/volleyball-scoreboard-configurator/)

### Available Endpoints

| Endpoint | Description |
| :--- | :--- |
| `/api/v1/...` | REST API (see [FRONTEND_DEVELOPMENT.md](FRONTEND_DEVELOPMENT.md)) |
| `/api/v1/ws?oid=X` | WebSocket for real-time state updates |
| `/health` | Health check endpoint. Returns `200 OK` with a timestamp. |

---

## Troubleshooting

| Issue | Solution |
| :--- | :--- |
| App won't start | Verify `UNO_OVERLAY_OID` is set correctly. Check logs for errors. |
| Overlay not updating | Ensure the overlay control token is valid. Try calling `POST /api/v1/session/init` again. |
| Docker container crashes | Check logs with `docker-compose logs app`. Ensure all environment variables in `.env` are properly formatted (especially JSON values). |
| "Outdated overlay version" error | Your overlay was created before March 2025. Create a new overlay from the [overlays.uno library](https://overlays.uno/library/437-Volleyball-Scorebug---Standard). |
| Custom overlay not receiving updates | Overlay IDs must start with `C-`. Ensure the backend is running and check logs for errors. See [Custom Overlay docs](CUSTOM_OVERLAY.md). |

---

## Contributing

Contributions are welcome! Here's how to get started:

1.  **Fork** the repository and create a feature branch.
2.  **Install dependencies** and ensure tests pass (`pytest tests/`).
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
