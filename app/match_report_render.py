"""HTML/SVG fragment builders for the match-report pages.

Split out of :mod:`app.match_report`: formatting helpers, contrast-safe
chart colours, and the renderers for the highlights grid, score charts,
timeline and the matches-index table. Page templates live in
:mod:`app.match_report_template`.
"""

from __future__ import annotations

import datetime
import html
import re

from app.api.schemas import ERROR_TYPES
from app.match_report_i18n import t as _t
from app.match_report_stats import (
    _is_score_action,
    _result_set,
    _running_score_pair,
)


def _fmt_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def _fmt_ts(ts: float | None) -> str:
    if ts is None:
        return "—"
    try:
        dt = datetime.datetime.fromtimestamp(float(ts), datetime.UTC)
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

    Key priority: the team-identity colours (``Team 1 Color`` /
    ``Team 1 Text Color``) come first because they're the *team's*
    brand, set per-team in the operator UI. The overlay-wide
    ``Color 1`` / ``Text Color 1`` keys are alternating row colours
    and shouldn't override the team's own colour in the report.
    """
    fallback_bg = ("#0047AB", "#E21836")[team - 1]
    fallback_fg = "#FFFFFF"
    bg_keys = {
        1: ("Team 1 Color", "Color 1", "color_primary"),
        2: ("Team 2 Color", "Color 2", "color_primary"),
    }
    fg_keys = {
        1: ("Team 1 Text Color", "Text Color 1"),
        2: ("Team 2 Text Color", "Text Color 2"),
    }
    keys = bg_keys[team] if primary else fg_keys[team]
    for key in keys:
        value = customization.get(key)
        if isinstance(value, str) and _HEX_COLOR_RE.match(value):
            return value
    return fallback_bg if primary else fallback_fg


def _team_name(customization: dict, team: int) -> str:
    # ``Team {n} Name`` is the canonical key the React control UI
    # writes; ``Team {n} Text Name`` is the legacy alias the rest
    # of the codebase still honours via ``Customization.A_TEAM`` /
    # ``B_TEAM``. The overlays.uno cloud customization is also
    # known to round-trip the legacy form depending on what the
    # operator typed into the UNO panel — without the alias here
    # the report falls back to the literal ``Team 1`` / ``Team 2``
    # strings for any UNO-backed match. Snake-case and ``name{n}``
    # cover older / external archives.
    for key in (
        f"Team {team} Name",
        f"Team {team} Text Name",
        f"team_{team}_name",
        f"name{team}",
    ):
        value = customization.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"Team {team}"


def _action_label(record: dict, locale: str) -> str:
    """Human-readable label for an audit-log row in the report.

    No ``(undone)`` suffix is emitted: ``_collapse_undos`` strips
    every undo record (and its forward pair) before this function
    runs, so a row reaching here always represents an action that
    survived to the final state.
    """
    action = record.get("action", "")
    params = record.get("params") or {}
    team = params.get("team")
    if action == "add_point":
        return _t(locale, "actionPoint", team=team)
    if action == "add_set":
        return _t(locale, "actionSet", team=team)
    if action == "add_timeout":
        return _t(locale, "actionTimeout", team=team)
    if action == "change_serve":
        return _t(locale, "actionServe", team=team)
    if action == "set_score":
        return _t(
            locale, "actionScore",
            team=team,
            set=params.get("set_number"),
            value=params.get("value"),
        )
    if action == "reset":
        return _t(locale, "actionReset")
    return action or _t(locale, "actionUnknown")


# Single source of truth for the timeline chip palette. Each entry
# pairs the chip kind (used as a CSS modifier ``chip-{kind}``) with
# the glyph rendered inside the accent strip and, when applicable,
# the i18n key that names it in the bottom legend.
#
# Order matters — the legend section iterates the catalogue in the
# order entries appear here, so the operator scans them top-to-
# bottom (per-team points, then set / timeout / serve / edit /
# reset).
#
# There is intentionally no ``undone`` entry: ``_collapse_undos``
# strips both halves of every undo pair upstream, so no row that
# reaches the timeline carries an undone state. The frontend
# audit drawer's ``chipCatalogue.ts`` keeps an ``undone`` entry
# because the live operator transcript still surfaces individual
# undo records as their own rows.
_CHIP_CATALOGUE: dict[str, dict[str, str | None]] = {
    "point-t1": {"glyph": "+1", "legend_key": "legendPointT1"},
    "point-t2": {"glyph": "+1", "legend_key": "legendPointT2"},
    # Generic point chip used for legacy/missing-team rows. Not
    # surfaced in the legend because the per-team variants already
    # cover the shared semantics.
    "point":    {"glyph": "+1", "legend_key": None},
    "set":      {"glyph": "🏆", "legend_key": "legendSet"},
    "timeout":  {"glyph": "⏸", "legend_key": "legendTimeout"},
    "serve":    {"glyph": "⇄", "legend_key": "legendServe"},
    "edit":     {"glyph": "✎", "legend_key": "legendEdit"},
    "reset":    {"glyph": "⟲", "legend_key": "legendReset"},
    # Final fallback — keeps unknown actions from rendering a blank
    # accent strip. Intentionally unlabelled in the legend.
    "other":    {"glyph": "•", "legend_key": None},
}


def _chip_glyph(kind: str) -> str:
    """Glyph shown inside the chip accent strip for a given kind."""
    entry = _CHIP_CATALOGUE.get(kind, _CHIP_CATALOGUE["other"])
    glyph = entry["glyph"]
    return glyph if isinstance(glyph, str) else "•"


# Classifier-driven chip metadata. Returns the (modifier, glyph) pair
# the timeline ``<li>`` and its accent strip use to differentiate
# action kinds at a glance. Glyphs come from ``_CHIP_CATALOGUE`` so
# the legend, the per-row strip and any future surface that needs
# the same palette stay consistent without manual sync.
def _chip_classifier(action: str, team: object) -> tuple[str, str]:
    """Map an audit-record action+team to a chip ``(modifier, glyph)``.

    ``modifier`` keys the chip's CSS class (``chip-{modifier}``) so
    the stylesheet can paint a different accent and background per
    action kind. Team-bound rows use ``point-t1`` / ``point-t2`` so
    the running score reads alongside its team colour without
    requiring per-team chip glyphs. ``_collapse_undos`` upstream
    guarantees no undone records reach this function.
    """
    if action == "add_point":
        if team == 1:
            kind = "point-t1"
        elif team == 2:
            kind = "point-t2"
        else:
            kind = "point"
    elif action == "add_set":
        kind = "set"
    elif action == "add_timeout":
        kind = "timeout"
    elif action == "change_serve":
        kind = "serve"
    elif action == "set_score":
        kind = "edit"
    elif action == "reset":
        kind = "reset"
    else:
        kind = "other"
    return (kind, _chip_glyph(kind))


def _format_relative_ts(ts: float | None, base_ts: float | None) -> str:
    """``+0:15`` / ``+1:23:45`` style offset from the match start.

    Returns ``"—"`` for missing inputs and ``"+0:00"`` for the very
    first record (relative to itself). Negative deltas would mean an
    out-of-order log; we clamp to zero rather than render a minus sign
    that would baffle the operator.
    """
    if ts is None or base_ts is None:
        return "—"
    delta = max(0, int(float(ts) - float(base_ts)))
    h, rem = divmod(delta, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"+{h}:{m:02d}:{s:02d}"
    return f"+{m}:{s:02d}"


def _logo_url(customization: dict, team: int) -> str | None:
    """Return a sanitised logo URL for *team*, or ``None`` if missing.

    Only ``http(s):`` and ``data:`` schemes are accepted — the URL is
    interpolated into ``<img src=…>`` and any other scheme would invite
    XSS via ``javascript:``-style payloads.
    """
    for key in (f"Team {team} Logo", f"team_{team}_logo", f"logo{team}"):
        value = customization.get(key)
        if not isinstance(value, str):
            continue
        candidate = value.strip()
        if not candidate:
            continue
        lowered = candidate.lower()
        if lowered.startswith(("http://", "https://", "data:image/")):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Contrast-safe colour pickers for the chart / highlight surfaces
# ---------------------------------------------------------------------------

# Distinguishable fallback palette for teams whose own brand colour is
# either too light to read on the report's white surface or
# indistinguishable from the other team's colour. ``team_index`` is
# 0-based so callers can use ``[team-1]``.
_CHART_FALLBACK = ("#0047AB", "#E21836")
# Luminance threshold above which the colour is "too light" for the
# white-ish report background. Computed as relative luminance per
# WCAG so 0.0 == black, 1.0 == white. ~0.85 keeps pastels usable but
# rejects pure white / very light yellows.
_LIGHTNESS_REJECT = 0.85


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int] | None:
    """Parse ``#RGB`` / ``#RRGGBB`` into ``(r, g, b)`` ∈ [0, 255]."""
    if not isinstance(hex_color, str) or not _HEX_COLOR_RE.match(hex_color):
        return None
    body = hex_color.lstrip("#")
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    return (int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16))


