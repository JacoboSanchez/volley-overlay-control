import copy
from dataclasses import dataclass, field
from enum import Enum


class Serve(str, Enum):
    """Serve indicator. Extends ``str`` so comparisons like
    ``serve == 'A'`` remain valid for backward compatibility."""
    TEAM_1 = 'A'
    TEAM_2 = 'B'
    NONE = 'None'


@dataclass
class GameState:
    """Typed internal representation of a volleyball match state."""
    serve: Serve = Serve.NONE
    current_set: int = 1
    team1_sets: int = 0
    team2_sets: int = 0
    team1_timeouts: int = 0
    team2_timeouts: int = 0
    # Index 0 is unused; indices 1-5 hold scores for sets 1-5.
    team1_scores: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0, 0])
    team2_scores: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0, 0])


class State:

    CHAMPIONSHIP_LAYOUT_ID = '446a382f-25c0-4d1d-ae25-48373334e06b'

    OIDStatus = Enum('ValidationResult', [('VALID', 'valid'), ('INVALID', 'invalid'), ('DEPRECATED', 'deprecated'), ('EMPTY', 'empty')])

    # Legacy string constants — kept as aliases for backward compatibility.
    SERVE = 'Serve'
    SERVE_1 = Serve.TEAM_1
    SERVE_2 = Serve.TEAM_2
    SERVE_NONE = Serve.NONE
    T1TIMEOUTS_INT = 'Team 1 Timeouts'
    T2TIMEOUTS_INT = 'Team 2 Timeouts'
    T1SETS_INT = 'Team 1 Sets'
    T2SETS_INT = 'Team 2 Sets'
    CURRENT_SET_INT = 'Current Set'
    T1SET1_INT = 'Team 1 Game 1 Score'
    T1SET2_INT = 'Team 1 Game 2 Score'
    T1SET3_INT = 'Team 1 Game 3 Score'
    T1SET4_INT = 'Team 1 Game 4 Score'
    T1SET5_INT = 'Team 1 Game 5 Score'
    T2SET1_INT = 'Team 2 Game 1 Score'
    T2SET2_INT = 'Team 2 Game 2 Score'
    T2SET3_INT = 'Team 2 Game 3 Score'
    T2SET4_INT = 'Team 2 Game 4 Score'
    T2SET5_INT = 'Team 2 Game 5 Score'

    reset_model = {
        SERVE: SERVE_NONE,
        T1SETS_INT: '0',
        T2SETS_INT: '0',
        T1SET1_INT: '0',
        T1SET2_INT: '0',
        T1SET3_INT: '0',
        T1SET4_INT: '0',
        T1SET5_INT: '0',
        T2SET1_INT: '0',
        T2SET2_INT: '0',
        T2SET3_INT: '0',
        T2SET4_INT: '0',
        T2SET5_INT: '0',
        T1TIMEOUTS_INT: '0',
        T2TIMEOUTS_INT: '0',
        CURRENT_SET_INT: '1',
    }

    @staticmethod
    def keys_to_reset_simple_mode():
        return {State.T1SET5_INT,
                State.T2SET5_INT,
                State.T1SET4_INT,
                State.T2SET4_INT,
                State.T1SET3_INT,
                State.T2SET3_INT,
                State.T1SET2_INT,
                State.T2SET2_INT,
                State.T1SET1_INT,
                State.T2SET1_INT}

    # ------------------------------------------------------------------
    # Construction & serialization
    # ------------------------------------------------------------------

    def __init__(self, new_state=None):
        if new_state is None:
            self._state = GameState()
        else:
            self._state = self._from_dict(new_state)
            self._state.current_set = 1

    @staticmethod
    def _from_dict(d: dict) -> GameState:
        """Parse a legacy string-keyed dict into a typed ``GameState``."""
        return GameState(
            serve=Serve(d.get('Serve', 'None')),
            current_set=int(d.get('Current Set', 1)),
            team1_sets=int(d.get('Team 1 Sets', 0)),
            team2_sets=int(d.get('Team 2 Sets', 0)),
            team1_timeouts=int(d.get('Team 1 Timeouts', 0)),
            team2_timeouts=int(d.get('Team 2 Timeouts', 0)),
            team1_scores=[0] + [int(d.get(f'Team 1 Game {i} Score', 0)) for i in range(1, 6)],
            team2_scores=[0] + [int(d.get(f'Team 2 Game {i} Score', 0)) for i in range(1, 6)],
        )

    def _to_dict(self) -> dict[str, str]:
        """Serialize to the legacy string-keyed dict format."""
        s = self._state
        d = {
            'Serve': s.serve.value,
            'Current Set': str(s.current_set),
            'Team 1 Sets': str(s.team1_sets),
            'Team 2 Sets': str(s.team2_sets),
            'Team 1 Timeouts': str(s.team1_timeouts),
            'Team 2 Timeouts': str(s.team2_timeouts),
        }
        for i in range(1, 6):
            d[f'Team 1 Game {i} Score'] = str(s.team1_scores[i])
            d[f'Team 2 Game {i} Score'] = str(s.team2_scores[i])
        return d

    def get_reset_model(self):
        return self.reset_model.copy()

    def get_current_model(self):
        return self._to_dict()

    # ------------------------------------------------------------------
    # Static dict helpers (operate on legacy dicts, not on GameState)
    # ------------------------------------------------------------------

    @staticmethod
    def simplify_model(simplified):
        current_set = simplified[State.CURRENT_SET_INT]
        t1_points = simplified[f'Team 1 Game {current_set} Score']
        t2_points = simplified[f'Team 2 Game {current_set} Score']
        for key in State.keys_to_reset_simple_mode():
            if key in simplified:
                simplified[key] = '0'

        simplified[State.T1SET1_INT] = t1_points
        simplified[State.T2SET1_INT] = t2_points
        return simplified

    # ------------------------------------------------------------------
    # Typed getters & setters
    # ------------------------------------------------------------------

    def set_current_set(self, value):
        self._state.current_set = int(value)

    def get_timeout(self, team):
        if team not in (1, 2):
            raise KeyError(f'Team {team} Timeouts')
        val = self._state.team1_timeouts if team == 1 else self._state.team2_timeouts
        if not isinstance(val, int):
            return int(val)  # raises ValueError for non-numeric values
        return val

    def set_timeout(self, team, value):
        if team not in (1, 2):
            raise KeyError(f'Team {team} Timeouts')
        # Store via int() so that invalid values (e.g. "invalid") raise
        # ValueError on the next get_timeout() call — matching old behavior
        # where str was stored and int() was called in the getter.
        if team == 1:
            self._state.team1_timeouts = value
        else:
            self._state.team2_timeouts = value

    def get_sets(self, team):
        if team not in (1, 2):
            raise KeyError(f'Team {team} Sets')
        return self._state.team1_sets if team == 1 else self._state.team2_sets

    def set_sets(self, team, value):
        if team not in (1, 2):
            raise KeyError(f'Team {team} Sets')
        if team == 1:
            self._state.team1_sets = value
        else:
            self._state.team2_sets = value

    def get_game(self, team, set_num):
        if team not in (1, 2):
            raise KeyError(f'Team {team} Game {set_num} Score')
        if not (1 <= set_num <= 5):
            raise KeyError(f'Team {team} Game {set_num} Score')
        scores = self._state.team1_scores if team == 1 else self._state.team2_scores
        return scores[set_num]

    def set_game(self, set_num, team, value):
        if team not in (1, 2):
            raise KeyError(f'Team {team} Game {set_num} Score')
        if not (1 <= set_num <= 5):
            raise KeyError(f'Team {team} Game {set_num} Score')
        scores = self._state.team1_scores if team == 1 else self._state.team2_scores
        scores[set_num] = value

    def set_current_serve(self, value):
        if isinstance(value, Serve):
            self._state.serve = value
        else:
            self._state.serve = Serve(value)

    def get_current_serve(self):
        return self._state.serve
