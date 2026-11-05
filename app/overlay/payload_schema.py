"""The overlay state contract: what OBS browser sources receive.

Every overlay template's JavaScript (``overlay_static/js``) consumes one JSON
document, pushed over ``/ws/{public_token}``: the overlay's merged render
state. Before this module that shape existed only implicitly, as whatever
:func:`app.overlay_payload.build_overlay_payload` and the state store's
deep-merge happened to produce, so a renamed key or a dead flag could only be
found by reading both sides.

This module makes the contract explicit:

* :class:`OverlayPayload` describes one broadcast payload. Its sections
  forbid unknown keys, so ``tests/test_overlay_payload_contract.py`` fails
  the moment the builder emits a field the contract does not name (or stops
  emitting one it requires).
* :class:`OverlayState` is what a client actually receives: the payload
  sections plus the ``raw_remote_customization`` pass-through the templates
  read for locale and appearance.
* :func:`public_overlay_state` projects the store's merged state onto that
  contract before it is sent. The store also keeps server-side bookkeeping
  in the same document — ``_meta.overlay_id`` (the owner's
  ``"<user_id>:<oid>"`` storage key) and ``raw_remote_model`` — which no
  template reads and which must not reach anyone holding the public URL.
* ``scripts/generate_overlay_schema.py`` writes the JSON Schema to
  ``overlay_static/schema/overlay-state.schema.json`` and TypeScript types
  for template authors; a test keeps the committed copy in sync.

The JSON-Schema shape is intentionally the *documented* contract. At runtime
the projection is lenient (top-level allowlist only) so a state row written
by an older release — which may still carry keys a later payload no longer
emits, because the store deep-merges — never fails a broadcast.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MatchInfo(_Strict):
    tournament: str = Field(description="Competition name (placeholder until match metadata exists)")
    phase: str = Field(description="Competition round (placeholder until match metadata exists)")
    best_of_sets: int = Field(description="Sets in the match (3 = best of 3, …)")
    current_set: int = Field(description="1-based set being played")
    mode: str = Field(description="Rules preset: indoor, beach, table_tennis, …")
    points_limit: int
    points_limit_last_set: int
    match_started_at: float | None = Field(description="Unix seconds the match clock started")
    match_finished_at: float | None = Field(description="Unix seconds the match ended")
    server_time: float = Field(description="Server clock at send time, for client clock-skew correction")
    match_finished: bool
    show_set_summary: bool = Field(description="Set-summary recap is on air")
    set_summary_style: str
    sides_swapped: bool = Field(description="Teams render mirrored (manual XOR auto side switch)")
    summary_set_num: int = Field(description="Set the recap describes")
    show_only_current_set: bool | None = Field(
        default=None, description="Simple mode: render only the current set"
    )


class TeamPayload(_Strict):
    name: str
    short_name: str
    color_primary: str
    color_secondary: str
    logo_url: str
    sets_won: int
    points: int = Field(description="Points in the current set")
    serving: bool
    timeouts_taken: int = Field(description="Timeouts in the current set")
    timeouts_by_set: dict[str, int] = Field(description='Per-set timeouts, keyed "set_1" … "set_7"')
    set_history: dict[str, int] = Field(description='Per-set points, keyed "set_1" … "set_7"')


class Geometry(_Strict):
    width: float
    height: float
    xpos: float
    ypos: float
    scale: float
    margin: float
    anchor: str


class Colors(_Strict):
    set_bg: str
    set_text: str
    game_bg: str
    game_text: str


class MatchPointInfo(_Strict):
    team_1_set_point: bool
    team_2_set_point: bool
    team_1_match_point: bool
    team_2_match_point: bool


class BeachSideSwitch(_Strict):
    interval: int
    points_in_set: int
    next_switch_at: int
    points_until_switch: int
    is_switch_pending: bool


class Streak(_Strict):
    team: int | None
    n: int
    set: int | None


class Comeback(_Strict):
    deficit: int
    set: int | None


class ServiceCount(_Strict):
    served: int
    won: int


class LiveStats(_Strict):
    """Match statistics derived from the audit log (``app/api/live_stats.py``).

    Team- and set-keyed maps use string keys (``"1"``, ``"2"``) because the
    document travels as JSON.
    """

    current_streak: Streak
    longest_streak: Streak
    partial_comeback: dict[str, Comeback]
    set_win_comeback: dict[str, Comeback]
    total_points: int
    set_durations: dict[str, float | int | None]
    services: dict[str, ServiceCount]
    longest_streak_by_set: dict[str, dict[str, int]]
    services_by_set: dict[str, dict[str, ServiceCount]]
    point_types: dict[str, dict[str, int]]
    error_types: dict[str, dict[str, int]]
    point_types_by_set: dict[str, dict[str, dict[str, int]]]
    last_point: dict[str, Any] | None


class OverlayControl(_Strict):
    show_main_scoreboard: bool | None = Field(
        default=None, description="Scoreboard visible (absent until visibility was toggled)"
    )
    alerts_visual: bool | None = Field(
        default=None, description="Style-preview pages only: suppress alert animations"
    )
    show_bottom_ticker: bool
    ticker_message: str
    show_player_stats: bool
    player_stats_data: dict[str, Any] | None
    geometry: Geometry
    colors: Colors
    preferredStyle: str | None = Field(description="Template the overlay URL serves")
    show_logos: bool
    show_stats: bool
    show_points_history: bool
    match_point_info: MatchPointInfo | None = None
    beach_side_switch: BeachSideSwitch | None = None
    stats: LiveStats | None = Field(
        default=None, description="Live match statistics derived from the audit log"
    )
    points_history: list[dict[str, Any]] | None = None
    points_by_set: dict[str, list[dict[str, Any]]] | None = None
    timeouts_by_set: dict[str, list[dict[str, Any]]] | None = None


class OverlayPayload(_Strict):
    """One broadcast payload, exactly as the builder emits it."""

    match_info: MatchInfo
    team_home: TeamPayload
    team_away: TeamPayload
    overlay_control: OverlayControl


class OverlayState(OverlayPayload):
    """What an overlay client receives over ``/ws/{public_token}``."""

    raw_remote_customization: dict[str, Any] = Field(
        default_factory=dict,
        description="Operator customization (team names/colors/logos, locale, style options) as saved",
    )


#: Top-level keys a client may receive. Everything else in the stored state
#: is server-side bookkeeping.
PUBLIC_KEYS: frozenset[str] = frozenset(OverlayState.model_fields)


def public_overlay_state(state: dict[str, Any]) -> dict[str, Any]:
    """Project the store's merged *state* onto the public contract.

    Also stamps ``match_info.server_time`` with the clock at send time. The
    stored value is whatever the last broadcast carried — hours old for an
    OBS source that reconnects to an idle overlay — and clients derive their
    clock skew from it, so a stale value would throw every on-air timer off
    until the next point.
    """
    out = {key: value for key, value in state.items() if key in PUBLIC_KEYS}
    match_info = out.get("match_info")
    if isinstance(match_info, dict):
        out["match_info"] = {**match_info, "server_time": time.time()}
        # A beach side-switch countdown only means something in beach mode.
        # Releases before 7.5.1 omitted the key outside beach instead of
        # sending null, and the store's deep-merge kept the last beach value
        # ("Switch in 5") in the stored state; clear it here so such a state
        # is right from the very first frame, before any new push.
        control = out.get("overlay_control")
        if (
            match_info.get("mode") != "beach"
            and isinstance(control, dict)
            and control.get("beach_side_switch") is not None
        ):
            out["overlay_control"] = {**control, "beach_side_switch": None}
    return out