def _relative_luminance(hex_color: str) -> float | None:
    """WCAG relative luminance for *hex_color*, or ``None`` on failure."""
    rgb = _hex_to_rgb(hex_color)
    if rgb is None:
        return None

    def _channel(v: int) -> float:
        c = v / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (_channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _chart_color(team: int, primary: str, fg: str) -> str:
    """Pick a chart-/highlight-safe colour for *team*.

    The team's primary brand colour is used when it has acceptable
    contrast against the report's white background. Otherwise we
    fall back to the team's text colour (which is, by design,
    high-contrast against the brand colour and usually against
    the page too) and finally to a fixed palette. This keeps every
    rendered datapoint visible without losing team identity.
    """
    candidates = [primary, fg, _CHART_FALLBACK[(team - 1) % 2]]
    for candidate in candidates:
        lum = _relative_luminance(candidate)
        if lum is not None and lum < _LIGHTNESS_REJECT:
            return candidate
    return _CHART_FALLBACK[(team - 1) % 2]


def _ensure_distinct_chart_colors(c1: str, c2: str) -> tuple[str, str]:
    """If both teams resolve to the same chart colour, force team 2 to fallback."""
    if c1.lower() != c2.lower():
        return c1, c2
    fallback = _CHART_FALLBACK[1] if c1.lower() != _CHART_FALLBACK[1].lower() \
        else _CHART_FALLBACK[0]
    return c1, fallback


# ---------------------------------------------------------------------------
# Original ``_compute_stats`` continues here (kept logically below the
# helpers above so the highlight / chart block has the colour-safety
# tools imported by name).
# ---------------------------------------------------------------------------


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

    grid_lines = "".join(
        f'<line x1="{pad_x_left}" y1="{_project(0, v)[1]:.1f}" '
        f'x2="{pad_x_left + plot_w}" y2="{_project(0, v)[1]:.1f}" '
        f'stroke="#e0e0e0" stroke-width="1" stroke-dasharray="2,3" />'
        for v in y_ticks
    )

    y_labels = "".join(
        f'<text x="{pad_x_left - 4}" y="{_project(0, v)[1] + 3:.1f}" '
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
        f'<text x="{pad_x_left}" y="{height - 8}" text-anchor="start" '
        f'font-size="9" fill="#999">{html.escape(left_label)}</text>'
        f'<text x="{pad_x_left + plot_w}" y="{height - 8}" '
        f'text-anchor="end" font-size="9" fill="#999">{html.escape(right_label)}</text>'
    )

    def _polyline(team_idx: int, color: str) -> str:
        coords = " ".join(
            f"{x:.1f},{y:.1f}"
            for x, y in (_project(i, p[team_idx]) for i, p in enumerate(points))
        )
        return (
            f'<polyline fill="none" stroke="{html.escape(color)}" '
            f'stroke-width="2" points="{coords}" />'
        )

    def _markers(team_idx: int, color: str) -> str:
        # ``r=2.5`` so they sit just above polyline thickness — big
        # enough to read on print, small enough not to obscure rapid
        # back-and-forth swings in volleyball-style 25-point sets.
        return "".join(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" '
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


def _render_set_durations_row(durations: dict[int, float], set_count: int) -> str:
    cells = []
    for i in range(1, set_count + 1):
        if i in durations:
            cells.append(f"<td>{html.escape(_fmt_seconds(durations[i]))}</td>")
        else:
            cells.append("<td>—</td>")
    return "".join(cells)


_PT_LABEL_KEYS = {
    "ace": "pointTypeAce",
    "kill": "pointTypeKill",
    "block": "pointTypeBlock",
    "opp_error": "pointTypeOppError",
}
_ET_LABEL_KEYS = {
    "serve_error": "errorTypeServe",
    "attack_error": "errorTypeAttack",
    "reception_error": "errorTypeReception",
    "ball_handling": "errorTypeBallHandling",
    "net_fault": "errorTypeNet",
    "position_fault": "errorTypePosition",
    "other": "errorTypeOther",
}


def _pct(n: int, denom: int) -> int:
    return round(100 * n / denom) if denom else 0


def _comeback_card(
    card, team_label, locale: str, data: dict, *,
    qualifies: bool, label_key: str, value_key: str,
) -> None:
    """Append one comeback highlight card (set-win or partial flavour).

    *data* is the per-team ``{team: {"deficit", "set"}}`` accumulator
    from ``_compute_stats``. When both teams' best deficit is the same,
    a single tied-card is rendered instead of arbitrarily picking one
    team. *qualifies* carries the flavour-specific threshold check.
    """
    if not qualifies:
        return
    d1 = (data.get(1) or {}).get("deficit", 0)
    d2 = (data.get(2) or {}).get("deficit", 0)
    if d1 == d2:
        card(
            _t(locale, label_key),
            _t(locale, "pointsValue", n=max(d1, d2)),
            _t(locale, "comebackTie"),
        )
        return
    team = 1 if d1 > d2 else 2
    entry = data[team]
    card(
        _t(locale, label_key),
        _t(locale, value_key, n=entry["deficit"], set=entry.get("set") or "?"),
        team_label(team),
    )


def _point_composition_cards(
    card, team_label, locale: str,
    point_types: dict, totals_by_team: dict,
) -> None:
    """Point composition: how each team scored, each type as a share
    of that team's total points won (the remainder, if any, is
    untagged). One card per team with at least one classified point.
    """
    for team in (1, 2):
        counts = point_types.get(team) or {}
        total_typed = sum(v for v in counts.values() if isinstance(v, int))
        if total_typed <= 0:
            continue
        team_total = totals_by_team.get(team) or 0
        parts = []
        for k in ("ace", "kill", "block", "opp_error"):
            n = counts.get(k) or 0
            if not n:
                continue
            # "Label: N" (plural category label) reads grammatically at
            # any count, unlike "N label" which yields "3 kill".
            label = f"{_t(locale, _PT_LABEL_KEYS[k])}: {n}"
            if team_total:
                label += f" ({_pct(n, team_total)}%)"
            parts.append(label)
        card(
            f"{team_label(team)} · {_t(locale, 'pointTypesHeading')}",
            str(total_typed),
            " · ".join(parts),
        )


def _own_error_cards(
    card, team_label, locale: str,
    point_types: dict, error_types: dict, totals_by_team: dict,
) -> None:
    """Own errors: points a team gave away through its own faults,
    i.e. the opponent's ``opp_error`` tally (and its cause breakdown),
    plus the share of the opponent's points those mistakes accounted
    for.
    """
    for team in (1, 2):
        opp = 2 if team == 1 else 1
        gifted = (point_types.get(opp) or {}).get("opp_error") or 0
        if gifted <= 0:
            continue
        opp_total = totals_by_team.get(opp) or 0
        errs = error_types.get(opp) or {}
        # "Label: N" (plural cause label) — grammatical at any count and
        # self-describing, so no separate "errors:" lead-in is needed.
        err_parts = [
            f"{_t(locale, _ET_LABEL_KEYS[k])}: {errs[k]}"
            for k in ERROR_TYPES
            if errs.get(k)
        ]
        detail = (
            _t(locale, "ownErrorsShare", pct=_pct(gifted, opp_total))
            if opp_total else ""
        )
        if err_parts:
            sep = " — " if detail else ""
            detail += sep + " · ".join(err_parts)
        card(
            f"{team_label(team)} · {_t(locale, 'ownErrorsHeading')}",
            str(gifted),
            detail,
        )


def _render_highlights(
    stats: dict, locale: str,
    *, team1_name: str, team2_name: str,
) -> str:
    """Build the Highlights grid (longest streak / comeback / totals / set durations).

    *team1_name* / *team2_name* are the human-readable team labels so
    the cards say "Alpha" instead of the cryptic "Team 1". Falls back
    to the i18n ``team`` template when a card references a team
    number we somehow can't map (defensive — shouldn't happen).
    """
    cards: list[str] = []

    def _team_label(team: int | None) -> str:
        if team == 1:
            return team1_name
        if team == 2:
            return team2_name
        if team:
            return _t(locale, "team", team=team)
        return ""

    def _card(label: str, value: str, detail: str = "") -> None:
        detail_html = (
            f'<div class="detail">{html.escape(detail)}</div>' if detail else ""
        )
        cards.append(
            f'<div class="highlight"><div class="label">{html.escape(label)}</div>'
            f'<div class="value">{html.escape(value)}</div>{detail_html}</div>'
        )

    streak = stats.get("longest_streak") or {}
    if streak.get("n", 0) >= 2 and streak.get("team"):
        _card(
            _t(locale, "highlightStreak"),
            _t(locale, "pointsValue", n=streak["n"]),
            f"{_team_label(streak['team'])} · "
            + _t(locale, "setLabel", n=streak.get("set") or "?"),
        )

    # Set-winning comeback: surface only big erased deficits (≥5 pts).
    set_win = stats.get("set_win_comeback") or {}
    sw_max = max(
        (set_win.get(1) or {}).get("deficit", 0),
        (set_win.get(2) or {}).get("deficit", 0),
    )
    _comeback_card(
        _card, _team_label, locale, set_win,
        qualifies=sw_max >= 5,
        label_key="highlightComeback",
        value_key="deltaValue",
    )

    # Partial comeback: a deficit a team trimmed but couldn't close.
    # Threshold > 3 pts so we don't celebrate a one-rally swing.
    partial = stats.get("partial_comeback") or {}
    p_max = max(
        (partial.get(1) or {}).get("deficit", 0),
        (partial.get(2) or {}).get("deficit", 0),
    )
    _comeback_card(
        _card, _team_label, locale, partial,
        qualifies=p_max > 3,
        label_key="highlightPartialComeback",
        value_key="partialDeltaValue",
    )

    rally = stats.get("longest_rally") or {}
    rally_duration = rally.get("duration_s") or 0
    if rally_duration >= 1 and rally.get("set"):
        # Sub-second rallies are noise (back-to-back action_log
        # appends at the same wallclock); only show when there's
        # actually a measurable gap.
        _card(
            _t(locale, "highlightLongestRally"),
            _fmt_seconds(rally_duration),
            _t(locale, "setLabel", n=rally["set"]),
        )

    total = stats.get("total_points", 0)
    if total:
        _card(_t(locale, "highlightTotalPoints"), str(total))

    durations = stats.get("set_durations") or {}
    if durations:
        longest = max(durations.items(), key=lambda kv: kv[1])
        shortest = min(durations.items(), key=lambda kv: kv[1])
        _card(
            _t(locale, "highlightLongestSet"),
            _fmt_seconds(longest[1]),
            _t(locale, "setLabel", n=longest[0]),
        )
        if shortest[0] != longest[0]:
            _card(
                _t(locale, "highlightShortestSet"),
                _fmt_seconds(shortest[1]),
                _t(locale, "setLabel", n=shortest[0]),
            )

    # Per-point classification breakdown (opt-in scouting tags). One
    # card per team that recorded at least one classified point; the
    # value is the classified total and the detail spells out the mix,
    # with opponent errors further broken down by cause when tracked.
    point_types = stats.get("point_types") or {}
    error_types = stats.get("error_types") or {}
    totals_by_team = stats.get("total_points_by_team") or {}
    _point_composition_cards(
        _card, _team_label, locale, point_types, totals_by_team,
    )
    _own_error_cards(
        _card, _team_label, locale, point_types, error_types, totals_by_team,
    )

    if not cards:
        # Empty matches still render an explicit "no highlights" card
        # rather than collapsing the whole section into a void.
        _card(_t(locale, "highlights"), "—")
    return "".join(cards)


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
        legend = (
            f'<div class="legend">'
            f'<span class="swatch" style="background: {html.escape(t1_color)};"></span>{html.escape(t1_name)}'
            f'<span class="swatch" style="background: {html.escape(t2_color)};"></span>{html.escape(t2_name)}'
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


def _render_timeline(
    audit: list[dict], locale: str, set_count: int,
    *, base_ts: float | None = None,
) -> str:
    """Group the audit by set and emit running-score-aware list items.

    *audit* is expected to already be collapsed via
    ``_collapse_undos`` upstream — every consumer in the report
    pipeline shares the same collapsed slice so the timeline,
    timeouts row, highlights and charts stay coherent.

    *base_ts* is the explicit match-start anchor (Start-match
    button or first-point auto-arm). When supplied, relative
    timestamps are measured from there — so a point scored 5 min
    after Start-match reads ``+5:00``, not ``+0:00``. Falls back
    to the first audit record's ts for legacy snapshots without
    an anchor.
    """
    if not audit:
        return f'<em>{html.escape(_t(locale, "noAudit"))}</em>'

    if base_ts is None:
        base_ts = next(
            (r.get("ts") for r in audit
             if isinstance(r.get("ts"), (int, float))),
            None,
        )

    by_set: dict[int, list[dict]] = {}
    orphans: list[dict] = []
    for record in audit:
        set_num = _result_set(record)
        target = by_set.setdefault(set_num, []) if set_num else orphans
        target.append(record)

    blocks: list[str] = []
    ordered_keys = [k for k in range(1, set_count + 1) if k in by_set]
    # Include any audit-mentioned set numbers above the formal limit
    # (e.g. data corruption / mode change). They go at the end so the
    # natural set order still reads top-to-bottom.
    for k in sorted(by_set.keys()):
        if k not in ordered_keys:
            ordered_keys.append(k)

    def _render_li(record: dict) -> str:
        rel = _format_relative_ts(record.get("ts"), base_ts)
        label = _action_label(record, locale)
        running = _running_score_pair(record)
        running_html = (
            f' <span class="running">({running[0]}–{running[1]})</span>'
            if running and _is_score_action(record) else ""
        )
        # Per-action-type chip: gives the timeline visual hierarchy
        # without changing the editorial text. Colour is keyed off
        # the action kind, not the team — team identity is already
        # encoded in the label and would clash with the
        # add_set/timeout / serve / reset / score-edit chip palette
        # if we tried to layer both. ``_collapse_undos`` already
        # removed every undo pair upstream, so no row that reaches
        # this function carries an undone state.
        action = record.get("action", "")
        params = record.get("params") or {}
        team = params.get("team")
        chip_kind, chip_icon = _chip_classifier(action, team)
        chip_glyph = (
            f'<span class="chip-glyph chip-glyph-{chip_kind}" '
            f'aria-hidden="true">{html.escape(chip_icon)}</span>'
        )
        return (
            f'<li class="timeline-li chip-{chip_kind}">{chip_glyph}'
            f'<span class="ts">{html.escape(rel)}</span>'
            f'{html.escape(label)}{running_html}</li>'
        )

    for set_num in ordered_keys:
        records = by_set[set_num]
        items = "".join(_render_li(r) for r in records)
        blocks.append(
            f'<section class="timeline-set">'
            f'<h3>{html.escape(_t(locale, "groupedSetLabel", n=set_num))}</h3>'
            f'<ol>{items}</ol></section>'
        )

    if orphans:
        items = "".join(_render_li(r) for r in orphans)
        blocks.append(
            f'<section class="timeline-set">'
            f'<ol>{items}</ol></section>'
        )

    # Mini legend so the per-action chip palette is decodable at a
    # glance. The order is the catalogue's declaration order; each
    # ``legend_key=None`` entry is skipped (e.g. the generic
    # ``point`` and the ``other`` fallback don't earn a row of
    # their own — they overlap semantically with the team-bound
    # points and an unrenderable action respectively).
    legend_html_parts: list[str] = []
    for kind, meta in _CHIP_CATALOGUE.items():
        legend_key = meta.get("legend_key")
        if not legend_key:
            continue
        label = _t(locale, legend_key)
        legend_html_parts.append(
            '<span class="timeline-legend-item">'
            f'<span class="chip-glyph chip-glyph-{kind}" aria-hidden="true">'
            f'{html.escape(_chip_glyph(kind))}</span>'
            f'{html.escape(label)}</span>'
        )
    blocks.append(
        f'<div class="timeline-legend">{"".join(legend_html_parts)}</div>',
    )

    return "".join(blocks) or f'<em>{html.escape(_t(locale, "noAudit"))}</em>'


def _render_logo(customization: dict, team: int) -> str:
    url = _logo_url(customization, team)
    if not url:
        return ""
    return (
        f'<img class="logo" src="{html.escape(url)}" '
        f'alt="" loading="lazy" decoding="async" />'
    )
