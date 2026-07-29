"""Contrast-safe color selection for report charts and highlights."""

from __future__ import annotations

import math
import re

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


# ---------------------------------------------------------------------------
# Contrast-safe colour pickers for the chart / highlight surfaces
# ---------------------------------------------------------------------------

# Distinguishable fallback palette for teams whose own brand colour is
# either too light to read on the report's surface or indistinguishable
# from the other team's colour. ``team_index`` is 0-based so callers can
# use ``[team-1]``.
_CHART_FALLBACK = ("#0047AB", "#E21836")
# The neutral surface the charts / highlights are drawn on — must track
# ``--surface`` in ``app/match_report_template.py`` (the ``.chart-card``
# background). Team colours are accepted for the polyline layer only when
# they clear a real contrast ratio against *this* colour; a bare luminance
# cap used to wave through light greys (e.g. ``#d3d3d3``) that then melted
# into the surface.
_CHART_SURFACE = "#fafafa"
# Dark-scheme counterparts: must track the dark ``--surface`` override in
# the template's ``prefers-color-scheme: dark`` block. The fallback pair
# is the light palette's cobalt/red lifted until it reads on the dark
# surface (pinned by a contrast test).
_CHART_SURFACE_DARK = "#1e1e1e"
_CHART_FALLBACK_DARK = ("#5b9bff", "#ff6b6b")
# WCAG 1.4.11 (non-text contrast) minimum for graphical objects. A chart
# polyline below this against the surface is treated as invisible, so we
# darken the brand colour (or fall back) until it clears the floor.
_MIN_CHART_CONTRAST = 3.0


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


def _contrast_ratio(c1: str, c2: str) -> float | None:
    """WCAG contrast ratio between two hex colours (>= 1), or ``None``."""
    l1 = _relative_luminance(c1)
    l2 = _relative_luminance(c2)
    if l1 is None or l2 is None:
        return None
    lighter, darker = (l1, l2) if l1 >= l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


def _darken_to_contrast(hex_color: str, surface: str, min_ratio: float) -> str | None:
    """Darken *hex_color* toward black until it clears *min_ratio* on *surface*.

    Hue is preserved (RGB is scaled toward black), so a light-but-coloured
    brand — a pale green, a sky blue — stays recognisably itself instead of
    snapping to the generic blue/red palette; an achromatic colour (white,
    grey) becomes a visible neutral. Against a *light* surface, contrast
    rises monotonically as the colour darkens, so a binary search finds the
    lightest scale (closest to the original) that still reads. Returns
    ``None`` only when *hex_color* doesn't parse. Black (the limit) always
    clears the floor on a light surface, so a parseable colour always
    resolves to something visible.
    """
    rgb = _hex_to_rgb(hex_color)
    if rgb is None:
        return None
    lo, hi = 0.0, 1.0
    best = "#000000"  # the dark limit always clears the floor on a light surface
    for _ in range(8):
        mid = (lo + hi) / 2.0
        scaled = "#{:02x}{:02x}{:02x}".format(*(round(c * mid) for c in rgb))
        ratio = _contrast_ratio(scaled, surface)
        if ratio is not None and ratio >= min_ratio:
            best = scaled   # readable — try lighter (nearer the brand colour)
            lo = mid
        else:
            hi = mid        # too light — darken further
    return best


def _lighten_to_contrast(hex_color: str, surface: str, min_ratio: float) -> str | None:
    """Lighten *hex_color* toward white until it clears *min_ratio* on *surface*.

    The dark-surface mirror of :func:`_darken_to_contrast`: each channel is
    scaled toward 255, so a dark-but-coloured brand (navy, maroon) stays
    recognisably itself instead of snapping to the generic fallback pair.
    Against a *dark* surface, contrast rises monotonically as the colour
    lightens, so the same binary search finds the darkest scale (closest to
    the original) that still reads. Returns ``None`` only when *hex_color*
    doesn't parse — white (the limit) always clears the floor on a dark
    surface.
    """
    rgb = _hex_to_rgb(hex_color)
    if rgb is None:
        return None
    lo, hi = 0.0, 1.0
    best = "#ffffff"  # the light limit always clears the floor on a dark surface
    for _ in range(8):
        mid = (lo + hi) / 2.0
        scaled = "#{:02x}{:02x}{:02x}".format(
            *(round(c + (255 - c) * mid) for c in rgb)
        )
        ratio = _contrast_ratio(scaled, surface)
        if ratio is not None and ratio >= min_ratio:
            best = scaled   # readable — try darker (nearer the brand colour)
            hi = mid
        else:
            lo = mid        # too dark — lighten further
    return best


