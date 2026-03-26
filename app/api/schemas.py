from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
import re


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class InitRequest(BaseModel):
    oid: str = Field(min_length=1, max_length=200)
    output_url: Optional[str] = None
    points_limit: Optional[int] = None
    points_limit_last_set: Optional[int] = None
    sets_limit: Optional[int] = None

    @field_validator('oid')
    @classmethod
    def validate_oid(cls, v):
        if not re.match(r'^[A-Za-z0-9_\-]+$', v):
            raise ValueError('OID must contain only alphanumeric characters, hyphens, and underscores')
        return v


class TeamActionRequest(BaseModel):
    team: Literal[1, 2]
    undo: bool = False


class SetScoreRequest(BaseModel):
    team: Literal[1, 2]
    set_number: int = Field(ge=1)
    value: int = Field(ge=0, le=99)


class SetSetsRequest(BaseModel):
    team: Literal[1, 2]
    value: int = Field(ge=0, le=9)


class ServeRequest(BaseModel):
    team: Literal[1, 2]


class VisibilityRequest(BaseModel):
    visible: bool


class SimpleModeRequest(BaseModel):
    enabled: bool


# ---------------------------------------------------------------------------
# Customization validation
# ---------------------------------------------------------------------------

# Allowed keys for customization updates
ALLOWED_CUSTOMIZATION_KEYS = {
    'Team 1 Name', 'Team 1 Text Name', 'Team 1 Color', 'Team 1 Text Color', 'Team 1 Logo',
    'Team 2 Name', 'Team 2 Text Name', 'Team 2 Color', 'Team 2 Text Color', 'Team 2 Logo',
    'Color 1', 'Color 2', 'Text Color 1', 'Text Color 2',
    'Logos', 'Gradient',
    'Height', 'Width', 'Left-Right', 'Up-Down',
    'preferredStyle',
}


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
