"""Server-rendered, print-friendly match report at ``/match/{match_id}/report``.

Reads the archive snapshot written by :mod:`app.api.match_archive` and
renders a single self-contained HTML page suitable for the browser's
built-in "Save as PDF" workflow.

Authentication
--------------

By default the route is **gated**: the snapshot bundles the audit log
and full team customization (logos, names, colors) and is strictly
more sensitive than live overlay state. ``app.match_report_access``
admits a reader if any of:

* the request carries the **owner's** session cookie (the user whose
  overlay produced the match);
* the URL carries a valid HMAC capability (``?exp=…&sig=…``), minted
  by the owner via ``POST /api/v1/matches/{id}/sign-url`` and signed
  with ``SESSION_SECRET`` — no credential travels in the URL;
* ``MATCH_REPORT_PUBLIC=true``, in which case any caller with the
  (non-guessable, hash-prefixed) ``match_id`` can read the report.
  This matches the ``/overlay/{public_token}`` model and is
  appropriate for deployments that already share output URLs widely.

Otherwise the route returns 401. Deleting a match is owner-only and
lives on the account API (``DELETE /api/v1/matches/{match_id}``).
"""

from __future__ import annotations

import html
import logging
import time

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.api import match_archive
from app.match_report_access import check_read_access
from app.match_report_i18n import SUPPORTED_LOCALES, resolve_locale
from app.match_report_i18n import t as _t
from app.match_report_render import (
    _chart_color,
    _ensure_distinct_chart_colors,
    _fmt_seconds,
    _fmt_ts,
    _render_charts,
    _render_highlights,
    _render_logo,
    _render_set_durations_row,
    _render_timeline,
    _team_color,
    _team_name,
)
from app.match_report_stats import (
    _collapse_undos,
    _compute_stats,
    _played_set_count,
    _timeouts_per_set,
    _trim_pregame,
)
from app.match_report_template import REPORT_TEMPLATE as _REPORT_TEMPLATE


def _is_supported_locale_tag(value: str | None) -> bool:
    """``True`` when *value*'s primary tag matches a supported locale.

    Used to disambiguate between a ``?lang=en`` that legitimately
    requested English and a ``?lang=xx`` that fell through to
    English by accident — the latter should defer to the
    ``Accept-Language`` header instead of locking the report into
    the default.
    """
    if not isinstance(value, str) or not value.strip():
        return False
    primary = value.strip().split("-", 1)[0].split(",", 1)[0].lower()
    return primary in SUPPORTED_LOCALES

logger = logging.getLogger(__name__)

match_report_router = APIRouter()


