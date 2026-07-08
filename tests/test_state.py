import copy
import os
import sys

import pytest

# Add the project's root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.state import State


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
    assert state.get_current_model()[State.CURRENT_SET_INT] == "1"
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
    # The flat legacy key carries the current-set value.
    assert state.get_current_model()[State.T1TIMEOUTS_INT] == '2'
    # The per-set key also carries it.
    assert state.get_current_model()[State._t_timeouts_key(1, 1)] == '2'
    state.set_timeout(2, 0)
    assert state.get_timeout(2) == 0


def test_timeouts_per_set(state):
    """Per-set timeout getters/setters target the requested set, and
    the default (no ``set_num`` arg) follows the current set."""
    state.set_timeout(1, 2, set_num=1)
    state.set_timeout(1, 1, set_num=2)
    state.set_current_set(2)
    # No arg → current set (2) value.
    assert state.get_timeout(1) == 1
    # Explicit set 1 is unchanged.
    assert state.get_timeout(1, set_num=1) == 2
    # Full history surfaces both sets.
    history = state.get_timeouts_by_set(1)
    assert history[1] == 2
    assert history[2] == 1
    assert history[3] == 0


def test_state_loads_legacy_flat_timeout(state):
    """A pre-refactor state file with only the flat ``Team N Timeouts``
    key should land the legacy value in the current set's slot."""
    legacy = {
        State.CURRENT_SET_INT: 3,
        State.T1TIMEOUTS_INT: '2',
        State.T2TIMEOUTS_INT: '1',
    }
    loaded = State(new_state=legacy)
    assert loaded.get_timeout(1, set_num=3) == 2
    assert loaded.get_timeout(2, set_num=3) == 1
    # Other sets are clean.
    assert loaded.get_timeout(1, set_num=1) == 0
    assert loaded.get_timeout(2, set_num=2) == 0


def test_get_timeout_returns_zero_for_out_of_bounds_set(state):
    """``get_timeout`` must not raise on an out-of-bounds ``set_num``:
    that would crash the state-broadcast hot path if (e.g.) a manual
    ``set_current_set`` ever lands ``current_set`` above 5. Returns 0
    — meaningfully "no timeouts in a set that doesn't exist".
    Bounds-checking remains the service layer's job."""
    # Direct out-of-bounds via explicit ``set_num``.
    assert state.get_timeout(1, set_num=6) == 0
    assert state.get_timeout(2, set_num=0) == 0
    # Same behaviour when current_set itself is out of bounds and we
    # rely on the default.
    state.set_current_set(99)
    assert state.get_timeout(1) == 0
    assert state.get_timeout(2) == 0
    # Bad ``team`` still raises (consistent with other accessors).
    with pytest.raises(KeyError):
        state.get_timeout(3, set_num=1)


def test_set_timeout_is_noop_for_out_of_bounds_set(state):
    """``set_timeout`` mirrors ``get_timeout``: out-of-bounds
    ``set_num`` is a silent no-op rather than a crash."""
    state.set_timeout(1, 1, set_num=1)
    state.set_timeout(1, 9, set_num=6)  # No-op, must not mutate slot 1.
    state.set_timeout(1, 9, set_num=0)  # No-op.
    assert state.get_timeout(1, set_num=1) == 1
    with pytest.raises(KeyError):
        state.set_timeout(3, 1, set_num=1)  # Bad team still raises.


def test_to_dict_legacy_timeouts_zero_when_current_set_out_of_bounds(state):
    """If ``current_set`` ever ends up out of bounds, the legacy
    ``Team N Timeouts`` keys must surface 0 (via the
    out-of-bounds-safe ``get_timeout``), not silently fall back to
    set 1's count under the legacy banner."""
    state.set_timeout(1, 2, set_num=1)
    state.set_current_set(99)
    model = state.get_current_model()
    assert model[State.T1TIMEOUTS_INT] == '0'
    # Per-set history is untouched.
    assert model[State._t_timeouts_key(1, 1)] == '2'


def test_state_round_trip_preserves_per_set_history(state):
    """Serialize-then-deserialize must preserve the full per-set
    timeout history (not just the current set)."""
    state.set_timeout(1, 2, set_num=1)
    state.set_timeout(2, 1, set_num=1)
    state.set_timeout(1, 1, set_num=2)
    state.set_current_set(2)
    round_tripped = State(new_state=state.get_current_model())
    assert round_tripped.get_timeouts_by_set(1) == {
        1: 2, 2: 1, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0,
    }
    assert round_tripped.get_timeouts_by_set(2) == {
        1: 1, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0,
    }

def test_get_and_set_sets(state):
    """Tests the getter and setter for sets, including type conversion."""
    state.set_sets(2, 3)
    assert state.get_sets(2) == 3
    assert state.get_current_model()[State.T2SETS_INT] == '3' # Internal representation is string

def test_get_and_set_game(state):
    """Tests the getter and setter for game scores across all possible sets."""
    state.set_game(set_num=1, team=1, value=15)
    assert state.get_game(1, 1) == 15
    assert state.get_current_model()[State.T1SET1_INT] == '15'

    state.set_game(set_num=5, team=2, value=10)
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
    assert state.get_current_model()[State.CURRENT_SET_INT] == '4'

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

def test_simplify_model_with_invalid_current_set(state):
    """Tests simplify_model with an invalid current_set value."""
    model = state.get_current_model()
    model[State.CURRENT_SET_INT] = 99 # Invalid set number
    with pytest.raises(KeyError):
        State.simplify_model(model)

def test_getters_with_invalid_keys(state):
    """Tests that getters raise KeyError for invalid team or set numbers."""
    with pytest.raises(KeyError):
        state.get_timeout(3)
    with pytest.raises(KeyError):
        state.get_sets(0)
    with pytest.raises(KeyError):
        state.get_game(1, 8)

def test_setters_with_invalid_values(state):
    """Tests that setters reject non-integer values with a ValueError."""
    with pytest.raises(ValueError):
        state.set_timeout(1, "invalid")
