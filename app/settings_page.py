import os
import json
from nicegui import ui
from typing import List, Dict, Any
from urllib.parse import urlparse

class SettingsPage:
    """Independent settings page for managing teams, overlays, and themes."""

    def __init__(self):
        # General Settings
        self.match_game_points = os.environ.get("MATCH_GAME_POINTS", "25")
        self.match_game_points_last_set = os.environ.get("MATCH_GAME_POINTS_LAST_SET", "15")
        self.match_sets = os.environ.get("MATCH_SETS", "5")
        self.ordered_teams = os.environ.get("ORDERED_TEAMS", "true").lower() == "true"
        self.scoreboard_language = os.environ.get("SCOREBOARD_LANGUAGE", "en")
        self.logging_level = os.environ.get("LOGGING_LEVEL", "warning")
        self.app_default_logo = os.environ.get("APP_DEFAULT_LOGO", "")

        # Other settings
        self.teams: List[Dict[str, Any]] = self._load_teams_from_env()
        self.overlays: List[Dict[str, Any]] = self._load_overlays_from_env()
        self.themes: List[Dict[str, Any]] = self._load_themes_from_env()
        self.single_overlay_mode = os.environ.get("UNO_OVERLAY_OID") is not None
        self.uno_overlay_oid = os.environ.get("UNO_OVERLAY_OID", "")
        self.uno_overlay_output = os.environ.get("UNO_OVERLAY_OUTPUT", "")
        self.allow_custom_overlay = not (os.environ.get("HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED", "false").lower() == "true")
        self.json_multiline = os.environ.get("JSON_MULTILINE_OUTPUT", "true").lower() == "true"

    def _load_from_env(self, key: str, default: Any) -> Any:
        """Loads data from a JSON environment variable."""
        json_str = os.environ.get(key, "{}")
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            ui.notify(f"Could not read JSON from {key}. Starting with an empty configuration.", type='negative')
            return default

    def _load_teams_from_env(self) -> List[Dict[str, Any]]:
        """Loads teams from the environment variable and converts the dict to a list."""
        teams_dict = self._load_from_env("APP_TEAMS", {})
        teams_list = []
        for name, properties in teams_dict.items():
            team_data = {"name": name}
            team_data.update(properties)
            teams_list.append(team_data)
        return teams_list

    def _load_overlays_from_env(self) -> List[Dict[str, Any]]:
        """Loads overlays from the environment variable and converts the dict to a list."""
        overlays_dict = self._load_from_env("PREDEFINED_OVERLAYS", {})
        overlays_list = []
        for name, properties in overlays_dict.items():
            overlay_data = {"name": name}
            overlay_data.update(properties)
            overlays_list.append(overlay_data)
        return overlays_list
        
    def _load_themes_from_env(self) -> List[Dict[str, Any]]:
        """Loads themes from the environment variable and converts the dict to a list."""
        themes_dict = self._load_from_env("APP_THEMES", {})
        themes_list = []
        for name, properties in themes_dict.items():
            theme_data = {"name": name}
            properties['team1_colors_enabled'] = "Team 1 Color" in properties
            properties['team2_colors_enabled'] = "Team 2 Color" in properties
            theme_data.update(properties)
            themes_list.append(theme_data)
        return themes_list

    def _get_env_file_content(self) -> str:
        """Generates the content for the .env file."""
        env_vars = {
            "MATCH_GAME_POINTS": f"'{self.match_game_points}'",
            "MATCH_GAME_POINTS_LAST_SET": f"'{self.match_game_points_last_set}'",
            "MATCH_SETS": f"'{self.match_sets}'",
            "ORDERED_TEAMS": f"'{str(self.ordered_teams).lower()}'",
            "SCOREBOARD_LANGUAGE": f"'{self.scoreboard_language}'",
            "LOGGING_LEVEL": f"'{self.logging_level}'",
            "APP_DEFAULT_LOGO": f"'{self.app_default_logo}'",
        }

        json_indent = 4 if self.json_multiline else None

        teams_to_save = {}
        for team in self.teams:
            if team_name := team.get("name", "").strip():
                properties = team.copy()
                del properties["name"]
                teams_to_save[team_name] = properties
        if teams_to_save:
            env_vars["APP_TEAMS"] = f"'{json.dumps(teams_to_save, indent=json_indent)}'"

        if self.single_overlay_mode:
            env_vars["UNO_OVERLAY_OID"] = f"'{self.uno_overlay_oid}'"
            env_vars["UNO_OVERLAY_OUTPUT"] = f"'{self.uno_overlay_output}'"
        else:
            overlays_to_save = {}
            for overlay in self.overlays:
                if overlay_name := overlay.get("name", "").strip():
                    properties = overlay.copy()
                    del properties["name"]
                    overlays_to_save[overlay_name] = properties
            if overlays_to_save:
                env_vars["PREDEFINED_OVERLAYS"] = f"'{json.dumps(overlays_to_save, indent=json_indent)}'"
            env_vars["HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED"] = f"'{str(not self.allow_custom_overlay).lower()}'"

        themes_to_save = {}
        for theme in self.themes:
            if theme_name := theme.get("name", "").strip():
                properties = theme.copy()
                del properties["name"]

                if not properties.get('team1_colors_enabled'):
                    properties.pop('Team 1 Color', None)
                    properties.pop('Team 1 Text Color', None)
                if not properties.get('team2_colors_enabled'):
                    properties.pop('Team 2 Color', None)
                    properties.pop('Team 2 Text Color', None)

                properties.pop('team1_colors_enabled', None)
                properties.pop('team2_colors_enabled', None)
                
                themes_to_save[theme_name] = properties
        if themes_to_save:
            env_vars["APP_THEMES"] = f"'{json.dumps(themes_to_save, indent=json_indent)}'"

        return "\n".join([f"{key}={value}" for key, value in env_vars.items()])

    def _download_env_file(self):
        """Triggers the download of the .env file."""
        content = self._get_env_file_content()
        ui.download(content.encode(), ".env")
        
    async def _upload_env_file(self, e):
        """Handles the upload of a .env file."""
        content = e.content.read().decode()
        
        for line in content.splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                if value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                os.environ[key] = value

        self.__init__()
        
        self.general_container.clear()
        self._build_general_tab_content()
        self.teams_container.clear()
        self._build_teams_ui()
        self.overlays_container.clear()
        self._build_overlays_ui()
        self.themes_container.clear()
        self._build_themes_ui()
        
        ui.notify("Configuration loaded successfully!", type='positive')

    def is_valid_url(self, url):
        """Checks if a string is a valid URL."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    def init_ui(self):
        """Initializes the user interface for the settings page."""
        with ui.header(elevated=True).classes('bg-primary text-white'):
            ui.label('Scoreboard Settings').classes('text-h5')
            ui.space()
            ui.button("Back to Scoreboard", on_click=lambda: ui.navigate.to('/')).props('flat color=white')

        with ui.tabs().classes('w-full') as tabs:
            general_tab = ui.tab('General')
            teams_tab = ui.tab('Teams')
            overlay_tab = ui.tab('Graphic Overlay')
            theme_tab = ui.tab('Theme')
            save_load_tab = ui.tab('Save/Load')

        with ui.tab_panels(tabs, value=general_tab).classes('w-full p-8 items-center'):
            with ui.tab_panel(general_tab):
                self._build_general_tab()
            with ui.tab_panel(teams_tab):
                self._build_teams_tab()
            with ui.tab_panel(overlay_tab):
                self._build_overlay_tab()
            with ui.tab_panel(theme_tab):
                self._build_theme_tab()
            with ui.tab_panel(save_load_tab):
                self._build_save_load_tab()
    
    def _build_general_tab(self):
        with ui.column().classes('w-full items-center'):
            ui.label('General Settings').classes('text-h4 font-semibold')
            self.general_container = ui.column().classes('w-full max-w-2xl gap-4')
            self._build_general_tab_content()

    def _build_general_tab_content(self):
        with self.general_container:
            with ui.card().classes('w-full'):
                ui.label("Match Rules").classes('text-h6')
                with ui.row().classes('w-full items-center'):
                    ui.input(label="Points per Set", value=self.match_game_points,
                             on_change=lambda e: setattr(self, 'match_game_points', e.value)).props('type=number').classes('w-32')
                    ui.input(label="Last Set Points", value=self.match_game_points_last_set,
                             on_change=lambda e: setattr(self, 'match_game_points_last_set', e.value)).props('type=number').classes('w-32')
                    ui.input(label="Sets to Win", value=self.match_sets,
                             on_change=lambda e: setattr(self, 'match_sets', e.value)).props('type=number').classes('w-32')

            with ui.card().classes('w-full'):
                ui.label("Application Settings").classes('text-h6')
                logo_input = ui.input(label="Default Logo URL", value=self.app_default_logo,
                                       on_change=lambda e: setattr(self, 'app_default_logo', e.value)).classes('w-full')
                ui.image().bind_source_from(logo_input, 'value').classes('w-32 h-32').bind_visibility_from(logo_input, 'value', backward=self.is_valid_url)

                ui.checkbox('Show team names ordered', value=self.ordered_teams,
                          on_change=lambda e: setattr(self, 'ordered_teams', e.value))
                with ui.row().classes('w-full items-center'):
                    ui.label("Language:")
                    ui.select(options=['en', 'es'], value=self.scoreboard_language,
                              on_change=lambda e: setattr(self, 'scoreboard_language', e.value))
                with ui.row().classes('w-full items-center'):
                    ui.label("Logging Level:")
                    ui.select(options=['debug', 'info', 'warning', 'error'], value=self.logging_level,
                              on_change=lambda e: setattr(self, 'logging_level', e.value))


    def _build_teams_tab(self):
        with ui.column().classes('w-full items-center'):
            ui.label('Team Editor').classes('text-h4 font-semibold')
            self.teams_container = ui.column().classes('w-full max-w-2xl gap-4')
            self._build_teams_ui()
            with ui.row().classes('mt-8 gap-4'):
                ui.button('Add Team', on_click=self._add_team, icon='add').props('color=positive')

    def _build_overlay_tab(self):
        with ui.column().classes('w-full items-center'):
            ui.label('Overlay Editor').classes('text-h4 font-semibold')
            
            with ui.row().classes('w-full max-w-2xl justify-start'):
                mode_switch = ui.switch('Single Overlay Mode', value=self.single_overlay_mode,
                                        on_change=lambda e: setattr(self, 'single_overlay_mode', e.value))

            with ui.column().classes('w-full max-w-2xl gap-4').bind_visibility_from(mode_switch, 'value'):
                ui.input(label="UNO Overlay OID", value=self.uno_overlay_oid,
                         on_change=lambda e: setattr(self, 'uno_overlay_oid', e.value)).classes('w-full')
                output_input = ui.input(label="UNO Overlay Output", value=self.uno_overlay_output,
                                        on_change=lambda e: setattr(self, 'uno_overlay_output', e.value)).classes('w-full')
                
                with ui.card().classes('w-full h-96').bind_visibility_from(output_input, 'value',
                                                                          backward=self.is_valid_url):
                    ui.html().bind_content_from(output_input, 'value',
                                               backward=lambda url: f'<iframe src="{url}" width="100%" height="100%"></iframe>')

            with ui.column().classes('w-full max-w-2xl gap-4').bind_visibility_from(mode_switch, 'value', backward=lambda val: not val):
                ui.checkbox('Allow custom overlay', value=self.allow_custom_overlay,
                          on_change=lambda e: setattr(self, 'allow_custom_overlay', e.value))
                self.overlays_container = ui.column().classes('w-full max-w-2xl gap-4')
                self._build_overlays_ui()
                with ui.row().classes('mt-8 gap-4'):
                    ui.button('Add Overlay', on_click=self._add_overlay, icon='add').props('color=positive')
    
    def _build_theme_tab(self):
        with ui.column().classes('w-full items-center'):
            ui.label('Theme Editor').classes('text-h4 font-semibold')
            self.themes_container = ui.column().classes('w-full max-w-2xl gap-4')
            self._build_themes_ui()
            with ui.row().classes('mt-8 gap-4'):
                ui.button('Add Theme', on_click=self._add_theme, icon='add').props('color=positive')

    def _build_save_load_tab(self):
        with ui.column().classes('w-full items-center'):
            ui.label('Save & Load Configuration').classes('text-h4 font-semibold')
            with ui.row().classes('mt-8 gap-4'):
                ui.button('Download .env', on_click=self._download_env_file, icon='download').props('color=primary')
                ui.upload(on_upload=self._upload_env_file, auto_upload=True).props('icon=upload color=secondary')

    def _build_teams_ui(self):
        """Builds the UI for editing the list of teams."""
        self.teams_container.clear()
        with self.teams_container:
            if not self.teams:
                ui.label("There are no teams defined. Add one to get started!").classes('text-center text-gray-500')
            for team in self.teams:
                self.create_team_card(team)

    def _build_overlays_ui(self):
        """Builds the UI for editing the list of overlays."""
        if hasattr(self, 'overlays_container'):
            self.overlays_container.clear()
            with self.overlays_container:
                if not self.overlays:
                    ui.label("No overlays defined.").classes('text-center text-gray-500')
                for overlay in self.overlays:
                    self.create_overlay_card(overlay)

    def _build_themes_ui(self):
        """Builds the UI for editing the list of themes."""
        self.themes_container.clear()
        with self.themes_container:
            if not self.themes:
                ui.label("No themes defined.").classes('text-center text-gray-500')
            for theme in self.themes:
                self.create_theme_card(theme)

    def create_team_card(self, team: Dict[str, Any]):
        """Creates a UI card for a single team."""
        with ui.card().classes('w-full'):
            with ui.row().classes('w-full items-center no-wrap gap-4'):
                icon_button = ui.button(on_click=lambda: self.icon_dialog(team, icon_button)).props('round dense flat').classes('w-14 h-14 p-0')
                self.update_icon_button(team, icon_button)
                
                ui.input(label="Name", value=team.get("name", ""), on_change=lambda e: team.update(name=e.value)).classes('flex-grow')
                
                with ui.button(icon='colorize').props('round dense flat').style(f'background-color: {team.get("color", "#fff")}') as color_button:
                    ui.tooltip('Main Color')
                    ui.color_picker(value=team.get("color", "#fff"), on_pick=lambda e: self.update_color(team, 'color', e.color, color_button))

                with ui.button(icon='format_color_text').props('round dense flat').style(f'background-color: {team.get("text_color", "#000")}') as text_color_button:
                    ui.tooltip('Text Color')
                    ui.color_picker(value=team.get("text_color", "#000"), on_pick=lambda e: self.update_color(team, 'text_color', e.color, text_color_button))

                with ui.button(icon='delete', on_click=lambda: self._confirm_delete(team, self._remove_team, "team")).props('flat color=negative'):
                    ui.tooltip('Remove Team')

    def create_overlay_card(self, overlay: Dict[str, Any]):
        """Creates a UI card for an overlay."""
        with ui.card().classes('w-full'):
            with ui.row().classes('w-full items-center no-wrap gap-4'):
                ui.input(label="Name", value=overlay.get("name", ""), on_change=lambda e: overlay.update(name=e.value)).classes('flex-grow')
                ui.input(label="Control Token", value=overlay.get("control", ""), on_change=lambda e: overlay.update(control=e.value)).classes('flex-grow')
                ui.input(label="Output URL", value=overlay.get("output", ""), on_change=lambda e: overlay.update(output=e.value)).classes('flex-grow')
                with ui.button(icon='delete', on_click=lambda: self._confirm_delete(overlay, self._remove_overlay, "overlay")).props('flat color=negative'):
                    ui.tooltip('Remove Overlay')
    
    def create_theme_card(self, theme: Dict[str, Any]):
        """Creates a UI card for a single theme."""
        with ui.expansion(text=theme.get("name", "New Theme"), group='themes').classes('w-full bg-gray-100 rounded-lg') as expansion:
            with ui.card().classes('w-full p-4'):
                with ui.row().classes('w-full items-center justify-between'):
                    theme_name_input = ui.input(
                        label="Theme Name",
                        value=theme.get("name", "New Theme"),
                    ).classes('flex-grow').bind_value(theme, "name").bind_value_to(expansion, 'text')
                    ui.button(icon='delete', on_click=lambda: self._confirm_delete(theme, self._remove_theme, "theme")).props('flat color=negative')

                ui.separator().classes('my-4')

                with ui.expansion("Colors").classes('w-full'):
                    with ui.row().classes('w-full gap-4 items-center'):
                        with ui.column():
                            ui.label("Game").classes('text-center')
                            with ui.row():
                                with ui.button(icon='colorize').props('round dense flat').style(f'background-color: {theme.get("Color 2", "#000000")}') as color_button:
                                    ui.tooltip('Game BG')
                                    ui.color_picker(value=theme.get("Color 2", "#000000"), on_pick=lambda e: self.update_theme_color(theme, "Color 2", e.color, color_button))
                                with ui.button(icon='format_color_text').props('round dense flat').style(f'background-color: {theme.get("Text Color 2", "#FFFFFF")}') as text_color_button:
                                    ui.tooltip('Game Text')
                                    ui.color_picker(value=theme.get("Text Color 2", "#FFFFFF"), on_pick=lambda e: self.update_theme_color(theme, "Text Color 2", e.color, text_color_button))
                        
                        ui.separator().props('vertical')

                        with ui.column():
                            ui.label("Sets").classes('text-center')
                            with ui.row():
                                with ui.button(icon='colorize').props('round dense flat').style(f'background-color: {theme.get("Color 1", "#333333")}') as color_button:
                                    ui.tooltip('Set BG')
                                    ui.color_picker(value=theme.get("Color 1", "#333333"), on_pick=lambda e: self.update_theme_color(theme, "Color 1", e.color, color_button))
                                with ui.button(icon='format_color_text').props('round dense flat').style(f'background-color: {theme.get("Text Color 1", "#FFFFFF")}') as text_color_button:
                                    ui.tooltip('Set Text')
                                    ui.color_picker(value=theme.get("Text Color 1", "#FFFFFF"), on_pick=lambda e: self.update_theme_color(theme, "Text Color 1", e.color, text_color_button))

                        ui.separator().props('vertical')

                        with ui.column():
                            team1_switch = ui.switch('Team 1', value=theme.get('team1_colors_enabled', False), on_change=lambda e: theme.update(team1_colors_enabled=e.value))
                            with ui.row().bind_visibility_from(team1_switch, 'value'):
                                with ui.button(icon='colorize').props('round dense flat').style(f'background-color: {theme.get("Team 1 Color", "#060f8a")}') as color_button:
                                    ui.tooltip('Team 1 BG')
                                    ui.color_picker(value=theme.get("Team 1 Color", "#060f8a"), on_pick=lambda e: self.update_theme_color(theme, "Team 1 Color", e.color, color_button))
                                with ui.button(icon='format_color_text').props('round dense flat').style(f'background-color: {theme.get("Team 1 Text Color", "#ededed")}') as text_color_button:
                                    ui.tooltip('Team 1 Text')
                                    ui.color_picker(value=theme.get("Team 1 Text Color", "#ededed"), on_pick=lambda e: self.update_theme_color(theme, "Team 1 Text Color", e.color, text_color_button))
                    
                        ui.separator().props('vertical')

                        with ui.column():
                            team2_switch = ui.switch('Team 2', value=theme.get('team2_colors_enabled', False), on_change=lambda e: theme.update(team2_colors_enabled=e.value))
                            with ui.row().bind_visibility_from(team2_switch, 'value'):
                                with ui.button(icon='colorize').props('round dense flat').style(f'background-color: {theme.get("Team 2 Color", "#ededed")}') as color_button:
                                    ui.tooltip('Team 2 BG')
                                    ui.color_picker(value=theme.get("Team 2 Color", "#ededed"), on_pick=lambda e: self.update_theme_color(theme, "Team 2 Color", e.color, color_button))
                                with ui.button(icon='format_color_text').props('round dense flat').style(f'background-color: {theme.get("Team 2 Text Color", "#2f2f2f")}') as text_color_button:
                                    ui.tooltip('Team 2 Text')
                                    ui.color_picker(value=theme.get("Team 2 Text Color", "#2f2f2f"), on_pick=lambda e: self.update_theme_color(theme, "Team 2 Text Color", e.color, text_color_button))

                with ui.expansion("Position & Size").classes('w-full'):
                    with ui.row().classes('w-full gap-4'):
                        ui.input(label='Position X', value=theme.get("Left-Right", 0), on_change=lambda e: theme.update(**{"Left-Right": e.value})).props('type=number')
                        ui.input(label='Position Y', value=theme.get("Up-Down", 0), on_change=lambda e: theme.update(**{"Up-Down": e.value})).props('type=number')
                        ui.input(label='Width', value=theme.get("Width", 100), on_change=lambda e: theme.update(Width=e.value)).props('type=number')
                        ui.input(label='Height', value=theme.get("Height", 100), on_change=lambda e: theme.update(Height=e.value)).props('type=number')

                with ui.expansion("Effects").classes('w-full'):
                    with ui.row().classes('w-full gap-4 items-center'):
                        ui.switch('Show Logos', value=theme.get("Logos", False), on_change=lambda e: theme.update(Logos=e.value))
                        ui.switch('Gradient Effect', value=theme.get("Glossy", False), on_change=lambda e: theme.update(Glossy=e.value))

    def _confirm_delete(self, item: Dict[str, Any], remove_action: callable, item_type: str):
        """Opens a confirmation dialog before deleting an item."""
        with ui.dialog() as dialog, ui.card():
            ui.card_section()
            ui.label(f'Are you sure you want to delete the {item_type} "{item.get("name")}"?')
            with ui.card_actions().classes('justify-end'):
                ui.button('Cancel', on_click=dialog.close, color='grey')
                ui.button('Delete', on_click=lambda: (remove_action(item), dialog.close()), color='negative')
        dialog.open()

    def update_color(self, item: Dict[str, Any], key: str, color: str, button: ui.button):
        """Updates a color and the button's style."""
        item[key] = color
        button.style(f'background-color: {color}')
        ui.notify(f'Color updated to {color}')

    def update_theme_color(self, theme: Dict[str, Any], key: str, color: str, button: ui.button):
        """Updates a theme color and the button's style."""
        theme[key] = color
        button.style(f'background-color: {color}')
        ui.notify(f'Color updated to {color}')

    def update_icon_button(self, team: Dict[str, Any], button: ui.button):
        """Updates the team icon."""
        button.clear()
        with button:
            if icon_url := team.get("icon", "").strip():
                ui.image(icon_url).classes('w-full h-full rounded-full').on('error', lambda: self.handle_image_error(button))
            else:
                ui.icon('image', size='lg')

    def handle_image_error(self, button: ui.button):
        """Handles image loading errors."""
        button.clear()
        with button:
            ui.icon('broken_image', size='lg', color='negative')
        ui.notify("Could not load the icon image.", type='warning')

    def icon_dialog(self, team: Dict[str, Any], button: ui.button):
        """Dialog to edit the icon URL."""
        with ui.dialog() as dialog, ui.card().classes('min-w-[400px]'):
            ui.label('Edit Icon URL').classes('text-h6')
            icon_url_input = ui.input(label='Icon URL', value=team.get("icon", "")).classes('w-full')
            with ui.row().classes('w-full justify-end mt-4'):
                ui.button('Cancel', on_click=dialog.close, color='grey')
                ui.button('Save', on_click=lambda: (
                    team.update(icon=icon_url_input.value),
                    self.update_icon_button(team, button),
                    dialog.close(),
                ))
        dialog.open()

    def _add_team(self):
        """Adds a new team."""
        self.teams.append({"name": "New Team", "icon": "", "color": "#FFFFFF", "text_color": "#000000"})
        self._build_teams_ui()

    def _remove_team(self, team_to_remove: Dict[str, Any]):
        """Removes a team."""
        self.teams = [t for t in self.teams if t is not team_to_remove]
        self._build_teams_ui()
    
    def _add_overlay(self):
        """Adds a new overlay."""
        self.overlays.append({"name": "New Overlay", "control": "", "output": ""})
        self._build_overlays_ui()

    def _remove_overlay(self, overlay_to_remove: Dict[str, Any]):
        """Removes an overlay."""
        self.overlays = [o for o in self.overlays if o is not overlay_to_remove]
        self._build_overlays_ui()

    def _add_theme(self):
        """Adds a new theme."""
        self.themes.append({"name": "New Theme"})
        self._build_themes_ui()

    def _remove_theme(self, theme_to_remove: Dict[str, Any]):
        """Removes a theme."""
        self.themes = [t for t in self.themes if t is not theme_to_remove]
        self._build_themes_ui()