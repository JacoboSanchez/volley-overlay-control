import pytest
import sys
import os
import copy

# Add the project's root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from state import State

@pytest.fixture
def state():
    """Returns a new State instance with the default reset model for each test."""
    return State()

@pytest.fixture
def custom_state_data():
    """Provides a sample pre-existing state model for testing initialization."""
    return {
        State.SERVE: State.SERVE_1,
        State.T1SETS_INT: '2',
        State.T2SETS_INT: '1',
        State.T1SET1_INT: '25',
        State.T2SET1_INT: '20',
        State.T1SET2_INT: '25',
        State.T2SET2_INT: '18',
        State.T1SET3_INT: '10',
        State.T2SET3_INT: '15',
        State.T1TIMEOUTS_INT: '1',
        State.T2TIMEOUTS_INT: '2',
    }

# --- Initialization and Basic State ---

def test_initialization_default(state):
    """Tests that the state is initialized correctly with the default model."""
    assert state.get_current_model() is not None
    # The constructor sets this to an integer 1
    assert state.get_current_model()[State.CURRENT_SET_INT] == 1
    assert state.get_sets(1) == 0
    assert state.get_game(2, 5) == 0

def test_initialization_with_custom_state(custom_state_data):
    """Tests that the state can be initialized with a pre-existing model."""
    custom_state = State(new_state=custom_state_data)
    assert custom_state.get_sets(1) == 2
    assert custom_state.get_sets(2) == 1
    assert custom_state.get_game(1, 3) == 10
    assert custom_state.get_current_serve() == State.SERVE_1
    # The constructor should overwrite the current set to '1' (string) upon custom load
    assert custom_state.get_current_model()[State.CURRENT_SET_INT] == '1'

def test_reset_model_is_immutable(state):
    """Tests that modifying the retrieved reset_model doesn't affect the class's original."""
    my_reset = state.get_reset_model()
    my_reset[State.T1SETS_INT] = '99'
    
    fresh_reset = state.get_reset_model()
    assert fresh_reset[State.T1SETS_INT] == '0'

def test_current_model_is_a_copy(state):
    """Tests that the model in a new state instance is a copy, not a reference."""
    state_a = State()
    state_b = State()
    state_a.set_sets(1, 5)
    assert state_b.get_sets(1) == 0

# --- Getters and Setters ---

def test_get_and_set_timeout(state):
    """Tests the getter and setter for timeouts, including type conversion."""
    state.set_timeout(1, 2)
    assert state.get_timeout(1) == 2
    assert state.get_current_model()[State.T1TIMEOUTS_INT] == '2' # Internal representation is string
    state.set_timeout(2, 0)
    assert state.get_timeout(2) == 0

def test_get_and_set_sets(state):
    """Tests the getter and setter for sets, including type conversion."""
    state.set_sets(2, 3)
    assert state.get_sets(2) == 3
    assert state.get_current_model()[State.T2SETS_INT] == '3' # Internal representation is string

def test_get_and_set_game(state):
    """Tests the getter and setter for game scores across all possible sets."""
    state.set_game(set=1, team=1, value=15)
    assert state.get_game(1, 1) == 15
    assert state.get_current_model()[State.T1SET1_INT] == '15'

    state.set_game(set=5, team=2, value=10)
    assert state.get_game(2, 5) == 10
    assert state.get_current_model()[State.T2SET5_INT] == '10'

def test_get_and_set_current_serve(state):
    """Tests the getter and setter for the serving team."""
    state.set_current_serve(State.SERVE_1)
    assert state.get_current_serve() == State.SERVE_1
    state.set_current_serve(State.SERVE_NONE)
    assert state.get_current_serve() == State.SERVE_NONE

def test_set_current_set(state):
    """Tests setting the current set number."""
    state.set_current_set(4)
    assert state.get_current_model()[State.CURRENT_SET_INT] == 4

# --- simplify_model Scenarios ---

def test_simplify_model_logic(state):
    """Tests the logic for simplifying the model for the backend API."""
    # Setup a complex state
    model = state.get_current_model()
    model[State.CURRENT_SET_INT] = 3
    model[State.T1SET1_INT] = '25'
    model[State.T2SET1_INT] = '20'
    model[State.T1SET2_INT] = '22'
    model[State.T2SET2_INT] = '25'
    model[State.T1SET3_INT] = '10'
    model[State.T2SET3_INT] = '12'

    # Simplify the model
    simplified = State.simplify_model(copy.copy(model))

    # The scores from the current set (3) should be moved to set 1
    assert simplified[State.T1SET1_INT] == '10'
    assert simplified[State.T2SET1_INT] == '12'
    # All other set scores should be zeroed out
    assert simplified[State.T1SET2_INT] == '0'
    assert simplified[State.T2SET2_INT] == '0'
    assert simplified[State.T1SET3_INT] == '0'
    assert simplified[State.T2SET3_INT] == '0'
    assert simplified[State.T1SET4_INT] == '0'
    assert simplified[State.T2SET4_INT] == '0'
    assert simplified[State.T1SET5_INT] == '0'
    assert simplified[State.T2SET5_INT] == '0'
    # The current set number itself should not be changed in the process
    assert simplified[State.CURRENT_SET_INT] == 3

def test_simplify_model_when_current_set_is_one(state):
    """Tests that simplify_model works correctly when the current set is already 1."""
    model = state.get_current_model()
    model[State.CURRENT_SET_INT] = 1
    model[State.T1SET1_INT] = '5'
    model[State.T2SET1_INT] = '7'
    model[State.T1SET2_INT] = '2' # Some leftover score
    
    simplified = State.simplify_model(copy.copy(model))

    # Scores for set 1 should remain
    assert simplified[State.T1SET1_INT] == '5'
    assert simplified[State.T2SET1_INT] == '7'
    # Other scores should be cleared
    assert simplified[State.T1SET2_INT] == '0'

def test_simplify_model_preserves_other_state(state):
    """Tests that simplify_model does not affect other parts of the state."""
    model = state.get_current_model()
    model[State.CURRENT_SET_INT] = 2
    model[State.T1SET2_INT] = '10'
    model[State.T2SET2_INT] = '10'
    model[State.SERVE] = State.SERVE_2
    model[State.T1TIMEOUTS_INT] = '1'
    model[State.T1SETS_INT] = '1'

    simplified = State.simplify_model(copy.copy(model))

    assert simplified[State.SERVE] == State.SERVE_2
    assert simplified[State.T1TIMEOUTS_INT] == '1'
    assert simplified[State.T1SETS_INT] == '1'