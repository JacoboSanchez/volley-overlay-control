# Volley Overlay Control

`volley-overlay-control` is a self-hostable web application for controlling volleyball scoreboards from *overlays.uno*. It provides a user-friendly interface to manage all aspects of a volleyball match, including scores, sets, timeouts, and serving teams. The application is highly customizable, allowing you to personalize the look and feel of your scoreboard with team logos, colors, and pre-defined themes. It also supports multiple users and overlays, making it a versatile solution for managing scoreboards for different events.

## Features

* **Complete Match Control:**
  * Manage points, sets, and timeouts for both teams.
  * Indicate the serving team.
  * Undo functionality for points and timeouts.
  * Support for both indoor (25 points, 5 sets) and beach volleyball (21 points, 3 sets) modes.
  * Long press to change set/points counter to a custom value.
* **Advanced Customization:**
  * Customize team names, logos, and colors.
  * Adjust the scoreboard's dimensions (height, width) and position (horizontal, vertical).
  * Apply a glossy/gradient effect to the scoreboard.
  * Show or hide team logos.
  * Lock team colors and icons to prevent accidental changes.
  * Create and load custom themes to quickly switch between different styles.
* **User and Overlay Management:**
  * Support for multiple users with password protection.
  * Control multiple overlays from a single instance of the application.
  * Select from a list of predefined overlays.
* **User-Friendly Interface:**
  * Dark mode support (auto, on, off).
  * Auto-hide the scoreboard during gameplay.
  * Automatically switch to a simplified view showing only the current set.
  * Internationalization support (English and Spanish).
* **Flexible Deployment:**
  * Run locally as a Python application.
  * Deploy as a Docker container.
  * Expose the application to the internet using ngrok-like services.

## Getting Started

### Prerequisites

* Python 3.x
* An account on *overlays.uno*
* A volleyball scoreboard overlay added to your account from the *overlays.uno* library.

### Instructions to create an overlay:

