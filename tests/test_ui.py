import pytest
import json
import os
import asyncio
from unittest.mock import patch
from nicegui.testing import User
from app.startup import startup
from app.theme import *
from app.customization import Customization

import main
from app.backend import Backend

# pylint: disable=missing-function-docstring

# Mark all tests in this file as asynchronous
pytestmark = pytest.mark.asyncio

# --- Functions and Fixtures ---

def load_fixture(name):
    """Auxiliary function to load a JSON file from the fixtures folder."""
    path = os.path.join(os.path.dirname(__file__), 'fixtures', f'{name}.json')
    with open(path) as f:
        return json.load(f)

@pytest.fixture
def mock_backend():
    """
    Main fixture that mocks the Backend. Now also loads
    customization data from a JSON file.
    """
    with patch('app.startup.Backend') as mock_backend_class:
        mock_instance = mock_backend_class.return_value
        
        # --- Default mock behavior ---
        mock_instance.is_visible.return_value = True
        # Load initial scoreboard state
        mock_instance.get_current_model.return_value = load_fixture('base_model')
        # Load initial customization state
        mock_instance.get_current_customization.return_value = load_fixture('base_customization')
        # Ensure OID validation is successful
        mock_instance.validate_and_store_model_for_oid.return_value = mock_backend_class.ValidationResult.VALID
        
        yield mock_instance

async def test_game_buttons_increment(user: User, mock_backend):
    await user.open('/')
    for i in range(1, 2):
        await user.should_see('00', marker=f'team-{i}-score')
        result = user.find(marker=f'team-{i}-score').elements.pop().text
        assert result == '00'
        user.find(marker=f'team-{i}-score').click()
        result = user.find(marker=f'team-{i}-score').elements.pop().text
        assert result == '01'
        user.find(marker=f'team-{i}-score').click()
        result = user.find(marker=f'team-{i}-score').elements.pop().text
        assert result == '02'
    mock_backend.save.assert_called()

async def test_set_buttons_increment(user: User, mock_backend):
    await user.open('/')
    for i in range(1, 2):
        await user.should_see('0', marker=f'team-{i}-sets')
        user.find(marker=f'team-{i}-sets').click()
        await user.should_see('1', marker=f'team-{i}-sets')
    mock_backend.save.assert_called()

async def test_timeout_buttons(user: User, mock_backend):
    await user.open('/')
    # Initially, no timeout icons should be visible
    for i in range(1, 2):
        await user.should_not_see(marker=f'team-{i}-timeouts-display')
        await user.should_not_see(marker=f'timeout-{i}-number-0')
        await user.should_not_see(marker=f'timeout-{i}-number-1')
        await user.should_see(marker=f'team-{i}-timeout')
        user.find(marker=f'team-{i}-timeout').click()
        await user.should_see(marker=f'team-{i}-timeout')
        # Now there should be one icon
        await user.should_see(marker=f'timeout-{i}-number-0')
        await user.should_not_see(marker=f'timeout-{i}-number-1')
        user.find(marker=f'team-{i}-timeout').click()
        await user.should_see(marker=f'timeout-{i}-number-0')
        await user.should_see(marker=f'timeout-{i}-number-1')
    
    mock_backend.save.assert_called()

async def test_set_pagination(user: User, mock_backend):
    """Tests that the set pagination works correctly."""
    await user.open('/')
    await user.should_see('0', marker='team-1-score')
    user.find(marker='team-1-score').click()
    await user.should_see('1', marker='team-1-score')

    # Click the next set button in the pagination
    user.find('2', marker='set-selector').click()
    # The score for the new set should be 00
    await user.should_see('0', marker='team-1-score')

    # Go back to the previous set
    user.find('1', marker='set-selector').click()
    # The score should be the one we set before
    await user.should_see('1', marker='team-1-score')

