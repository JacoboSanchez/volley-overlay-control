"""SVG score-chart rendering for match reports."""

from __future__ import annotations

import html

from app.match_report.i18n import t as _t
from app.match_report.stats import (
    _is_score_action,
    _result_set,
    _running_score_pair,
)

# Anything beyond this gap between consecutive points is treated as
# "the operator left the tab open / time isn't trustworthy", and the
# chart falls back to the rally-number X-axis. 15 minutes is well
# beyond a normal set-break and well short of operator-distraction
# territory.
_TIME_AXIS_MAX_GAP_S = 15 * 60


def _format_mmss(seconds: float) -> str:
    """``MM:SS`` (no leading zero on minutes) for the X-axis label."""
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def _reliable_time_axis(timestamps: list[float | None]) -> list[float] | None:
    """Return the float timestamps when they can drive a time X-axis.

    Time mode requires every record to carry a timestamp *and* no gap
    between consecutive records to exceed :data:`_TIME_AXIS_MAX_GAP_S`
    — anything bigger means the operator was AFK and the wallclock no
    longer tracks play. A negative gap (non-monotonic timestamps from
    clock skew / NTP correction) would plot points outside the SVG
    viewport. Either case returns ``None`` so the caller falls back to
    rally-number indexing rather than compress the whole set into a
    thin slice on the left.
    """
    if any(t is None for t in timestamps):
        return None
    # ``timestamps`` is structurally ``list[Optional[float]]``; the
    # check above narrows it but mypy can't see through it, so build
    # the float-only list explicitly.
    times = [float(t) for t in timestamps if t is not None]
    for i in range(1, len(times)):
        gap = times[i] - times[i - 1]
        if gap > _TIME_AXIS_MAX_GAP_S or gap < 0:
            return None
    return times


