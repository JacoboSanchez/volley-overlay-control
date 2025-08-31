# tests/test_ui.py
import pytest
import time
import json
import os
from unittest.mock import patch, MagicMock
from nicegui.testing import Screen

import main
from app.backend import Backend

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

# --- Tests ---

@pytest.mark.module_under_test(main)
async def test_initial_scoreboard_is_rendered(screen: Screen, mock_backend):
    """
    Prueba que el marcador principal se renderiza correctamente con el estado inicial.
    """
    screen.open('/')
    # Verifica que los marcadores de puntuación y sets están en '00' y '0' respectivamente
    assert screen.click('00')
    assert screen.click('01')
    assert screen.click('00')
    mock_backend.save.assert_called()