async def test_serve_icon_asignation(user: User, mock_backend):
    """Tests that the serve icon is assigned to the scoring team."""
    await user.open('/')
    await user.should_see(marker='team-1-serve')
    # Initially no serve is set
    team1_serve_icon = user.find(marker='team-1-serve')
    assert TACOLOR_VLIGHT == team1_serve_icon.elements.pop().props['color']
    team2_serve_icon = user.find(marker='team-2-serve')
    assert TBCOLOR_VLIGHT == team2_serve_icon.elements.pop().props['color']
    
    # point scored by team 1 => t1 color high, t2 color light 
    user.find(marker='team-1-serve').click()
    await user.should_see(marker='team-1-serve')
    team1_serve_icon = user.find(marker='team-1-serve')
    assert TACOLOR_HIGH in team1_serve_icon.elements.pop().props['color']
    team2_serve_icon = user.find(marker='team-2-serve')
    assert TBCOLOR_VLIGHT == team2_serve_icon.elements.pop().props['color']

    # point scored by team 2 => t2 color high, t1 color light 
    user.find(marker='team-2-serve').click()
    await user.should_see(marker='team-2-serve')
    team2_serve_icon = user.find(marker='team-2-serve')
    assert TBCOLOR_HIGH == team2_serve_icon.elements.pop().props['color']
    team1_serve_icon = user.find(marker='team-1-serve')
    assert TACOLOR_VLIGHT == team1_serve_icon.elements.pop().props['color']

    # point scored by team 1 => t1 color high, t2 color light 
    user.find(marker='team-1-serve').click()
    await user.should_see(marker='team-2-serve')
    team2_serve_icon = user.find(marker='team-2-serve')
    assert TBCOLOR_VLIGHT == team2_serve_icon.elements.pop().props['color']
    team1_serve_icon = user.find(marker='team-1-serve')
    assert TACOLOR_HIGH == team1_serve_icon.elements.pop().props['color']



async def test_undo_button(user: User, mock_backend):
    """Tests that the undo button reverts the last score."""
    await user.open('/')
    for i in range(1, 2):
        await user.should_see('00', marker=f'team-{i}-score')
        user.find(marker=f'team-{i}-score').click()
        await user.should_see('01', marker=f'team-{i}-score')
        
        # Click undo button
        user.find(marker='undo-button').click()
        user.find(marker=f'team-{i}-score').click() # This now should be an undo action
        await user.should_see('00', marker=f'team-{i}-score')

async def test_simple_mode_button(user: User, mock_backend):
    """Tests the simple/full mode toggle."""
    await user.open('/')
    await user.should_see('grid_on', marker='simple-mode-button')
    await user.should_not_see('window', marker='simple-mode-button')
    simple_button = user.find(marker='simple-mode-button').click()
    await user.should_see('window', marker='simple-mode-button')
    await user.should_not_see('grid_on', marker='simple-mode-button')
    mock_backend.reduce_games_to_one.assert_called_once()
    simple_button.click()
    await user.should_see('grid_on', marker='simple-mode-button')
    
    
async def test_visibility_button(user: User, mock_backend):
    """Tests the overlay visibility button."""
    await user.open('/')
    await user.should_see('visibility', marker='visibility-button')
    await user.should_not_see('visibility_off', marker='visibility-button')
    user.find(marker='visibility-button').click()

    await user.should_see('visibility_off', marker='visibility-button')
    mock_backend.change_overlay_visibility.assert_called_with(False)
    
    user.find(marker='visibility-button').click()
    await user.should_see('visibility', marker='visibility-button')
    await user.should_not_see('visibility_off', marker='visibility-button')
    mock_backend.change_overlay_visibility.assert_called_with(True)

async def test_navigation_to_config_tab(user: User, mock_backend):
    """Tests navigating to the configuration tab."""
    await user.open('/')
    await user.should_see(marker='config-tab-button')
    user.find(marker='config-tab-button').click()
    # After clicking, we should see an element from the config page
    await user.should_see(marker='height-input')
    await user.should_see(marker='width-input')

