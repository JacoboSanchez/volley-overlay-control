import pytest
import json
import os
import asyncio
import importlib
from nicegui.testing import User
from tests.conftest import load_fixture
from app.theme import *
from app.customization import Customization
from app.messages import Messages
from app.state import State


# pylint: disable=missing-function-docstring

# Mark all tests in this file as asynchronous
pytestmark = pytest.mark.asyncio

async def _assert_scores_and_sets(user: User, score1: str, sets1: str, score2: str, sets2: str):
    """Utility method to validate scores and sets for both teams."""
    await user.should_see(content=score1, marker='team-1-score')
    await user.should_see(content=sets1, marker='team-1-sets')
    await user.should_see(content=score2, marker='team-2-score')
    await user.should_see(content=sets2, marker='team-2-sets')

async def _assert_all_set_scores(user: User, expected_scores: list[tuple[str, str]]):
    """Utility method to validate the content on games score for all sets on the table.
    expected_scores is a list of tuples, where each tuple is (team1_score, team2_score) for a set.
    """
    for i, (team1_score, team2_score) in enumerate(expected_scores):
        set_number = i + 1
        await user.should_see(content=team1_score, marker=f'team-1-set-{set_number}-score')
        await user.should_see(content=team2_score, marker=f'team-2-set-{set_number}-score')

async def _do_long_press(user: User, marker: str, value: str, confirm: bool, first_call: bool=True):
    """Utility method to test the long press functionality."""
    # Determine the expected message based on the marker
    if 'score' in marker:
        message = Messages.get(Messages.SET_CUSTOM_GAME_VALUE)
    elif 'sets' in marker:
        message = Messages.get(Messages.SET_CUSTOM_SET_VALUE)
    else:
        pytest.fail(f"Unknown marker type for long press: {marker}")

    if first_call:
        await user.should_not_see(message)
    else:
        # The dialog should have been already rendered
        await user.should_see(message)

    # Perform a long press on the specified element
    user.find(marker=marker).trigger('mousedown')
    await asyncio.sleep(1)
    user.find(marker=marker).trigger('mouseup')
    await asyncio.sleep(0)
    
    # The dialog to set a custom value should appear
    await user.should_see(message)
    
    # Set the value in the input
    user.find(marker='value-input').elements.pop().set_value(value)
    
    # Click OK or Cancel
    if confirm:
        user.find(marker='value-input-ok-button').click()
    else:
        user.find(marker='value-input-cancel-button').click()
    
    await asyncio.sleep(0.5)

async def _handle_dialog(user: User, trigger_marker: str, confirm: bool):
    """
    Utility method to test dialog interactions (confirm/cancel).
    """
    # Click the button that opens the dialog
    user.find(marker=trigger_marker).click()
    await asyncio.sleep(0) # Allow UI to update

    if confirm:
        confirm_marker = 'confirm-reset-button'
        if 'logout' in trigger_marker:
            confirm_marker = 'confirm-logout-button'
        elif 'refresh' in trigger_marker:
            confirm_marker = 'confirm-refresh-button'
        
        await user.should_see(marker=confirm_marker)
        user.find(marker=confirm_marker).click()
    else:
        cancel_marker = 'cancel-reset-button'
        if 'logout' in trigger_marker:
            cancel_marker = 'cancel-logout-button'
        elif 'refresh' in trigger_marker:
            cancel_marker = 'cancel-refresh-button'

        await user.should_see(marker=cancel_marker)
        user.find(marker=cancel_marker).click()
    
    await asyncio.sleep(0.2) # Wait for the action to complete

async def _login(user: User, username: str, password: str):
    """
    Handles the login process. Assumes the user is on the login page.
    """
    await user.should_see(marker='username-input')
    user.find(marker='username-input').type(username)
    user.find(marker='password-input').type(password)
    user.find(marker='login-button').click()

async def _navigate_to_config(user: User, open_root_page: str='/'):
    """
    Opens the page and navigates to the configuration tab, waiting for it to load.
    """
    if open_root_page is not None:
        await user.open(open_root_page)
    await user.should_see(marker='config-tab-button')
    user.find(marker='config-tab-button').click()
    await user.should_see(marker='height-input') # Wait for a representative element