1. Login to your *overlays.uno* account.
2. Go to [this overlay](https://overlays.uno/library/437-Volleyball-Scorebug---Standard) and click on *Add to My Overlays*.
3. Open your overlay:
   * Copy the control URL. The last part of the URL (after `https://app.overlays.uno/control/`) is your **`UNO_OVERLAY_OID`**.
   * Click on *Copy Output URL*. This will be your **`UNO_OVERLAY_OUTPUT`**.
4. (Optional) If you don't want to expose the service to the internet, you can use the [on air](https://nicegui.io/documentation/section_configuration_deployment#nicegui_on_air) feature from nicegui. Obtain your token and use it as `UNO_OVERLAY_AIR_ID`.

> **Note:** Version 0.2 breaks compatibility with overlays created before March 2025.

## Usage

### Running Locally

1.  Clone the repository and install the dependencies from `requirements.txt`.
2.  Configure your environment variables. You can either export them directly in your terminal or create a `.env` file in the root of the project. `UNO_OVERLAY_OID` is required to start the scoreboard directly.
3.  Execute `python main.py`.
4.  NiceGUI will start a server and open the scoreboard in a browser automatically.

**Example using a `.env` file:**

    # Create a file named .env in the project's root directory
    UNO_OVERLAY_OID=XXXXXXXX
    UNO_OVERLAY_OUTPUT=https://app.overlays.uno/output/YYYYYYY
    SCOREBOARD_USERS={"user1": {"password": "password1"}}

**Example exporting variables:**

```sh
# On Windows Command Prompt
set UNO_OVERLAY_OID=XXXXXXXX
set UNO_OVERLAY_OUTPUT=[https://app.overlays.uno/output/YYYYYYY](https://app.overlays.uno/output/YYYYYYY)
python main.py

# On Linux/macOS
export UNO_OVERLAY_OID=XXXXXXXX
export UNO_OVERLAY_OUTPUT=[https://app.overlays.uno/output/YYYYYYY](https://app.overlays.uno/output/YYYYYYY)
python main.py
```

### Running with Docker

You can use the `docker-compose.yml` file provided. Create a `.env` file in the same directory to configure your environment variables.

**Example `.env` file:**
```
EXTERNAL_PORT=80
APP_TITLE=MyScoreboard
UNO_OVERLAY_OID=<overlay_control_token>
UNO_OVERLAY_OUTPUT=<overlay_output_url>
```

Then, run `docker-compose up -d`.

## Configuration

You can configure the application's behavior using the following environment variables:

| Variable | Description | Default Value |
| :--- | :--- | :--- |
| `UNO_OVERLAY_OID` | The control token for your overlays.uno overlay. **(Required)** |  |
| `UNO_OVERLAY_OUTPUT` | The output URL of the overlay, used to display a link. |  |
| `APP_PORT` | The TCP port where the application will run. | `8080` |
| `APP_TITLE` | The title of the web page. | `Scoreboard` |
| `APP_DARK_MODE` | Dark mode setting. Can be `on`, `off`, or `auto`. | `auto` |
| `APP_DEFAULT_LOGO` | URL of an image for teams without a predefined logo. | `https://...` |
| `MATCH_GAME_POINTS` | Points needed to win a set. | `25` |
| `MATCH_GAME_POINTS_LAST_SET` | Points needed to win the last set. | `15` |
| `MATCH_SETS` | Number of sets to win the match. | `5` |
| `ORDERED_TEAMS` | If `true`, the team list will be displayed in alphabetical order. | `true` |
| `ENABLE_MULTITHREAD` | If `true`, API calls will not block the UI. | `true` |
| `LOGGING_LEVEL` | Log level (`debug`, `info`, `warning`, `error`). | `warning` |
| `STORAGE_SECRET` | Secret key to encrypt user data in the browser. |  |
| `SCOREBOARD_LANGUAGE` | Language code (e.g., `es` for Spanish). | `en` |
| `REST_USER_AGENT` | User-Agent to avoid Cloudflare bot detection. | `curl/8.15.0` |
| `APP_TEAMS` | JSON with the list of predefined teams. |  |
| `SCOREBOARD_USERS` | JSON with the list of users and passwords. |  |
| `PREDEFINED_OVERLAYS` | JSON with a list of preconfigured overlays. |  |
| `HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED` | If `true`, hides the option to manually enter an overlay. | `false` |
| `APP_THEMES` | JSON with a list of customization themes. |  |
| `APP_RELOAD` | If `true`, the app will automatically reload when code changes are detected. | `false` |
| `APP_SHOW` | If `true`, automatically opens the app in a new browser tab on startup. | `false` |

<br>

#### `APP_TEAMS`

List of predefined teams. The key is the name and the value must contain "icon", "color", and "text_color".

```json
{
    "Local": {"icon":"[https://cdn-icons-png.flaticon.com/512/8686/8686758.png](https://cdn-icons-png.flaticon.com/512/8686/8686758.png)", "color":"#060f8a", "text_color":"#ffffff"},
    "Visitor": {"icon":"[https://cdn-icons-png.flaticon.com/512/8686/8686758.png](https://cdn-icons-png.flaticon.com/512/8686/8686758.png)", "color":"#ffffff", "text_color":"#000000"}
}
```

#### `SCOREBOARD_USERS`

List of allowed users. Optionally, it can include overlay information for that user.

```json
{
    "user1": {"password":"password1"},
    "user2": {"password":"password2", "control":"CONTROLTOKEN", "output":"OUTPUTTOKEN"}
}
```

#### `PREDEFINED_OVERLAYS`

List of predefined overlay configurations. It can include a user whitelist (`allowed_users`).

```json
{
    "Overlay for user 1": {"control":"CONTROLTOKEN", "output":"OUTPUTTOKEN", "allowed_users":["user1"]},
    "Overlay for all users": {"control":"CONTROLTOKEN", "output":"OUTPUTTOKEN"}
}
```

#### `APP_THEMES`

List of themes. The key is the theme name and the value is a JSON with the customization parameters from the UNO API.

```json
{
    "Change position and show logos theme": {"Height": 10, "Left-Right": -33.5, "Logos": true},
    "Change only game status colors": {"Game Status Color": "#252525", "Game Status Text Color": "#ffffff"}
}
```

### Overlay Loading Priority

The application determines which overlay to load based on the following priority order:

1.  **URL Parameter**: An overlay specified in the URL (e.g., `?control=<your_oid>`) will always take precedence. This is useful for sharing direct links to a specific scoreboard.
2.  **Saved Session**: If no overlay is specified in the URL, the application will automatically load the last valid overlay you used.
3.  **Environment Variable**: If you are running the application for the first time without a saved session, it will use the `UNO_OVERLAY_OID` from your environment variables or `.env` file.
4.  **Interactive Dialog**: If none of the above methods provide a valid overlay, you will be prompted to enter one through a dialog.

## Screenshots

**Main Control Panel:**

![Main Control Panel](https://github.com/user-attachments/assets/d945dbf3-9a1d-40ed-aaf4-cc012bf41d4c)

**Setup Panel:**

<img width="577" alt="Setup Panel" src="https://github.com/user-attachments/assets/355a4d89-aece-4fe8-816c-8258968b78f2">

**Configuration Dialog:**

<img width="268" alt="Configuration Dialog" src="https://github.com/user-attachments/assets/577db9a9-4f3b-4d70-ac52-dc5da7a11db2">

**Example Overlay:**

![Example Overlay](https://github.com/user-attachments/assets/152a586c-1aaa-4c30-b969-c15884097d04)

## Disclaimer

This software was developed as a personal project and is provided as-is. It was built iteratively by adapting sample code, so it may lack comprehensive error handling and logging.

**Security Warning:** The authentication feature is intended only for distributing overlays among trusted users and is not secure. **Do not expose this application directly to the internet without additional security measures.**

Use at your own risk.
