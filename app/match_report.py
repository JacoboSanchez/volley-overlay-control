"""Server-rendered, print-friendly match report at ``/match/{match_id}/report``.

Reads the archive snapshot written by :mod:`app.api.match_archive` and
renders a single self-contained HTML page suitable for the browser's
built-in "Save as PDF" workflow.

Authentication
--------------

By default the route is **gated**: the snapshot bundles the audit log
and full team customization (logos, names, colors) and is strictly
more sensitive than live overlay state. Access requires either:

* ``Authorization: Bearer <OVERLAY_MANAGER_PASSWORD>`` — same admin
  token used by ``/api/v1/admin/*`` and ``/manage``;
* a ``token=<OVERLAY_MANAGER_PASSWORD>`` query parameter — necessary
  when opening the URL in a plain browser tab (no header API);
* setting ``MATCH_REPORT_PUBLIC=true``, in which case any caller with
  the (non-guessable, hash-prefixed) ``match_id`` can read the
  report. This matches the ``/overlay/{output_key}`` model and is
  appropriate for deployments that already share output URLs widely.

When ``OVERLAY_MANAGER_PASSWORD`` is unset and ``MATCH_REPORT_PUBLIC``
is not enabled, the route returns 503 — operators must explicitly
opt in to one mode or the other.
"""

from __future__ import annotations

import datetime
import html
import logging
import re
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.api import match_archive
from app.env_vars_manager import EnvVarsManager

logger = logging.getLogger(__name__)

match_report_router = APIRouter()


def _public_mode_enabled() -> bool:
    raw = EnvVarsManager.get_env_var("MATCH_REPORT_PUBLIC", "false")
    return str(raw).strip().lower() in ("1", "true", "t", "yes", "on")


def _admin_password() -> Optional[str]:
    raw = EnvVarsManager.get_env_var("OVERLAY_MANAGER_PASSWORD", None)
    if raw is None:
        return None
    raw = str(raw).strip()
    return raw or None


def _check_access(authorization: Optional[str], token: Optional[str]) -> None:
    """Raise an ``HTTPException`` unless the caller is allowed to read.

    Order of precedence:
      1. ``MATCH_REPORT_PUBLIC=true`` — open access (matches the
         existing ``/overlay/{output_key}`` model);
      2. otherwise, ``OVERLAY_MANAGER_PASSWORD`` must be set and
         provided via Bearer header or ``?token=`` query;
      3. when neither is configured, return 503 to make
         misconfiguration loud rather than silently public.
    """
    if _public_mode_enabled():
        return
    expected = _admin_password()
    if expected is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Match reports are disabled. Set OVERLAY_MANAGER_PASSWORD "
                "for gated access or MATCH_REPORT_PUBLIC=true for open "
                "access."
            ),
        )
    provided: Optional[str] = None
    if authorization and authorization.startswith("Bearer "):
        provided = authorization.removeprefix("Bearer ").strip() or None
    if provided is None and token:
        provided = token.strip() or None
    if provided is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "Authentication required. Pass Authorization: Bearer "
                "<token> or ?token=<token> matching "
                "OVERLAY_MANAGER_PASSWORD."
            ),
        )
    if provided != expected:
        raise HTTPException(status_code=403, detail="Invalid token.")


_REPORT_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Match report — {match_label}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root {{
    --fg: #1a1a1a;
    --muted: #666;
    --border: #d0d0d0;
    --t1: {team1_color};
    --t1-fg: {team1_fg};
    --t2: {team2_color};
    --t2-fg: {team2_fg};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: var(--fg);
    margin: 0;
    padding: 24px;
    max-width: 960px;
    margin-left: auto;
    margin-right: auto;
    line-height: 1.5;
  }}
  header h1 {{ margin: 0 0 4px; font-size: 24px; }}
  header .meta {{ color: var(--muted); font-size: 14px; }}
  .scoreboard {{
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    gap: 16px;
    align-items: center;
    margin: 24px 0;
    padding: 16px;
    border: 1px solid var(--border);
    border-radius: 8px;
  }}
  .team {{
    text-align: center;
    padding: 12px;
    border-radius: 6px;
  }}
  .team.t1 {{ background: var(--t1); color: var(--t1-fg); }}
  .team.t2 {{ background: var(--t2); color: var(--t2-fg); }}
  .team .name {{ font-weight: 600; font-size: 18px; }}
  .team .sets {{ font-size: 56px; line-height: 1; font-weight: 700; }}
  .team .winner {{ font-size: 12px; opacity: 0.85; margin-top: 4px; }}
  .vs {{ font-size: 24px; font-weight: 600; color: var(--muted); }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
  }}
  th, td {{
    text-align: center;
    padding: 8px;
    border-bottom: 1px solid var(--border);
  }}
  th:first-child, td:first-child {{ text-align: left; }}
  h2 {{ font-size: 18px; margin: 24px 0 8px; }}
  .timeline {{
    font-size: 13px;
    color: var(--muted);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    max-height: 320px;
    overflow: auto;
  }}
  .timeline ol {{ margin: 0; padding-left: 20px; }}
  .footer {{
    margin-top: 32px;
    font-size: 12px;
    color: var(--muted);
    border-top: 1px solid var(--border);
    padding-top: 12px;
  }}
  @media print {{
    body {{ padding: 0; max-width: none; }}
    .timeline {{ max-height: none; overflow: visible; }}
    @page {{ margin: 16mm; }}
  }}
