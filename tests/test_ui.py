import pytest
import json
import os
from unittest.mock import patch
from nicegui.testing import User
from app.startup import startup
from app.theme import *

import main
from app.backend import Backend

# pylint: disable=missing-function-docstring

# Marca todos los tests en este fichero como asíncronos
pytestmark = pytest.mark.asyncio

# --- Funciones y Fixtures ---

def load_fixture(name):
    """Función auxiliar para cargar un fichero JSON desde la carpeta fixtures."""
    path = os.path.join(os.path.dirname(__file__), 'fixtures', f'{name}.json')
    with open(path) as f:
        return json.load(f)

@pytest.fixture
def mock_backend():
    """
    Fixture principal que mockea el Backend. Ahora también carga los datos
    de personalización desde un fichero JSON.
    """
    with patch('app.startup.Backend') as mock_backend_class:
        mock_instance = mock_backend_class.return_value
        
        # --- Comportamiento por defecto del mock ---
        mock_instance.is_visible.return_value = True
        # Carga el estado inicial del marcador
        mock_instance.get_current_model.return_value = load_fixture('base_model')
        # Carga el estado inicial de la personalización
        mock_instance.get_current_customization.return_value = load_fixture('base_customization')
        # Asegura que la validación del OID sea exitosa
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