async def test_game_buttons_increment(user: User, mock_backend):
    await user.open('/')
    await _assert_scores_and_sets(user, '00', '0', '00', '0')
    user.find(marker='team-1-score').click()
    await _assert_scores_and_sets(user, '01', '0', '00', '0')
    user.find(marker='team-1-score').click()
    await _assert_scores_and_sets(user, '02', '0', '00', '0')
    await asyncio.sleep(0.1)
    mock_backend.save.assert_called()


async def test_set_buttons_increment(user: User, mock_backend):
    await user.open('/')
    await _assert_scores_and_sets(user, '00', '0', '00', '0')
    user.find(marker='team-1-sets').click()
    await _assert_scores_and_sets(user, '00', '1', '00', '0')
    await _assert_all_set_scores(user, [('00', '00')])
    user.find(marker='team-2-sets').click()
    await _assert_scores_and_sets(user, '00', '1', '00', '1')
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

    await _assert_scores_and_sets(user, '05', '1', '06', '1')
    user.find(marker=f'team-1-score').click()
    await _assert_scores_and_sets(user, '06', '1', '06', '1')

    # Click the next set button in the pagination
    user.find(marker='set-selector').elements.pop().set_value(2)
    await _assert_scores_and_sets(user, '03', '1', '04', '1')

    # Click the next set button in the pagination
    user.find(marker='set-selector').elements.pop().set_value(1)
    await _assert_scores_and_sets(user, '15', '1', '15', '1')

    # Go back to the previous set
    user.find(marker='set-selector').elements.pop().set_value(3)
    await _assert_scores_and_sets(user, '06', '1', '06', '1')
    await _assert_all_set_scores(user, [('15', '15'), ('03', '04')])
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
    await _navigate_to_config(user)
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
    await _assert_scores_and_sets(user, '23', '2', '22', '1')

    # Team 1 scores two points to win the set and match
    user.find(marker='team-1-score').click()
    await _assert_scores_and_sets(user, '24', '2', '22', '1')
    user.find(marker='team-1-score').click()
    await _assert_scores_and_sets(user, '25', '3', '22', '1') # Match finished

    # Test that adding more points is blocked
    user.find(marker='team-1-score').click()
    await user.should_see(Messages.get(Messages.MATCH_FINISHED))
    await _assert_scores_and_sets(user, '25', '3', '22', '1')  # Score should not change
    await _assert_all_set_scores(user, [('16', '25'), ('25', '14'), ('25', '09'), ('25', '22')])

    # Test that undo works and reverts the end-game state
    user.find(marker='undo-button').click()
    user.find(marker='team-1-score').click()  # Undo the winning point

    # After undoing, score is 24, and set count for T1 should be 2.
    await asyncio.sleep(0.1)
    await _assert_scores_and_sets(user, '24', '2', '22', '1')
    await _assert_all_set_scores(user, [('16', '25'), ('25', '14'), ('25', '09')])
    await asyncio.sleep(0.3)


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
    await _assert_scores_and_sets(user, '23', '2', '22', '1')

    # Team 1 scores two points to win the set and match
    user.find(marker='team-1-score').click()
    await _assert_scores_and_sets(user, '24', '2', '22', '1')
    user.find(marker='team-1-score').click()
    await _assert_scores_and_sets(user, '25', '3', '22', '1')

    # Go to config tab to test refresh
    await _navigate_to_config(user, open_root_page=None)
    await user.should_see(marker='refresh-button')
    
    # Test refresh cancellation using the new helper
    await _handle_dialog(user, 'refresh-button', confirm=False)
    await user.should_see(marker='scoreboard-tab-button')

    # Go back to scoreboard and check that nothing changed
    user.find(marker='scoreboard-tab-button').click()
    await _assert_scores_and_sets(user, '25', '3', '22', '1') # Score should still be 25

    # Go back to config and test refresh confirmation using the new helper
    await _navigate_to_config(user, open_root_page=None)
    await _handle_dialog(user, 'refresh-button', confirm=True)
    
    # Go back to scoreboard
    user.find(marker='scoreboard-tab-button').click()

    # The state should have been reloaded from the modified backend data
    await _assert_scores_and_sets(user, '23', '2', '22', '1')
    await asyncio.sleep(0.3)


