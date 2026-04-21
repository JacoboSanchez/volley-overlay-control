import json
import logging

from app.env_vars_manager import EnvVarsManager

logger = logging.getLogger(__name__)


class Customization:

    CONFIG_TAB = "Configuration"
    SCOREBOARD_TAB = "Scoreboard"

    A_TEAM = 'Team 1 Text Name'
    B_TEAM = 'Team 2 Text Name'
    LOGOS_BOOL='Logos'
    GLOSS_EFFECT_BOOL = "Gradient"
    HEIGHT_FLOAT = "Height"
    HPOS_FLOAT = "Left-Right"
    VPOS_FLOAT = "Up-Down"
    WIDTH_FLOAT = "Width"
    T1_COLOR = "Team 1 Color"
    T1_TEXT_COLOR = "Team 1 Text Color"
    T1_LOGO = "Team 1 Logo"
    T1_LOGO_FIT = "Team 1 Logo Fit"
    T2_COLOR = "Team 2 Color"
    T2_LOGO = "Team 2 Logo"
    T2_LOGO_FIT = "Team 2 Logo Fit"
    T2_TEXT_COLOR = "Team 2 Text Color"
    LOGO_FIT_CONTAIN = "contain"
    SET_COLOR = "Color 1"
    SET_TEXT_COLOR = "Text Color 1"
    GAME_COLOR = "Color 2"
    GAME_TEXT_COLOR = "Text Color 2"
    COLOR3 = "Color 3"
    TEXT_COLOR3 = "Text Color 3"
    PREFERRED_STYLE = "preferredStyle"
    LOCAL_NAME = "Local"
    VISITOR_NAME = "Visitor"

    TEAM_VALUES_ICON = "icon"
    TEAM_VALUES_COLOR = "color"
    TEAM_VALUES_TEXT_COLOR = "text_color"
    DEFAULT_IMAGE= EnvVarsManager.get_env_var('APP_DEFAULT_LOGO', 'https://cdn-icons-png.flaticon.com/512/7788/7788863.png')


    RESET_COLORS = {
        SET_COLOR: "#2a2f35",
        GAME_COLOR: "#ffffff",
        COLOR3: "0055ff",
        SET_TEXT_COLOR: "#ffffff",
        GAME_TEXT_COLOR: "#2a2f35",
        TEXT_COLOR3: "FFFFFF"
    }


    reset_state = {
        SET_TEXT_COLOR: RESET_COLORS[SET_TEXT_COLOR],
        SET_COLOR: RESET_COLORS[SET_COLOR],
        GLOSS_EFFECT_BOOL: "true",
        LOGOS_BOOL: "true",
        HEIGHT_FLOAT: 10,
        HPOS_FLOAT: -33,
        GAME_COLOR: RESET_COLORS[GAME_COLOR],
        GAME_TEXT_COLOR: RESET_COLORS[GAME_TEXT_COLOR],
        T1_COLOR: "#060f8a",
        T1_LOGO: DEFAULT_IMAGE,
        T1_LOGO_FIT: "contain",
        T1_TEXT_COLOR: "#ffffff",
        T2_COLOR: "#ffffff",
        T2_LOGO: DEFAULT_IMAGE,
        T2_LOGO_FIT: "contain",
        T2_TEXT_COLOR : "#000000",
        COLOR3:RESET_COLORS[COLOR3],
        TEXT_COLOR3:RESET_COLORS[TEXT_COLOR3],
        VPOS_FLOAT: -41.1,
        WIDTH_FLOAT: 30}

    predefined_teams = {}
    THEMES = {}

    def refresh():
        provided_teams_json = EnvVarsManager.get_env_var('APP_TEAMS', None)

        if provided_teams_json is None or provided_teams_json == '':
            Customization.predefined_teams = {
                Customization.LOCAL_NAME: {Customization.TEAM_VALUES_ICON:Customization.DEFAULT_IMAGE, Customization.TEAM_VALUES_COLOR:"#060f8a", Customization.TEAM_VALUES_TEXT_COLOR:"#ffffff"},
                Customization.VISITOR_NAME: {Customization.TEAM_VALUES_ICON:Customization.DEFAULT_IMAGE, Customization.TEAM_VALUES_COLOR:"#ffffff", Customization.TEAM_VALUES_TEXT_COLOR:"#000000"},
            }
        else:
            try:
                Customization.predefined_teams = json.loads(provided_teams_json)
            except json.JSONDecodeError:
                logger.warning("Malformed APP_TEAMS env var; ignoring value")
                Customization.predefined_teams = {}


        provided_themes_json = EnvVarsManager.get_env_var('APP_THEMES', None)
        Customization.THEMES = {}
        if provided_themes_json:
            try:
                Customization.THEMES = json.loads(provided_themes_json)
            except json.JSONDecodeError:
                logger.warning("Malformed APP_THEMES env var; ignoring value")



    def __init__(self, current_customization_state):
        Customization.refresh()
        self.customization_model = current_customization_state

    def get_model(self):
        return self.customization_model

    def set_model(self, new_model):
        self.customization_model = new_model

    def get_team_color(self, team):
        if team == 1:
            return self.customization_model.get(Customization.T1_COLOR, "#060f8a")
        else:
            return self.customization_model.get(Customization.T2_COLOR, "#ffffff")

    def get_team_text_color(self, team):
        if team == 1:
            return self.customization_model.get(Customization.T1_TEXT_COLOR, "#ffffff")
        else:
            return self.customization_model.get(Customization.T2_TEXT_COLOR, "#000000")

    def get_team_logo(self, team):
        if team == 1:
            return Customization.fix_icon(self.customization_model.get(Customization.T1_LOGO, Customization.DEFAULT_IMAGE))
        else:
            return Customization.fix_icon(self.customization_model.get(Customization.T2_LOGO, Customization.DEFAULT_IMAGE))

    def set_team_text_color(self, team, color):
        if team == 1:
            self.customization_model[Customization.T1_TEXT_COLOR] = color
        else:
            self.customization_model[Customization.T2_TEXT_COLOR] = color

    def set_team_color(self, team, color):
        if team == 1:
            self.customization_model[Customization.T1_COLOR] = color
        else:
            self.customization_model[Customization.T2_COLOR] = color

    def set_team_logo(self, team, logo):
        if team == 1:
            self.customization_model[Customization.T1_LOGO] = logo
        else:
            self.customization_model[Customization.T2_LOGO] = logo


    def set_theme(self, theme:str):
        if theme in Customization.THEMES:
            for key, value in Customization.THEMES[theme].items():
                self.customization_model[key] = value

    def get_theme_names(self):
        return Customization.THEMES.keys()


    def get_set_color(self):
        return self.customization_model[Customization.SET_COLOR]


    def get_game_color(self):
        return self.customization_model[Customization.GAME_COLOR]

    def get_set_text_color(self):
        return self.customization_model[Customization.SET_TEXT_COLOR]


    def get_game_text_color(self):
        return self.customization_model[Customization.GAME_TEXT_COLOR]

    def set_set_color(self, color):
        self.customization_model[Customization.SET_COLOR] = color


    def set_game_color(self, color):
        self.customization_model[Customization.GAME_COLOR] = color

    def set_set_text_color(self, color):
        self.customization_model[Customization.SET_TEXT_COLOR] = color

    def get_team_name(self, team):
        old_key = Customization.A_TEAM if team == 1 else Customization.B_TEAM
        new_key = "Team 1 Name" if team == 1 else "Team 2 Name"

        if old_key in self.customization_model:
            return self.customization_model[old_key]
        return self.customization_model.get(new_key, "")

    def set_team_name(self, team, name):
        old_key = Customization.A_TEAM if team == 1 else Customization.B_TEAM
        new_key = "Team 1 Name" if team == 1 else "Team 2 Name"

        if old_key in self.customization_model:
            self.customization_model[old_key] = name
        else:
            self.customization_model[new_key] = name

    def is_show_logos(self):
        return self.customization_model.get(Customization.LOGOS_BOOL, "true")

    def set_show_logos(self, value):
        self.customization_model[Customization.LOGOS_BOOL] = value


    def set_game_text_color(self, color):
        self.customization_model[Customization.GAME_TEXT_COLOR] = color

    def is_glossy(self):
        return self.customization_model.get(Customization.GLOSS_EFFECT_BOOL, False)

    def set_glossy(self, value):
        self.customization_model[Customization.GLOSS_EFFECT_BOOL] = value

    def get_preferred_style(self):
        return self.customization_model.get(Customization.PREFERRED_STYLE, None)

    def set_preferred_style(self, style):
        if style:
            self.customization_model[Customization.PREFERRED_STYLE] = style
        elif Customization.PREFERRED_STYLE in self.customization_model:
            del self.customization_model[Customization.PREFERRED_STYLE]

    def get_width(self):
        val = self.customization_model.get(Customization.WIDTH_FLOAT, 30)
        return float(val) if val not in [None, 'None', ''] else 30.0

    def set_width(self, width):
        self.customization_model[Customization.WIDTH_FLOAT] = width

    def get_height(self):
        val = self.customization_model.get(Customization.HEIGHT_FLOAT, 10)
        return float(val) if val not in [None, 'None', ''] else 10.0

    def get_hpos(self):
        val = self.customization_model.get(Customization.HPOS_FLOAT, -33)
        return float(val) if val not in [None, 'None', ''] else -33.0

    def get_vpos(self):
        val = self.customization_model.get(Customization.VPOS_FLOAT, -41.1)
        return float(val) if val not in [None, 'None', ''] else -41.1

    def set_height(self, float_val):
        self.customization_model[Customization.HEIGHT_FLOAT] = float_val

    def get_h_pos(self):
        val = self.customization_model.get(Customization.HPOS_FLOAT, -33)
        return float(val) if val not in [None, 'None', ''] else -33.0

    def set_h_pos(self, width):
        self.customization_model[Customization.HPOS_FLOAT] = width

    def get_v_pos(self):
        val = self.customization_model.get(Customization.VPOS_FLOAT, -41.1)
        return float(val) if val not in [None, 'None', ''] else -41.1

    def set_v_pos(self, float_val):
        self.customization_model[Customization.VPOS_FLOAT] = float_val

    def get_predefined_teams():
        Customization.refresh()
        return Customization.predefined_teams

    def fix_icon(url):
        if url.startswith("//"):
            return "https:" + url
        return url
