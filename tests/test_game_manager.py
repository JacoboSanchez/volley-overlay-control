import pytest
import sys
import os

# Add the project's root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.game_manager import GameManager
from app.conf import Conf
from app.backend import Backend
from app.state import State
from unittest.mock import MagicMock

# Mock the Backend class to avoid actual API calls during tests
@pytest.fixture
def mock_backend():
    backend = MagicMock(spec=Backend)
    # Each time get_current_model is called, return a fresh copy of the reset_model
    backend.get_current_model.side_effect = lambda: State.reset_model.copy()
    return backend

# Fixture to create a GameManager instance with the mocked backend for each test
@pytest.fixture
def game_manager(mock_backend):
    conf = Conf()
    return GameManager(conf, mock_backend)

def test_initial_state(game_manager):
    """Tests that the game manager initializes with the correct default state."""
    state = game_manager.get_current_state()
    assert state.get_sets(1) == 0
    assert state.get_sets(2) == 0
    assert state.get_current_serve() == State.SERVE_NONE

def test_add_point(game_manager):
    """Tests adding a point to a team."""
    game_manager.add_game(1, 1, 25, 15, 5, False)
    state = game_manager.get_current_state()
    assert state.get_game(1, 1) == 1
    assert state.get_current_serve() == State.SERVE_1

def test_win_set(game_manager):
    """Tests the logic for winning a set."""
    for _ in range(24):
        game_manager.add_game(1, 1, 25, 15, 5, False)
    
    # a 24-24 score
    for _ in range(24):
        game_manager.add_game(2, 1, 25, 15, 5, False)

    game_manager.add_game(1, 1, 25, 15, 5, False)
    game_manager.add_game(1, 1, 25, 15, 5, False)

    state = game_manager.get_current_state()
    assert state.get_sets(1) == 1
    assert state.get_sets(2) == 0

def test_match_finished(game_manager):
    """Tests the logic for finishing a match."""
    # Team 1 wins 3 sets
    for i in range(1, 4):
        for _ in range(25):
            game_manager.add_game(1, i, 25, 15, 5, False)
    
    assert game_manager.match_finished() is True

def test_add_point_again(game_manager):
    """Tests adding a point to a team, verifying state isolation."""
    game_manager.add_game(2, 1, 25, 15, 5, False)
    state = game_manager.get_current_state()
    assert state.get_game(2, 1) == 1
    assert state.get_game(1,1) == 0 # This should be 0, not 1 from the previous test
    assert state.get_current_serve() == State.SERVE_2

def test_undo_point(game_manager):
    """Tests the undo functionality for adding a point."""
    game_manager.add_game(1, 1, 25, 15, 5, False)
    game_manager.add_game(1, 1, 25, 15, 5, True) # Undo the point
    state = game_manager.get_current_state()
    assert state.get_game(1, 1) == 0

def test_undo_set(game_manager):
    """Tests the undo functionality for adding a set."""
    game_manager.add_set(1, False)
    game_manager.add_set(1, True) # Undo the set
    state = game_manager.get_current_state()
    assert state.get_sets(1) == 0

def test_timeout_logic(game_manager):
    """Tests adding and undoing timeouts."""
    game_manager.add_timeout(1, False)
    state = game_manager.get_current_state()
    assert state.get_timeout(1) == 1

    game_manager.add_timeout(1, False)
    state = game_manager.get_current_state()
    assert state.get_timeout(1) == 2

    game_manager.add_timeout(1, True)
    state = game_manager.get_current_state()
    assert state.get_timeout(1) == 1

def test_serve_logic(game_manager):
    """Tests changing the serve."""
    game_manager.change_serve(1)
    state = game_manager.get_current_state()
    assert state.get_current_serve() == State.SERVE_1

    game_manager.change_serve(2)
    state = game_manager.get_current_state()
    assert state.get_current_serve() == State.SERVE_2

    game_manager.change_serve(0)
    state = game_manager.get_current_state()
    assert state.get_current_serve() == State.SERVE_NONE

def test_set_and_game_value(game_manager):
    """Tests the functions that directly set the game and set values."""
    game_manager.set_game_value(1, 10, 1)
    state = game_manager.get_current_state()
    assert state.get_game(1, 1) == 10

    game_manager.set_sets_value(2, 2)
    state = game_manager.get_current_state()
    assert state.get_sets(2) == 2

def test_last_set_point_limit(game_manager):
    """Tests that the points limit for the last set is correctly applied."""
    # Win the first 2 sets for each team
    for i in range(1, 3):
        for _ in range(25):
            game_manager.add_game(1, i, 25, 15, 5, False)
    for i in range(3, 5):
        for _ in range(25):
            game_manager.add_game(2, i, 25, 15, 5, False)
    
    # Play the last set
    for _ in range(14):
        game_manager.add_game(1, 5, 25, 15, 5, False)
    
    game_manager.add_game(1, 5, 25, 15, 5, False)
    state = game_manager.get_current_state()
    assert state.get_sets(1) == 3
    assert game_manager.match_finished() is True

def test_no_points_after_match_finished(game_manager):
    """Tests that no more points can be added after a match is finished."""
    # Team 1 wins 3 sets
    for i in range(1, 4):
        for _ in range(25):
            game_manager.add_game(1, i, 25, 15, 5, False)
    
    game_manager.add_game(1, 3, 25, 15, 5, False)
    state = game_manager.get_current_state()
    assert state.get_game(1, 3) == 25

def test_deuce_not_a_win(game_manager):
    """Tests that a set is not won at 25-24."""
    for _ in range(24):
        game_manager.add_game(1, 1, 25, 15, 5, False)
    for _ in range(24):
        game_manager.add_game(2, 1, 25, 15, 5, False)
    
    game_manager.add_game(1, 1, 25, 15, 5, False)
    state = game_manager.get_current_state()
    assert state.get_sets(1) == 0
    assert state.get_sets(2) == 0

def test_undo_winning_point(game_manager):
    """Tests undoing a point that won a set."""
    for _ in range(24):
        game_manager.add_game(1, 1, 25, 15, 5, False)
    
    game_manager.add_game(1, 1, 25, 15, 5, False) # Winning point
    game_manager.add_game(1, 1, 25, 15, 5, True) # Undo winning point
    
    state = game_manager.get_current_state()
    assert state.get_sets(1) == 0

def test_max_timeouts(game_manager):
    """Tests that a team cannot exceed the maximum number of timeouts."""
    game_manager.add_timeout(1, False)
    game_manager.add_timeout(1, False)
    game_manager.add_timeout(1, False) # Third timeout should not be added
    state = game_manager.get_current_state()
    assert state.get_timeout(1) == 2

def test_undo_timeout_at_zero(game_manager):
    """Tests that undoing a timeout at zero does not result in a negative value."""
    game_manager.add_timeout(1, True)
    state = game_manager.get_current_state()
    assert state.get_timeout(1) == 0