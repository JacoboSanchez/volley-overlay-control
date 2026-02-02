# 🏐 Volley Overlay Control

![License](https://img.shields.io/badge/license-Apache%202-blue)
![Python](https://img.shields.io/badge/python-3.x-blue.svg)
![NiceGUI](https://img.shields.io/badge/built%20with-NiceGUI-5898d4.svg)

**Volley Overlay Control** is a powerful, self-hostable web application designed to seamlessly control volleyball scoreboards from *overlays.uno*. 

It offers a user-friendly interface to manage every aspect of a volleyball match—scores, sets, timeouts, and serving teams. Highly customizable and built for versatility, it supports multiple users, overlays, and personalized themes, making it the perfect solution for managing scoreboards across various events.

---

## ✨ Features

### 🎮 Complete Match Control
*   **Score Management**: Easily manage points, sets, and timeouts for both teams.
*   **Service Indicator**: Clearly indicate the serving team.
*   **Undo Capability**: Mistake-proof your scoring with undo functionality for points and timeouts.
*   **Game Modes**: Support for both **Indoor** (25 points, 5 sets) and **Beach Volleyball** (21 points, 3 sets).
*   **Quick Edits**: Long press to manually adjust set or point counters.

### 🎨 Advanced Customization
*   **Team Identity**: Customize team names, logos, and colors to match the teams playing.
*   **Scoreboard Layout**: Adjust dimensions (height, width) and position (horizontal, vertical).
*   **Visual Effects**: Apply glossy/gradient effects for a premium look.
*   **Logo Control**: Toggle team logos on or off.
*   **Lock Settings**: Lock team colors and icons to prevent accidental changes during a match.
*   **Themes**: Create, save, and load custom themes to switch styles instantly.

### 👥 User and Overlay Management
*   **Multi-User Support**: Secure access with password protection for multiple users.
*   **Multi-Overlay Control**: Manage multiple overlays from a single application instance.
*   **Overlay Library**: Select from a list of predefined overlays for quick setup.

### 🖥️ User-Friendly Interface
*   **Dark Mode**: Native support for dark mode (Auto, On, Off).
*   **Auto-Hide**: Automatically hide the scoreboard after a configurable timeout.
*   **Simple Mode**: Automatically switch to a simplified view showing only the current set during gameplay.
*   **Smart Timeout**: Option to switch back to full mode when a timeout is called.
*   **Live Preview**: Toggle a real-time preview of the overlay directly in the control panel.
*   **Internationalization**: Available in **English** and **Spanish**.

### 🚀 Flexible Deployment
*   **Local Execution**: Run locally as a standard Python application.
*   **Docker Support**: Deploy easily using Docker containers.
*   **Remote Access**: Expose to the internet using tunneling services (like ngrok).

---

## 🚀 Getting Started

### Prerequisites

*   **Python 3.x**
*   An account on **[overlays.uno](https://overlays.uno)**
*   A volleyball scoreboard overlay added to your account from the *overlays.uno* library.

### 🛠️ Creating an Overlay

1.  **Login** to your *overlays.uno* account.
2.  Navigate to [this overlay](https://overlays.uno/library/437-Volleyball-Scorebug---Standard) and click **Add to My Overlays**.
3.  **Open your overlay** to get the necessary tokens:
    *   **Control URL**: Copy the URL. The part after `https://app.overlays.uno/control/` is your **`UNO_OVERLAY_OID`**.
4.  *(Optional)* For local-only setups, use the [NiceGUI On Air](https://nicegui.io/documentation/section_configuration_deployment#nicegui_on_air) feature. Get your token and use it as `UNO_OVERLAY_AIR_ID`.

> [!IMPORTANT]
> **Compatibility Note:** Version 0.2 breaks compatibility with overlays created before March 2025.

---

## 📖 Usage

### Running Locally

1.  **Clone the repository** and install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Configure Environment Variables**:
    Create a `.env` file in the root directory or export variables in your terminal. `UNO_OVERLAY_OID` is required.

    **Option A: Using a `.env` file**
    ```env
    # .env file
    UNO_OVERLAY_OID=XXXXXXXX
    SCOREBOARD_USERS={"user1": {"password": "password1"}}
    ```

    **Option B: Exporting Variables**
    *Windows (CMD):*
    ```cmd
    set UNO_OVERLAY_OID=XXXXXXXX
    python main.py
    ```
    *Linux/macOS:*
    ```bash
    export UNO_OVERLAY_OID=XXXXXXXX
    python main.py
    ```

3.  **Start the Application**:
    ```bash
    python main.py
    ```
    NiceGUI will automatically open the scoreboard in your browser.

### Running with Docker 🐳

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

## ⚙️ Configuration

Configure the application using the following environment variables:

| Variable | Description | Default Value |
| :--- | :--- | :--- |
| `UNO_OVERLAY_OID` | The control token for your overlays.uno overlay. A dialog will ask for it if not configured | |
| `APP_PORT` | The TCP port where the application will run. | `8080` |
| `APP_TITLE` | The title of the web page. | `Scoreboard` |
| `APP_DARK_MODE` | Dark mode setting. Options: `on`, `off`, `auto`. | `auto` |
| `APP_DEFAULT_LOGO` | URL of an image for teams without a predefined logo. | `https://...` |
| `MATCH_GAME_POINTS` | Points needed to win a set. | `25` |
| `MATCH_GAME_POINTS_LAST_SET` | Points needed to win the last set. | `15` |
| `MATCH_SETS` | Number of sets to win the match. | `5` |
| `ORDERED_TEAMS` | If `true`, the team list will be displayed in alphabetical order. | `true` |
| `ENABLE_MULTITHREAD` | If `true`, API calls will not block the UI. | `true` |
| `LOGGING_LEVEL` | Log level (`debug`, `info`, `warning`, `error`). | `warning` |
| `STORAGE_SECRET` | Secret key to encrypt user data in the browser. | |
| `SCOREBOARD_LANGUAGE` | Language code (e.g., `es` for Spanish). | `en` |
| `REST_USER_AGENT` | User-Agent to avoid Cloudflare bot detection. | `curl/8.15.0` |
| `APP_TEAMS` | JSON with the list of predefined teams. | |
| `SCOREBOARD_USERS` | JSON with the list of users and passwords. | |
| `PREDEFINED_OVERLAYS` | JSON with a list of preconfigured overlays. | |
| `HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED` | If `true`, hides the option to manually enter an overlay. | `false` |
| `APP_THEMES` | JSON with a list of customization themes. | |
| `APP_RELOAD` | If `true`, automatically reload on code changes. | `false` |
| `APP_SHOW` | If `true`, automatically opens the app in a new tab on startup. | `false` |
| `REMOTE_CONFIG_URL` | URL to a remote JSON file with the configuration. | |
| `AUTO_HIDE_ENABLED` | If `true`, scoreboard hides after inactivity. | `false` |
| `DEFAULT_HIDE_TIMEOUT` | Seconds to wait before hiding the scoreboard. | `5` |
| `AUTO_SIMPLE_MODE` | If `true`, auto-switch to simplified view during gameplay. | `false` |
| `AUTO_SIMPLE_MODE_TIMEOUT` | If `true`, switch back to full view on timeout. | `false` |
| `SHOW_PREVIEW` | If `true`, shows a preview of the overlay on the control page. | `true` |

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
List of allowed users.
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

### Overlay Loading Priority
1.  **URL Parameter**: `?control=<your_oid>` (Highest priority)
2.  **Saved Session**: Last valid overlay used.
3.  **Environment Variable**: `UNO_OVERLAY_OID`
4.  **Interactive Dialog**: Prompt user if no other source is found.

---

## 📸 Screenshots

### Main Control Panel
<p align="center">
  <img width="909" height="389" alt="image" src="https://github.com/user-attachments/assets/3585b1ab-7611-4473-80b3-44f8e29b9ada" />
</p>

### Setup & Preview
| Setup Panel | Preview Page |
| :---: | :---: |
| <img width="945" height="383" alt="image" src="https://github.com/user-attachments/assets/63c0c546-fe9b-446a-b69a-461df43abb34" /> | <img src="https://github.com/user-attachments/assets/a1abbfa8-4e01-4f3f-a128-07bf71f8b5e4" width="100%" /> |

### Dialogs
| Configuration Dialog | Links Dialog |
| :---: | :---: |
| <img width="904" height="293" alt="image" src="https://github.com/user-attachments/assets/3930da7f-ed6e-4198-9789-e20761bddeea" /> | <img src="https://github.com/user-attachments/assets/2ca28187-ee74-436f-acfa-ca09605b82ed" width="100%" /> |

### Example Overlay
<p align="center">
  <img src="https://github.com/user-attachments/assets/152a586c-1aaa-4c30-b969-c15884097d04" width="100%" />
</p>

---

## ⚠️ Disclaimer

This software was developed as a personal project and is provided **as-is**. It was built iteratively and may lack comprehensive error handling.

> [!CAUTION]
> **Security Warning:** The authentication feature is intended only for distributing overlays among trusted users and is **not secure**. **Do not expose this application directly to the internet without additional security measures.**

**Use at your own risk.**