async def test_team_customization(user: User, mock_backend, monkeypatch):
    """Tests changing a team's name and checks if the backend is called correctly."""
    # Define new predefined teams for this test
    new_teams = json.dumps({
        "Eagles": {"icon": "path/to/eagle.png", "color": "#FF0000", "text_color": "#FFFFFF"},
    })
    monkeypatch.setenv("APP_TEAMS", new_teams)
    

    await _navigate_to_config(user)
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
    
    await _navigate_to_config(user)
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

    await _navigate_to_config(user)
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
    await _assert_scores_and_sets(user, '23', '2', '22', '1')
    user.find(marker='team-1-score').click()
    await _assert_scores_and_sets(user, '24', '2', '22', '1')
    await _assert_all_set_scores(user, [('16', '25'), ('25', '14'), ('25', '09')])

    # Go to config tab
    await _navigate_to_config(user, open_root_page=None)
    await user.should_see(marker='reset-button')

    # Click reset and cancel using the new helper
    await _handle_dialog(user, 'reset-button', confirm=False)
    # Should be back on the scoreboard, and score should NOT be reset
    await _assert_scores_and_sets(user, '24', '2', '22', '1')

    # Go to config tab again
    await _navigate_to_config(user, open_root_page=None)
    await user.should_see(marker='reset-button')

    # Click reset and confirm using the new helper
    await _handle_dialog(user, 'reset-button', confirm=True)
    # Verify that the backend's reset method was called
    mock_backend.reset.assert_called()
    await _assert_scores_and_sets(user, '00', '0', '00', '0')
    
    # Verify that save_json_model was called with the reset model
    mock_backend.save_json_model.assert_called_with(State.reset_model)

    await asyncio.sleep(0.2)

    
async def test_theme_application(user: User, mock_backend, monkeypatch):
    """Tests applying a predefined theme."""
    themes = json.dumps({
        "Test Theme": {
            "Team 1 Color": "#112233",
            "Width": 50.0,
            "Logos": "false",
            "Gradient": "false",
            "Height": 15.0
        }
    })

    monkeypatch.setenv("APP_THEMES", themes)

    await _navigate_to_config(user)
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
    await _navigate_to_config(user)
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
    await _assert_scores_and_sets(user, '00', '0', '00', '0')
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
    await _assert_scores_and_sets(user, '10', '0', '05', '0')
    user.find(marker='links-button').click()
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
    await _assert_scores_and_sets(user, '12', '1', '11', '0')
    user.find(marker='links-button').click()
    await user.should_not_see(Messages.get(Messages.OVERLAY_LINK))

    
    # --- Part 2: Reset and Use Manual OID ---

    # Go to config page and click reset link
    await _navigate_to_config(user, open_root_page=None)
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
    await _assert_scores_and_sets(user, '05', '1', '06', '1')
    await asyncio.sleep(0.1)

async def test_url_params_override_oid(user: User, mock_backend, monkeypatch):
    """Tests that the 'control' URL parameter correctly sets a mid-game OID."""
    # Ensure no OID is set initially from environment or storage
    monkeypatch.delenv("UNO_OVERLAY_OID", raising=False)
    
    # Open the page with a control URL parameter for a mid-game overlay.
    # The 'predefined_2_valid' fixture simulates a mid-game state.
    await user.open('/?control=predefined_1_valid')
    
    # The scoreboard should load directly with the scores from the mid-game fixture.
    # In predefined_overlay_1.json, the score is 10-5.
    await _assert_scores_and_sets(user, '10', '0', '05', '0')

    # Go to the configuration tab
    await _navigate_to_config(user, open_root_page=None)
    
    # Verify the control link uses the OID from the URL parameter
    user.find(marker='links-button').click()
    await user.should_see(Messages.get(Messages.CONTROL_LINK))
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
    await _assert_scores_and_sets(user, '12', '1', '11', '0')
    # Go to the configuration tab
    await _navigate_to_config(user, open_root_page=None)
    
    # Verify the output link is present and correct
    user.find(marker='links-button').click()
    await user.should_see(Messages.get(Messages.OVERLAY_LINK))
    output_link = user.find(Messages.get(Messages.OVERLAY_LINK))
    expected_href = 'https://app.overlays.uno/output/custom_output_token'
    assert output_link.elements.pop().props['href'] == expected_href

    # Verify the preview link is present and correct
    user.find(marker='links-button').click()
    await user.should_see(Messages.get(Messages.PREVIEW_LINK))
    output_link = user.find(Messages.get(Messages.PREVIEW_LINK))
    expected_href = './preview?output=custom_output_token&width=55.0&height=20.0&x=-19.5&y=34.0'
    assert output_link.elements.pop().props['href'] == expected_href

    await asyncio.sleep(0.1)