def _render_score_chart(
    set_records: list[dict], *,
    t1_color: str, t2_color: str,
    timeouts: list[dict] | None = None,
) -> str:
    """Inline SVG showing how each team's score evolved through a set.

    X axis: time elapsed since the first point of the set (``MM:SS``)
    when the audit timestamps look reliable. If any gap between two
    consecutive scoring records exceeds :data:`_TIME_AXIS_MAX_GAP_S`
    we fall back to plain rally-number indexing — that's the signal
    the operator stepped away and the timestamps stopped reflecting
    play. Y axis: points scored, labelled 0 / mid / max. Each rally
    datapoint is marked with a small filled circle so single-point
    spikes are legible. One polyline per team, coloured via the
    contrast-safe palette resolved upstream. Pure SVG, no JS, so it
    survives "Save as PDF".

    *timeouts* (optional) is the list of ``add_timeout`` audit
    records belonging to this set, already collapsed for undos by
    the caller. Each one renders as a thin dashed vertical guide
    line in the calling team's colour, with a small downward
    triangle perched above the chart so the operator can correlate
    "score stalled here" with "the team called timeout".

    Returns a placeholder string when the set has fewer than two
    scoring records (nothing to plot).
    """
    points: list[tuple[int, int]] = []
    timestamps: list[float | None] = []
    for r in set_records:
        pair = _running_score_pair(r)
        if not pair:
            continue
        points.append(pair)
        ts = r.get("ts")
        timestamps.append(float(ts) if isinstance(ts, (int, float)) else None)
    if len(points) < 2:
        return ""

    max_score = max(max(p) for p in points)
    width, height = 360, 150
    pad_x_left, pad_x_right = 32, 18
    pad_y_top, pad_y_bottom = 14, 26
    plot_w = width - pad_x_left - pad_x_right
    plot_h = height - pad_y_top - pad_y_bottom
    last_idx = len(points) - 1
    if last_idx == 0 or max_score == 0:
        return ""

    # Decide axis mode — see ``_reliable_time_axis`` for the trust
    # rules that gate the time X-axis.
    times = _reliable_time_axis(timestamps)
    use_time_axis = times is not None
    if times is not None:
        base_ts = times[0]
        x_values: list[float] = [t - base_ts for t in times]
        # Guard against a degenerate "all points at the same ts" set:
        # the polyline would collapse, but we still need a non-zero
        # divisor for the projection.
        x_max = x_values[-1] if x_values[-1] > 0 else 1.0
    else:
        x_values = [float(i) for i in range(len(points))]
        x_max = float(last_idx) if last_idx else 1.0

    def _project(idx: int, score: int) -> tuple[float, float]:
        x_norm = x_values[idx] / x_max if x_max else 0.0
        x = pad_x_left + x_norm * plot_w
        y = pad_y_top + plot_h - (score / max_score) * plot_h
        return x, y

    mid_score = max_score // 2 if max_score >= 2 else max_score
    y_ticks = sorted({0, mid_score, max_score})

    # The class names alongside the inline presentation attributes are
    # the dark-mode hook: the stylesheet re-points them at CSS vars
    # (which beat presentation attributes), while the attributes keep
    # the light rendering identical for no-CSS consumers and pinned
    # tests.
    grid_lines = "".join(
        f'<line class="chart-grid" x1="{pad_x_left}" y1="{_project(0, v)[1]:.1f}" '
        f'x2="{pad_x_left + plot_w}" y2="{_project(0, v)[1]:.1f}" '
        f'stroke="#e0e0e0" stroke-width="1" stroke-dasharray="2,3" />'
        for v in y_ticks
    )

    y_labels = "".join(
        f'<text class="chart-axis" x="{pad_x_left - 4}" y="{_project(0, v)[1] + 3:.1f}" '
        f'text-anchor="end" font-size="9" fill="#999">{v}</text>'
        for v in y_ticks
    )

    if use_time_axis:
        # Endpoints: ``0:00`` → ``M:SS`` of the last rally relative
        # to the set's first point.
        left_label = "0:00"
        right_label = _format_mmss(x_values[-1])
    else:
        # 1-indexed rally numbers, matching prior behaviour.
        left_label = "1"
        right_label = str(len(points))

    x_labels = (
        f'<text class="chart-axis" x="{pad_x_left}" y="{height - 8}" text-anchor="start" '
        f'font-size="9" fill="#999">{html.escape(left_label)}</text>'
        f'<text class="chart-axis" x="{pad_x_left + plot_w}" y="{height - 8}" '
        f'text-anchor="end" font-size="9" fill="#999">{html.escape(right_label)}</text>'
    )

    def _polyline(team_idx: int, color: str) -> str:
        coords = " ".join(
            f"{x:.1f},{y:.1f}"
            for x, y in (_project(i, p[team_idx]) for i, p in enumerate(points))
        )
        return (
            f'<polyline class="t{team_idx + 1}-stroke" fill="none" '
            f'stroke="{html.escape(color)}" '
            f'stroke-width="2" points="{coords}" />'
        )

    def _markers(team_idx: int, color: str) -> str:
        # ``r=2.5`` so they sit just above polyline thickness — big
        # enough to read on print, small enough not to obscure rapid
        # back-and-forth swings in volleyball-style 25-point sets.
        return "".join(
            f'<circle class="t{team_idx + 1}-fill" cx="{x:.1f}" cy="{y:.1f}" r="2.5" '
            f'fill="{html.escape(color)}" />'
            for x, y in (_project(i, p[team_idx]) for i, p in enumerate(points))
        )

    def _timeout_markers() -> str:
        if not timeouts:
            return ""
        # Reuse ``timestamps`` (1:1 with the plotted ``points``)
        # rather than rebuilding from ``set_records`` — the polyline
        # already filters out records that lack a ``_running_score_pair``,
        # so a parallel rebuild here would drift the rally indices.
        # Some entries may still be ``None`` when the chart fell back
        # to rally mode because of missing timestamps; those score
        # records simply don't contribute to the timeout's rally
        # position.
        items: list[str] = []
        for record in timeouts:
            params = record.get("params") or {}
            team = params.get("team")
            if team not in (1, 2):
                continue
            ts = record.get("ts")
            if not isinstance(ts, (int, float)):
                continue
            ts_float = float(ts)
            if use_time_axis and times is not None:
                # Time mode: anchor to the same ``base_ts`` the score
                # polyline uses. A timeout called *before* the first
                # point of the set lands at x=0 (left edge) rather
                # than off-canvas.
                x_val = max(0.0, ts_float - times[0])
                x_val = min(x_val, x_max)
            else:
                # Rally mode: count plotted score records whose
                # timestamp is ``<= ts_float``. ``idx`` is the rally
                # number after which the timeout was called; clamp
                # into ``[0, last_idx]`` so a post-final-point
                # timeout still renders on the right edge. Skip
                # ``None`` entries (records without a timestamp)
                # rather than letting the comparison raise.
                idx = sum(
                    1 for t in timestamps if t is not None and t <= ts_float
                ) - 1
                idx = max(0, min(idx, last_idx))
                x_val = float(idx)
            x_norm = x_val / x_max if x_max else 0.0
            x = pad_x_left + x_norm * plot_w
            color = t1_color if team == 1 else t2_color
            color_safe = html.escape(color)
            # Dashed guide spanning the plot height + a small clock
            # face perched ~9 px above the plot area so it doesn't
            # collide with the polylines or the ``max_score`` Y label.
            # The glyph is a hand-rolled inline SVG (circle + two
            # hands) rather than a Material Icons font ref so the
            # report keeps surviving "Save as PDF" with no external
            # font load.
            cy = pad_y_top - 5
            items.append(
                f'<line class="set-chart-timeout" data-team="{team}" '
                f'x1="{x:.1f}" y1="{pad_y_top:.1f}" '
                f'x2="{x:.1f}" y2="{pad_y_top + plot_h:.1f}" '
                f'stroke="{color_safe}" stroke-width="1" '
                f'stroke-dasharray="3,3" opacity="0.55" />'
                # Lift the shared stroke attributes to the ``<g>`` so
                # the children only override what they need (the face
                # gets a slightly thicker border than the hands).
                f'<g class="set-chart-timeout-glyph" data-team="{team}" '
                f'stroke="{color_safe}" stroke-width="1" '
                f'stroke-linecap="round">'
                f'<circle cx="{x:.1f}" cy="{cy:.1f}" r="3.5" '
                f'fill="none" stroke-width="1.2" />'
                # Minute hand: pointing up to "12".
                f'<line x1="{x:.1f}" y1="{cy:.1f}" '
                f'x2="{x:.1f}" y2="{cy - 2.2:.1f}" />'
                # Hour hand: pointing right to "3".
                f'<line x1="{x:.1f}" y1="{cy:.1f}" '
                f'x2="{x + 1.7:.1f}" y2="{cy:.1f}" />'
                f'</g>'
            )
        return "".join(items)

    # ``data-x-axis`` lets tests assert which mode kicked in without
    # parsing the rendered labels.
    axis_attr = "time" if use_time_axis else "rally"
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'class="set-chart" data-x-axis="{axis_attr}" '
        f'preserveAspectRatio="xMidYMid meet">'
        f'<rect x="0" y="0" width="{width}" height="{height}" '
        f'fill="transparent" />'
        f'{grid_lines}{y_labels}{x_labels}'
        f'{_polyline(0, t1_color)}{_polyline(1, t2_color)}'
        f'{_markers(0, t1_color)}{_markers(1, t2_color)}'
        f'{_timeout_markers()}'
        f'</svg>'
    )


