Project Documentation: Volley Overlay Control
1. Project Overview

Volley Overlay Control is a web-based application built with Python and NiceGUI. It serves as a remote control for updating volleyball scoreboards (overlays) in real-time. The application manages game logic (score, sets, serving, timeouts), handles user authentication, and synchronizes state with an external backend (likely the Uno Overlay system).

Tech Stack:

    Frontend/UI: NiceGUI (based on Vue/Quasar, rendered via Python).

    Backend Logic: Python 3.x.

    Styling: Tailwind CSS (via NiceGUI utility classes) and app/theme.py.
    
    State Management: In-memory Python objects synchronized with an external API.

    Containerization: Docker (using `uv` for package management).
    
    CI/CD: GitHub Actions pipelines defined in `.github/workflows/` for automated resting and linting.

2. Directory Structure & Key Files
Plaintext

├── main.py                  # Entry point. Sets up the NiceGUI app, middleware, and env vars.
├── .github/                 # GitHub specific files.
│   └── workflows/           # CI/CD pipelines (e.g., ci.yml).
├── app/
│   ├── backend.py           # Handles communication with the external Overlay API & local overlay instance.
│   ├── game_manager.py      # Core business logic (rules, scoring, limits).
│   ├── state.py             # Data model definition. Holds the raw state dictionary.
│   ├── gui.py               # Main UI logic orchestrator.
│   ├── components/          # Reusable NiceGUI UI components (ScoreButton, TeamPanel, etc.).
│   ├── startup.py           # Route definitions, page loading logic, and lifecycle hooks.
│   ├── customization.py     # Logic for handling team names, colors, logos, and layout.
│   ├── theme.py             # UI constants (colors, CSS classes).
│   ├── conf.py              # Configuration object mapping env vars to settings.
│   ├── authentication.py    # User login/logout logic.
│   ├── app_storage.py       # Wrapper for NiceGUI's browser-local storage.
│   ├── pwa/                 # Progressive Web App assets (Service Worker, Manifest, Icons).
│   └── ... (Dialogs and helper pages)
├── overlay/                 # Optional High-Speed Local Broadcast Package
│   ├── main.py              # A FastAPI websockets server
│   └── templates/index.html # Local Browser Source UI
├── font/                    # Custom font files for the UI/Overlay.
└── tests/                   # Pytest suite.

3. Core Architecture & Data Flow

The application follows a Model-View-Controller (MVC) hybrid pattern:

    Model (State): Represents the snapshot of the game (scores, timeouts, serve status).

    Controller (GameManager): Manipulates the Model based on Volleyball rules. It acts as the bridge between the UI and the Data.

    View (GUI): Displays the Model to the user and captures input events.

    Sync (Backend): Pushes the Model changes to the external overlay server.

Typical Data Flow (e.g., Adding a Point):

    User Action: User clicks "Team 1 Score" button in GUI.

    Event Handling: GUI calls GameManager.add_game(team=1).

    Logic Processing: GameManager validates the move (checks if match finished), increments the score in State, checks for set-win conditions, and auto-switches serve.

    State Sync: GameManager calls Backend.save() to push new data to the cloud/overlay (and to `overlay/main.py` if running locally).

    UI Refresh: GUI reads the updated State and calls update_ui() to reflect changes (e.g., button text, colors).

4. Class & Method Reference
A. Core Logic
app/state.py - class State

Represents the data structure of the match.

    Responsibility: Holds the "Single Source of Truth" dictionary (current_model) that maps keys (e.g., 'Team 1 Sets') to values.

    Key Attributes:

        reset_model: A dictionary defining the default/zero state.

        current_model: The active state dictionary.

    Key Methods:

        get_game(team, set) / set_game(...): Get/Set points for a specific set.

        get_sets(team) / set_sets(...): Get/Set sets won.

        simplify_model(simplified): Prepares the state for "simple mode" (reduced data payload).

app/game_manager.py - class GameManager

The "Brain" of the application. It enforces volleyball rules.

    Responsibility: Manipulate State safely.

    Key Methods:

        add_game(team, ...): Increments score. Handles logic for "Winning by 2", reaching point limits, and match completion.

        add_set(team): Increments set count. Resets timeouts and serve for the next set.

        change_serve(team): Updates the serving indicator.

        undo: (Boolean flag passed to methods) Reverses the last action (decrements score/set).

        match_finished(): Returns True if a team has reached the set limit.

        save(simple, current_set): Persists state via Backend.

app/backend.py - class Backend

The "Bridge" to the outside world.

    Responsibility: HTTP communication with the Overlay API.

    Key Methods:

        get_current_model(): Fetches the last known state from the remote API. For Custom Overlays, this hits `/api/raw_config/{id}` to bypass local caching storage requirements.

        save(state, simple): Pushes local state changes to the cloud server and proxies it to the local overlay engine via `update_local_overlay()`. For custom overlays, it also syncs raw state JSON structure payloads backwards via `POST /api/raw_config/{id}` to keep persistent data alive across backend restarts since the backend no longer saves custom JSON states locally on its own disk.

        update_local_overlay(current_model, force_visibility, customization_state): Parses the game scoring and UI branding properties, combining them into a standardized JSON payload structure (`match_info`, `team_home`/`team_away`, `overlay_control`). It executes a POST request containing this payload to `[APP_CUSTOM_OVERLAY_URL]/api/state/{custom_id}`.

        fetch_and_update_overlay_id(oid): Executes `GetOverlays` to translate a user's Control Token (OID) into the specific backend layout ID (e.g., `8637...` or `446a...`). This ensures all API calls target the correct schema.

        fetch_output_token(oid): Retrieves the URL/Token required to display the UNO overlay iframe.