async def test_beach_mode_limits(user: User, mock_backend):
    """Tests that the /beach URL correctly applies beach volleyball rules (21 points, 3 sets)."""
    # Open the specific URL for beach mode
    await user.open('/beach?control=test_oid_valid')
    await user.should_see(marker='team-1-score')

    await _do_long_press(user, 'team-1-score', '20', True)
    await _assert_scores_and_sets(user, '20', '0', '00', '0') # Set should not be won yet

    # Score the winning point for Team 1
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.01)
    await _assert_scores_and_sets(user, '00', '1', '00', '0') # Team 1 wins the set
    await _assert_all_set_scores(user, [('21', '00')])

    await _do_long_press(user, 'team-1-score', '21', True, first_call=False)
    await _assert_scores_and_sets(user, '21', '2', '00', '0')
    
    # Try to score another point, which should be blocked as the match is over
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.01)
    await _assert_scores_and_sets(user, '21', '2', '00', '0') # Score should not change
    await _assert_all_set_scores(user, [('21', '00'), ('21', '00')])
    await asyncio.sleep(0.3)


async def test_indoor_mode_limits(user: User, mock_backend):
    """Tests that the /indoor URL correctly applies indoor volleyball rules (25 points, 5 sets)."""
    await user.open('/indoor?control=endgame_oid_valid')
    await user.should_see(marker='team-1-score')

    # Score points up to 24 for Team 1
    user.find(marker='team-1-score').click()
    await _assert_scores_and_sets(user, '24', '2', '22', '1') # Set not won yet
    await _assert_all_set_scores(user, [('16', '25'), ('25', '14'), ('25', '09')])

    # Score the winning point
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.01)
    await _assert_all_set_scores(user, [('16', '25'), ('25', '14'), ('25', '09'), ('25', '22')]) # Team 1 wins the set
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
    for i in range(1, 10):
        user.find(marker='team-1-score').click()
        await asyncio.sleep(0.01)
        await _assert_scores_and_sets(user, f'{i:02d}', '0', '00', '0')

    # Score the winning point
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.1)
    await _assert_scores_and_sets(user, '00', '1', '00', '0')
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
    for i in range(1, 6):
        user.find(marker='team-2-score').click()
        await asyncio.sleep(0.01)
        if i < 5:
            await _assert_scores_and_sets(user, '00', '0', f'{i:02d}', '0')

    await _assert_scores_and_sets(user, '00', '0', '05', '1')

    # The match should be over. Trying to score another point should fail.
    user.find(marker='team-2-score').click()
    await asyncio.sleep(0.1)
    await _assert_scores_and_sets(user, '00', '0', '05', '1') # Score should not change
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
    await _login(user, 'user1', 'password1')
    
    # After login, we should see the scoreboard with data from "predefined_1_valid"
    await user.should_see(marker='team-1-score')
    await _assert_scores_and_sets(user, '10', '0', '05', '0')
    
    # Go to the configuration tab and check links
    await _navigate_to_config(user, open_root_page=None)
    user.find(marker='links-button').click()
    await user.should_see(Messages.get(Messages.OVERLAY_LINK))
    assert 'https://app.overlays.uno/output/output_1' in user.find(Messages.get(Messages.OVERLAY_LINK)).elements.pop().props['href']
    assert 'https://app.overlays.uno/control/predefined_1_valid' in user.find(Messages.get(Messages.CONTROL_LINK)).elements.pop().props['href']
    await asyncio.sleep(0.3)