def _render_charts(
    audit: list[dict], set_count: int, locale: str,
    *, t1_name: str, t2_name: str, t1_color: str, t2_color: str,
) -> str:
    """Build the per-set score-evolution chart grid."""
    scores_by_set: dict[int, list[dict]] = {}
    timeouts_by_set: dict[int, list[dict]] = {}
    for record in audit:
        if record.get("params", {}).get("undo"):
            continue
        set_num = _result_set(record)
        if set_num is None:
            continue
        if _is_score_action(record):
            scores_by_set.setdefault(set_num, []).append(record)
        elif record.get("action") == "add_timeout":
            timeouts_by_set.setdefault(set_num, []).append(record)

    timeout_legend = (
        f'<span class="swatch swatch-timeout" aria-hidden="true"></span>'
        f'{html.escape(_t(locale, "legendTimeout"))}'
    )

    cards: list[str] = []
    for i in range(1, set_count + 1):
        records = scores_by_set.get(i, [])
        chart = _render_score_chart(
            records,
            t1_color=t1_color, t2_color=t2_color,
            timeouts=timeouts_by_set.get(i, []),
        )
        body = chart or (
            f'<p class="legend">{html.escape(_t(locale, "noScoreEvolution"))}</p>'
        )
        # Timeout swatch only when this set had at least one — the
        # operator doesn't need a "Timeout" key on a clean set.
        timeout_html = (
            timeout_legend if timeouts_by_set.get(i) else ""
        )
        # Swatch colours come from the ``--t1-chart``/``--t2-chart``
        # CSS vars (see the template) so they track the scheme-specific
        # chart palette instead of freezing the light colour inline.
        legend = (
            f'<div class="legend">'
            f'<span class="swatch swatch-t1"></span>{html.escape(t1_name)}'
            f'<span class="swatch swatch-t2"></span>{html.escape(t2_name)}'
            f'{timeout_html}'
            f'</div>'
        )
        cards.append(
            f'<div class="chart-card">'
            f'<h3>{html.escape(_t(locale, "setLabel", n=i))}</h3>'
            f'{legend}{body}'
            f'</div>'
        )
    return "".join(cards) or ""
