import pytest
import sys
import os
import json

# Add the project's root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.customization import Customization

@pytest.fixture
def customization():
    """Returns a new Customization instance with the default reset state for each test."""
    # Start with a fresh copy of the reset state for isolation
    initial_state = Customization.reset_state.copy()
    return Customization(initial_state)

# --- Basic Getters and Setters ---

def test_initial_state(customization):
    """Tests that the customization model is initialized with default values."""
    assert customization.get_team_color(1) == "#060f8a"
    assert customization.get_team_text_color(2) == "#000000"
    assert customization.get_width() == 30.0
    assert customization.is_glossy() == "true"
    assert customization.get_team_name(1) is None # Names are not in the reset_state and should return None

def test_get_and_set_team_colors(customization):
    """Tests getting and setting colors for both teams."""
    customization.set_team_color(1, "#FF0000")
    assert customization.get_team_color(1) == "#FF0000"

    customization.set_team_text_color(2, "#00FF00")
    assert customization.get_team_text_color(2) == "#00FF00"

def test_get_and_set_team_logos(customization):
    """Tests getting and setting logos for both teams."""
    logo_url = "https://example.com/logo.png"
    customization.set_team_logo(1, logo_url)
    assert customization.get_team_logo(1) == logo_url

def test_get_and_set_team_names(customization):
    """Tests getting and setting team names."""
    customization.set_team_name(1, "Warriors")
    assert customization.get_team_name(1) == "Warriors"
    customization.set_team_name(2, "Titans")
    assert customization.get_team_name(2) == "Titans"

def test_get_and_set_scoreboard_colors(customization):
    """Tests the getters and setters for scoreboard element colors."""
    customization.set_set_color("#AAAAAA")
    assert customization.get_set_color() == "#AAAAAA"

    customization.set_game_text_color("#BBBBBB")
    assert customization.get_game_text_color() == "#BBBBBB"

def test_boolean_flags(customization):
    """Tests the getters and setters for boolean-like string flags."""
    customization.set_show_logos("false")
    assert customization.is_show_logos() == "false"

    customization.set_glossy("true")
    assert customization.is_glossy() == "true"

def test_geometry_setters(customization):
    """Tests the setters for scoreboard geometry and float conversion."""
    customization.set_width(50.5)
    assert customization.get_width() == 50.5

    customization.set_height(15.2)
    assert customization.get_height() == 15.2

    customization.set_h_pos(-20.0)
    assert customization.get_h_pos() == -20.0

    customization.set_v_pos(10.0)
    assert customization.get_v_pos() == 10.0
    
    # Test that it handles string inputs correctly
    customization.set_width("42.7")
    assert customization.get_width() == 42.7


# --- Advanced Scenarios and Edge Cases ---

def test_fix_icon_url(customization):
    """Tests the static method for fixing icon URLs."""
    assert Customization.fix_icon("//example.com/icon.png") == "https://example.com/icon.png"
    assert Customization.fix_icon("https://example.com/icon.png") == "https://example.com/icon.png"
    assert Customization.fix_icon("http://example.com/icon.png") == "http://example.com/icon.png"
    assert Customization.fix_icon("") == "" # Test empty string

def test_set_theme(customization, monkeypatch):
    """Tests applying a predefined theme."""
    themes = {
        "Test Theme": {
            "Team 1 Color": "#112233",
            "Width": 50.0,
            "Logos": "false"
        }
    }
    # Temporarily replace the THEMES constant for this test
    monkeypatch.setattr(Customization, "THEMES", themes)

    customization.set_theme("Test Theme")
    assert customization.get_team_color(1) == "#112233"
    assert customization.get_width() == 50.0
    assert customization.is_show_logos() == "false"
    # Ensure other values are untouched
    assert customization.get_height() == 10.0

def test_set_nonexistent_theme(customization, monkeypatch):
    """Tests that applying a nonexistent theme does not change the model."""
    themes = {"Real Theme": {"Width": 99.0}}
    monkeypatch.setattr(Customization, "THEMES", themes)
    
    initial_model = customization.get_model().copy()
    customization.set_theme("Fake Theme")
    
    assert customization.get_model() == initial_model

def test_direct_model_manipulation(customization):
    """Tests that directly changing the retrieved model dictionary is reflected."""
    model = customization.get_model()
    model[Customization.T1_COLOR] = "#ABCDEF"
    assert customization.get_team_color(1) == "#ABCDEF"

def test_set_new_model(customization):
    """Tests replacing the entire customization model."""
    new_model = {
        Customization.WIDTH_FLOAT: 42.0,
        Customization.HEIGHT_FLOAT: 21.0,
        Customization.T1_COLOR: "#000000"
    }
    customization.set_model(new_model)
    assert customization.get_width() == 42.0
    assert customization.get_height() == 21.0
    assert customization.get_team_color(1) == "#000000"
    # Check for a key that wasn't in the new model to ensure it's gone
    assert customization.get_model().get(Customization.T2_COLOR) is None
    # Check that get_team_name now returns None since the key is missing
    assert customization.get_team_name(1) is None


# --- Environment Variable Loading (Requires monkeypatch) ---

def test_predefined_teams_loading(monkeypatch):
    """Tests loading of predefined teams from environment variables."""
    teams_json = json.dumps({
        "Eagles": {"icon": "eagle.png", "color": "#0000FF", "text_color": "#FFFFFF"},
        "Sharks": {"icon": "shark.png", "color": "#CCCCCC", "text_color": "#000000"}
    })
    monkeypatch.setenv("APP_TEAMS", teams_json)
    
    # The teams are loaded at class level, so we need to reload the module
    # to see the change. This is an advanced technique.
    import importlib
    import app.customization as cust_module
    importlib.reload(cust_module)
    
    predefined_teams = cust_module.Customization.get_predefined_teams()
    assert "Eagles" in predefined_teams
    assert predefined_teams["Sharks"]["icon"] == "shark.png"

def test_predefined_themes_loading(monkeypatch):
    """Tests loading of customization themes from environment variables."""
    themes_json = json.dumps({
        "Dark Mode": {"Game Color": "#111111", "Game Text Color": "#EEEEEE"},
        "High Vis": {"Team 1 Color": "#FFFF00"}
    })
    monkeypatch.setenv("APP_THEMES", themes_json)

    import importlib
    import app.customization as cust_module
    importlib.reload(cust_module)

    assert "Dark Mode" in cust_module.Customization.THEMES
    assert cust_module.Customization.THEMES["High Vis"]["Team 1 Color"] == "#FFFF00"