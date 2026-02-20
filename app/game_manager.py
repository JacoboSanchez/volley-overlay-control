import logging
from app.state import State
from app.backend import Backend
from app.conf import Conf

class GameManager:
    """
    Manages the game logic, state, and backend communication.
    """

    def __init__(self, conf: Conf, backend: Backend):
        self.logger = logging.getLogger("GameManager")
        self.logger.debug("Initializing GameManager")
        self.conf = conf
        self.backend = backend
        self.main_state = State(backend.get_current_model())

    def get_current_state(self) -> State:
        """Returns the current state of the game."""
        self.logger.debug("Getting current state")
        return self.main_state

    def reset(self):
        """Resets the game state."""
        self.logger.debug("Resetting game state")
        self.backend.reset(self.main_state)
        self.main_state = State(self.backend.get_current_model())

    def save(self, simple: bool, current_set: int):
        """Saves the current game state."""
        self.logger.debug(f"Saving state, simple mode: {simple}, current set: {current_set}")
        self.main_state.set_current_set(current_set)
        self.backend.save(self.main_state, simple)

    def change_serve(self, team: int, force: bool = False):
        """Changes the serving team."""
        self.logger.debug(f"Changing serve to team {team}, force: {force}")
        current_serve = self.main_state.get_current_serve()
        new_serve = State.SERVE_NONE
        if team == 1:
            if force or current_serve != State.SERVE_1:
                new_serve = State.SERVE_1
        elif team == 2:
            if force or current_serve != State.SERVE_2:
                new_serve = State.SERVE_2
        self.main_state.set_current_serve(new_serve)

    def add_timeout(self, team: int, undo: bool):
        """Adds or removes a timeout for a team."""
        self.logger.debug(f"Adding timeout for team {team}, undo: {undo}")
        current_timeouts = self.main_state.get_timeout(team)
        if undo:
            if current_timeouts > 0:
                self.main_state.set_timeout(team, current_timeouts - 1)
        else:
            if current_timeouts < 2:
                self.main_state.set_timeout(team, current_timeouts + 1)

    def set_game_value(self, team: int, value: int, current_set: int):
        """Directly sets the game score for a team."""
        self.logger.debug(f"Setting game value for team {team} to {value} in set {current_set}")
        self.main_state.set_game(current_set, team, value)

    def set_sets_value(self, team: int, value: int):
        """Directly sets the sets won for a team."""
        self.logger.debug(f"Setting sets value for team {team} to {value}")
        self.main_state.set_sets(team, value)

    def _is_winning_score(self, score: int, rival_score: int, limit: int) -> bool:
        """Helper method to determine if a score is enough to win the set."""
        return score >= limit and (score - rival_score > 1)

    def add_game(self, team: int, current_set: int, points_limit: int, points_limit_last_set: int, sets_limit: int, undo: bool) -> bool:
        """Adds or removes a point to a team and checks if the set or match is won."""
        self.logger.debug(f"Adding game point for team {team} in set {current_set}, undo: {undo}")
        if not undo and self.match_finished():
             self.logger.debug("Match finished, not adding point.")
             return False

        self.change_serve(team, True)

        current_score = self.main_state.get_game(team, current_set)
        rival_team = 2 if team == 1 else 1
        rival_score = self.main_state.get_game(rival_team, current_set)
        game_limit = points_limit_last_set if current_set == sets_limit else points_limit

        if undo:
            if current_score > 0:
                # Check if the score before undoing was a winning score
                was_a_win = self._is_winning_score(current_score, rival_score, game_limit)
                
                self.main_state.set_game(current_set, team, current_score - 1)
                new_score = current_score - 1
                
                # Check if the new score is no longer a winning score
                is_still_a_win = self._is_winning_score(new_score, rival_score, game_limit)

                if was_a_win and not is_still_a_win:
                    self.logger.debug(f"Team {team} 'un-won' set {current_set} due to undo.")
                    self.add_set(team, undo=True)
                    return True # Signal that the set state changed
        else:
            self.main_state.set_game(current_set, team, current_score + 1)
            current_score += 1

            if self._is_winning_score(current_score, rival_score, game_limit):
                self.logger.debug(f"Team {team} won set {current_set}")
                self.add_set(team, undo)
                return True
        return False

    def add_set(self, team: int, undo: bool):
        """Adds or removes a set to a team."""
        self.logger.debug(f"Adding set for team {team}, undo: {undo}")
        if not undo and self.match_finished():
            self.logger.debug("Match finished, not adding set.")
            return

        current_sets = self.main_state.get_sets(team)
        if undo:
             if current_sets > 0:
                  self.main_state.set_sets(team, current_sets - 1)
        else:
            self.main_state.set_sets(team, current_sets + 1)
            # Reset timeouts and serve for the new set
            self.main_state.set_timeout(1, 0)
            self.main_state.set_timeout(2, 0)
            self.change_serve(0)


    def match_finished(self) -> bool:
        """Checks if the match has finished."""
        self.logger.debug("Checking if match is finished")
        t1_sets = self.main_state.get_sets(1)
        t2_sets = self.main_state.get_sets(2)
        limit = self.conf.sets
        soft_limit = int(limit / 2) + 1
        if t1_sets >= soft_limit or t2_sets >= soft_limit:
            self.logger.debug(f"Match finished. Score: {t1_sets}-{t2_sets}, required: {soft_limit}")
            return True
        self.logger.debug(f"Match not finished. Score: {t1_sets}-{t2_sets}, required: {soft_limit}")
        return False
    
    def check_set_won(self, team: int, current_set: int, points_limit: int, points_limit_last_set: int, sets_limit: int) -> bool:
        """Checks if a team has won the current set after a direct score update."""
        self.logger.debug(f"Checking if team {team} won set {current_set}")
        current_score = self.main_state.get_game(team, current_set)
        rival_team = 2 if team == 1 else 1
        rival_score = self.main_state.get_game(rival_team, current_set)
        game_limit = points_limit_last_set if current_set == sets_limit else points_limit

        if self._is_winning_score(current_score, rival_score, game_limit):
            self.logger.debug(f"Team {team} won set {current_set}")
            self.add_set(team, False)
            return True
        return False