async def test_logout_flow(user: User, mock_backend, auth_users_env):
    """Tests the complete logout and login flow."""
    await user.open('/')
    
    # Login as user2
    await _login(user, 'user2', 'password2')
    
    # User2 has no predefined OID, so the OID dialog should appear
    await user.should_see(marker='control-url-input')
    
    # Logout from the OID dialog
    user.find(marker='logout-button-oid').click()
    
    # We should be back on the login page
    await user.should_see(marker='username-input')
    
    # Login again as user1
    await _login(user, 'user1', 'password1')
    
    # We should see the scoreboard for user1
    await user.should_see(marker='team-1-score')
    await _assert_scores_and_sets(user, '10', '0', '05', '0')
    
    # Go to config tab and logout (confirm)
    await _navigate_to_config(user, open_root_page=None)
    await _handle_dialog(user, 'logout-button', confirm=True)
    
    # We should be back on the login page
    await user.should_see(marker='username-input')
    await user.should_not_see(marker='config-tab-button')

    # Login again as user1, but cancel logout
    await _login(user, 'user1', 'password1')
    await user.should_see(marker='team-1-score')
    await _navigate_to_config(user, open_root_page=None)
    await _handle_dialog(user, 'logout-button', confirm=False)
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
    await _login(user, 'user2', 'password2')
    
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
    await _login(user, 'user1', 'password1')
    
    # User1 has a predefined OID, so the scoreboard loads directly.
    # We need to go to the config, reset the OID to see the dialog again.
    await _navigate_to_config(user, open_root_page=None)
    await user.should_see(marker='change-overlay-button')
    user.find(marker='change-overlay-button').click()
    
    # Now user1 sees the OID dialog. Let's check the overlays.
    await user.should_see(marker='predefined-overlay-selector')
    user.find(marker='predefined-overlay-selector').click()
    
    # User1 should see both overlays
    await user.should_see("User 1 Overlay")
    await asyncio.sleep(0.3)

async def test_autohide_feature(user: User, mock_backend, monkeypatch):
    """Tests the auto-hide functionality with corrected initial state."""
    mock_backend.get_current_model.return_value = load_fixture('base_model')
    monkeypatch.setenv('DEFAULT_HIDE_TIMEOUT', '1')

    # Set initial visibility to False to ensure the first call is to show
    mock_backend.is_visible.return_value = False
    
    # Go to config tab, open options, and enable auto-hide
    await _navigate_to_config(user, open_root_page='/?control=test_oid_valid')
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
    
    await _do_long_press(user, 'team-1-score', '24', True)
    await _assert_scores_and_sets(user, '24', '0', '05', '0')
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.1)
    await _assert_scores_and_sets(user, '00', '1', '00', '0') # Set is won
    await _assert_all_set_scores(user, [('25', '05')])

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
    # Go to config tab, open options, and enable auto-simple-mode
    await _navigate_to_config(user, open_root_page='/?control=test_oid_valid')
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
    await _assert_scores_and_sets(user, '00', '0', '00', '0')
    await _do_long_press(user, 'team-1-score', '15', True)
    await _assert_scores_and_sets(user, '15', '0', '00', '0')
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.1)
    await _assert_scores_and_sets(user, '16', '0', '00', '0')
    await asyncio.sleep(0.2)
    mock_backend.save.assert_called()


async def test_long_press_game_score_and_cancel(user: User, mock_backend):
    """Tests the long press feature to set a custom game score."""
    await user.open('/')
    await _assert_scores_and_sets(user, '00', '0', '00', '0')
    await _do_long_press(user, 'team-2-score', '12', False)
    await _assert_scores_and_sets(user, '00', '0', '00', '0')
    user.find(marker='team-2-score').click()
    await asyncio.sleep(0.1)
    await _assert_scores_and_sets(user, '00', '0', '01', '0')
    await asyncio.sleep(0.2)

async def test_long_press_set_score(user: User, mock_backend):
    """Tests the long press feature to set a custom set score."""
    await user.open('/')
    await _assert_scores_and_sets(user, '00', '0', '00', '0')
    await _do_long_press(user, 'team-2-sets', '2', True)
    await _assert_scores_and_sets(user, '00', '0', '00', '2')
    user.find(marker='team-2-sets').click()
    await _assert_scores_and_sets(user, '00', '0', '00', '3')
    await asyncio.sleep(0.2)
    mock_backend.save.assert_called()

