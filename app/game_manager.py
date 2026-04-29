import logging

from app.backend import Backend
from app.conf import Conf
from app.state import State

logger = logging.getLogger(__name__)


class GameManager:
    """
    Manages the game logic, state, and backend communication.
    """

    def __init__(self, conf: Conf, backend: Backend):
        logger.debug("Initializing GameManager")
        self.conf = conf
        self.backend = backend
        self.main_state = State(backend.get_current_model())

    def get_current_state(self) -> State:
        """Returns the current state of the game."""
        logger.debug("Getting current state")
        return self.main_state

    def reset(self):
        """Resets the game state."""
        logger.debug("Resetting game state")
        self.backend.reset(self.main_state)
        self.main_state = State(self.backend.get_current_model())

    def save(self, simple: bool, current_set: int):
        """Saves the current game state."""
        logger.debug("Saving state, simple mode: %s, current set: %s", simple, current_set)
        self.main_state.set_current_set(current_set)
        self.backend.save(self.main_state, simple)

    def change_serve(self, team: int, force: bool = False):
        """Changes the serving team."""
        logger.debug("Changing serve to team %s, force: %s", team, force)
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
        logger.debug("Adding timeout for team %s, undo: %s", team, undo)
        current_timeouts = self.main_state.get_timeout(team)
        if undo:
            if current_timeouts > 0:
                self.main_state.set_timeout(team, current_timeouts - 1)
        else:
            if current_timeouts < 2:
                self.main_state.set_timeout(team, current_timeouts + 1)

    def set_game_value(self, team: int, value: int, current_set: int):
        """Directly sets the game score for a team."""
        logger.debug("Setting game value for team %s to %s in set %s", team, value, current_set)
        self.main_state.set_game(current_set, team, value)

    def set_sets_value(self, team: int, value: int):
        """Directly sets the sets won for a team."""
        logger.debug("Setting sets value for team %s to %s", team, value)
        self.main_state.set_sets(team, value)

    def _is_winning_score(self, score: int, rival_score: int, limit: int) -> bool:
        """Helper method to determine if a score is enough to win the set."""
        return score >= limit and (score - rival_score > 1)

    def add_game(self, team: int, current_set: int, points_limit: int, points_limit_last_set: int, sets_limit: int, undo: bool) -> bool:
        """Adds or removes a point to a team and checks if the set or match is won."""
        logger.debug("Adding game point for team %s in set %s, undo: %s", team, current_set, undo)
        if not undo and self.match_finished():
             logger.debug("Match finished, not adding point.")
             return False

        self.change_serve(team, True)

        rival_team = 2 if team == 1 else 1

        if undo:
            # When the most recent point was set-winning, the session has already
            # advanced to the next set, leaving its score at 0-0. Fall back to
            # the prior set so the cascade in this branch can un-win it.
            target_set = current_set
            if self.main_state.get_game(team, target_set) == 0 and target_set > 1:
                target_set -= 1

            current_score = self.main_state.get_game(team, target_set)
            if current_score > 0:
                rival_score = self.main_state.get_game(rival_team, target_set)
                game_limit = points_limit_last_set if target_set == sets_limit else points_limit
                was_a_win = self._is_winning_score(current_score, rival_score, game_limit)

                self.main_state.set_game(target_set, team, current_score - 1)
                new_score = current_score - 1

                is_still_a_win = self._is_winning_score(new_score, rival_score, game_limit)

                if was_a_win and not is_still_a_win:
                    logger.debug("Team %s 'un-won' set %s due to undo.", team, target_set)
                    self.add_set(team, undo=True)
                    return True
        else:
            current_score = self.main_state.get_game(team, current_set)
            rival_score = self.main_state.get_game(rival_team, current_set)
            game_limit = points_limit_last_set if current_set == sets_limit else points_limit

            self.main_state.set_game(current_set, team, current_score + 1)
            current_score += 1

            if self._is_winning_score(current_score, rival_score, game_limit):
                logger.debug("Team %s won set %s", team, current_set)
                self.add_set(team, undo)
                return True
        return False

    def add_set(self, team: int, undo: bool):
        """Adds or removes a set to a team."""
        logger.debug("Adding set for team %s, undo: %s", team, undo)
        if not undo and self.match_finished():
            logger.debug("Match finished, not adding set.")
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
        logger.debug("Checking if match is finished")
        t1_sets = self.main_state.get_sets(1)
        t2_sets = self.main_state.get_sets(2)
        limit = self.conf.sets
        soft_limit = int(limit / 2) + 1
        if t1_sets >= soft_limit or t2_sets >= soft_limit:
            logger.debug("Match finished. Score: %s-%s, required: %s", t1_sets, t2_sets, soft_limit)
            return True
        logger.debug("Match not finished. Score: %s-%s, required: %s", t1_sets, t2_sets, soft_limit)
        return False

    def check_set_won(self, team: int, current_set: int, points_limit: int, points_limit_last_set: int, sets_limit: int) -> bool:
        """Checks if a team has won the current set after a direct score update."""
        logger.debug("Checking if team %s won set %s", team, current_set)
        current_score = self.main_state.get_game(team, current_set)
        rival_team = 2 if team == 1 else 1
        rival_score = self.main_state.get_game(rival_team, current_set)
        game_limit = points_limit_last_set if current_set == sets_limit else points_limit

        if self._is_winning_score(current_score, rival_score, game_limit):
            logger.debug("Team %s won set %s", team, current_set)
            self.add_set(team, False)
            return True
        return False
