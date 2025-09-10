import pytest
import json
import os
import asyncio
import importlib
from unittest.mock import patch, MagicMock
from nicegui.testing import User
from app.startup import startup
from app.theme import *
from app.customization import Customization
from app.messages import Messages
import main
from app.backend import Backend
from app.state import State


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
    Main fixture that simulates the Backend.
    Each test is responsible for overriding the mock's behavior as needed.
    """
    with patch('app.startup.Backend') as mock_backend_class:
        mock_instance = mock_backend_class.return_value

        # --- Default simulated behavior ---
        mock_instance.is_visible.return_value = True
        mock_instance.get_current_customization.return_value = load_fixture('base_customization')
        # Default model for simple tests. More complex tests will override this.
        mock_instance.get_current_model.return_value = load_fixture('base_model')

        # Simulates OID validation: only 'test_oid_valid' is valid.
        def validate_side_effect(oid):
            if oid is None:
                return State.OIDStatus.EMPTY
            if oid.endswith('_valid'):
                # We need to mock the get_current_model call inside validation
                if oid == 'predefined_1_valid':
                    mock_instance.get_current_model.return_value = load_fixture('predefined_overlay_1')
                elif oid == 'predefined_2_valid':
                    mock_instance.get_current_model.return_value = load_fixture('predefined_overlay_2')
                elif oid == 'manual_oid_valid':
                    mock_instance.get_current_model.return_value = load_fixture('manual_overlay')
                elif oid == 'endgame_oid_valid':
                    mock_instance.get_current_model.return_value = load_fixture('endgame_model')
                return State.OIDStatus.VALID
            return State.OIDStatus.INVALID
        
        # We need a MagicMock to allow replacing the side_effect in tests
        mock_instance.validate_and_store_model_for_oid = MagicMock(side_effect=validate_side_effect)

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
    await asyncio.sleep(0.1)
    mock_backend.save.assert_called()

async def test_set_buttons_increment(user: User, mock_backend):
    await user.open('/')
    for i in range(1, 2):
        await user.should_see('0', marker=f'team-{i}-sets')
        user.find(marker=f'team-{i}-sets').click()
        await user.should_see('1', marker=f'team-{i}-sets')
    await asyncio.sleep(0.1)
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
    await asyncio.sleep(0.1)
    mock_backend.save.assert_called()

async def test_set_pagination(user: User, mock_backend, monkeypatch):
    """Tests that the set pagination works correctly."""
    monkeypatch.delenv("UNO_OVERLAY_OID", raising=False)

    await user.open('/')
    await user.should_see(marker='control-url-input')
    user.find(marker='control-url-input').type('manual_oid_valid')
    user.find(marker='submit-overlay-button').click()
    await asyncio.sleep(0)

    await user.should_see(content='05', marker='team-1-score')
    user.find(marker=f'team-1-score').click()
    await user.should_see(content='06', marker='team-1-score')

    # Click the next set button in the pagination
    user.find(marker='set-selector').elements.pop().set_value(2)
    # The score for the new set should be 00
    await user.should_see(content='03', marker='team-1-score')

    # Click the next set button in the pagination
    user.find(marker='set-selector').elements.pop().set_value(1)
    # The score for the new set should be 00
    await user.should_see(content='15', marker='team-1-score')

    # Go back to the previous set
    user.find(marker='set-selector').elements.pop().set_value(3)
    # The score should be the one we set before
    await user.should_see(content='06', marker='team-1-score')
    await asyncio.sleep(0.1)

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
    await asyncio.sleep(0.1)



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
    await asyncio.sleep(0.1)

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
    await asyncio.sleep(0.1)
    
    
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
    await asyncio.sleep(0.1)

async def test_navigation_to_config_tab(user: User, mock_backend):
    """Tests navigating to the configuration tab."""
    await user.open('/')
    await user.should_see(marker='config-tab-button')
    user.find(marker='config-tab-button').click()
    # After clicking, we should see an element from the config page
    await user.should_see(marker='height-input')
    await user.should_see(marker='width-input')
    await asyncio.sleep(0.1)

async def test_end_game_and_undo(user: User, mock_backend):
    """
    Tests reaching the end of a game from a fixture, that buttons are disabled,
    and that undo reverts the end-game state. Also tests refresh confirmation and cancellation.
    """
    # Load the endgame fixture and temporarily override the mock for this test
    end_game_model = load_fixture('endgame_model')
    mock_backend.get_current_model.return_value = end_game_model
    mock_backend.validate_and_store_model_for_oid.return_value = State.OIDStatus.VALID


    await user.open('/')

    # Initial state from fixture should be loaded correctly now
    await user.should_see(content='23', marker='team-1-score')
    await user.should_see(content='22', marker='team-2-score')
    await user.should_see(content='2', marker='team-1-sets')

    # Team 1 scores two points to win the set and match
    user.find(marker='team-1-score').click()
    await user.should_see(content='24', marker='team-1-score')
    user.find(marker='team-1-score').click()
    await user.should_see(content='25', marker='team-1-score')
    await user.should_see(content='3', marker='team-1-sets')  # Match finished

    # Test that adding more points is blocked
    user.find(marker='team-1-score').click()
    await user.should_see(content='25', marker='team-1-score')  # Score should not change

    # Test that undo works and reverts the end-game state
    user.find(marker='undo-button').click()
    user.find(marker='team-1-score').click()  # Undo the winning point

    # After undoing, score is 24, and set count for T1 should be 2.
    await user.should_see(content='24', marker='team-1-score')
    await user.should_see(content='2', marker='team-1-sets')
    await asyncio.sleep(0.1)


async def test_refresh(user: User, mock_backend):
    """
    Tests the refresh functionality, ensuring it reloads the state from the backend.
    """
    # Setup a modifiable dictionary that the mock will return
    backend_data = load_fixture('endgame_model')
    # Use side_effect to return the current state of backend_data on each call
    mock_backend.get_current_model.side_effect = lambda customOid=None, saveResult=False: backend_data.copy()
    mock_backend.validate_and_store_model_for_oid.return_value = State.OIDStatus.VALID

    await user.open('/')

    # Initial state from fixture
    await user.should_see(content='23', marker='team-1-score')
    await user.should_see(content='22', marker='team-2-score')
    await user.should_see(content='2', marker='team-1-sets')

    # Team 1 scores two points to win the set and match
    user.find(marker='team-1-score').click()
    await user.should_see(content='24', marker='team-1-score')
    user.find(marker='team-1-score').click()
    await user.should_see(content='25', marker='team-1-score')

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
    await user.should_see(content='25', marker='team-1-score') # Score should still be 25
    await user.should_see(content='3', marker='team-1-sets')

    # Go back to config and test refresh confirmation
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='refresh-button')
    user.find(marker='refresh-button').click()
    await asyncio.sleep(0)
    await user.should_see(marker='confirm-refresh-button')
    user.find(marker='confirm-refresh-button').click()
    await asyncio.sleep(0.2) # Give time for async operations
    
    # Go back to scoreboard
    user.find(marker='scoreboard-tab-button').click()

    # The state should have been reloaded from the modified backend data
    await user.should_see(content='23', marker='team-1-score')
    await user.should_see(content='2', marker='team-1-sets')
    await asyncio.sleep(0.1)


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
    await user.should_see(marker='team-1-score') # Wait to be back on the scoreboard
    await asyncio.sleep(0.2)

    # Verify that save_json_customization was called with the correct data
    mock_backend.save_json_customization.assert_called()
    # Get the arguments from the last call
    call_args = mock_backend.save_json_customization.call_args[0][0]
    
    assert call_args[Customization.A_TEAM] == "Eagles"
    assert call_args[Customization.T1_LOGO] == "path/to/eagle.png"
    assert call_args[Customization.T1_COLOR] == "#FF0000"
    await asyncio.sleep(0.1)


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
    await asyncio.sleep(0.1)


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
    await user.should_see(marker='save-button')
    # Save the changes
    user.find(marker='save-button').click()
    await user.should_see(marker='team-1-score') # Wait to be back on the scoreboard
    await asyncio.sleep(0.2)

    # Verify that save_json_customization was called
    mock_backend.save_json_customization.assert_called()
    call_args = mock_backend.save_json_customization.call_args[0][0]
    
    # Assert that team 1's color and logo have NOT changed
    assert call_args[Customization.T1_COLOR] == initial_t1_color
    assert call_args[Customization.T1_LOGO] == initial_t1_logo
    # The name should still change
    assert call_args[Customization.A_TEAM] == "Team A"
    await asyncio.sleep(0.1)


async def test_reset_from_config(user: User, mock_backend):
    """Tests the reset button on the customization page."""

    # This dictionary simulates our backend's database
    backend_data = load_fixture('endgame_model')

    # get_current_model will return the current state of our backend_data
    mock_backend.get_current_model.side_effect = lambda customOid=None, saveResult=False: backend_data

    # The reset function in the backend calls save_json_model
    # with the initial state. We simulate this behavior here.
    def reset_side_effect(state):
        nonlocal backend_data
        reset_model = state.get_reset_model()
        backend_data = reset_model
        mock_backend.save_json_model(reset_model)

    mock_backend.reset.side_effect = reset_side_effect
    await user.open('/')

    # Score a point
    await user.should_see(content='23', marker='team-1-score')
    user.find(marker='team-1-score').click()
    await user.should_see(content='24', marker='team-1-score')

    # Go to config tab
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='reset-button')

    # Click reset and cancel
    user.find(marker='reset-button').click()
    await asyncio.sleep(0)
    await user.should_see(marker='cancel-reset-button')
    user.find(marker='cancel-reset-button').click()
    # Should be back on the scoreboard, and score should NOT be reset
    await user.should_see(content='24', marker='team-1-score')

    # Go to config tab again
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='reset-button')

    # Click reset and confirm
    user.find(marker='reset-button').click()
    await asyncio.sleep(0)
    await user.should_see(marker='confirm-reset-button')
    user.find(marker='confirm-reset-button').click()
    await asyncio.sleep(0.2)
    # Verify that the backend's reset method was called
    mock_backend.reset.assert_called()
    await user.should_see(content='00', marker='team-1-score')
    
    # Verify that save_json_model was called with the reset model
    mock_backend.save_json_model.assert_called_with(State.reset_model)

    await asyncio.sleep(0.2)

    
async def test_theme_application(user: User, mock_backend, monkeypatch):
    """Tests applying a predefined theme."""
    themes = {
        "Test Theme": {
            "Team 1 Color": "#112233",
            "Width": 50.0,
            "Logos": "false",
            "Gradient": "false",
            "Height": 15.0
        }
    }
    monkeypatch.setattr('app.customization.Customization.THEMES', themes)

    await user.open('/')
    await user.should_see(marker='config-tab-button')

    # Go to the configuration tab
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='theme-button')

    # Check initial width
    assert user.find(marker='width-input').elements.pop().props['model-value'] == '55.0'

    # Open theme dialog, select and load the theme
    user.find(marker='theme-button').click()
    await user.should_see(marker='theme-selector')
    user.find(marker='theme-selector').click()
    await user.should_see("Test Theme")
    user.find("Test Theme").click()
    user.find(marker='load-theme-button').click()

    # Wait for UI to re-render with new theme values
    await asyncio.sleep(0.1)

    # Check that the input on the config page has updated
    assert user.find(marker='width-input').elements.pop().props['model-value'] == '50.0'

    # Save the changes
    user.find(marker='save-button').click()
    await user.should_see(marker='team-1-score')  # Wait to be back on the scoreboard
    await asyncio.sleep(0.2)  # Allow event loop to settle

    # Verify that save_json_customization was called with the theme data
    mock_backend.save_json_customization.assert_called()
    call_args = mock_backend.save_json_customization.call_args[0][0]

    assert call_args[Customization.T1_COLOR] == "#112233"
    assert call_args[Customization.WIDTH_FLOAT] == 50.0
    assert call_args[Customization.LOGOS_BOOL] == "false"
    assert call_args[Customization.GLOSS_EFFECT_BOOL] == "false"
    assert call_args[Customization.HEIGHT_FLOAT] == 15.0
    await asyncio.sleep(0.1)


async def test_manual_customization(user: User, mock_backend):
    """Tests manually changing customization values."""
    await user.open('/')
    await user.should_see(marker='config-tab-button')

    # Go to config tab
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='height-input')

    assert user.find(marker='width-input').elements.pop().props['model-value'] == '55.0'
    assert user.find(marker='height-input').elements.pop().props['model-value'] == '20.0'
    assert user.find(marker='hpos-input').elements.pop().props['model-value'] == '-19.5'
    assert user.find(marker='vpos-input').elements.pop().props['model-value'] == '34.0'

    # Change some values
    user.find(marker='width-input').elements.pop().set_value('54')
    user.find(marker='height-input').elements.pop().set_value('19')
    user.find(marker='hpos-input').elements.pop().set_value('-20')
    user.find(marker='vpos-input').elements.pop().set_value('32')

    assert user.find(marker='width-input').elements.pop().props['model-value'] == '54.0'
    assert user.find(marker='height-input').elements.pop().props['model-value'] == '19.0'
    assert user.find(marker='hpos-input').elements.pop().props['model-value'] == '-20.0'
    assert user.find(marker='vpos-input').elements.pop().props['model-value'] == '32.0'

    user.find(marker='logo-switch').click() # Disable logos
    user.find(marker='gradient-switch').click() # Disable gradient

    # Save the changes
    user.find(marker='save-button').click()
    await user.should_see(marker='team-1-score')
    await asyncio.sleep(0.2)

    # Verify that save_json_customization was called with the correct data
    mock_backend.save_json_customization.assert_called()
    call_args = mock_backend.save_json_customization.call_args[0][0]
    
    assert call_args[Customization.WIDTH_FLOAT] == '54'
    assert call_args[Customization.HEIGHT_FLOAT] == '19'
    assert not call_args[Customization.LOGOS_BOOL]
    assert not call_args[Customization.GLOSS_EFFECT_BOOL]
    await asyncio.sleep(0.1)

async def test_oid_dialog_flow(user: User, mock_backend, monkeypatch):
    """
    Tests that the dialog to enter the OID appears when it is not provided
    and that the scoreboard loads correctly after entering a valid OID.
    """
    # We make sure that the environment variable is not defined for this test.
    monkeypatch.delenv("UNO_OVERLAY_OID", raising=False)
    
    await user.open('/')
    await asyncio.sleep(0)
    # The dialog should be visible, so we look for its input field.
    await user.should_see(marker='control-url-input')
    
    # We enter an OID that our mock will consider valid.
    user.find(marker='control-url-input').type('test_oid_valid')
    
    # We click on the submit button.
    user.find(marker='submit-overlay-button').click()
    await asyncio.sleep(0)
    # We wait for the dialog to close and the main scoreboard to be visible.
    await user.should_see(marker='team-1-score')
    await user.should_see(content='00', marker='team-1-score')
    await asyncio.sleep(0.1)

# --- NEW TESTS FOR PREDEFINED OVERLAYS ---
@pytest.fixture
def predefined_overlays_env(monkeypatch):
    """Fixture to set up environment variables for predefined overlays."""
    overlays = {
        "Overlay 1": {"control": "predefined_1_valid", "output": "output_token"},
        "Overlay 2": {"control": "predefined_2_valid"},
    }
    monkeypatch.setenv('PREDEFINED_OVERLAYS', json.dumps(overlays))
    monkeypatch.delenv('UNO_OVERLAY_OID', raising=False)
    # Reload the oid_dialog module to ensure it picks up the changed environment variables
    import importlib
    import app.oid_dialog
    importlib.reload(app.oid_dialog)

async def test_predefined_overlay_dialog_with_hide_flag(user: User, mock_backend, predefined_overlays_env, monkeypatch):
    """
    Tests that with HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED=true, the manual input is hidden.
    """
    monkeypatch.setenv('HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED', 'true')
    import importlib
    import app.oid_dialog
    importlib.reload(app.oid_dialog)

    await user.open('/')
    
    await user.should_see(marker='predefined-overlay-selector')
    await user.should_not_see(marker='control-url-input')
    await user.should_not_see(marker='predefined-overlay-checkbox')

    user.find(marker='predefined-overlay-selector').click()
    await user.should_see("Overlay 1")
    user.find("Overlay 1").click()
    user.find(marker='submit-overlay-button').click()

    await user.should_see(marker='team-1-score')
    await user.should_see(content='10', marker='team-1-score')
    await user.should_see(content='05', marker='team-2-score')
    await user.should_see(Messages.get(Messages.OVERLAY_LINK))
    assert 'https://app.overlays.uno/output/output_token' == user.find(Messages.get(Messages.OVERLAY_LINK)).elements.pop().props['href']
    await asyncio.sleep(0.1)


async def test_predefined_overlay_cycle(user: User, mock_backend, predefined_overlays_env, monkeypatch):
    """
    Tests the full cycle: using predefined overlays, resetting, and then using manual input.
    """
    monkeypatch.setenv('HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED', 'false')
    import importlib
    import app.oid_dialog
    importlib.reload(app.oid_dialog)
    
    await user.open('/')
    
    # --- Part 1: Use Predefined Overlay ---
    
    # Dialog should be visible with all elements
    await user.should_see(marker='control-url-input')
    await user.should_see(marker='predefined-overlay-checkbox')
    await user.should_see(marker='predefined-overlay-selector')

    # Click checkbox if required to select overlay
    if user.find(marker='control-url-input').elements.pop().enabled:
        user.find(marker='predefined-overlay-checkbox').click()
        await user.should_see(marker='control-url-input')
    
    assert not user.find(marker='control-url-input').elements.pop().enabled
    assert user.find(marker='predefined-overlay-selector').elements.pop().enabled

    user.find(marker='predefined-overlay-selector').click()
    await asyncio.sleep(0)
    # Select "Overlay 2" and submit
    await user.should_see("Overlay 2")
    user.find("Overlay 2").click()
    user.find(marker='submit-overlay-button').click()

    # Verify scoreboard loaded with data from Overlay 2
    await user.should_see(marker='team-1-score')
    await user.should_see(content='12', marker='team-1-score')
    await user.should_see(content='11', marker='team-2-score')
    await user.should_see(content='1', marker='team-1-sets')
    await user.should_see(content='0', marker='team-2-sets')
    await user.should_not_see(Messages.get(Messages.OVERLAY_LINK))

    
    # --- Part 2: Reset and Use Manual OID ---

    # Go to config page and click reset link
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='change-overlay-button')
    user.find(marker='change-overlay-button').click()
    await asyncio.sleep(0.2)

    
    # Dialog should reappear in its default state or
    if not user.find(marker='control-url-input').elements.pop().enabled:
        user.find(marker='predefined-overlay-checkbox').click()
    await asyncio.sleep(0)
    await user.should_see(marker='control-url-input')
    assert user.find(marker='control-url-input').elements.pop().enabled
    assert not user.find(marker='predefined-overlay-selector').elements.pop().enabled

    
    # Enter a manual OID and submit
    user.find(marker='control-url-input').type('manual_oid_valid')
    await asyncio.sleep(0)
    user.find(marker='submit-overlay-button').click()
    await asyncio.sleep(0)


    # Verify scoreboard loaded with manual OID data
    await user.should_see(marker='team-1-score')
    await user.should_see(content='05', marker='team-1-score')
    await user.should_see(content='06', marker='team-2-score')
    await user.should_see(content='1', marker='team-1-sets')
    await user.should_see(content='1', marker='team-2-sets')
    await asyncio.sleep(0.1)

async def test_url_params_override_oid(user: User, mock_backend, monkeypatch):
    """Tests that the 'control' URL parameter correctly sets a mid-game OID."""
    # Ensure no OID is set initially from environment or storage
    monkeypatch.delenv("UNO_OVERLAY_OID", raising=False)
    
    # Open the page with a control URL parameter for a mid-game overlay.
    # The 'predefined_2_valid' fixture simulates a mid-game state.
    await user.open('/?control=predefined_1_valid')
    
    # The scoreboard should load directly with the scores from the mid-game fixture.
    # In predefined_overlay_2.json, the score for the current set (3) is 10-12.
    await user.should_see(content='10', marker='team-1-score')
    await user.should_see(content='05', marker='team-2-score')
    await user.should_see(content='0', marker='team-1-sets')
    await user.should_see(content='0', marker='team-2-sets')

    # Go to the configuration tab
    user.find(marker='config-tab-button').click()
    
    # Verify the control link uses the OID from the URL parameter
    control_link = user.find(Messages.get(Messages.CONTROL_LINK))
    expected_href = 'https://app.overlays.uno/control/predefined_1_valid'
    assert control_link.elements.pop().props['href'] == expected_href
    await asyncio.sleep(0.1)


async def test_url_params_set_output(user: User, mock_backend, monkeypatch):
    """Tests that the 'output' URL parameter works with a mid-game OID."""
    # Ensure no OID is set initially
    monkeypatch.delenv("UNO_OVERLAY_OID", raising=False)
    
    # Open the page with both control and output URL parameters for a mid-game overlay
    await user.open('/?control=predefined_2_valid&output=custom_output_token')
    
    # The scoreboard should load with the correct mid-game scores
    await user.should_see(content='12', marker='team-1-score')
    await user.should_see(content='11', marker='team-2-score')
    await user.should_see(content='1', marker='team-1-sets')
    await user.should_see(content='0', marker='team-2-sets')
    # Go to the configuration tab
    user.find(marker='config-tab-button').click()
    
    # Verify the output link is present and correct
    output_link = user.find(Messages.get(Messages.OVERLAY_LINK))
    expected_href = 'https://app.overlays.uno/output/custom_output_token'
    assert output_link.elements.pop().props['href'] == expected_href
    await asyncio.sleep(0.1)

async def test_beach_mode_limits(user: User, mock_backend):
    """Tests that the /beach URL correctly applies beach volleyball rules (21 points, 3 sets)."""
    # Open the specific URL for beach mode
    await user.open('/beach?control=test_oid_valid')
    await user.should_see(marker='team-1-score')

    # Score points up to 20 for Team 1
    for _ in range(20):
        user.find(marker='team-1-score').click()
        await asyncio.sleep(0.01) # Small delay to allow UI to update
    await user.should_see(content='20', marker='team-1-score')
    await user.should_see(content='0', marker='team-1-sets') # Set should not be won yet

    # Score the winning point for Team 1
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.01)
    await user.should_see(content='00', marker='team-1-score')
    await user.should_see(content='1', marker='team-1-sets') # Team 1 wins the set

    # Win the second set for Team 1 to win the match (best of 3)
    for _ in range(21):
        user.find(marker='team-1-score').click()
        await asyncio.sleep(0.01)
    
    await user.should_see(content='2', marker='team-1-sets')
    
    # Try to score another point, which should be blocked as the match is over
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.01)
    await user.should_see(content='21', marker='team-1-score') # Score should not change
    await asyncio.sleep(0.3)


async def test_indoor_mode_limits(user: User, mock_backend):
    """Tests that the /indoor URL correctly applies indoor volleyball rules (25 points, 5 sets)."""
    await user.open('/indoor?control=endgame_oid_valid')
    await user.should_see(marker='team-1-score')

    # Score points up to 24 for Team 1
    user.find(marker='team-1-score').click()
    await user.should_see(content='24', marker='team-1-score')
    await user.should_see(content='2', marker='team-1-sets') # Set not won yet

    # Score the winning point
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.01)
    await user.should_see(content='25', marker='team-1-score')
    await user.should_see(content='3', marker='team-1-sets') # Team 1 wins the set
    await asyncio.sleep(0.3)


async def test_env_vars_for_points_limit(user: User, mock_backend, monkeypatch):
    """Tests custom game point limits set by environment variables."""
    # Set a custom point limit via environment variable
    monkeypatch.setenv("MATCH_GAME_POINTS", "10")
    monkeypatch.setenv("MATCH_GAME_POINTS_LAST_SET", "5")
    monkeypatch.setenv("MATCH_SETS", "3")

    # Reload modules to apply the new environment variables
    import app.conf
    importlib.reload(app.conf)

    await user.open('/?control=test_oid_valid')
    await user.should_see(marker='team-1-score')

    # Score up to 9 points for Team 1
    for _ in range(9):
        user.find(marker='team-1-score').click()
        await asyncio.sleep(0.01)
    await user.should_see(content='09', marker='team-1-score')
    await user.should_see(content='0', marker='team-1-sets')

    # Score the winning point
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.1)
    await user.should_see(content='00', marker='team-1-score')
    await user.should_see(content='1', marker='team-1-sets')
    await asyncio.sleep(0.2)


async def test_env_vars_for_sets_limit(user: User, mock_backend, monkeypatch):
    """Tests custom set limits set by an environment variable."""
    # Set a best-of-1 match (win with 1 set) and a low point limit
    monkeypatch.setenv("MATCH_SETS", "1")
    monkeypatch.setenv("MATCH_GAME_POINTS", "15")
    monkeypatch.setenv("MATCH_GAME_POINTS_LAST_SET", "5")

    
    import app.conf
    importlib.reload(app.conf)

    await user.open('/?control=test_oid_valid')
    await asyncio.sleep(0)
    await user.should_see(marker='team-2-score')

    # Win the first set
    for _ in range(5):
        user.find(marker='team-2-score').click()
        await asyncio.sleep(0.01)
    
    await user.should_see(content='1', marker='team-2-sets')

    # The match should be over. Trying to score another point should fail.
    user.find(marker='team-2-score').click()
    await asyncio.sleep(0.1)
    await user.should_see(content='05', marker='team-2-score') # Score should not change
    await asyncio.sleep(0.2)
    
# --- Authentication Tests ---

@pytest.fixture
def auth_users_env(monkeypatch):
    """Fixture to set up SCOREBOARD_USERS environment variable."""
    users = {
        "user1": {"password": "password1", "control": "predefined_1_valid", "output": "output_1"},
        "user2": {"password": "password2"}
    }
    monkeypatch.setenv('SCOREBOARD_USERS', json.dumps(users))
    monkeypatch.delenv('UNO_OVERLAY_OID', raising=False)
    # Reload modules to apply the new environment variables
    import app.authentication
    importlib.reload(app.authentication)
    import main
    importlib.reload(main)

async def test_login_and_auto_load_oid(user: User, mock_backend, auth_users_env):
    """Tests that a user can log in and their predefined OID is loaded automatically."""
    await user.open('/')
    
    # We should be on the login page
    await user.should_see(marker='username-input')
    user.find(marker='username-input').type('user1')
    user.find(marker='password-input').type('password1')
    user.find(marker='login-button').click()
    
    # After login, we should see the scoreboard with data from "predefined_1_valid"
    await user.should_see(marker='team-1-score')
    await user.should_see(content='10', marker='team-1-score')
    await user.should_see(content='05', marker='team-2-score')
    
    # Go to the configuration tab and check links
    user.find(marker='config-tab-button').click()
    await user.should_see(Messages.get(Messages.OVERLAY_LINK))
    assert 'https://app.overlays.uno/output/output_1' in user.find(Messages.get(Messages.OVERLAY_LINK)).elements.pop().props['href']
    assert 'https://app.overlays.uno/control/predefined_1_valid' in user.find(Messages.get(Messages.CONTROL_LINK)).elements.pop().props['href']
    await asyncio.sleep(0.3)

async def test_logout_flow(user: User, mock_backend, auth_users_env):
    """Tests the complete logout and login flow."""
    await user.open('/')
    
    # Login as user2
    await user.should_see(marker='username-input')
    user.find(marker='username-input').type('user2')
    user.find(marker='password-input').type('password2')
    user.find(marker='login-button').click()
    
    # User2 has no predefined OID, so the OID dialog should appear
    await user.should_see(marker='control-url-input')
    
    # Logout from the OID dialog
    user.find(marker='logout-button-oid').click()
    
    # We should be back on the login page
    await user.should_see(marker='username-input')
    
    # Login again as user1
    user.find(marker='username-input').type('user1')
    user.find(marker='password-input').type('password1')
    user.find(marker='login-button').click()
    
    # We should see the scoreboard for user1
    await user.should_see(marker='team-1-score')
    await user.should_see(content='10', marker='team-1-score')
    
    # Go to config tab and logout
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='logout-button')
    user.find(marker='logout-button').click()
    await asyncio.sleep(0)
    
    # Confirm logout
    await user.should_see(Messages.get(Messages.ASK_LOGOUT))
    user.find(marker='confirm-logout-button').click()
    await asyncio.sleep(0.3)

    # We should be back on the login page
    await user.should_see(marker='username-input')
    await user.should_not_see(marker='config-tab-button')

    # Login again as user1, but cancel logout
    user.find(marker='username-input').type('user1')
    user.find(marker='password-input').type('password1')
    user.find(marker='login-button').click()
    await user.should_see(marker='team-1-score')
    user.find(marker='config-tab-button').click()
    user.find(marker='logout-button').click()
    await user.should_see(Messages.get(Messages.ASK_LOGOUT))
    user.find(marker='cancel-logout-button').click()
    await user.should_see(marker='config-tab-button')
    await asyncio.sleep(0.3)

async def test_predefined_overlay_with_user_filter(user: User, mock_backend, auth_users_env, monkeypatch):
    """Tests that users only see the predefined overlays they are allowed to see."""
    overlays = {
        "User 1 Overlay": {"control": "predefined_1_valid", "allowed_users": ["user1"]},
        "All Users Overlay": {"control": "predefined_2_valid"}
    }
    monkeypatch.setenv('PREDEFINED_OVERLAYS', json.dumps(overlays))
    
    import app.oid_dialog
    importlib.reload(app.oid_dialog)
    
    await user.open('/')
    
    # Login as user2
    await user.should_see(marker='username-input')
    user.find(marker='username-input').type('user2')
    user.find(marker='password-input').type('password2')
    user.find(marker='login-button').click()
    
    # User2 should see the OID dialog. Let's check the available overlays.
    await user.should_see(marker='predefined-overlay-selector')
    user.find(marker='predefined-overlay-selector').click()
    
    # User2 should only see "All Users Overlay"
    await user.should_see("All Users Overlay")
    await user.should_not_see("User 1 Overlay")
    
    # Close the selector and logout
    user.find("All Users Overlay").click()
    user.find(marker='logout-button-oid').click()
    
    # Login as user1
    await user.should_see(marker='username-input')
    user.find(marker='username-input').type('user1')
    user.find(marker='password-input').type('password1')
    user.find(marker='login-button').click()
    
    # User1 has a predefined OID, so the scoreboard loads directly.
    # We need to go to the config, reset the OID to see the dialog again.
    await user.should_see(marker='team-1-score')
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='change-overlay-button')
    user.find(marker='change-overlay-button').click()
    
    # Now user1 sees the OID dialog. Let's check the overlays.
    await user.should_see(marker='predefined-overlay-selector')
    user.find(marker='predefined-overlay-selector').click()
    
    # User1 should see both overlays
    await user.should_see("User 1 Overlay")
    await user.should_see("All Users Overlay")
    await asyncio.sleep(0.3)

async def test_autohide_feature(user: User, mock_backend, monkeypatch):
    """Tests the auto-hide functionality with corrected initial state."""
    monkeypatch.setenv('DEFAULT_HIDE_TIMEOUT', '1')

    # Set initial visibility to False to ensure the first call is to show
    mock_backend.is_visible.return_value = False

    await user.open('/?control=test_oid_valid')
    await user.should_see(marker='config-tab-button')

    # Go to config tab, open options, and enable auto-hide
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='save-button')
    user.find(marker='options-button').click()
    await user.should_see(Messages.get(Messages.AUTO_HIDE))
    user.find(Messages.get(Messages.AUTO_HIDE)).click()
    user.find(Messages.get(Messages.CLOSE)).click()
    user.find(marker='scoreboard-tab-button').click()
    await user.should_see(marker='team-1-score')

    # --- Test 1: Scoring a regular point should trigger hide ---
    mock_backend.change_overlay_visibility.reset_mock()
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.1)

    # Should immediately become visible
    mock_backend.change_overlay_visibility.assert_called_once_with(True)
    await user.should_see('visibility', marker='visibility-button')

    # Wait for the timeout
    await asyncio.sleep(1.1)
    # Should now be hidden
    mock_backend.change_overlay_visibility.assert_called_with(False)
    await user.should_see('visibility_off', marker='visibility-button')

    # --- Test 2: Scoring multiple points should reset the timer ---
    mock_backend.change_overlay_visibility.reset_mock()
    mock_backend.is_visible.return_value = False

    # Score 5 points with a 0.3s delay
    for _ in range(5):
        user.find(marker='team-2-score').click()
        await asyncio.sleep(0.3)

    # It should have been made visible on the first click
    mock_backend.change_overlay_visibility.assert_called_with(True)
    await user.should_see('visibility', marker='visibility-button')

    # Wait for a period longer than the original timeout, but shorter
    # than the timeout after the last click.
    await asyncio.sleep(0.2) # Total time since first click: 1.6s

    # It should NOT be hidden, as the timer should have been reset.
    # The last call should still be the one that made it visible.
    mock_backend.change_overlay_visibility.assert_called_with(True)
    await user.should_see('visibility', marker='visibility-button')

    # Wait for the full timeout after the LAST click
    await asyncio.sleep(0.7) 

    # NOW it should be hidden
    mock_backend.change_overlay_visibility.assert_called_with(False)
    await user.should_see('visibility_off', marker='visibility-button')

    # --- Test 3: Scoring a set-winning point should NOT trigger hide ---
    # Set visibility to False again for a clean test
    mock_backend.change_overlay_visibility.reset_mock()
    mock_backend.is_visible.return_value = False
    # Score 24 points to set up the win
    for _ in range(24):
        user.find(marker='team-1-score').click()
        await asyncio.sleep(0.01)

    await user.should_see('25', marker='team-1-score') # Score is now 25 vs 0
    await user.should_see('1', marker='team-1-sets')   # Set is won

    # The overlay should have been made visible, and only called once
    mock_backend.change_overlay_visibility.assert_called_once_with(True)
    await user.should_see('visibility', marker='visibility-button')

    # Wait for the timeout period again
    await asyncio.sleep(1.1)

    # Assert that no new calls were made. The last (and only) call was to set visibility to True.
    mock_backend.change_overlay_visibility.assert_called_once_with(True)
    await user.should_see('visibility', marker='visibility-button')

   


async def test_auto_simple_mode_feature(user: User, mock_backend):
    """Tests the auto-simple-mode functionality with precise assertions."""
    await user.open('/?control=test_oid_valid')
    await user.should_see(marker='config-tab-button')

    # Go to config tab, open options, and enable auto-simple-mode
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='save-button')
    user.find(marker='options-button').click()
    await user.should_see(Messages.get(Messages.AUTO_SIMPLE_MODE))
    user.find(Messages.get(Messages.AUTO_SIMPLE_MODE)).click()
    user.find(Messages.get(Messages.CLOSE)).click()
    user.find(marker='scoreboard-tab-button').click()
    await user.should_see(marker='team-1-score')

    # --- Test 1: Assert function is NOT called before the action ---
    mock_backend.reduce_games_to_one.assert_not_called()
    await user.should_see('grid_on', marker='simple-mode-button')


    # --- Test 2: Scoring a point should switch to simple mode ---
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.1)

    mock_backend.reduce_games_to_one.assert_called_once()
    await user.should_see('window', marker='simple-mode-button')


    # --- Test 3: Winning a set should switch back to full mode ---

    for _ in range(23):
        user.find(marker='team-1-score').click()
        await asyncio.sleep(0.01)
        await user.should_see('window', marker='simple-mode-button')

    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.01)
    await user.should_see('1', marker='team-1-sets')
    await asyncio.sleep(0.1)

    # The function should NOT be called again when switching back to full mode.
    await user.should_see('grid_on', marker='simple-mode-button')

    # Starting the set again returns to simple mode
    user.find(marker='team-2-score').click()
    await asyncio.sleep(0.01)
    await user.should_see('window', marker='simple-mode-button')

async def test_long_press_game_score(user: User, mock_backend):
    """Tests the long press feature to set a custom game score."""
    await user.open('/')
    await user.should_see('00', marker='team-1-score')
    await user.should_not_see(Messages.get(Messages.SET_CUSTOM_GAME_VALUE))

    # Perform a long press on the team 1 score button
    user.find(marker='team-1-score').trigger('mousedown')
    await asyncio.sleep(1)
    user.find(marker='team-1-score').trigger('mouseup')
    await asyncio.sleep(0)
    
    # The dialog to set a custom value should appear
    await user.should_see(Messages.get(Messages.SET_CUSTOM_GAME_VALUE))
    
    # Set the value to 15 and submit
    # Note: Accessing the input element requires a different approach with .find()
    user.find(marker='value-input').elements.pop().set_value('15')
    user.find(marker='value-input-ok-button').click()
    await asyncio.sleep(0.5)
    # The score should now be 15
    await user.should_see('15', marker='team-1-score')

    # A regular click should now increment the score to 16
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.1)
    await user.should_see('16', marker='team-1-score')
    await asyncio.sleep(0.2)
    mock_backend.save.assert_called()


async def test_long_press_game_score_and_cancel(user: User, mock_backend):
    """Tests the long press feature to set a custom game score."""
    await user.open('/')
    await user.should_see('00', marker='team-2-score')
    await user.should_not_see(Messages.get(Messages.SET_CUSTOM_GAME_VALUE))

    # Perform a long press on the team 2 score button
    user.find(marker='team-2-score').trigger('mousedown')
    await asyncio.sleep(1)
    user.find(marker='team-2-score').trigger('mouseup')
    await asyncio.sleep(0)
    
    # The dialog to set a custom value should appear
    await user.should_see(Messages.get(Messages.SET_CUSTOM_GAME_VALUE))
    
    # Set the value to 15 and submit
    # Note: Accessing the input element requires a different approach with .find()
    user.find(marker='value-input').elements.pop().set_value('12')
    user.find(marker='value-input-cancel-button').click()
    await asyncio.sleep(0.5)
    # The score should now be 0
    await user.should_see('0', marker='team-1-score')

    # A regular click should now increment the score to 1
    user.find(marker='team-2-score').click()
    await asyncio.sleep(0.1)
    await user.should_see('01', marker='team-2-score')
    await asyncio.sleep(0.2)

async def test_long_press_set_score(user: User, mock_backend):
    """Tests the long press feature to set a custom set score."""
    await user.open('/')
    await user.should_see('0', marker='team-2-sets')
    await user.should_not_see(Messages.get(Messages.SET_CUSTOM_SET_VALUE))

    # Perform a long press on the team 2 set button
    user.find(marker='team-2-sets').trigger('mousedown')
    await asyncio.sleep(1)
    user.find(marker='team-2-sets').trigger('mouseup')
    await asyncio.sleep(0)

    # The dialog to set a custom value should appear
    await user.should_see(Messages.get(Messages.SET_CUSTOM_SET_VALUE))
    
    # Set the value to 2 and submit
    user.find(marker='value-input').elements.pop().set_value('2')
    user.find(marker='value-input-ok-button').click()
    await asyncio.sleep(0.5)
    # The set score should now be 2
    await user.should_see('2', marker='team-2-sets')

    # A regular click should now increment the set score to 3
    user.find(marker='team-2-sets').click()
    await user.should_see('3', marker='team-2-sets')
    await asyncio.sleep(0.2)
    mock_backend.save.assert_called()

async def test_long_press_set_score_cancel(user: User, mock_backend):
    """Tests the long press feature to set a custom set score."""
    await user.open('/')
    await user.should_see('0', marker='team-1-sets')
    await user.should_not_see(Messages.get(Messages.SET_CUSTOM_SET_VALUE))

    # Perform a long press on the team 2 set button
    user.find(marker='team-1-sets').trigger('mousedown')
    await asyncio.sleep(1)
    user.find(marker='team-1-sets').trigger('mouseup')
    await asyncio.sleep(0)

    # The dialog to set a custom value should appear
    await user.should_see(Messages.get(Messages.SET_CUSTOM_SET_VALUE))
    
    # Set the value to 2 and submit
    user.find(marker='value-input').elements.pop().set_value('2')
    user.find(marker='value-input-cancel-button').click()
    await asyncio.sleep(0.5)
    # The set score should now be 2
    await user.should_see('0', marker='team-2-sets')

    # A regular click should now increment the set score to 3
    user.find(marker='team-2-sets').click()
    await user.should_see('1', marker='team-2-sets')
    await asyncio.sleep(0.2)

async def test_long_press_wins_set(user: User, mock_backend):
    """Tests that a long press to the winning score awards the set."""
    await user.open('/')
    await user.should_see('00', marker='team-2-score')
    await user.should_see('0', marker='team-12-sets')

    # Long press to set the score to the winning value
    user.find(marker='team-2-score').trigger('mousedown')
    await asyncio.sleep(1)
    user.find(marker='team-2-score').trigger('mouseup')
    await asyncio.sleep(0)
    
    await user.should_see(Messages.get(Messages.SET_CUSTOM_GAME_VALUE))
    user.find(marker='value-input').elements.pop().set_value('25')
    user.find(marker='value-input-ok-button').click()
    await asyncio.sleep(0.5)

    # The set should be awarded to team 1, and the score should reset
    await user.should_see('1', marker='team-2-sets')
    await user.should_see('00', marker='team-2-score')

async def test_long_press_wins_match(user: User, mock_backend, monkeypatch):
    """Tests that a long press can win the final set and the match."""
    # Set up a match where team 1 has 2 sets and team 2 has 2 sets
    monkeypatch.setenv("MATCH_SETS", "5")
    end_game_model = load_fixture('endgame_model')
    end_game_model["Team 1 Sets"] = 2
    end_game_model["Team 2 Sets"] = 2
    mock_backend.get_current_model.return_value = end_game_model
    mock_backend.validate_and_store_model_for_oid.return_value = State.OIDStatus.VALID
    
    await user.open('/?control=endgame_oid_valid')
    await user.should_see(marker='team-1-score')
    # Long press to set the score to the winning value for the last set
    user.find(marker='team-1-score').trigger('mousedown')
    await asyncio.sleep(1)
    user.find(marker='team-1-score').trigger('mouseup')
    await asyncio.sleep(0)
    
    await user.should_see(Messages.get(Messages.SET_CUSTOM_GAME_VALUE))
    user.find(marker='value-input').elements.pop().set_value('15')
    user.find(marker='value-input-ok-button').click()
    await asyncio.sleep(0.5)

    # Team 1 should now have 3 sets, and the match should be over
    await user.should_see('3', marker='team-1-sets')
    
    # Try to score another point, which should be blocked
    user.find(marker='team-2-score').click()
    await user.should_see('00', marker='team-2-score') # Score should not change

async def test_long_press_on_sets_wins_match(user: User, mock_backend, monkeypatch):
    """Tests that a long press on the sets button can win the match."""
    monkeypatch.setenv("MATCH_SETS", "3")
    mid_game_model = load_fixture('midgame_model')
    mid_game_model["Team 1 Sets"] = 1
    mock_backend.get_current_model.return_value = mid_game_model
    mock_backend.validate_and_store_model_for_oid.return_value = State.OIDStatus.VALID

    await user.open('/?control=midgame_oid_valid')
    await user.should_see('1', marker='team-1-sets')

    # Long press the sets button to award the final set
    user.find(marker='team-1-sets').trigger('mousedown')
    await asyncio.sleep(1)
    user.find(marker='team-1-sets').trigger('mouseup')
    await asyncio.sleep(0)
    
    await user.should_see(Messages.get(Messages.SET_CUSTOM_SET_VALUE))
    user.find(marker='value-input').elements.pop().set_value('2')
    user.find(marker='value-input-ok-button').click()
    await asyncio.sleep(0.5)

    # Team 1 should now have 2 sets, and the match should be over
    await user.should_see('2', marker='team-1-sets')

    # Try to score a point, which should be blocked
    user.find(marker='team-2-score').click()
    await user.should_see('09', marker='team-2-score')