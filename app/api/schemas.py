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


# Set summary overlay — list of supported visual styles (mirrored in the
# frontend `SET_SUMMARY_STYLES` constant and the runtime overlay CSS).
SET_SUMMARY_STYLE_CHOICES = (
    "brand_ledger",
    "bento",
    "glass",
    "brand_columns",
    "podium",
    "bumper",
)
SetSummaryStyle = Literal[
    "brand_ledger",
    "bento",
    "glass",
    "brand_columns",
    "podium",
    "bumper",
]


class SetSummaryRequest(BaseModel):
    enabled: bool


class SetSummaryStyleRequest(BaseModel):
    style: SetSummaryStyle


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
    # Operator-chosen locale propagated through the overlay's
    # ``raw_remote_customization`` so OBS-embedded overlays (whose URL
    # is fixed in the streaming app and cannot carry ``?lang=``) pick
    # up the operator's language change live.
    'locale',
}

# Locale codes the set-summary overlay knows how to render. Keep in
# sync with the LABELS dictionaries in ``overlay_static/js/set_summary.js``
# and with ``_resolve_overlay_locale`` in ``app/overlay/routes.py``.
SUPPORTED_OVERLAY_LOCALES = frozenset({'en', 'es', 'pt', 'it', 'fr', 'de'})

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
    # Wall-clock seconds at which the match transitioned to finished,
    # or ``None`` while the match is still in progress (or pending).
    # Lets clients freeze the match timer at the actual end-of-match
    # value instead of letting it keep ticking after match end.
    # Cleared on reset and on ``start_match``.
    match_finished_at: float | None = None
    # Wall-clock seconds at the first scoring event recorded in the
    # operator's current set, or ``None`` when no rally has been
    # played in this set yet. The React control UI uses this to
    # detect "abandoned" sessions on page load — if the current set
    # has been live for more than an hour the operator probably left
    # the scoreboard running by mistake and gets prompted to reset.
    current_set_started_at: float | None = None
    # Set summary overlay (panel that replaces the scoreboard between
    # sets with a chart + key stats). ``set_summary`` is the operator
    # toggle. ``set_summary_set_num`` is the resolved set the panel
    # shows — current_set when it has points, otherwise the previous
    # set so the operator can show a recap immediately after a set
    # ends. ``set_summary_style`` is the visual variant.
    set_summary: bool = False
    set_summary_set_num: int | None = None
    set_summary_style: str = "brand_ledger"
    # Server wall-clock at the moment this response was composed.
    # Lets clients derive a skew offset against their own ``Date.now()``
    # so every live-tick calculation (match elapsed, set duration,
    # stale-set "abandoned match" check) tracks the server even when
    # the client's system clock is wrong.
    server_time: float | None = None


class ActionResponse(BaseModel):
    success: bool
    state: GameStateResponse | None = None
    message: str | None = None


class AppConfigResponse(BaseModel):
    title: str
