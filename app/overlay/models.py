"""Pydantic request models for the overlay server endpoints.

Split out of :mod:`app.overlay.routes` — same contract as the original
standalone overlay server.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict


class TeamStateModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str | None = None
    short_name: str | None = None
    color_primary: str | None = None
    color_secondary: str | None = None
    logo_url: str | None = None
    sets_won: int | None = None
    points: int | None = None
    serving: bool | None = None
    timeouts_taken: int | None = None
    set_history: dict[str, int] | None = None


class MatchInfoModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    tournament: str | None = None
    phase: str | None = None
    best_of_sets: int | None = None
    current_set: int | None = None
    show_only_current_set: bool | None = None


class OverlayControlModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    show_main_scoreboard: bool | None = None
    show_bottom_ticker: bool | None = None
    ticker_message: str | None = None
    show_player_stats: bool | None = None
    player_stats_data: Any | None = None
    geometry: dict[str, Any] | None = None
    colors: dict[str, str] | None = None
    preferredStyle: str | None = None


class OverlayStateUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")
    match_info: MatchInfoModel | None = None
    team_home: TeamStateModel | None = None
    team_away: TeamStateModel | None = None
    overlay_control: OverlayControlModel | None = None
    raw_remote_model: Any | None = None
    raw_remote_customization: Any | None = None


class RawConfigPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: Any | None = None
    customization: Any | None = None