def _chart_color(
    team: int, primary: str, fg: str, *,
    surface: str = _CHART_SURFACE,
    fallbacks: tuple[str, str] = _CHART_FALLBACK,
) -> str:
    """Pick a chart-/highlight-safe colour for *team*.

    Priority, all measured as a real WCAG contrast ratio against the
    report's neutral *surface* (not a bare luminance cap):

    1. the team's primary brand colour, when it already reads on the surface;
    2. otherwise the team's text colour, which is high-contrast against the
       brand by design and usually against the page too;
    3. otherwise the brand colour nudged just enough to read — darkened on a
       light surface, lightened on a dark one — keeping the team's hue
       rather than discarding its identity;
    4. and finally the fixed *fallbacks* palette (only when nothing parses).

    This keeps every datapoint visible regardless of how light (or dark)
    the brand colour is. The defaults keep existing callers on the light
    palette; the dark-scheme pass swaps in ``_CHART_SURFACE_DARK`` /
    ``_CHART_FALLBACK_DARK``.
    """
    for candidate in (primary, fg):
        ratio = _contrast_ratio(candidate, surface)
        if ratio is not None and ratio >= _MIN_CHART_CONTRAST:
            return candidate
    surface_luminance = _relative_luminance(surface)
    if surface_luminance is not None and surface_luminance < 0.5:
        nudged = _lighten_to_contrast(primary, surface, _MIN_CHART_CONTRAST)
    else:
        nudged = _darken_to_contrast(primary, surface, _MIN_CHART_CONTRAST)
    return nudged if nudged is not None else fallbacks[(team - 1) % 2]


def _color_distance(c1: str, c2: str) -> float:
    """Euclidean RGB distance between two hex colours.

    Unparseable input returns ``inf`` — "can't tell" must never trigger
    the collision swap, mirroring ``colorDistance`` in
    ``overlay_static/js/spectator.js``.
    """
    rgb1 = _hex_to_rgb(c1)
    rgb2 = _hex_to_rgb(c2)
    if rgb1 is None or rgb2 is None:
        return float("inf")
    return math.dist(rgb1, rgb2)


# Two chart colours closer than this read as a single trace at the
# report's polyline stroke width — an exact-equality check used to wave
# through near-identical pairs (e.g. both teams resolving to near-white
# on the dark surface). Keep in sync with ``COLOR_COLLISION_THRESHOLD``
# in ``overlay_static/js/spectator.js``, which was tuned empirically on
# the bundled theme palettes.
_CHART_COLOR_COLLISION_THRESHOLD = 60.0


def _ensure_distinct_chart_colors(
    c1: str, c2: str, *,
    fallbacks: tuple[str, str] = _CHART_FALLBACK,
) -> tuple[str, str]:
    """If the teams' chart colours are too close to tell apart, swap team 2's.

    Perceptual closeness, not just exact equality: two brands that both
    resolve to (say) near-white on the dark surface would otherwise
    render as one line. Team 2 gets the fallback farthest from team 1's
    colour — the fallback pair is far enough apart that the farther one
    is always distinguishable from ``c1``.
    """
    if _color_distance(c1, c2) > _CHART_COLOR_COLLISION_THRESHOLD:
        return c1, c2
    fallback = fallbacks[0] \
        if _color_distance(c1, fallbacks[0]) >= _color_distance(c1, fallbacks[1]) \
        else fallbacks[1]
    return c1, fallback


# ---------------------------------------------------------------------------
# Original ``_compute_stats`` continues here (kept logically below the
# helpers above so the highlight / chart block has the colour-safety
# tools imported by name).
# ---------------------------------------------------------------------------