async def test_long_press_set_score_cancel(user: User, mock_backend):
    """Tests the long press feature to set a custom set score."""
    await user.open('/')
    await _assert_scores_and_sets(user, '00', '0', '00', '0')
    await _do_long_press(user, 'team-1-sets', '2', False)
    await _assert_scores_and_sets(user, '00', '0', '00', '0')
    user.find(marker='team-2-sets').click()
    await _assert_scores_and_sets(user, '00', '0', '00', '1')
    await asyncio.sleep(0.2)

async def test_long_press_wins_set(user: User, mock_backend):
    """Tests that a long press to the winning score awards the set."""
    await user.open('/')
    await _assert_scores_and_sets(user, '00', '0', '00', '0')
    await _do_long_press(user, 'team-2-score', '25', True)
    await _assert_scores_and_sets(user, '00', '0', '00', '1')
    await _assert_all_set_scores(user, [('00', '25')])
    await asyncio.sleep(0.2)

async def test_long_press_wins_match(user: User, mock_backend, monkeypatch):
    """Tests that a long press can win the final set and the match."""
    # Set up a match where team 1 has 2 sets and team 2 has 2 sets
    monkeypatch.setenv("MATCH_SETS", "5")
    mock_backend.validate_and_store_model_for_oid.return_value = State.OIDStatus.VALID
    await user.open('/?control=endgame_oid_valid')
    await user.should_see(marker='team-1-score')
    await _assert_scores_and_sets(user, '23', '2', '22', '1')
    await _do_long_press(user, 'team-2-score', '25', True)
    await _assert_scores_and_sets(user, '00', '2', '00', '2')
    await asyncio.sleep(0.2)
    await _do_long_press(user, 'team-1-score', '15', True, first_call=False)
    await _assert_scores_and_sets(user, '15', '3', '00', '2')
    
    # Try to score another point, which should be blocked
    user.find(marker='team-2-score').click()
    await _assert_scores_and_sets(user, '15', '3', '00', '2') # Score should not change
    await _assert_all_set_scores(user, [('16', '25'), ('25', '14'), ('25', '09'), ('23', '25'), ('15', '00')])
    await asyncio.sleep(0.2)

async def test_long_press_on_sets_wins_match(user: User, mock_backend, monkeypatch):
    """Tests that a long press on the sets button can win the match."""
    monkeypatch.setenv("MATCH_SETS", "3")
    mid_game_model = load_fixture('midgame_model')
    mid_game_model["Team 1 Sets"] = 1
    mock_backend.get_current_model.return_value = mid_game_model
    mock_backend.validate_and_store_model_for_oid.return_value = State.OIDStatus.VALID

    await user.open('/?control=midgame_oid_valid')
    await _assert_scores_and_sets(user, '11', '1', '09', '1')
    await _do_long_press(user, 'team-1-sets', '2', True)
    await _assert_scores_and_sets(user, '11', '2', '09', '1')

    # Try to score a point, which should be blocked
    user.find(marker='team-2-score').click()
    await _assert_scores_and_sets(user, '11', '2', '09', '1')
    await asyncio.sleep(0.2)

async def test_simultaneous_clicks(user: User, mock_backend):
    """Tests the application's behavior with rapid, simultaneous clicks."""
    await user.open('/')
    await _assert_scores_and_sets(user, '00', '0', '00', '0')

    # Simulate rapid clicks on both score buttons
    user.find(marker='team-1-score').click()
    user.find(marker='team-2-score').click()
    user.find(marker='team-1-score').click()
    user.find(marker='team-2-score').click()

    await asyncio.sleep(0.5) # Allow UI to settle

    # The final score should be deterministic, not a race condition.
    # Depending on the processing order, it could be 2-2 or another combination.
    # The key is that it's consistent and doesn't crash.
    # Based on the current implementation, it should be 2-2.
    await _assert_scores_and_sets(user, '02', '0', '02', '0')

