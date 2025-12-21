Project Documentation: Volley Overlay Control
1. Project Overview

Volley Overlay Control is a web-based application built with Python and NiceGUI. It serves as a remote control for updating volleyball scoreboards (overlays) in real-time. The application manages game logic (score, sets, serving, timeouts), handles user authentication, and synchronizes state with an external backend (likely the Uno Overlay system).

Tech Stack:

    Frontend/UI: NiceGUI (based on Vue/Quasar, rendered via Python).

    Backend Logic: Python 3.x.

    Styling: Tailwind CSS (via NiceGUI utility classes) and app/theme.py.
    
    State Management: In-memory Python objects synchronized with an external API.

    Containerization: Docker (using `uv` for package management).

2. Directory Structure & Key Files
Plaintext

├── main.py                  # Entry point. Sets up the NiceGUI app, middleware, and env vars.
├── app/
│   ├── backend.py           # Handles communication with the external Overlay API.
│   ├── game_manager.py      # Core business logic (rules, scoring, limits).
│   ├── state.py             # Data model definition. Holds the raw state dictionary.
│   ├── gui.py               # Main UI logic. Renders the scoreboard control panel.
│   ├── startup.py           # Route definitions, page loading logic, and lifecycle hooks.
│   ├── customization.py     # Logic for handling team names, colors, logos, and layout.
│   ├── theme.py             # UI constants (colors, CSS classes).
│   ├── conf.py              # Configuration object mapping env vars to settings.
│   ├── authentication.py    # User login/logout logic.
│   ├── app_storage.py       # Wrapper for NiceGUI's browser-local storage.
│   └── ... (Dialogs and helper pages)
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

    State Sync: GameManager calls Backend.save() to push new data to the cloud/overlay.

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

        get_current_model(): Fetches the last known state from the server.

        save(state, simple): Pushes local state changes to the server.

        fetch_output_token(oid): Retrieves the URL/Token required to display the overlay iframe.

B. User Interface
app/gui.py - class GUI

The NiceGUI presentation layer.

    Responsibility: Render buttons, listen for clicks, and update the DOM.

    Key Methods:

        init(...): Builds the initial layout (Team panels, Center panel).

        update_ui(load_from_backend): Refreshes all visual elements (scores, colors, logos) to match the GameManager state.

        handle_button_press/release: Implements "Long Press" logic (Short press = +1, Long press = Edit value).

        switch_simple_mode(): Toggles the UI and backend data payload between full detail and simplified view.

        _create_team_panel(...): Generates the UI column for a specific team.

app/startup.py - startup()

    Responsibility: Defines the application routing (/, /login, /preview) and startup sequence.

    Logic:

        Checks for oid (Overlay ID) in URL, Storage, or Environment.

        If missing, launches OidDialog.

        Initializes GUI and Backend.

app/theme.py

    Responsibility: Centralized configuration for UI colors (Tailwind classes) and button styles.

    Key Constants: 
        - GAME_BUTTON_CLASSES: Defines the shape, shadow, and text alignment (centered) of score buttons.
        - TACOLOR / TBCOLOR: Team colors.

C. Configuration & Extras
app/customization.py

    Responsibility: Manages cosmetic data that isn't strict game logic: Team Names, Logos, Colors, and Overlay geometry (X/Y/Width/Height).

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