import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.oid_validation import OID_PATTERN

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class InitRequest(BaseModel):
    oid: str = Field(min_length=1, max_length=200)
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


# Per-point classification vocabulary (optional, opt-in scouting tags).
# ``POINT_TYPES`` / ``ERROR_TYPES`` are the single source of truth; the
# frontend mirrors them in ``frontend/src/api/client.ts`` and the match
# report / live stats aggregate against them. Keep the tuples and the
# ``Literal`` aliases below in sync.
POINT_TYPES = ("ace", "kill", "block", "opp_error")
PointType = Literal["ace", "kill", "block", "opp_error"]

ERROR_TYPES = (
    "serve_error",
    "attack_error",
    "reception_error",
    "ball_handling",
    "net_fault",
    "position_fault",
    "other",
)
ErrorType = Literal[
    "serve_error",
    "attack_error",
    "reception_error",
    "ball_handling",
    "net_fault",
    "position_fault",
    "other",
]


class AddPointRequest(TeamActionRequest):
    """Body for ``POST /api/v1/game/add-point``.

    Extends the shared team-action body with optional scouting tags.
    ``point_type`` classifies how the rally was won; ``error_type``
    sub-classifies an opponent error and is only valid when
    ``point_type == "opp_error"``. Both are ignored on undo and may be
    omitted entirely to record an untyped point exactly as before.
    """
    point_type: PointType | None = None
    error_type: ErrorType | None = None

    @model_validator(mode="after")
    def _error_type_requires_opp_error(self) -> "AddPointRequest":
        if self.error_type is not None and self.point_type != "opp_error":
            raise ValueError(
                "error_type is only valid when point_type == 'opp_error'."
            )
        return self


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
    "ledger_diff",
    "bumper",
)
SetSummaryStyle = Literal[
    "brand_ledger",
    "bento",
    "glass",
    "brand_columns",
    "ledger_diff",
    "bumper",
]


class SetSummaryRequest(BaseModel):
    enabled: bool


class SwapSidesRequest(BaseModel):
    """Set the *effective* display orientation (True = team 2 left)."""
    swapped: bool


class AutoSwapSidesRequest(BaseModel):
    enabled: bool


class SetSummaryStyleRequest(BaseModel):
    style: SetSummaryStyle


class SetRulesRequest(BaseModel):
    """Body for ``POST /api/v1/session/rules``.

    All fields are optional. ``mode`` switches between ``"indoor"``,
    ``"beach"`` and ``"table_tennis"``; ``reset_to_defaults`` replaces
    every limit with the canonical preset for the resulting mode
    (per-field overrides in the same call still win).
    """
    mode: Literal["indoor", "beach", "table_tennis"] | None = None
    points_limit: int | None = Field(default=None, ge=1, le=99)
    points_limit_last_set: int | None = Field(default=None, ge=1, le=99)
    sets_limit: int | None = Field(default=None, ge=1, le=7)
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
    # Output-wide zoom (%) and symmetric outer margin (% of canvas) for
    # the built-in overlay engine. Applied as a global transform by app.js.
    'Scale', 'Margin',
    # Placement anchor: 'free' (legacy absolute xpos/ypos) or one of the
    # nine zone values ('top-left' … 'bottom-right'). In zone mode app.js
    # pins the matching corner/edge against the box's measured size and
    # treats Left-Right/Up-Down as a fine nudge (% of canvas).
    'Anchor',
    'preferredStyle',
    # Overlay surface theme: '' (per-style default), 'dark' or 'light'.
    # Applied by app.js as a body class on styles that define the
    # matching palette; a ``?theme=`` URL override takes precedence.
    'overlayTheme',
    # Vertical anchor for edge-pinned styles (pylons/corners): 'top',
    # 'bottom' or 'center' (any other string, including the legacy '',
    # also renders centred; an absent key defaults to top). Applied by
    # app.js as a ``data-vertical-anchor`` attribute; an ``?anchor=``
    # URL override takes precedence.
    'verticalAnchor',
    # Operator UI locale, broadcast to OBS-embedded overlays (whose URL
    # is fixed in the streaming app and cannot carry ``?lang=``).
    'locale',
}

# Per-value bounds for ``PUT /customization``. Logos can hold base64
# data URLs so they get a much larger budget than the rest. Everything
# else maps to a short label or a numeric position, so 256 chars is
# generous and keeps a malicious operator from stuffing megabyte
# strings into the broadcast state.
LOGO_KEYS = frozenset({'Team 1 Logo', 'Team 2 Logo'})