async def test_deuce_and_win_by_two(user: User, mock_backend):
    """Tests the deuce rule (must win by 2 points)."""
    await user.open('/?control=test_oid_valid')
    await user.should_see(marker='team-1-score')

    # Go to 24-24
    await _do_long_press(user, 'team-1-score', '24', True)
    await _do_long_press(user, 'team-2-score', '24', True, first_call=False)
    await _assert_scores_and_sets(user, '24', '0', '24', '0')

    # Team 1 scores, now 25-24
    user.find(marker='team-1-score').click()
    await _assert_scores_and_sets(user, '25', '0', '24', '0') # Set is not won yet

    # Team 2 scores, back to deuce 25-25
    user.find(marker='team-2-score').click()
    await _assert_scores_and_sets(user, '25', '0', '25', '0')

    # Team 2 scores again, 25-26
    user.find(marker='team-2-score').click()
    await _assert_scores_and_sets(user, '25', '0', '26', '0') # Set is not won yet

    # Team 2 scores the winning point, 25-27
    user.find(marker='team-2-score').click()
    await _assert_scores_and_sets(user, '00', '0', '00', '1') # Team 2 wins the set
    await _assert_all_set_scores(user, [('25', '27')])
    await asyncio.sleep(0.2)

async def test_state_persistence_on_refresh(user: User, mock_backend):
    """Tests that the scoreboard state is restored after a page refresh."""
    await user.open('/?control=test_oid_valid')
    await user.should_see(marker='team-1-score')

    # Score some points
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0)
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0)
    user.find(marker='team-1-sets').click()
    await asyncio.sleep(0)
    
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0)
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0)
    user.find(marker='team-2-score').click()
    await asyncio.sleep(0)
    await user.should_see(marker='team-1-score')

    await _assert_scores_and_sets(user, '02', '1', '01', '0')

    # Simulate a page refresh
    await user.open('/?control=test_oid_valid')
    await user.should_see(marker='team-1-score')


    # The state should be restored from the backend
    await _assert_scores_and_sets(user, '02', '1', '01', '0')
    await _assert_all_set_scores(user, [('02', '00')])
    await asyncio.sleep(0.2)

async def test_single_overlay_mode_false_with_env_var(user: User, mock_backend, monkeypatch):
    """
    Tests that with SINGLE_OVERLAY_MODE=false, the OID dialog is shown even if UNO_OVERLAY_OID is set.
    """
    monkeypatch.setenv('SINGLE_OVERLAY_MODE', 'false')
    monkeypatch.setenv('UNO_OVERLAY_OID', 'test_oid_valid')
    # Reload conf to apply env var
    import app.conf
    importlib.reload(app.conf)


    await user.open('/')
    await user.should_see(marker='control-url-input')
    await user.should_not_see(marker='team-1-score')


async def test_single_overlay_mode_true_with_env_var(user: User, mock_backend, monkeypatch):
    """
    Tests that with SINGLE_OVERLAY_MODE=true, the scoreboard loads directly using UNO_OVERLAY_OID.
    """
    monkeypatch.setenv('SINGLE_OVERLAY_MODE', 'true')
    monkeypatch.setenv('UNO_OVERLAY_OID', 'test_oid_valid')
    # Reload conf to apply env var
    import app.conf
    importlib.reload(app.conf)

    await user.open('/')
    await user.should_not_see(marker='control-url-input')
    await user.should_see(marker='team-1-score')
    await _assert_scores_and_sets(user, '00', '0', '00', '0')


async def test_single_overlay_mode_false_with_url_param(user: User, mock_backend, monkeypatch):
    """
    Tests that with SINGLE_OVERLAY_MODE=false, an OID from a URL parameter is still used.
    """
    monkeypatch.setenv('SINGLE_OVERLAY_MODE', 'false')
    monkeypatch.delenv('UNO_OVERLAY_OID', raising=False)
    # Reload conf to apply env var
    import app.conf
    importlib.reload(app.conf)

    await user.open('/?control=predefined_1_valid')
    await user.should_not_see(marker='control-url-input')
    await user.should_see(marker='team-1-score')
    await _assert_scores_and_sets(user, '10', '0', '05', '0')


async def test_single_overlay_mode_true_with_url_param_override(user: User, mock_backend, monkeypatch):
    """
    Tests that an OID from a URL parameter overrides UNO_OVERLAY_OID when SINGLE_OVERLAY_MODE=true.
    """
    monkeypatch.setenv('SINGLE_OVERLAY_MODE', 'true')
    monkeypatch.setenv('UNO_OVERLAY_OID', 'test_oid_valid')
    # Reload conf to apply env var
    import app.conf
    importlib.reload(app.conf)

    await user.open('/?control=predefined_1_valid')
    await user.should_not_see(marker='control-url-input')
    await user.should_see(marker='team-1-score')
    # predefined_1_valid has scores 10-5
    await _assert_scores_and_sets(user, '10', '0', '05', '0')