</style>
</head>
<body>
<header>
  <h1>{match_label}</h1>
  <div class="meta">
    {ended_at_display} &middot; Duration {duration_display}
  </div>
</header>

<section class="scoreboard">
  <div class="team t1">
    <div class="name">{team1_name}</div>
    <div class="sets">{team1_sets}</div>
    {team1_winner_badge}
  </div>
  <div class="vs">vs</div>
  <div class="team t2">
    <div class="name">{team2_name}</div>
    <div class="sets">{team2_sets}</div>
    {team2_winner_badge}
  </div>
</section>

<h2>Set-by-set</h2>
<table>
  <thead>
    <tr><th>Team</th>{set_headers}</tr>
  </thead>
  <tbody>
    <tr><td>{team1_name}</td>{team1_set_cells}</tr>
    <tr><td>{team2_name}</td>{team2_set_cells}</tr>
    <tr><td>Timeouts (final set)</td><td colspan="{set_count}">{timeouts_summary}</td></tr>
  </tbody>
</table>

<h2>Match facts</h2>
<table>
  <tbody>
    <tr><td>Match ID</td><td>{match_id}</td></tr>
    <tr><td>OID</td><td>{oid}</td></tr>
    <tr><td>Format</td><td>Best of {sets_limit} &middot; {points_limit} pts/set ({points_limit_last_set} in final)</td></tr>
    <tr><td>Started</td><td>{started_at_display}</td></tr>
    <tr><td>Ended</td><td>{ended_at_display}</td></tr>
    <tr><td>Audit entries</td><td>{audit_count}</td></tr>
  </tbody>
</table>

<h2>Action timeline</h2>
<div class="timeline">{timeline_html}</div>

<div class="footer">
  Generated by Volley Overlay Control. Use your browser's "Save as PDF" to export.