# Accepted values for the ``Anchor`` placement field. ``free`` is the
# legacy absolute-coordinate mode; the nine zone values pin the overlay
# to a screen zone. ``update_customization`` rejects anything else so a
# bad value can never reach the broadcast state (the overlay client also
# treats unknown anchors as ``free``, but we validate up front).
VALID_ANCHORS = frozenset({
    'free',
    'top-left', 'top-center', 'top-right',
    'middle-left', 'middle-center', 'middle-right',
    'bottom-left', 'bottom-center', 'bottom-right',
})

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

    Same-origin absolute paths (``/media/icons/x.webp``, the
    ``/static/...`` default logo) are accepted too — the hosted icon
    library stores icons as origin-relative URLs so they work behind
    any hostname. The second-character guard is load-bearing: ``//host``
    is protocol-relative (handled above), and ``/\\evil.com`` would be
    normalized to ``https://evil.com/`` by WHATWG URL parsers, so a
    backslash in position two is rejected outright.
    """
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if not candidate:
        return False
    if len(candidate) > MAX_LOGO_VALUE_LENGTH:
        return False
    if candidate.startswith("/") and not candidate.startswith(("//", "/\\")):
        return True
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    lowered = candidate.lower()
    return lowered.startswith(ALLOWED_LOGO_PREFIXES)


# Explicit-scheme detector for the catalog icon validator: matches
# ``scheme:`` per RFC 3986 (letter, then letters/digits/+/-/.).
_EXPLICIT_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def is_acceptable_catalog_icon(value: object) -> bool:
    """Permissive gate for team-catalog ``icon`` writes.

    The catalog historically accepted any string (only a length cap),
    so plenty of stored values are scheme-less (``foo.png``) and an
    unrelated PATCH must not start rejecting them — the team editors
    always resend the full field set. This validator therefore only
    refuses values that are *positively* dangerous in an ``<img src>``:

    * an explicit scheme outside http/https/data:image (``javascript:``,
      ``vbscript:``, ``data:text/html`` …),
    * ``/\\`` and ``\\\\`` prefixes — WHATWG backslash normalization
      turns both into protocol-relative URLs that leave the origin, and
      a UNC path in an ``<img>`` can leak NTLM hashes on Windows.

    Everything scheme-less, same-origin, or allowlisted passes. The
    strict :func:`is_safe_logo_url` still guards the customization PUT
    (the path every value crosses before reaching an overlay).
    """
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if not candidate:
        return True
    if candidate.startswith(("/\\", "\\\\")):
        return False
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    if _EXPLICIT_SCHEME_RE.match(candidate):
        return candidate.lower().startswith(ALLOWED_LOGO_PREFIXES)
    return True


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class TeamState(BaseModel):
    sets: int
    timeouts: int  # Current-set timeouts (kept for backwards compat).
    # Per-set timeout history keyed by ``"set_N"`` so an operator-side
    # undo across set boundaries can surface the prior set's count.
    timeouts_by_set: dict = {}
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


class ServeSwitch(BaseModel):
    """Table-tennis serve-rotation indicator (only set when
    mode='table_tennis').

    The serve alternates every 2 points, then every point once both
    players reach 10 (deuce). ``server`` is the team (1 or 2) currently
    on serve; ``is_change_pending`` is true the moment a point handed
    the serve over — so the control UI can flash a "serve changes now"
    pill — and ``points_until_change`` counts down to the next handover.
    """
    server: int
    points_in_set: int
    next_change_at: int
    points_until_change: int
    is_change_pending: bool


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
    # Table-tennis serve-rotation indicator (None for volleyball modes,
    # where serve follows the rally winner). Drives the serve-change
    # countdown chip in the control UI.
    serve_switch: ServeSwitch | None = None
    match_point_info: MatchPointInfo | None = None
    # Display-side swap: the orientation every live view should render
    # right now (True = team 2 on the left), plus the auto-swap
    # setting so the config UI can show its toggle state. Presentation
    # only — team_1/team_2 identity in this response never changes.
    sides_swapped: bool = False
    auto_swap_sides: bool = False
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
    # Number of live output clients (OBS browser sources + spectator
    # pages) currently connected to this overlay's public broadcast.
    # Lets the control board show an "on-air" indicator so the operator
    # can confirm the scoreboard is actually reaching OBS/viewers.
    obs_clients: int = 0
    # ``match_id`` of the report archived for the just-finished match,
    # populated only while ``match_finished`` is true so the control
    # board can offer a "View match report" link. ``None`` mid-match.
    last_match_id: str | None = None


class ActionResponse(BaseModel):
    success: bool
    state: GameStateResponse | None = None
    message: str | None = None


class AppConfigResponse(BaseModel):
    title: str
    # Minutes a single set may be live before the control-UI abandoned-
    # match prompt fires (0 disables). Sourced from the
    # ``STALE_SET_THRESHOLD_MINUTES`` env var; defaults to 60.
    stale_set_threshold_minutes: int = 60
