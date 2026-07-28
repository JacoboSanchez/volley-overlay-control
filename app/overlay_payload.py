"""Construction of the wire payload consumed by overlays and spectators."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from app.customization import Customization
from app.state import State


def _rule_context(
    conf: Any,
    getter: Callable[[], dict] | None,
    logger: logging.Logger,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "mode": "indoor",
        "points_limit": int(conf.points),
        "points_limit_last_set": int(conf.points_last_set),
        "sets_limit": int(conf.sets),
        "match_finished": False,
        "match_started_at": None,
        "match_finished_at": None,
        "set_summary": False,
        "set_summary_style": "brand_ledger",
        "sides_swapped_manual": False,
        "auto_swap_sides": False,
    }
    if not callable(getter):
        return context
    try:
        overrides = getter() or {}
    except Exception:  # pragma: no cover - defensive
        logger.exception("Rule overrides getter raised")
        return context

    context.update(
        mode=str(overrides.get("mode", context["mode"])),
        points_limit=int(
            overrides.get("points_limit", context["points_limit"])
        ),
        points_limit_last_set=int(
            overrides.get(
                "points_limit_last_set",
                context["points_limit_last_set"],
            )
        ),
        sets_limit=int(overrides.get("sets_limit", context["sets_limit"])),
        match_finished=bool(overrides.get("match_finished", False)),
        set_summary=bool(overrides.get("set_summary", False)),
        sides_swapped_manual=bool(
            overrides.get("sides_swapped_manual", False)
        ),
        auto_swap_sides=bool(overrides.get("auto_swap_sides", False)),
    )
    for key in ("match_started_at", "match_finished_at"):
        value = overrides.get(key)
        if isinstance(value, (int, float)):
            context[key] = float(value)
    style = overrides.get("set_summary_style")
    if isinstance(style, str) and style:
        context["set_summary_style"] = style
    return context


def _set_history(current_model: dict, team: int) -> dict[str, int]:
    return {
        f"set_{index}": int(
            current_model.get(f"Team {team} Game {index} Score", 0)
        )
        for index in range(1, 8)
    }


def _team_payload(
    current_model: dict,
    customization: Customization,
    team: int,
    current_set: int,
) -> dict[str, Any]:
    home = team == 1
    name = customization.get_team_name(team)
    return {
        "name": name,
        "short_name": name[:3].upper() if name else ("HOM" if home else "AWA"),
        "color_primary": customization.get_team_color(team),
        "color_secondary": customization.get_team_text_color(team),
        "logo_url": customization.get_team_logo(team),
        "sets_won": int(
            current_model.get(State.T1SETS_INT if home else State.T2SETS_INT, 0)
        ),
        "points": int(
            current_model.get(f"Team {team} Game {current_set} Score", 0)
        ),
        "serving": current_model.get(State.SERVE)
        == (State.SERVE_1 if home else State.SERVE_2),
        "timeouts_taken": int(
            current_model.get(
                State.T1TIMEOUTS_INT if home else State.T2TIMEOUTS_INT,
                0,
            )
        ),
        "set_history": _set_history(current_model, team),
    }


def _add_rule_indicators(
    payload: dict,
    current_model: dict,
    rules: dict[str, Any],
    current_set: int,
    logger: logging.Logger,
) -> None:
    try:
        from app.api.match_rules import (
            compute_match_point_info,
            compute_side_switch,
            compute_sides_swapped_auto,
        )

        team1_score = int(
            current_model.get(f"Team 1 Game {current_set} Score", 0)
        )
        team2_score = int(
            current_model.get(f"Team 2 Game {current_set} Score", 0)
        )
        team1_sets = int(current_model.get(State.T1SETS_INT, 0))
        team2_sets = int(current_model.get(State.T2SETS_INT, 0))
        control = payload["overlay_control"]
        control["match_point_info"] = compute_match_point_info(
            current_set=current_set,
            sets_limit=rules["sets_limit"],
            team1_sets=team1_sets,
            team2_sets=team2_sets,
            team1_score=team1_score,
            team2_score=team2_score,
            points_limit=rules["points_limit"],
            points_limit_last_set=rules["points_limit_last_set"],
            match_finished=rules["match_finished"],
        )
        side_switch = compute_side_switch(
            mode=rules["mode"],
            current_set=current_set,
            sets_limit=rules["sets_limit"],
            team1_score=team1_score,
            team2_score=team2_score,
            points_limit=rules["points_limit"],
            points_limit_last_set=rules["points_limit_last_set"],
        )
        if side_switch is not None:
            control["beach_side_switch"] = side_switch
        if rules["auto_swap_sides"]:
            completed = [
                (
                    int(current_model.get(f"Team 1 Game {index} Score", 0)),
                    int(current_model.get(f"Team 2 Game {index} Score", 0)),
                )
                for index in range(1, current_set)
            ]
            payload["match_info"]["sides_swapped"] = (
                rules["sides_swapped_manual"]
                ^ compute_sides_swapped_auto(
                    mode=rules["mode"],
                    current_set=current_set,
                    sets_limit=rules["sets_limit"],
                    team1_score=team1_score,
                    team2_score=team2_score,
                    points_limit=rules["points_limit"],
                    points_limit_last_set=rules["points_limit_last_set"],
                    completed_set_scores=completed,
                )
            )
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to compute match-point / side-switch info")


def _add_live_stats(payload: dict, storage_key: str, logger: logging.Logger) -> None:
    try:
        from app.api.live_stats import compute_live_stats

        stats = compute_live_stats(storage_key, history_limit=30)
        control = payload["overlay_control"]
        control["stats"] = {
            "current_streak": stats["current_streak"],
            "longest_streak": stats["longest_streak"],
            "partial_comeback": stats["partial_comeback"],
            "set_win_comeback": stats["set_win_comeback"],
            "total_points": stats["total_points"],
            "set_durations": {
                str(key): value
                for key, value in stats["set_durations"].items()
            },
            "services": {
                str(team): counts
                for team, counts in stats["services"].items()
            },
            "longest_streak_by_set": {
                str(set_num): {
                    str(team): value for team, value in by_team.items()
                }
                for set_num, by_team in stats[
                    "longest_streak_by_set"
                ].items()
            },
            "services_by_set": {
                str(set_num): {
                    str(team): counts for team, counts in by_team.items()
                }
                for set_num, by_team in stats["services_by_set"].items()
            },
            "point_types": {
                str(team): counts
                for team, counts in stats["point_types"].items()
            },
            "error_types": {
                str(team): counts
                for team, counts in stats["error_types"].items()
            },
            "point_types_by_set": {
                str(set_num): {
                    str(team): counts for team, counts in by_team.items()
                }
                for set_num, by_team in stats["point_types_by_set"].items()
            },
            "last_point": stats.get("last_point"),
        }
        control["points_history"] = stats["points_history"]
        control["points_by_set"] = {
            str(key): value for key, value in stats["points_by_set"].items()
        }
        control["timeouts_by_set"] = {
            str(key): value
            for key, value in stats["timeouts_by_set"].items()
        }
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to compute live stats for overlay payload")


def build_overlay_payload(
    current_model: dict,
    customization_state: dict,
    *,
    conf: Any,
    rule_overrides_getter: Callable[[], dict] | None,
    logger: logging.Logger,
    force_visibility: bool | None = None,
    show_only_current_set: bool | None = None,
) -> dict[str, Any]:
    """Build the standardized overlay state JSON payload."""
    customization = Customization(customization_state)
    current_set = int(current_model.get(State.CURRENT_SET_INT, 1))
    rules = _rule_context(conf, rule_overrides_getter, logger)

    payload: dict[str, Any] = {
        "match_info": {
            "tournament": "Superliga Masculina",
            "phase": "Playoffs",
            "best_of_sets": rules["sets_limit"],
            "current_set": current_set,
            "mode": rules["mode"],
            "points_limit": rules["points_limit"],
            "points_limit_last_set": rules["points_limit_last_set"],
            "match_started_at": rules["match_started_at"],
            "match_finished_at": rules["match_finished_at"],
            "server_time": time.time(),
            "match_finished": rules["match_finished"],
            "show_set_summary": rules["set_summary"],
            "set_summary_style": rules["set_summary_style"],
            "sides_swapped": rules["sides_swapped_manual"],
        },
        "team_home": _team_payload(
            current_model, customization, 1, current_set
        ),
        "team_away": _team_payload(
            current_model, customization, 2, current_set
        ),
        "overlay_control": {
            "show_bottom_ticker": False,
            "ticker_message": "",
            "show_player_stats": False,
            "player_stats_data": None,
            "geometry": {
                "width": customization.get_width(),
                "height": customization.get_height(),
                "xpos": customization.get_hpos(),
                "ypos": customization.get_vpos(),
                "scale": customization.get_scale(),
                "margin": customization.get_margin(),
                "anchor": customization.get_anchor(),
            },
            "colors": {
                "set_bg": customization.get_set_color(),
                "set_text": customization.get_set_text_color(),
                "game_bg": customization.get_game_color(),
                "game_text": customization.get_game_text_color(),
            },
            "preferredStyle": customization.get_preferred_style(),
            "show_logos": customization.is_show_logos()
            not in (False, "false", "False", 0, "0", None, ""),
            "show_stats": customization.is_show_stats(),
            "show_points_history": customization.is_show_points_history(),
        },
    }

    _add_rule_indicators(payload, current_model, rules, current_set, logger)
    _add_live_stats(payload, conf.skey or conf.oid, logger)

    if show_only_current_set is not None:
        payload["match_info"]["show_only_current_set"] = show_only_current_set
    try:
        from app.api.live_stats import resolve_summary_set_num

        payload["match_info"]["summary_set_num"] = resolve_summary_set_num(
            payload["overlay_control"].get("points_by_set"),
            current_set,
        )
    except Exception:  # pragma: no cover - defensive
        payload["match_info"]["summary_set_num"] = max(current_set - 1, 1)
    if force_visibility is not None:
        payload["overlay_control"]["show_main_scoreboard"] = force_visibility
    return payload
