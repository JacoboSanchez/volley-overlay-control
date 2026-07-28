"""HTML/SVG fragment builders for packaged match-report pages.

Split out of :mod:`app.match_report`: formatting helpers, contrast-safe
chart colours, and the renderers for the highlights grid, score charts,
timeline and the matches-index table. Page templates live in
:mod:`app.match_report_template`.
"""

from __future__ import annotations

import datetime
import html
import re
from typing import Any

from app.api.schemas import is_safe_logo_url
from app.match_report import cards as _cards
from app.match_report import charts as _charts
from app.match_report import color_utils as _color_utils
from app.match_report.i18n import t as _t
from app.match_report.stats import _is_score_action, _result_set, _running_score_pair


def __getattr__(name: str) -> Any:
    """Forward historical render-module helpers to their focused modules."""
    for module in (_cards, _charts, _color_utils):
        try:
            return getattr(module, name)
        except AttributeError:
            continue
    raise AttributeError(name)

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


def _fmt_ts_html(ts: float | None) -> str:
    """``_fmt_ts`` wrapped in a span carrying the raw epoch.

    The ``data-utc-ts`` attribute is the hook for the template's
    progressive-enhancement script, which rewrites the text into the
    viewer's local time; without JS (and in any non-browser consumer)
    the server-rendered UTC string stands. Missing/invalid inputs
    render the bare ``—``, and a non-numeric-but-parseable value (a
    stringified epoch from a legacy archive) degrades to the plain
    UTC text — an epoch span is only emitted for a real number.
    """
    if not isinstance(ts, (int, float)):
        return _fmt_ts(ts)
    text = _fmt_ts(ts)
    if text == "—":
        return text
    return f'<span data-utc-ts="{int(ts)}">{text}</span>'


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

    Delegates to :func:`app.api.schemas.is_safe_logo_url` — the single
    source of truth for what may reach an ``<img src=…>`` — so hosted
    same-origin icons (``/media/icons/…``) render in the report while
    ``javascript:``-style payloads stay out.
    """
    for key in (f"Team {team} Logo", f"team_{team}_logo", f"logo{team}"):
        value = customization.get(key)
        if not isinstance(value, str):
            continue
        candidate = value.strip()
        if not candidate:
            continue
        if is_safe_logo_url(candidate):
            return candidate
    return None


def _render_set_durations_row(durations: dict[int, float], set_count: int) -> str:
    cells = []
    for i in range(1, set_count + 1):
        if i in durations:
            cells.append(f"<td>{html.escape(_fmt_seconds(durations[i]))}</td>")
        else:
            cells.append("<td>—</td>")
    return "".join(cells)


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
