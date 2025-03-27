from messages import Messages
import os
import json

class Customization:

    CONFIG_TAB = "Configuration"
    SCOREBOARD_TAB = "Scoreboard"

    A_TEAM = 'Team 1 Text Name'
    B_TEAM = 'Team 2 Text Name'
    LOGOS_BOOL='Logos'
    SET_COLOR = "Color 1"
    SET_TEXT_COLOR = "Text Color 1"
    GLOSS_EFFECT_BOOL = "Gradient"
    HEIGHT_FLOAT = "Height"
    HPOS_FLOAT = "Left-Right"
    VPOS_FLOAT = "Up-Down"
    WIDTH_FLOAT = "Width"
    GAME_COLOR = "Color 2"
    GAME_TEXT_COLOR = "Text Color 2"
    T1_COLOR = "Team 1 Color"
    T1_TEXT_COLOR = "Team 1 Text Color"
    T1_LOGO = "Team 1 Logo"
    T1_LOGO_FIT = "Team 1 Logo Fit"
    T2_COLOR = "Team 2 Color"
    T2_LOGO = "Team 2 Logo"
    T2_LOGO_FIT = "Team 2 Logo Fit"
    T2_TEXT_COLOR = "Team 2 Text Color"
    LOGO_FIT_CONTAIN = "contain"
    
    LOCAL_NAME = Messages.LOCAL
    VISITOR_NAME = Messages.VISITOR

    TEAM_VALUES_ICON = "icon"
    TEAM_VALUES_COLOR = "color"
    TEAM_VALUES_TEXT_COLOR = "text_color"
    DEFAULT_IMAGE= os.environ.get('APP_DEFAULT_LOGO', 'https://cdn-icons-png.flaticon.com/512/7788/7788863.png')

    provided_teams_json = os.environ.get('APP_TEAMS', None)

    if provided_teams_json == None or provided_teams_json == '':
        predefined_teams = {
            LOCAL_NAME: {TEAM_VALUES_ICON:DEFAULT_IMAGE, TEAM_VALUES_COLOR:"#060f8a", TEAM_VALUES_TEXT_COLOR:"#ffffff"},
            VISITOR_NAME: {TEAM_VALUES_ICON:DEFAULT_IMAGE, TEAM_VALUES_COLOR:"#ffffff", TEAM_VALUES_TEXT_COLOR:"#000000"},
        }
    else: 
        predefined_teams = json.loads(provided_teams_json)
    

    reset_state = {
        SET_TEXT_COLOR: "#ffffff",
        SET_COLOR: "#2a2f35",
        GLOSS_EFFECT_BOOL: "true",
        HEIGHT_FLOAT: 10,
        HPOS_FLOAT: -33,
        GAME_COLOR: "#ffffff",
        GAME_TEXT_COLOR: "#2a2f35",
        T1_COLOR: "#060f8a",
        T1_LOGO: DEFAULT_IMAGE,
        T1_LOGO_FIT: "contain",
        T1_TEXT_COLOR: "#ffffff",
        T2_COLOR: "#ffffff",
        T2_LOGO: DEFAULT_IMAGE,
        T2_LOGO_FIT: "contain",
        T2_TEXT_COLOR : "#000000",
        VPOS_FLOAT: -41.1,
        WIDTH_FLOAT: 30}


    def __init__(self, current_customization_state):
        self.customization_model = current_customization_state

    def getModel(self):
        return self.customization_model
    
    def setModel(self, new_model):
        self.customization_model = new_model

    def getTeamColor(self, team):
        if team == 1:
            return self.customization_model[Customization.T1_COLOR]
        else:
            return self.customization_model[Customization.T2_COLOR]
    
    def getTeamTextColor(self, team):
        if team == 1:
            return self.customization_model[Customization.T1_TEXT_COLOR]
        else:
            return self.customization_model[Customization.T2_TEXT_COLOR]
        
    def getTeamLogo(self, team):
        if team == 1:
            return Customization.fixIcon(self.customization_model[Customization.T1_LOGO])
        else:
            return Customization.fixIcon(self.customization_model[Customization.T2_LOGO])
        
    def getTeamColor(self, team):
        if team == 1:
            return self.customization_model[Customization.T1_COLOR]
        else:
            return self.customization_model[Customization.T2_COLOR]
    
    def setTeamTextColor(self, team, color):
        if team == 1:
            self.customization_model[Customization.T1_TEXT_COLOR] = color
        else:
            self.customization_model[Customization.T2_TEXT_COLOR] = color

    def setTeamColor(self, team, color):
        if team == 1:
            self.customization_model[Customization.T1_COLOR] = color
        else:
            self.customization_model[Customization.T2_COLOR] = color            
        
    def setTeamLogo(self, team, logo):
        if team == 1:
            self.customization_model[Customization.T1_LOGO] = logo
        else:
            self.customization_model[Customization.T2_LOGO] = logo

    def getSetColor(self):
        return self.customization_model[Customization.SET_COLOR]

    
    def getGameColor(self):
        return self.customization_model[Customization.GAME_COLOR]

    def getSetTextColor(self):
        return self.customization_model[Customization.SET_TEXT_COLOR]

    
    def getGameTextColor(self):
        return self.customization_model[Customization.GAME_TEXT_COLOR]

    def setSetColor(self, color):
        self.customization_model[Customization.SET_COLOR] = color

    
    def setGameColor(self, color):
        self.customization_model[Customization.GAME_COLOR] = color

    def setSetTextColor(self, color):
        self.customization_model[Customization.SET_TEXT_COLOR] = color

    def getTeamName(self, team):
        if (team == 1):
            return self.customization_model[Customization.A_TEAM]
        return self.customization_model[Customization.B_TEAM]
    
    def setTeamName(self, team, name):
        if (team == 1):
            self.customization_model[Customization.A_TEAM] = name
        else:
            self.customization_model[Customization.B_TEAM] = name
    
    def isShowLogos(self):
        return self.customization_model[Customization.LOGOS_BOOL]
    
    def setShowLogos(self, value):
        self.customization_model[Customization.LOGOS_BOOL] = value


    def setGameTextColor(self, color):
        self.customization_model[Customization.GAME_TEXT_COLOR] = color

    def isGlossy(self):
        return self.customization_model[Customization.GLOSS_EFFECT_BOOL]

    def setGlossy(self, value):
        self.customization_model[Customization.GLOSS_EFFECT_BOOL] = value                    

    def getWidth(self):
        return float(self.customization_model[Customization.WIDTH_FLOAT])

    def setWidth(self, width):
        self.customization_model[Customization.WIDTH_FLOAT] = width

    def getHeight(self):
        return float(self.customization_model[Customization.HEIGHT_FLOAT])

    def setHeight(self, float):
        self.customization_model[Customization.HEIGHT_FLOAT] = float

    def getHPos(self):
        return float(self.customization_model[Customization.HPOS_FLOAT])

    def setHPos(self, width):
        self.customization_model[Customization.HPOS_FLOAT] = width

    def getVPos(self):
        return float(self.customization_model[Customization.VPOS_FLOAT])

    def setVPos(self, float):
        self.customization_model[Customization.VPOS_FLOAT] = float

    def getPredefinedTeams():
        return Customization.predefined_teams

    def fixIcon(url):
        if url.startswith("//"):
            return "https:" + url
        return url        