</div>
</body>
</html>
"""


def _fmt_seconds(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def _fmt_ts(ts: Optional[float]) -> str:
    if ts is None:
        return "—"
    try:
        dt = datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M UTC")


_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _team_color(customization: dict, team: int, primary: bool) -> str:
    """Resolve a strict hex colour from the customization dict.

    Falls back to a sensible default when the key is missing or the
    stored value is anything but ``#RGB`` / ``#RRGGBB``. Strictness is
    load-bearing: this value is interpolated into a CSS custom
    property, so a malformed input could otherwise inject CSS.
    """
    fallback_bg = ("#0047AB", "#E21836")[team - 1]
    fallback_fg = "#FFFFFF"
    bg_keys = {
        1: ("Color 1", "Team 1 Color", "color_primary"),
        2: ("Color 2", "Team 2 Color", "color_primary"),
    }
    fg_keys = {
        1: ("Text Color 1", "Team 1 Text Color"),
        2: ("Text Color 2", "Team 2 Text Color"),
    }
    keys = bg_keys[team] if primary else fg_keys[team]
    for key in keys:
        value = customization.get(key)
        if isinstance(value, str) and _HEX_COLOR_RE.match(value):
            return value
    return fallback_bg if primary else fallback_fg


def _team_name(customization: dict, team: int) -> str:
    for key in (f"Team {team} Name", f"team_{team}_name", f"name{team}"):
        value = customization.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"Team {team}"


def _action_label(record: dict) -> str:
    action = record.get("action", "")
    params = record.get("params") or {}
    team = params.get("team")
    undo = " (undo)" if params.get("undo") else ""
    if action == "add_point":
        return f"Point — Team {team}{undo}"
    if action == "add_set":
        return f"Set won — Team {team}{undo}"
    if action == "add_timeout":
        return f"Timeout — Team {team}{undo}"
    if action == "change_serve":
        return f"Serve change → Team {team}"
    if action == "set_score":
        return (
            f"Manual score — Team {team} set "
            f"{params.get('set_number')} = {params.get('value')}"
        )
    if action == "reset":
        return "Reset"
    return action or "(unknown action)"


@match_report_router.get(
    "/match/{match_id}/report",
    response_class=HTMLResponse,
    summary="Print-friendly HTML report for an archived match",
)
async def match_report(
    match_id: str,
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None,
                                 description="OVERLAY_MANAGER_PASSWORD; "
                                             "alternative to Bearer header."),
):
    _check_access(authorization, token)
    payload = match_archive.load_match(match_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Match not found.")

    customization = payload.get("customization", {}) or {}
    final = payload.get("final_state", {}) or {}
    config = payload.get("config", {}) or {}
    audit = payload.get("audit_log", []) or []

    team1_name = _team_name(customization, 1)
    team2_name = _team_name(customization, 2)

    team1 = final.get("team_1", {}) or {}
    team2 = final.get("team_2", {}) or {}
    team1_sets = team1.get("sets") or 0
    team2_sets = team2.get("sets") or 0
    sets_limit = config.get("sets_limit") or 5

    set_headers = "".join(
        f"<th>Set {i}</th>" for i in range(1, sets_limit + 1)
    )

    def _team_set_cells(team_dict: dict) -> str:
        cells = []
        scores = team_dict.get("scores", {}) or {}
        for i in range(1, sets_limit + 1):
            v = scores.get(f"set_{i}", "")
            cells.append(f"<td>{html.escape(str(v) if v != '' else '—')}</td>")
        return "".join(cells)

    timeouts_t1 = team1.get("timeouts")
    timeouts_t2 = team2.get("timeouts")
    timeouts_summary = (
        f"{html.escape(team1_name)}: {timeouts_t1 if timeouts_t1 is not None else '—'} &middot; "
        f"{html.escape(team2_name)}: {timeouts_t2 if timeouts_t2 is not None else '—'}"
    )

    winning_team = payload.get("winning_team")
    team1_winner = (
        '<div class="winner">Match winner</div>'
        if winning_team == 1 else ""
    )
    team2_winner = (
        '<div class="winner">Match winner</div>'
        if winning_team == 2 else ""
    )

    timeline_items = []
    for record in audit:
        ts = _fmt_ts(record.get("ts"))
        label = _action_label(record)
        timeline_items.append(
            f"<li>{html.escape(ts)} — {html.escape(label)}</li>"
        )
    timeline_html = (
        f"<ol>{''.join(timeline_items)}</ol>"
        if timeline_items else "<em>No audit records.</em>"
    )

    match_label = (
        f"{html.escape(team1_name)} {team1_sets} – {team2_sets} "
        f"{html.escape(team2_name)}"
    )

    rendered = _REPORT_TEMPLATE.format(
        match_label=match_label,
        match_id=html.escape(payload.get("match_id", match_id)),
        oid=html.escape(payload.get("oid", "—")),
        team1_name=html.escape(team1_name),
        team2_name=html.escape(team2_name),
        team1_sets=team1_sets,
        team2_sets=team2_sets,
        team1_color=_team_color(customization, 1, primary=True),
        team1_fg=_team_color(customization, 1, primary=False),
        team2_color=_team_color(customization, 2, primary=True),
        team2_fg=_team_color(customization, 2, primary=False),
        team1_winner_badge=team1_winner,
        team2_winner_badge=team2_winner,
        set_count=sets_limit,
        set_headers=set_headers,
        team1_set_cells=_team_set_cells(team1),
        team2_set_cells=_team_set_cells(team2),
        timeouts_summary=timeouts_summary,
        sets_limit=sets_limit,
        points_limit=config.get("points_limit") or "—",
        points_limit_last_set=config.get("points_limit_last_set") or "—",
        started_at_display=_fmt_ts(payload.get("started_at")),
        ended_at_display=_fmt_ts(payload.get("ended_at")),
        duration_display=_fmt_seconds(payload.get("duration_s")),
        audit_count=len(audit),
        timeline_html=timeline_html,
    )
    return HTMLResponse(content=rendered)
