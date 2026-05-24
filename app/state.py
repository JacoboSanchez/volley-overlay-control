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
    # Index 0 is unused; indices 1-5 hold per-set values.
    # Per-set timeout history lets undo across a set boundary restore the
    # prior set's timeouts (the flat counter that used to live here got
    # zeroed on every forward set transition).
    team1_timeouts_by_set: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0, 0])
    team2_timeouts_by_set: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0, 0])
    team1_scores: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0, 0])
    team2_scores: list[int] = field(default_factory=lambda: [0, 0, 0, 0, 0, 0])


class State:

    CHAMPIONSHIP_LAYOUT_ID = '446a382f-25c0-4d1d-ae25-48373334e06b'

    OIDStatus = Enum('OIDStatus', [('VALID', 'valid'), ('INVALID', 'invalid'), ('DEPRECATED', 'deprecated'), ('EMPTY', 'empty')])

    # Legacy string constants — kept as aliases for backward compatibility.
    SERVE = 'Serve'
    SERVE_1 = Serve.TEAM_1
    SERVE_2 = Serve.TEAM_2
    SERVE_NONE = Serve.NONE
    # Legacy flat timeout keys — populated on serialization with the
    # current set's value so any external integrator reading the JSON
    # by hand still gets a meaningful number. Per-set history lives in
    # the per-set keys produced by :meth:`_t_timeouts_key`.
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
        # Per-set timeout history keys — match the shape produced by
        # ``_to_dict`` so a reset payload zeroes the per-set history
        # alongside the legacy flat counter.
        **{f'Team {team} Set {set_num} Timeouts': '0'
           for team in (1, 2) for set_num in range(1, 6)},
    }

    @staticmethod
    def _t_timeouts_key(team: int, set_num: int) -> str:
        """Per-set timeout key in the legacy string-keyed dict shape."""
        return f'Team {team} Set {set_num} Timeouts'

    @staticmethod
    def keys_to_reset_simple_mode():
        keys = {State.T1SET5_INT,
                State.T2SET5_INT,
                State.T1SET4_INT,
                State.T2SET4_INT,
                State.T1SET3_INT,
                State.T2SET3_INT,
                State.T1SET2_INT,
                State.T2SET2_INT,
                State.T1SET1_INT,
                State.T2SET1_INT}
        for team in (1, 2):
            for set_num in range(1, 6):
                keys.add(State._t_timeouts_key(team, set_num))
        return keys

    # ------------------------------------------------------------------
    # Construction & serialization
    # ------------------------------------------------------------------

    def __init__(self, new_state=None):
        if new_state is None:
            self._state = GameState()
        else:
            self._state = self._from_dict(new_state)

    @staticmethod
    def _from_dict(d: dict) -> GameState:
        """Parse a legacy string-keyed dict into a typed ``GameState``.

        Per-set timeout history is read from ``Team N Set M Timeouts``
        keys when present. For pre-existing state files written before
        per-set history was introduced, the legacy single
        ``Team N Timeouts`` key is read and stamped into the current
        set's slot — preserving the operator's current in-flight count.
        """
        current_set = int(d.get('Current Set', 1))

        def per_set_timeouts(team: int) -> list[int]:
            slots = [0, 0, 0, 0, 0, 0]
            has_per_set = any(
                State._t_timeouts_key(team, i) in d for i in range(1, 6)
            )
            if has_per_set:
                for i in range(1, 6):
                    slots[i] = int(d.get(State._t_timeouts_key(team, i), 0))
            else:
                legacy = int(d.get(f'Team {team} Timeouts', 0))
                if 1 <= current_set <= 5:
                    slots[current_set] = legacy
            return slots

        return GameState(
            serve=Serve(d.get('Serve', 'None')),
            current_set=current_set,
            team1_sets=int(d.get('Team 1 Sets', 0)),
            team2_sets=int(d.get('Team 2 Sets', 0)),
            team1_timeouts_by_set=per_set_timeouts(1),
            team2_timeouts_by_set=per_set_timeouts(2),
            team1_scores=[0] + [int(d.get(f'Team 1 Game {i} Score', 0)) for i in range(1, 6)],
            team2_scores=[0] + [int(d.get(f'Team 2 Game {i} Score', 0)) for i in range(1, 6)],
        )

    def _to_dict(self) -> dict[str, str]:
        """Serialize to the legacy string-keyed dict format.

        Legacy ``Team N Timeouts`` keys carry the current set's value so
        external integrators reading the JSON by hand still see a
        meaningful number. ``Team N Set M Timeouts`` keys carry the
        per-set history.
        """
        s = self._state
        d = {
            'Serve': s.serve.value,
            'Current Set': str(s.current_set),
            'Team 1 Sets': str(s.team1_sets),
            'Team 2 Sets': str(s.team2_sets),
            # Route through ``get_timeout`` so out-of-bounds
            # ``current_set`` (defensive — shouldn't happen via the
            # normal session flow, but a stray manual ``set_current_set``
            # could) yields 0 instead of indexing into the array with
            # an arbitrary fallback set.
            'Team 1 Timeouts': str(self.get_timeout(1)),
            'Team 2 Timeouts': str(self.get_timeout(2)),
        }
        for i in range(1, 6):
            d[f'Team 1 Game {i} Score'] = str(s.team1_scores[i])
            d[f'Team 2 Game {i} Score'] = str(s.team2_scores[i])
            d[State._t_timeouts_key(1, i)] = str(s.team1_timeouts_by_set[i])
            d[State._t_timeouts_key(2, i)] = str(s.team2_timeouts_by_set[i])
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
        # Capture per-set timeout values for the current set before we
        # zero the per-set keys — so the moved-to-set-1 representation
        # still reflects the timeouts the operator has taken.
        t1_timeouts_current = simplified.get(
            State._t_timeouts_key(1, current_set), '0',
        )
        t2_timeouts_current = simplified.get(
            State._t_timeouts_key(2, current_set), '0',
        )
        for key in State.keys_to_reset_simple_mode():
            if key in simplified:
                simplified[key] = '0'

        simplified[State.T1SET1_INT] = t1_points
        simplified[State.T2SET1_INT] = t2_points
        if State._t_timeouts_key(1, 1) in simplified:
            simplified[State._t_timeouts_key(1, 1)] = t1_timeouts_current
        if State._t_timeouts_key(2, 1) in simplified:
            simplified[State._t_timeouts_key(2, 1)] = t2_timeouts_current
        return simplified

    # ------------------------------------------------------------------
    # Typed getters & setters
    # ------------------------------------------------------------------

    def set_current_set(self, value):
        self._state.current_set = int(value)

    def get_timeout(self, team, set_num=None):
        """Return the timeouts taken by *team* in *set_num*.

        ``set_num`` defaults to the current set when omitted, preserving
        the historical ``get_timeout(team)`` call shape. An invalid
        ``team`` raises ``KeyError`` (consistent with the other team-
        keyed accessors). An out-of-bounds ``set_num`` returns ``0``:
        the per-set timeout count for a set that doesn't exist (e.g.
        a manual edit landing the current set above ``sets_limit``)
        is meaningfully zero, and a hard raise here would crash the
        state-broadcast hot path on what should be a service-layer
        guard.
        """
        if team not in (1, 2):
            raise KeyError(f'Team {team} Timeouts')
        if set_num is None:
            set_num = self._state.current_set
        if not (1 <= set_num <= 5):
            return 0
        slots = (
            self._state.team1_timeouts_by_set if team == 1
            else self._state.team2_timeouts_by_set
        )
        return slots[set_num]

    def set_timeout(self, team, value, set_num=None):
        """Set the timeout count for *team* in *set_num* (defaults to
        the current set).

        An invalid ``team`` raises ``KeyError`` (consistent with the
        other team-keyed setters). An out-of-bounds ``set_num`` is a
        no-op for the same reason ``get_timeout`` returns ``0`` —
        bounds belong in the service layer, not the data accessors.
        """
        if team not in (1, 2):
            raise KeyError(f'Team {team} Timeouts')
        if set_num is None:
            set_num = self._state.current_set
        if not (1 <= set_num <= 5):
            return
        slots = (
            self._state.team1_timeouts_by_set if team == 1
            else self._state.team2_timeouts_by_set
        )
        slots[set_num] = int(value)

    def get_timeouts_by_set(self, team) -> dict[int, int]:
        """Return the full per-set timeout history for *team* as a
        1-indexed dict (set 1 through 5)."""
        if team not in (1, 2):
            raise KeyError(f'Team {team} Timeouts')
        slots = (
            self._state.team1_timeouts_by_set if team == 1
            else self._state.team2_timeouts_by_set
        )
        return {i: slots[i] for i in range(1, 6)}

    def get_sets(self, team):
        if team not in (1, 2):
            raise KeyError(f'Team {team} Sets')
        return self._state.team1_sets if team == 1 else self._state.team2_sets

    def set_sets(self, team, value):
        if team not in (1, 2):
            raise KeyError(f'Team {team} Sets')
        if team == 1:
            self._state.team1_sets = int(value)
        else:
            self._state.team2_sets = int(value)

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
        scores[set_num] = int(value)

    def set_current_serve(self, value):
        if isinstance(value, Serve):
            self._state.serve = value
        else:
            self._state.serve = Serve(value)

    def get_current_serve(self):
        return self._state.serve
