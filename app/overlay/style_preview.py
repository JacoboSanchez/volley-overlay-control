"""Read-only style examples, independent of accounts and live match state."""

import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from app.api.schemas import SET_SUMMARY_STYLE_CHOICES
from app.overlay.locale import _resolve_overlay_locale
from app.overlay.state_store import OverlayStateStore


def demo_state(style: str, summary: str | None) -> dict[str, Any]:
    """An invented finished match; never reads or writes persisted state."""
    points = []
    scores = [0, 0]
    # A varied 25–21 sequence including a late home run.
    for index, scoring_team in enumerate([1, 2] * 21 + [1] * 4):
        scores[scoring_team - 1] += 1
        points.append({
            "action": "add_point", "team": scoring_team,
            "score": list(scores), "set_num": 3,
            "ts": 1700002400 + index * 28,
        })

    def team(home: bool) -> dict[str, Any]:
        return {
            "name": "Team A" if home else "Team B",
            "short_name": "A" if home else "B",
            "color_primary": "#145bea" if home else "#d92b3a",
            "color_secondary": "#ffffff",
            "logo_url": f"/static/img/style-previews/{'home' if home else 'away'}.svg",
            "points": 25 if home else 21, "sets_won": 3 if home else 0,
            "serving": home, "timeouts_taken": 1,
            "timeouts_by_set": {"set_1": 1, "set_2": 2, "set_3": 1},
            "set_history": {
                "set_1": 25 if home else 23,
                "set_2": 25 if home else 21,
                "set_3": 25 if home else 21,
            },
        }

    return {
        "team_home": team(True), "team_away": team(False),
        "match_info": {
            "current_set": 3, "summary_set_num": 3, "best_of_sets": 5,
            "points_limit": 25, "points_limit_last_set": 15,
            "show_only_current_set": False,
            "show_set_summary": summary is not None,
            "set_summary_style": summary or "brand_ledger",
            "match_finished": True, "match_started_at": 1700000000,
            "match_finished_at": 1700003660, "server_time": 1700003660,
        },
        "raw_remote_customization": {},
        "overlay_control": {
            "preferredStyle": style, "show_main_scoreboard": True,
            "show_logos": True, "alerts_visual": False,
            "show_bottom_ticker": False, "show_player_stats": False,
            "geometry": {"width": 30, "anchor": "middle-center"},
            "points_by_set": {"3": points},
            "timeouts_by_set": {"3": [
                {"team": 1, "score": [10, 10], "ts": 1700002950},
                {"team": 2, "score": [22, 21], "ts": 1700003580},
            ]},
            "stats": {
                "set_durations": {"1": 1260, "2": 1140, "3": 1260},
                "longest_streak_by_set": {"3": {"1": 4, "2": 1}},
                "services_by_set": {"3": {
                    "1": {"served": 24, "won": 4},
                    "2": {"served": 22, "won": 0},
                }},
            },
        },
    }


def register_style_preview(
    router: APIRouter, store: OverlayStateStore, templates: Jinja2Templates,
) -> None:
    @router.get("/overlay-preview/{style}", response_class=HTMLResponse)
    async def style_preview(
        request: Request, style: str, summary: str | None = None,
        lang: str | None = None, theme: Literal["light", "dark"] | None = None,
    ) -> Response:
        available = await run_in_threadpool(store.get_available_styles_list)
        if style not in available:
            raise HTTPException(status_code=404, detail="Unknown preview style")
        if summary is not None and summary not in SET_SUMMARY_STYLE_CHOICES:
            raise HTTPException(status_code=404, detail="Unknown summary style")
        caps = await run_in_threadpool(store.get_style_capabilities)
        capability = caps.get(style, {})
        preview_state = demo_state(style, summary)
        preview_state["raw_remote_customization"]["overlayTheme"] = theme or ""
        return templates.TemplateResponse(
            request=request,
            name="index.html" if style == "default" else f"{style}.html",
            context={
                "target_id": "Style example", "output_key": "",
                "style": style, "v": int(time.time()),
                "locale": _resolve_overlay_locale(lang, request, None),
                "native_theme": capability.get("nativeTheme", "dark"),
                "preview_state": preview_state,
            },
            headers={"Cache-Control": "no-store"},
        )
