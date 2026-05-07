from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.api.oid_validation import OID_PATTERN

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class InitRequest(BaseModel):
    oid: str = Field(min_length=1, max_length=200)
    output_url: str | None = None
    points_limit: int | None = None
    points_limit_last_set: int | None = None
    sets_limit: int | None = None

    @field_validator('oid')
    @classmethod
    def validate_oid(cls, v):
        if not OID_PATTERN.match(v):
            raise ValueError(
                'OID must contain only alphanumeric characters, hyphens, '
                'underscores, slashes, and dots. ".." is not allowed.'
            )
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


class SetRulesRequest(BaseModel):
    """Body for ``POST /api/v1/session/rules``.

    All fields are optional. ``mode`` switches between ``"indoor"``
    and ``"beach"``; ``reset_to_defaults`` replaces every limit with
    the canonical preset for the resulting mode (per-field overrides
    in the same call still win).
    """
    mode: Literal["indoor", "beach"] | None = None
    points_limit: int | None = Field(default=None, ge=1, le=99)
    points_limit_last_set: int | None = Field(default=None, ge=1, le=99)
    sets_limit: int | None = Field(default=None, ge=1, le=5)
    reset_to_defaults: bool = False


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

# Per-value bounds for ``PUT /customization``. Logos can hold base64
# data URLs so they get a much larger budget than the rest. Everything
# else maps to a short label or a numeric position, so 256 chars is
# generous and keeps a malicious operator from stuffing megabyte
# strings into the broadcast state.
LOGO_KEYS = frozenset({'Team 1 Logo', 'Team 2 Logo'})
MAX_LOGO_VALUE_LENGTH = 8192
MAX_STRING_VALUE_LENGTH = 256
MAX_CUSTOMIZATION_KEYS = 64

# Logo URL schemes accepted by the customization endpoint. Any other
# scheme (``javascript:``, ``vbscript:``, ``data:text/html`` …) is
# rejected so a compromised client cannot plant XSS payloads via a
# logo string that downstream surfaces (match report, /links preview,
# overlay templates) interpolate into ``<img src=…>``.
ALLOWED_LOGO_PREFIXES = (
    "http://",
    "https://",
    "data:image/",
)


def is_safe_logo_url(value: object) -> bool:
    """Return True iff *value* is a non-empty string with an allowed scheme.

    Protocol-relative URLs (``//cdn.example.com/logo.png``) are accepted
    because :func:`app.customization.Customization.fix_icon` rewrites
    them to ``https://`` before they are persisted.
    """
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if not candidate:
        return False
    if len(candidate) > MAX_LOGO_VALUE_LENGTH:
        return False
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    lowered = candidate.lower()
    return lowered.startswith(ALLOWED_LOGO_PREFIXES)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class TeamState(BaseModel):
    sets: int
    timeouts: int
    scores: dict  # {"set_1": 5, "set_2": 12, ...}
    serving: bool


class BeachSideSwitch(BaseModel):
    """Beach volleyball side-switch indicator (only set when mode='beach').

    Sides switch every 7 combined points in non-tiebreak sets and
    every 5 in the tiebreak. ``is_switch_pending`` is true the moment
    a point crosses a boundary — operators should swap teams now.
    """
    interval: int
    points_in_set: int
    next_switch_at: int
    points_until_switch: int
    is_switch_pending: bool


class MatchPointInfo(BaseModel):
    """Per-team flags signalling that the next point would close out the
    current set or the entire match.

    Match point implies set point. The renderer is expected to show only
    the more specific label (match point) when both apply. All flags
    collapse to ``False`` once ``match_finished`` is true.
    """
    team_1_set_point: bool
    team_2_set_point: bool
    team_1_match_point: bool
    team_2_match_point: bool


class GameStateResponse(BaseModel):
    current_set: int
    visible: bool
    simple_mode: bool
    match_finished: bool
    team_1: TeamState
    team_2: TeamState
    serve: str
    config: dict  # points_limit, sets_limit, mode, etc.
    beach_side_switch: BeachSideSwitch | None = None
    match_point_info: MatchPointInfo | None = None
    # True when the audit log has at least one pending undoable
    # forward record (any of add_point/add_set/add_timeout). Lets
    # frontends drive the global Undo button from the server-side
    # stack instead of maintaining their own LIFO.
    can_undo: bool = False
    # Wall-clock seconds at which the current match started, or
    # ``None`` when the match hasn't begun yet. Drives the live
    # match timer in the HUD and toggles the Start-match / Reset
    # button in the control bar.
    match_started_at: float | None = None


class ActionResponse(BaseModel):
    success: bool
    state: GameStateResponse | None = None
    message: str | None = None


class AppConfigResponse(BaseModel):
    title: str