async def test_end_game_and_undo(user: User, mock_backend):
    """
    Tests reaching the end of a game from a fixture, that buttons are disabled,
    and that undo reverts the end-game state. Also tests refresh confirmation and cancellation.
    """
    # Load the endgame fixture
    end_game_model = load_fixture('endgame_model')
    mock_backend.get_current_model.return_value = end_game_model

    await user.open('/')

    # Initial state from fixture
    await user.should_see('23', marker='team-1-score')
    await user.should_see('22', marker='team-2-score')
    await user.should_see('2', marker='team-1-sets')

    # Team 1 scores two points to win the set and match
    user.find(marker='team-1-score').click()
    await user.should_see('24', marker='team-1-score')
    user.find(marker='team-1-score').click()
    await user.should_see('25', marker='team-1-score')
    await user.should_see('3', marker='team-1-sets')  # Match finished

    # Test that adding more points is blocked
    user.find(marker='team-1-score').click()
    await user.should_see('25', marker='team-1-score')  # Score should not change

    # Test that undo works and reverts the end-game state
    user.find(marker='undo-button').click()
    user.find(marker='team-1-score').click()  # Undo the winning point

    # After undoing, score is 24, and set count for T1 should be 2.
    await user.should_see('24', marker='team-1-score')
    await user.should_see('2', marker='team-1-sets')


async def test_refresh(user: User, mock_backend):
    """
    Tests reaching the end of a game from a fixture, that buttons are disabled,
    and that undo reverts the end-game state. Also tests refresh confirmation and cancellation.
    """
    end_game_model = load_fixture('endgame_model')
    mock_backend.get_current_model.return_value = end_game_model

    await user.open('/')

    # Initial state from fixture
    await user.should_see('2', marker='team-1-sets')
    mock_backend.get_current_model.return_value[f'Team 1 Game 4 Score'] = 10
    mock_backend.get_current_model.return_value[f'Team 2 Game 4 Score'] = 9
    await user.should_see('23', marker='team-1-score')
    await user.should_see('22', marker='team-2-score')
    # Go to config tab to test refresh
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='refresh-button')
    
    # Test refresh cancellation
    user.find(marker='refresh-button').click()
    await user.should_see(marker='cancel-refresh-button')
    user.find(marker='cancel-refresh-button').click()
    await user.should_see(marker='scoreboard-tab-button')

    # Go back to scoreboard and check that nothing changed
    user.find(marker='scoreboard-tab-button').click()
    await user.should_see('23', marker='team-1-score') # Score should still be 23

    # Go back to config and test refresh confirmation
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='refresh-button')
    user.find(marker='refresh-button').click()
    await user.should_see(marker='confirm-refresh-button')
    user.find(marker='confirm-refresh-button').click()
    # Give the dialog a moment to close and the async events to be processed
    # Go back to scoreboard
    user.find(marker='scoreboard-tab-button').click()

    # The state should have been reloaded from the mock_backend (original endgame_model)
    await user.should_see('10', marker='team-1-score')
    await user.should_see('09', marker='team-2-score')
    await user.should_see('2', marker='team-1-sets')

async def test_team_customization(user: User, mock_backend, monkeypatch):
    """Tests changing a team's name and checks if the backend is called correctly."""
    # Define new predefined teams for this test
    new_teams = {
        "Eagles": {"icon": "path/to/eagle.png", "color": "#FF0000", "text_color": "#FFFFFF"},
        Customization.VISITOR_NAME: Customization.predefined_teams[Customization.VISITOR_NAME]
    }
    monkeypatch.setattr('app.customization.Customization.predefined_teams', new_teams)

    await user.open('/')
    # Go to config tab
    await user.should_see(marker='config-tab-button')
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='team-1-name-selector')

    # Change team 1's name to "Eagles"
    user.find(marker='team-1-name-selector').click()
    await user.should_see("Eagles")
    user.find("Eagles").click()
    
    # Save the changes
    user.find(marker='save-button').click()
    await asyncio.sleep(0)
    await user.should_see(marker='team-1-score') # Wait to be back on the scoreboard

    # Verify that save_json_customization was called with the correct data
    mock_backend.save_json_customization.assert_called()
    # Get the arguments from the last call
    call_args = mock_backend.save_json_customization.call_args[0][0]
    
    assert call_args[Customization.A_TEAM] == "Eagles"
    assert call_args[Customization.T1_LOGO] == "path/to/eagle.png"
    assert call_args[Customization.T1_COLOR] == "#FF0000"