async def test_single_overlay_mode_false_no_oid(user: User, mock_backend, monkeypatch):
    """
    Tests that with SINGLE_OVERLAY_MODE=false and no OID, the OID dialog is shown.
    """
    monkeypatch.setenv('SINGLE_OVERLAY_MODE', 'false')
    monkeypatch.delenv('UNO_OVERLAY_OID', raising=False)
    # Reload conf to apply env var
    import app.conf
    importlib.reload(app.conf)

    await user.open('/')
    await user.should_see(marker='control-url-input')
    await user.should_not_see(marker='team-1-score')


async def test_single_overlay_mode_true_no_oid(user: User, mock_backend, monkeypatch):
    """
    Tests that with SINGLE_OVERLAY_MODE=true and no OID, the OID dialog is shown.
    """
    monkeypatch.setenv('SINGLE_OVERLAY_MODE', 'true')
    monkeypatch.delenv('UNO_OVERLAY_OID', raising=False)
    # Reload conf to apply env var
    import app.conf
    importlib.reload(app.conf)

    await user.open('/')
    await user.should_see(marker='control-url-input')
    await user.should_not_see(marker='team-1-score')

async def test_auto_simple_mode_timeout_feature(user: User, mock_backend):
    """Tests the auto-simple-mode-timeout functionality."""
    # Go to config tab, open options, and enable auto-simple-mode and timeout option
    await _navigate_to_config(user, open_root_page='/?control=test_oid_valid')
    await user.should_see(marker='save-button')
    user.find(marker='options-button').click()
    await user.should_see(Messages.get(Messages.AUTO_SIMPLE_MODE))
    user.find(Messages.get(Messages.AUTO_SIMPLE_MODE)).click()
    await user.should_see(Messages.get(Messages.AUTO_SIMPLE_MODE_TIMEOUT_ON_TIMEOUT))
    user.find(Messages.get(Messages.AUTO_SIMPLE_MODE_TIMEOUT_ON_TIMEOUT)).click()
    user.find(Messages.get(Messages.CLOSE)).click()
    user.find(marker='scoreboard-tab-button').click()
    await user.should_see(marker='team-1-score')

    # Scoring a point should switch to simple mode
    user.find(marker='team-1-score').click()
    await asyncio.sleep(0.1)
    mock_backend.reduce_games_to_one.assert_called_once()
    await user.should_see('window', marker='simple-mode-button')

    # Adding a timeout should switch back to full mode
    user.find(marker='team-1-timeout').click()
    await asyncio.sleep(0.1)
    await user.should_see('grid_on', marker='simple-mode-button')


async def test_show_preview_toggle(user: User, mock_backend, monkeypatch):
    """Tests the show/hide preview functionality and its persistence."""
    monkeypatch.setenv('SHOW_PREVIEW', 'true')
    
    import app.conf
    importlib.reload(app.conf)

    await user.open('/?control=test_oid_valid&output=custom_output_token')
    await asyncio.sleep(0)
    await user.should_see(marker='preview-button')

    # Iframe should be visible initially
    await user.should_see(marker='preview-iframe')

    # Click to hide
    user.find(marker='preview-button').click()
    await asyncio.sleep(0.1)
    await user.should_not_see(marker='preview-iframe')

    # Click to show again
    user.find(marker='preview-button').click()
    await asyncio.sleep(0.1)
    await user.should_see(marker='preview-iframe')

    # Reload the page and check if it's still visible
    await user.open('/?control=test_oid_valid&output=custom_output_token')
    await user.should_see(marker='preview-button')
    await user.should_see(marker='preview-iframe')

    # Click to hide, then reload
    user.find(marker='preview-button').click()
    await asyncio.sleep(0.1)
    await user.should_not_see(marker='preview-iframe')

    await user.open('/?control=test_oid_valid&output=custom_output_token')
    await user.should_see(marker='preview-button')
    await user.should_not_see(marker='preview-iframe')

    # without output there is no button or overlay
    await user.open('/?control=test_oid_valid')
    await asyncio.sleep(0)
    await user.should_not_see(marker='preview-button')
    await user.should_not_see(marker='preview-iframe')
