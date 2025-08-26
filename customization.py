from messages import Messages
import os
import json

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
    LOCAL_NAME = Messages.get(Messages.LOCAL)
    VISITOR_NAME = Messages.get(Messages.VISITOR)

    TEAM_VALUES_ICON = "icon"
    TEAM_VALUES_COLOR = "color"
    TEAM_VALUES_TEXT_COLOR = "text_color"
    DEFAULT_IMAGE= os.environ.get('APP_DEFAULT_LOGO', 'https://cdn-icons-png.flaticon.com/512/7788/7788863.png')


    RESET_COLORS = { 
        SET_COLOR: "#2a2f35",
        GAME_COLOR: "#ffffff",
        COLOR3: "0055ff",
        SET_TEXT_COLOR: "#ffffff",
        GAME_TEXT_COLOR: "#2a2f35",
        TEXT_COLOR3: "FFFFFF"
    }   

    provided_teams_json = os.environ.get('APP_TEAMS', None)

    if provided_teams_json == None or provided_teams_json == '':
        predefined_teams = {
            LOCAL_NAME: {TEAM_VALUES_ICON:DEFAULT_IMAGE, TEAM_VALUES_COLOR:"#060f8a", TEAM_VALUES_TEXT_COLOR:"#ffffff"},
            VISITOR_NAME: {TEAM_VALUES_ICON:DEFAULT_IMAGE, TEAM_VALUES_COLOR:"#ffffff", TEAM_VALUES_TEXT_COLOR:"#000000"},
        }
    else: 
        predefined_teams = json.loads(provided_teams_json)
    
    
    provided_themes_json = os.environ.get('APP_THEMES', None)
    THEMES = {}
    if provided_themes_json:
        try:
            THEMES = json.loads(provided_themes_json)
        except json.JSONDecodeError:
            print(f"Error decoding THEMES from environment variable: {provided_themes_json}")


    reset_state = {
        SET_TEXT_COLOR: RESET_COLORS[SET_TEXT_COLOR],
        SET_COLOR: RESET_COLORS[SET_COLOR],
        GLOSS_EFFECT_BOOL: "true",
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


    def __init__(self, current_customization_state):
        self.customization_model = current_customization_state

    def get_model(self):
        return self.customization_model
    
    def set_model(self, new_model):
        self.customization_model = new_model

    def get_team_color(self, team):
        if team == 1:
            return self.customization_model[Customization.T1_COLOR]
        else:
            return self.customization_model[Customization.T2_COLOR]
    
    def get_team_text_color(self, team):
        if team == 1:
            return self.customization_model[Customization.T1_TEXT_COLOR]
        else:
            return self.customization_model[Customization.T2_TEXT_COLOR]
        
    def get_team_logo(self, team):
        if team == 1:
            return Customization.fix_icon(self.customization_model[Customization.T1_LOGO])
        else:
            return Customization.fix_icon(self.customization_model[Customization.T2_LOGO])
        
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
        if (team == 1):
            return self.customization_model[Customization.A_TEAM]
        return self.customization_model[Customization.B_TEAM]
    
    def set_team_name(self, team, name):
        if (team == 1):
            self.customization_model[Customization.A_TEAM] = name
        else:
            self.customization_model[Customization.B_TEAM] = name
    
    def is_show_logos(self):
        return self.customization_model[Customization.LOGOS_BOOL]
    
    def set_show_logos(self, value):
        self.customization_model[Customization.LOGOS_BOOL] = value


    def set_game_text_color(self, color):
        self.customization_model[Customization.GAME_TEXT_COLOR] = color

    def is_glossy(self):
        return self.customization_model[Customization.GLOSS_EFFECT_BOOL]

    def set_glossy(self, value):
        self.customization_model[Customization.GLOSS_EFFECT_BOOL] = value                    

    def get_width(self):
        return float(self.customization_model[Customization.WIDTH_FLOAT])

    def set_width(self, width):
        self.customization_model[Customization.WIDTH_FLOAT] = width

    def get_height(self):
        return float(self.customization_model[Customization.HEIGHT_FLOAT])

    def set_height(self, float):
        self.customization_model[Customization.HEIGHT_FLOAT] = float

    def get_h_pos(self):
        return float(self.customization_model[Customization.HPOS_FLOAT])

    def set_h_pos(self, width):
        self.customization_model[Customization.HPOS_FLOAT] = width

    def get_v_pos(self):
        return float(self.customization_model[Customization.VPOS_FLOAT])

    def set_v_pos(self, float):
        self.customization_model[Customization.VPOS_FLOAT] = float

    def get_predefined_teams():
        return Customization.predefined_teams

    def fix_icon(url):
        if url.startswith("//"):
            return "https:" + url
        return url