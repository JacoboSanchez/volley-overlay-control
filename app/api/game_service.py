import logging
from app.api.schemas import GameStateResponse, TeamState, ActionResponse
from app.api.ws_hub import WSHub
from app.state import State

logger = logging.getLogger("GameService")


class MatchFinishedError(Exception):
    """Raised when an action is blocked because the match is already over."""
    pass


class GameService:
    """Stateless service that operates on GameSession instances.

    Both the NiceGUI frontend and the REST API call these methods, ensuring
    a single code path for all game mutations.
    """

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    @staticmethod
    def get_state(session) -> GameStateResponse:
        """Build a ``GameStateResponse`` from the current session state."""
        state = session.game_manager.get_current_state()
        serve = state.get_current_serve()

        def team_state(team):
            scores = {}
            for i in range(1, session.sets_limit + 1):
                scores[f"set_{i}"] = state.get_game(team, i)
            return TeamState(
                sets=state.get_sets(team),
                timeouts=state.get_timeout(team),
                scores=scores,
                serving=(serve == State.SERVE_1 if team == 1 else serve == State.SERVE_2),
            )

        return GameStateResponse(
            current_set=session.current_set,
            visible=session.visible,
            simple_mode=session.simple,
            match_finished=session.game_manager.match_finished(),
            team_1=team_state(1),
            team_2=team_state(2),
            serve=serve,
            config={
                "points_limit": session.points_limit,
                "points_limit_last_set": session.points_limit_last_set,
                "sets_limit": session.sets_limit,
            },
        )

    @staticmethod
    def get_customization(session) -> dict:
        return session.customization.get_model()

    # ------------------------------------------------------------------
    # State mutations
    # ------------------------------------------------------------------

    @staticmethod
    def add_point(session, team: int, undo: bool = False) -> ActionResponse:
        if not undo and session.game_manager.match_finished():
            return ActionResponse(
                success=False,
                state=GameService.get_state(session),
                message="Match is already finished.",
            )

        set_won = session.game_manager.add_game(
            team, session.current_set,
            session.points_limit, session.points_limit_last_set,
            session.sets_limit, undo,
        )

        if undo and session.undo:
            session.undo = False

        if set_won and not session.game_manager.match_finished():
            session.current_set = session._compute_current_set()

        GameService._save_and_broadcast(session)
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def add_set(session, team: int, undo: bool = False) -> ActionResponse:
        if not undo and session.game_manager.match_finished():
            return ActionResponse(
                success=False,
                state=GameService.get_state(session),
                message="Match is already finished.",
            )

        session.game_manager.add_set(team, undo)

        if undo and session.undo:
            session.undo = False

        session.current_set = session._compute_current_set()
        GameService._save_and_broadcast(session)
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def add_timeout(session, team: int, undo: bool = False) -> ActionResponse:
        session.game_manager.add_timeout(team, undo)

        if undo and session.undo:
            session.undo = False

        GameService._save_and_broadcast(session)
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def change_serve(session, team: int) -> ActionResponse:
        session.game_manager.change_serve(team)
        GameService._save_and_broadcast(session)
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def set_score(session, team: int, set_number: int, value: int) -> ActionResponse:
        session.game_manager.set_game_value(team, value, set_number)
        set_won = session.game_manager.check_set_won(
            team, set_number,
            session.points_limit, session.points_limit_last_set,
            session.sets_limit,
        )
        if set_won and not session.game_manager.match_finished():
            session.current_set = session._compute_current_set()
        GameService._save_and_broadcast(session)
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def set_sets_value(session, team: int, value: int) -> ActionResponse:
        session.game_manager.set_sets_value(team, value)
        session.current_set = session._compute_current_set()
        GameService._save_and_broadcast(session)
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def reset(session) -> ActionResponse:
        session.game_manager.reset()
        session.current_set = session._compute_current_set()
        GameService._save_and_broadcast(session)
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def set_visibility(session, visible: bool) -> ActionResponse:
        session.visible = visible
        session.backend.change_overlay_visibility(visible)
        GameService._broadcast(session)
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def set_simple_mode(session, enabled: bool) -> ActionResponse:
        session.simple = enabled
        if enabled:
            session.backend.reduce_games_to_one()
        GameService._save_and_broadcast(session)
        return ActionResponse(success=True, state=GameService.get_state(session))

    @staticmethod
    def update_customization(session, data: dict) -> ActionResponse:
        session.customization.set_model(data)
        session.backend.save_json_customization(data)
        GameService._broadcast(session)
        return ActionResponse(success=True, state=GameService.get_state(session))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _save_and_broadcast(session):
        """Persist state to the overlay backend and notify WS clients."""
        session.game_manager.save(session.simple, session.current_set)
        GameService._broadcast(session)

    @staticmethod
    def _broadcast(session):
        """Notify all WebSocket frontend clients about the new state."""
        state_data = GameService.get_state(session).model_dump()
        WSHub.broadcast_sync(session.oid, state_data)