async def test_team_selection_from_env_var(user: User, mock_backend, monkeypatch):
    """Tests that teams from the APP_TEAMS environment variable are selectable."""
    # Define new teams as a JSON string, simulating the environment variable
    teams_json = json.dumps({
        "Warriors": {"icon": "warriors.png", "color": "#ffc600", "text_color": "#000000"},
        "Gladiators": {"icon": "gladiators.png", "color": "#c0c0c0", "text_color": "#ffffff"},
    })
    monkeypatch.setenv("APP_TEAMS", teams_json)
    
    # We need to reload the customization module for the change to take effect
    import importlib
    import app.customization
    importlib.reload(app.customization)
    
    await user.open('/')
    # Go to config tab
    await user.should_see(marker='config-tab-button')
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='team-1-name-selector')

    # Check if the new teams are in the selector
    user.find(marker='team-1-name-selector').click()
    await user.should_see("Warriors")
    await user.should_see("Gladiators")


async def test_lock_buttons_prevent_changes(user: User, mock_backend, monkeypatch):
    """Tests that the lock buttons prevent color and icon changes when a new team is selected."""
    # Define new teams for this test
    new_teams = {
        "Team A": {"icon": "A.png", "color": "#AAAAAA", "text_color": "#111111"},
        "Team B": {"icon": "B.png", "color": "#BBBBBB", "text_color": "#222222"},
    }
    monkeypatch.setattr('app.customization.Customization.predefined_teams', new_teams)

    await user.open('/')
    # Go to config tab
    await user.should_see(marker='config-tab-button')
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='team-1-name-selector')

    # Get the initial color and icon of team 1
    initial_customization = load_fixture('base_customization')
    initial_t1_color = initial_customization[Customization.T1_COLOR]
    initial_t1_logo = initial_customization[Customization.T1_LOGO]

    # Lock team 1's icons and colors
    await user.should_see(marker='team-1-icon-lock')
    user.find(marker='team-1-icon-lock').click()
    await user.should_see(marker='team-1-color-lock')
    user.find(marker='team-1-color-lock').click()
    

    # Change team 1 to "Team A"
    await user.should_see(marker='team-1-name-selector')
    user.find(marker='team-1-name-selector').click()
    await user.should_see("Team A")
    user.find("Team A").click()
    await user.should_see(marker='save-button ')
    # Save the changes
    user.find(marker='save-button').click()
    await user.should_see(marker='team-1-score') # Wait to be back on the scoreboard
    await asyncio.sleep(0)

    # Verify that save_json_customization was called
    mock_backend.save_json_customization.assert_called()
    call_args = mock_backend.save_json_customization.call_args[0][0]
    
    # Assert that team 1's color and logo have NOT changed
    assert call_args[Customization.T1_COLOR] == initial_t1_color
    assert call_args[Customization.T1_LOGO] == initial_t1_logo
    # The name should still change
    assert call_args[Customization.A_TEAM] == "Team A"


async def test_reset_from_config(user: User, mock_backend):
    """Tests the reset button on the customization page."""
    await user.open('/')

    # Score a point
    await user.should_see(marker='team-1-score')
    user.find(marker='team-1-score').click()
    await user.should_see('01', marker='team-1-score')

    # Go to config tab
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='reset-button')

    # Click reset and cancel
    user.find(marker='reset-button').click()
    await asyncio.sleep(0)
    await user.should_see(marker='cancel-reset-button')
    user.find(marker='cancel-reset-button').click()
    # Should be back on the scoreboard, and score should be reset
    await user.should_see('01', marker='team-1-score')

    # Click reset and confirm
    user.find(marker='reset-button').click()
    await asyncio.sleep(0)
    await user.should_see(marker='confirm-reset-button')
    user.find(marker='confirm-reset-button').click()
    
    # Should be back on the scoreboard, and score should be reset
    await user.should_see('00', marker='team-1-score')
    await asyncio.sleep(0)
    # Verify that the backend's reset method was called
    mock_backend.reset.assert_called()