B. User Interface

app/components/
This directory contains modular UI pieces to prevent `gui.py` from becoming a monolith.
    - `score_button.py`: Wraps `ui.button` with complex long-press and tap detection logic.
    - `team_panel.py`: Renders an entire vertical/horizontal column for a specific team (Scores, Timeouts, Serve Indicator).
    - `center_panel.py`: Manages the middle column (Detailed score table, set pagination, Live Preview iframe).
    - `control_buttons.py`: Manages the top/bottom action bar (Visibility toggle, Simple Mode, Undo, Config).

app/gui.py - class GUI

The NiceGUI presentation layer orchestrator.

    Responsibility: Instantiate modular components from `app/components/`, listen for state changes from the `GameManager`, and trigger updates across those components.

    Key Methods:

        init(...): Builds the initial layout by instantiating `TeamPanel`, `CenterPanel`, and `ControlButtons`.

        update_ui(load_from_backend): Refreshes all visual elements (scores, colors, logos) by mutating the state of the component instances.

        handle_button_press/release: Invoked by `ScoreButton` components to process "Long Press", "Tap", and "Double Tap" (undo) logic.

        switch_simple_mode(): Toggles the UI and backend data payload between full detail and simplified view.

app/startup.py - startup()

    Responsibility: Defines the application routing (/, /login, /preview) and startup sequence.

    Logic:

        Checks for oid (Overlay ID) in URL, Storage, or Environment.

        If missing, launches OidDialog.

        Initializes GUI and Backend.
        
        Serves PWA assets (`/sw.js`, `/manifest.json`, `/pwa/*`), registers the Service Worker, and implements the Screen Wake Lock API logic (via JavaScript injection) to keep devices awake during use.

app/theme.py

    Responsibility: Centralized configuration for UI colors (Tailwind classes) and button styles.

    Key Constants: 
        - GAME_BUTTON_CLASSES: Defines the shape, shadow, and text alignment (centered) of score buttons.
        - TACOLOR / TBCOLOR: Team colors.

C. Configuration & Extras
app/customization.py & app/customization_page.py

    Responsibility: Manages cosmetic data that isn't strict game logic: Team Names, Logos, Colors, and Overlay geometry (X/Y/Width/Height).
    Logic Details: Abstracts payload keys to support multiple layout templates. If `Team 1 Text Name` doesn't exist (like in newer layouts), it automatically falls back to looking for `Team 1 Name`. Applies safe `.get()` defaults to gracefully handle unsupported customization variables per layout. `customization_page.py` additionally hides components natively unsupported by the active layout (e.g. Volleyball Championship layout removes team color configuration and renames "Set").

app/conf.py

    Responsibility: Loads environment variables (e.g., APP_PORT, UNO_OVERLAY_URL) into a structured object.

5. Important Logic Flows for AI Agents

When modifying the code, keep these dependencies in mind:

    UI Updates:

        NiceGUI is reactive but often requires manual calls to element.update() or set_text().

        Crucial: If you modify State in GameManager, you must ensure GUI.update_ui() is triggered (usually via a refresh flow or immediate UI set) so the user sees the change.

    Long Press Logic:

        The buttons in GUI use a timer-based system to distinguish between a tap (Add Point) and a hold (Open Edit Dialog). Do not remove the touchstart/mousedown event listeners without preserving this logic.

    State Synchronization:

        The app assumes it is the primary controller. However, GameManager.reset() reloads data from the Backend to ensure it syncs with any external resets.

    Responsive Design:

        GUI detects orientation (is_portrait). Layouts switch between ui.row() (Landscape) and ui.column() (Portrait). Any new UI elements must handle both contexts.

    Fonts:

        The app loads custom fonts from the font/ directory. These are applied via CSS injection in app/startup.py (addHeader function) and used in theme.py / gui.py.
        Custom fonts are normalized to match the visual footprint of the default font. `FONT_SCALES` in `theme.py` defines a precise `scale` multiplier and vertical offset (`offset_y`) for each font. These values were generated by rendering each font in a flex container (emulating NiceGUI behavior) and mathematically measuring the exact painted pixels. Any new font additions should be measured and added to `FONT_SCALES` to ensure UI consistency.

6. Common Modification Scenarios

    Adding a new Rule (e.g., Golden Set):

        Modify app/game_manager.py -> add_game to check for the new condition.

        Update app/state.py if new counters are needed.

    Changing Button Styles:

        Edit app/theme.py constants.

        If logic-based (e.g., color changes on win), edit app/gui.py -> update_button_style.

    Adding a new Setting:

        Add field to app/conf.py.

        Add UI control to app/options_dialog.py.

        Pass the config to GameManager if it affects rules.