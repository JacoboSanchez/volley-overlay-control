from pydantic import BaseModel, Field
from typing import Literal, Optional


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class InitRequest(BaseModel):
    oid: str
    output_url: Optional[str] = None
    points_limit: Optional[int] = None
    points_limit_last_set: Optional[int] = None
    sets_limit: Optional[int] = None


class TeamActionRequest(BaseModel):
    team: Literal[1, 2]
    undo: bool = False


class SetScoreRequest(BaseModel):
    team: Literal[1, 2]
    set_number: int = Field(ge=1, le=5)
    value: int = Field(ge=0)


class SetSetsRequest(BaseModel):
    team: Literal[1, 2]
    value: int = Field(ge=0)


class ServeRequest(BaseModel):
    team: Literal[1, 2]


class VisibilityRequest(BaseModel):
    visible: bool


class SimpleModeRequest(BaseModel):
    enabled: bool


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class TeamState(BaseModel):
    sets: int
    timeouts: int
    scores: dict  # {"set_1": 5, "set_2": 12, ...}
    serving: bool


class GameStateResponse(BaseModel):
    current_set: int
    visible: bool
    simple_mode: bool
    match_finished: bool
    team_1: TeamState
    team_2: TeamState
    serve: str
    config: dict  # points_limit, sets_limit, etc.


class ActionResponse(BaseModel):
    success: bool
    state: Optional[GameStateResponse] = None
    message: Optional[str] = None