@match_report_router.get(
    "/match/{match_id}/report",
    response_class=HTMLResponse,
    summary="Print-friendly HTML report for an archived match",
)
async def match_report(
    match_id: str,
    request: Request,
    exp: str | None = Query(default=None,
                               description="Signed-URL expiry (unix seconds)."),
    sig: str | None = Query(default=None,
                               description="Signed-URL HMAC-SHA256 hex digest."),
    lang: str | None = Query(
        default=None,
        description=(
            "Force the report locale (en/es/pt/it/fr/de). When the "
            "operator shares the report from the React control UI, "
            "the share dialog appends ``?lang=<active-locale>`` so "
            "the spectator sees the same language the operator was "
            "using. Falls back to the request's ``Accept-Language`` "
            "header (browser preference) when omitted, then to "
            "English. Unsupported values fall back the same way."
        ),
    ),
    accept_language: str | None = Header(default=None),
):
    check_read_access(request, match_id, exp=exp, sig=sig)
    payload = match_archive.load_match(match_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Match not found.")

    # Explicit ``?lang=`` wins over the browser's ``Accept-Language``.
    # Without this, a report shared from a Spanish-set control UI to
    # a browser with an English Accept-Language would render in
    # English — surprising the operator who set the locale.
    # An unsupported ``?lang=xx`` falls through to ``Accept-Language``
    # rather than locking the report into the default — otherwise
    # the cap would silently override a usable browser preference.
    if lang and _is_supported_locale_tag(lang):
        locale = resolve_locale(lang)
    else:
        locale = resolve_locale(accept_language)
    customization = payload.get("customization", {}) or {}
    final = payload.get("final_state", {}) or {}
    config = payload.get("config", {}) or {}
    raw_audit = payload.get("audit_log", []) or []
    # The "match" only exists from the first scored point onward — see
    # ``_first_scoring_index`` for the rationale. Every audit consumer
    # below operates on the trimmed slice so pre-game noise (resets,
    # stray clicks) doesn't skew durations, charts, or relative times.
    # ``_collapse_undos`` then drops both halves of every undo pair so
    # the report's reducers (timeouts row, highlights, charts, …) all
    # see the same final-state narrative the timeline renders. Without
    # this single collapse pass each reducer would have to re-derive
    # the post-undo view, and at least one (``_timeouts_per_set``)
    # was leaking undone forward-counts into the per-set row.
    audit = _collapse_undos(_trim_pregame(raw_audit))

    team1_name = _team_name(customization, 1)
    team2_name = _team_name(customization, 2)

    team1 = final.get("team_1", {}) or {}
    team2 = final.get("team_2", {}) or {}
    team1_sets = team1.get("sets") or 0
    team2_sets = team2.get("sets") or 0
    sets_limit = config.get("sets_limit") or 5
    # Trailing sets that never saw points (e.g. set 3 of a 2-0 best-of-3)
    # don't earn a column / chart / duration cell; they'd just read as
    # ``—``s and dilute the rest of the report.
    played_sets = _played_set_count(final, sets_limit)

    t1_color = _team_color(customization, 1, primary=True)
    t1_fg = _team_color(customization, 1, primary=False)
    t2_color = _team_color(customization, 2, primary=True)
    t2_fg = _team_color(customization, 2, primary=False)
    # The team's brand colour can be white-on-white (or the same hue
    # for both teams) on the report's neutral surface — that would
    # erase the chart polylines and the highlight text. Snap to a
    # contrast-safe pick for the chart / legend layer; the panel
    # backgrounds in ``.scoreboard`` keep the original brand colour.
    t1_chart, t2_chart = _ensure_distinct_chart_colors(
        _chart_color(1, t1_color, t1_fg),
        _chart_color(2, t2_color, t2_fg),
    )

    set_headers = "".join(
        f'<th>{html.escape(_t(locale, "setLabel", n=i))}</th>'
        for i in range(1, played_sets + 1)
    )

    timeouts_by_set = _timeouts_per_set(audit)

    def _team_set_cells(team_dict: dict, team_id: int) -> str:
        cells = []
        scores = team_dict.get("scores", {}) or {}
        for i in range(1, played_sets + 1):
            v = scores.get(f"set_{i}", "")
            text = str(v) if v != "" else "—"
            timeouts = timeouts_by_set.get(i, {}).get(team_id, 0)
            if timeouts > 0:
                text = f"{text} ({timeouts})"
            cells.append(f"<td>{html.escape(text)}</td>")
        return "".join(cells)

    stats = _compute_stats(audit)
    set_durations = stats.get("set_durations", {}) or {}

    # The reported "Started" and "Duration" snap to the match anchor
    # the session captured: ``session.match_started_at`` is set by the
    # explicit Start-match button or implicitly by the first scored
    # point, then archived as ``payload.started_at``. Either source is
    # the moment the *match* really began; we just trust it. Legacy
    # snapshots (no anchor stored) fall back to the first scoring
    # action so the report still has something honest to show.
    first_scoring_ts: float | None = None
    for record in audit:
        ts = record.get("ts")
        if isinstance(ts, (int, float)):
            first_scoring_ts = float(ts)
            break
    payload_started = payload.get("started_at")
    if isinstance(payload_started, (int, float)):
        effective_started_at: float | None = float(payload_started)
    else:
        effective_started_at = first_scoring_ts
    ended_at = payload.get("ended_at")
    effective_duration: float | None
    if (
        effective_started_at is not None
        and isinstance(ended_at, (int, float))
    ):
        effective_duration = max(
            0.0, float(ended_at) - effective_started_at,
        )
    else:
        effective_duration = payload.get("duration_s")

    # ``match_label`` and ``permalink`` are kept raw here — every
    # consumer escapes at insertion time. Pre-escaping the source
    # would push the title through ``html.escape`` twice (once here,
    # once at the template kwarg) and produce ``&amp;amp;`` for any
    # ``&`` in a team name.
    match_label = f"{team1_name} {team1_sets} – {team2_sets} {team2_name}"
    permalink = f"/match/{match_id}/report"

    rendered = _REPORT_TEMPLATE.format(
        locale=locale,
        title=html.escape(_t(locale, "title", label=match_label)),
        match_label=html.escape(match_label),
        match_id=html.escape(payload.get("match_id", match_id)),
        team1_name=html.escape(team1_name),
        team2_name=html.escape(team2_name),
        team1_logo=_render_logo(customization, 1),
        team2_logo=_render_logo(customization, 2),
        team1_sets=team1_sets,
        team2_sets=team2_sets,
        team1_color=t1_color,
        team1_fg=t1_fg,
        team2_color=t2_color,
        team2_fg=t2_fg,
        set_count=played_sets,
        set_headers=set_headers,
        team1_set_cells=_team_set_cells(team1, 1),
        team2_set_cells=_team_set_cells(team2, 2),
        set_duration_cells=_render_set_durations_row(set_durations, played_sets),
        # ``config`` values are operator-controlled — escape the
        # interpolated string defensively even though the formatter
        # only sees ints in the happy path. ``Best of {sets_limit}`` is
        # the *match rule* and stays at sets_limit even when fewer
        # sets actually got played.
        format_desc=html.escape(_t(
            locale, "formatDesc",
            sets=sets_limit,
            points=config.get("points_limit") or "—",
            last=config.get("points_limit_last_set") or "—",
        )),
        started_at_display=_fmt_ts(effective_started_at),
        ended_at_display=_fmt_ts(payload.get("ended_at")),
        duration_display=_fmt_seconds(effective_duration),
        audit_count=len(audit),
        highlights_html=_render_highlights(
            stats, locale,
            team1_name=team1_name, team2_name=team2_name,
        ),
        charts_html=_render_charts(
            audit, played_sets, locale,
            t1_name=team1_name, t2_name=team2_name,
            t1_color=t1_chart, t2_color=t2_chart,
        ),
        timeline_html=_render_timeline(
            audit, locale, played_sets, base_ts=effective_started_at,
        ),
        # i18n labels
        duration_label=html.escape(_t(locale, "duration")),
        versus=html.escape(_t(locale, "versus")),
        h_team=html.escape(_t(locale, "team")),
        h_set_byset=html.escape(_t(locale, "setByset")),
        h_set_durations=html.escape(_t(locale, "setDurations")),
        h_highlights=html.escape(_t(locale, "highlights")),
        h_score_evolution=html.escape(_t(locale, "scoreEvolution")),
        h_match_facts=html.escape(_t(locale, "matchFacts")),
        h_match_id=html.escape(_t(locale, "matchId")),
        h_format=html.escape(_t(locale, "format")),
        h_started=html.escape(_t(locale, "started")),
        h_ended=html.escape(_t(locale, "ended")),
        h_audit_entries=html.escape(_t(locale, "auditEntries")),
        h_timeline=html.escape(_t(locale, "timeline")),
        timeline_hint=html.escape(_t(locale, "timelineHint")),
        footer_text=html.escape(_t(locale, "footer")),
        permalink_label=html.escape(_t(locale, "permalinkLabel")),
        permalink_display=html.escape(permalink),
        generated_label=html.escape(_t(locale, "generatedLabel")),
        # ``_fmt_ts`` reuses the same human format as the started /
        # ended cells in the match-facts table, so the footer reads
        # in the same shape regardless of locale.
        generated_at_display=_fmt_ts(time.time()),
        btn_print=html.escape(_t(locale, "print")),
        btn_print_include_prompt=html.escape(
            _t(locale, "printIncludeLogPrompt"), quote=True,
        ),
        btn_copy=html.escape(_t(locale, "copyLink")),
        btn_copy_ok=html.escape(_t(locale, "copyLinkOk")),
        permalink=html.escape(permalink, quote=True),
    )
    return HTMLResponse(content=rendered)
