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

Destructive actions (``DELETE /matches/{match_id}``) keep their own
flag, ``MATCH_REPORT_PUBLIC_DELETE``: when ``true`` the delete route
no longer requires the admin token. This is intentionally separate
from ``MATCH_REPORT_PUBLIC`` so that public *read* doesn't silently
unlock public *delete* — the operator has to opt in to each.
"""

from __future__ import annotations

import datetime
import html
import logging
import re
import time
from typing import overload

from fastapi import APIRouter, Header, HTTPException, Query, Response
from fastapi.responses import HTMLResponse

from app.api import match_archive
from app.auth_utils import require_admin_token as _require_admin_token
from app.env_vars_manager import EnvVarsManager
from app.match_report_i18n import (
    SUPPORTED_LOCALES,
    resolve_locale,
)
from app.match_report_i18n import t as _t


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


_TRUTHY_ENV = ("1", "true", "t", "yes", "on")


def _is_env_enabled(key: str) -> bool:
    """``True`` when env var *key* parses as a truthy boolean string."""
    raw = EnvVarsManager.get_env_var(key, "false")
    return str(raw).strip().lower() in _TRUTHY_ENV


def _public_mode_enabled() -> bool:
    return _is_env_enabled("MATCH_REPORT_PUBLIC")


def _public_delete_enabled() -> bool:
    """``True`` when the operator has opted into unauthenticated delete.

    Independent from :func:`_public_mode_enabled` on purpose: granting
    public read shouldn't silently authorise public destruction.
    """
    return _is_env_enabled("MATCH_REPORT_PUBLIC_DELETE")


def _check_access(
    authorization: str | None,
    token: str | None,
    *,
    match_id: str | None = None,
    exp: str | None = None,
    sig: str | None = None,
) -> None:
    """Raise an ``HTTPException`` unless the caller is allowed to read.

    Order of precedence:
      1. ``MATCH_REPORT_PUBLIC=true`` — open access (matches the
         existing ``/overlay/{output_key}`` model);
      2. a valid HMAC signature on ``(match_id, exp)`` (capability URL
         minted by the admin endpoint, no password in the link);
      3. otherwise, ``OVERLAY_MANAGER_PASSWORD`` must be set and
         provided via Bearer header or ``?token=`` query (legacy);
      4. when neither password nor signature works and no public-read
         mode is enabled, return 503 to make misconfiguration loud
         rather than silently public.
    """
    if _public_mode_enabled():
        return
    # Capability URL — no need for the password to be on the wire.
    # Signed URLs are minted by the admin endpoint and embed an
    # ``exp`` that lets the operator share a short-lived link
    # without leaking ``OVERLAY_MANAGER_PASSWORD``.
    if match_id is not None and (exp or sig):
        from app.match_report_signing import verify_signed_query
        if verify_signed_query(match_id, exp, sig):
            return
        # Falling through is intentional: an invalid sig should not
        # leak via a different error than an invalid token, so the
        # require_admin_token call below produces the canonical 401/403.
    _require_admin_token(
        authorization, token,
        # Bandit B106 false positive: this is the error message shown
        # when the password env var is unset, not a hardcoded credential.
        missing_password_detail=(  # nosec B106
            "Match reports are disabled. Set OVERLAY_MANAGER_PASSWORD "
            "for gated access or MATCH_REPORT_PUBLIC=true for open "
            "access."
        ),
    )


def _check_admin_access(authorization: str | None, token: str | None) -> None:
    """Stricter sibling of :func:`_check_access` for destructive actions.

    The public-mode shortcut from :func:`_check_access` deliberately does
    not apply here: ``MATCH_REPORT_PUBLIC=true`` grants read-only access
    (anyone with a non-guessable ``match_id`` can view a report), but
    deletion must still go through the admin token. When
    ``OVERLAY_MANAGER_PASSWORD`` is unset the operator has no way to
    authenticate destructive calls — return 503 rather than silently
    accepting them.
    """
    _require_admin_token(
        authorization, token,
        # Bandit B106 false positive: this is the error message shown
        # when the password env var is unset, not a hardcoded credential.
        missing_password_detail=(  # nosec B106
            "Destructive match-archive actions are disabled. "
            "Set OVERLAY_MANAGER_PASSWORD to enable them."
        ),
    )


_REPORT_TEMPLATE = """<!doctype html>
<html lang="{locale}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root {{
    --fg: #1a1a1a;
    --muted: #666;
    --border: #d0d0d0;
    --surface: #fafafa;
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
  .toolbar {{
    display: flex;
    gap: 8px;
    margin: 12px 0 0;
    flex-wrap: wrap;
  }}
  .toolbar button {{
    cursor: pointer;
    font: inherit;
    padding: 6px 12px;
    border: 1px solid var(--border);
    background: #fff;
    border-radius: 4px;
    transition: background 0.1s ease;
  }}
  .toolbar button:hover {{ background: var(--surface); }}
  .toolbar button:disabled {{ opacity: 0.6; cursor: default; }}
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
  .team .logo {{
    max-height: 44px;
    max-width: 80px;
    object-fit: contain;
    margin: 0 auto 6px;
    display: block;
    background: rgba(255, 255, 255, 0.15);
    border-radius: 4px;
  }}
  .team .name {{ font-weight: 600; font-size: 18px; }}
  .team .sets {{ font-size: 56px; line-height: 1; font-weight: 700; }}
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
  h3 {{ font-size: 15px; margin: 14px 0 6px; color: var(--muted); }}
  .highlights {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
    margin: 12px 0;
  }}
  .highlight {{
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    background: var(--surface);
  }}
  .highlight .label {{
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 4px;
  }}
  .highlight .value {{ font-size: 18px; font-weight: 600; }}
  .highlight .detail {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}
  .charts {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px;
    margin: 12px 0;
  }}
  .chart-card {{
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 12px;
    background: var(--surface);
    break-inside: avoid;
  }}
  .chart-card h3 {{ margin: 0 0 4px; }}
  .chart-card .legend {{ font-size: 11px; color: var(--muted); }}
  .chart-card .legend .swatch {{
    display: inline-block;
    width: 8px;
    height: 8px;
    margin: 0 4px 0 8px;
    border-radius: 50%;
  }}
  /* Timeout legend pip mirrors the chart's dashed guide: a thin
     horizontal track of three dashes that visually echoes the
     vertical guides drawn over the polylines. ``border-radius:0``
     overrides the default round-pip style. */
  .chart-card .legend .swatch-timeout {{
    background: repeating-linear-gradient(
      to right,
      var(--muted) 0 2px,
      transparent 2px 4px
    );
    border-radius: 0;
    height: 2px;
    width: 14px;
  }}
  .set-chart {{
    width: 100%;
    height: auto;
    display: block;
  }}
  .timeline {{
    font-size: 13px;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    max-height: 480px;
    overflow: auto;
  }}
  .timeline-set {{ margin-bottom: 12px; }}
  .timeline-set h3 {{ margin: 0 0 6px; }}
  .timeline-set ol {{
    margin: 0;
    padding-left: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }}
  .timeline-set li {{
    margin: 0;
    padding: 4px 8px 4px 10px;
    border-radius: 6px;
    border-left: 3px solid var(--border);
    background: rgba(127, 127, 127, 0.04);
    display: flex;
    align-items: baseline;
    gap: 6px;
    flex-wrap: wrap;
  }}
  /* Per-action accent strip + glyph. Colours stay legible on both
     the dark and light schemes the rest of the report uses, and the
     glyph stays ASCII / a single emoji so the print stylesheet
     doesn't depend on a Material Icons font being loaded.
     Undo records are stripped upstream (``_collapse_undos`` drops
     both halves of every pair) so no ``undone`` modifier is
     emitted. */
  .timeline-set li.chip-point-t1 {{ border-left-color: #2196f3;
    background: rgba(33, 150, 243, 0.07); }}
  .timeline-set li.chip-point-t2 {{ border-left-color: #f44336;
    background: rgba(244, 67, 54, 0.07); }}
  .timeline-set li.chip-point    {{ border-left-color: #607d8b;
    background: rgba(96, 125, 139, 0.07); }}
  .timeline-set li.chip-set      {{ border-left-color: #2e7d32;
    background: rgba(46, 125, 50, 0.10); }}
  .timeline-set li.chip-timeout  {{ border-left-color: #ff9800;
    background: rgba(255, 152, 0, 0.10); }}
  .timeline-set li.chip-serve    {{ border-left-color: #5c6bc0;
    background: rgba(92, 107, 192, 0.07); }}
  .timeline-set li.chip-edit     {{ border-left-color: #ab47bc;
    background: rgba(171, 71, 188, 0.08); }}
  .timeline-set li.chip-reset    {{ border-left-color: #9e9e9e;
    background: rgba(158, 158, 158, 0.10); }}
  .timeline-set li.chip-other    {{ border-left-color: var(--muted);
    background: rgba(127, 127, 127, 0.05); }}
  .chip-glyph {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 22px;
    padding: 0 4px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    line-height: 18px;
    color: #fff;
    background: var(--muted);
    text-decoration: none;
  }}
  .chip-glyph-point-t1 {{ background: #2196f3; }}
  .chip-glyph-point-t2 {{ background: #f44336; }}
  .chip-glyph-point    {{ background: #607d8b; }}
  .chip-glyph-set      {{ background: #2e7d32; }}
  .chip-glyph-timeout  {{ background: #ff9800; color: #1f1300; }}
  .chip-glyph-serve    {{ background: #5c6bc0; }}
  .chip-glyph-edit     {{ background: #ab47bc; }}
  .chip-glyph-reset    {{ background: #9e9e9e; color: #1a1a2e; }}
  .chip-glyph-other    {{ background: transparent;
    color: var(--muted);
    border: 1px solid var(--border); }}
  .timeline-legend {{
    margin: 8px 0 0;
    padding: 8px 10px;
    border-top: 1px dashed var(--border);
    display: flex;
    flex-wrap: wrap;
    gap: 6px 12px;
    font-size: 11px;
    color: var(--muted);
  }}
  .timeline-legend-item {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }}
  @media print {{
    .timeline-set li {{
      background: transparent !important;
      border-left-style: solid;
    }}
    .chip-glyph {{
      background: transparent !important;
      color: var(--muted) !important;
      border: 1px solid var(--border);
    }}
  }}
  .timeline-set li .ts {{
    font-variant-numeric: tabular-nums;
    color: var(--muted);
    margin-right: 6px;
  }}
  .timeline-set li .running {{
    font-variant-numeric: tabular-nums;
    color: var(--muted);
    margin-left: 6px;
  }}
  .footer {{
    margin-top: 32px;
    font-size: 12px;
    color: var(--muted);
    border-top: 1px solid var(--border);
    padding-top: 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }}
  .footer-line {{ word-break: break-word; }}
  .footer-permalink {{
    color: inherit;
    text-decoration: underline;
    text-underline-offset: 2px;
  }}
  @media print {{
    body {{ padding: 0; max-width: none; }}
    .toolbar {{ display: none; }}
    .timeline {{ max-height: none; overflow: visible; }}
    .charts, .highlights, .scoreboard {{ break-inside: avoid; }}
    h2 {{ break-after: avoid; }}
    .timeline-set {{ break-inside: avoid; }}
    /* The Print toolbar can ask the operator to omit the timeline
       from the printout. The class is toggled around the
       ``window.print()`` call and only takes effect at print time. */
    .print-hidden {{ display: none !important; }}
    @page {{ margin: 16mm; }}
  }}
</style>
</head>
<body>
<header>
  <h1>{match_label}</h1>
  <div class="meta">
    {ended_at_display} &middot; {duration_label} {duration_display}
  </div>
  <div class="toolbar" data-permalink="{permalink}">
    <button type="button" data-action="print"
            data-include-prompt="{btn_print_include_prompt}">{btn_print}</button>
    <button type="button" data-action="copy"
            data-default-label="{btn_copy}"
            data-ok-label="{btn_copy_ok}">{btn_copy}</button>
  </div>
</header>

<section class="scoreboard">
  <div class="team t1">
    {team1_logo}
    <div class="name">{team1_name}</div>
    <div class="sets">{team1_sets}</div>
  </div>
  <div class="vs">{versus}</div>
  <div class="team t2">
    {team2_logo}
    <div class="name">{team2_name}</div>
    <div class="sets">{team2_sets}</div>
  </div>
</section>

<h2>{h_set_byset}</h2>
<table>
  <thead>
    <tr><th>{h_team}</th>{set_headers}</tr>
  </thead>
  <tbody>
    <tr><td>{team1_name}</td>{team1_set_cells}</tr>
    <tr><td>{team2_name}</td>{team2_set_cells}</tr>
    <tr><td>{h_set_durations}</td>{set_duration_cells}</tr>
  </tbody>
</table>

<h2>{h_highlights}</h2>
<div class="highlights">{highlights_html}</div>

<h2>{h_score_evolution}</h2>
<div class="charts">{charts_html}</div>

<h2>{h_match_facts}</h2>
<table>
  <tbody>
    <tr><td>{h_match_id}</td><td>{match_id}</td></tr>
    <tr><td>{h_format}</td><td>{format_desc}</td></tr>
    <tr><td>{h_started}</td><td>{started_at_display}</td></tr>
    <tr><td>{h_ended}</td><td>{ended_at_display}</td></tr>
    <tr><td>{h_audit_entries}</td><td>{audit_count}</td></tr>
  </tbody>
</table>

<section id="report-timeline-section">
<h2>{h_timeline}</h2>
<p style="margin: 0 0 8px; font-size: 12px; color: var(--muted);">
  {timeline_hint}
</p>
<div class="timeline">{timeline_html}</div>
</section>

<footer class="footer">
  <div class="footer-line">{footer_text}</div>
  <div class="footer-line">
    <strong>{permalink_label}:</strong>
    <a href="{permalink}" class="footer-permalink">{permalink_display}</a>
  </div>
  <div class="footer-line">
    <strong>{generated_label}:</strong> {generated_at_display}
  </div>
</footer>

<script>
(function() {{
  const toolbar = document.querySelector('.toolbar');
  if (!toolbar) return;
  const permalink = toolbar.getAttribute('data-permalink') || window.location.href;
  const printBtn = toolbar.querySelector('button[data-action="print"]');
  const includePrompt = printBtn ? printBtn.getAttribute('data-include-prompt') : '';
  const timelineSection = document.getElementById('report-timeline-section');
  toolbar.addEventListener('click', async (event) => {{
    const target = event.target.closest('button[data-action]');
    if (!target) return;
    const action = target.getAttribute('data-action');
    if (action === 'print') {{
      // ``confirm`` returns true when the operator wants the timeline
      // included; declining hides the section just for the duration
      // of the print dialog and restores it afterwards. Falsy
      // ``timelineSection`` (no timeline emitted at all) skips the
      // toggle so we never strip a missing element.
      const include = includePrompt
        ? window.confirm(includePrompt)
        : true;
      if (!include && timelineSection) {{
        timelineSection.classList.add('print-hidden');
      }}
      try {{
        window.print();
      }} finally {{
        if (!include && timelineSection) {{
          timelineSection.classList.remove('print-hidden');
        }}
      }}
      return;
    }}
    if (action === 'copy') {{
      const ok = target.getAttribute('data-ok-label');
      const def = target.getAttribute('data-default-label');
      const restore = () => {{ target.textContent = def; target.disabled = false; }};
      try {{
        if (navigator.clipboard && navigator.clipboard.writeText) {{
          await navigator.clipboard.writeText(permalink);
        }} else {{
          // Older browsers: fall back to a transient textarea so the
          // toolbar still reports something useful.
          const ta = document.createElement('textarea');
          ta.value = permalink;
          ta.setAttribute('readonly', 'true');
          ta.style.position = 'absolute';
          ta.style.left = '-9999px';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          ta.remove();
        }}
        target.textContent = ok;
        target.disabled = true;
        setTimeout(restore, 1500);
      }} catch (e) {{
        // Browser denied the clipboard write — leave the label alone
        // rather than silently lying about success.
        console.warn('Copy failed', e);
      }}
    }}
  }});
}})();
</script>
</body>
</html>
"""


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


# ---------------------------------------------------------------------------
# Audit-log derived helpers (running score, undo collapse, stats, charts)
# ---------------------------------------------------------------------------

def _coerce_int(raw: object) -> int | None:
    """Best-effort ``int`` parse for audit-record numeric fields.

    Accepts a real ``int`` directly or a string of digits (some
    archive paths stringify scores). Returns ``None`` for anything
    else. Caller decides whether to apply a positivity filter.
    """
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


@overload
def _safe_int(value: object) -> int | None: ...
@overload
def _safe_int(value: object, default: int) -> int: ...
@overload
def _safe_int(value: object, default: None) -> int | None: ...


def _safe_int(value: object, default: int | None = None) -> int | None:
    """Lenient ``int`` parse: like ``int(value)`` but returns *default* on failure.

    Stricter callers should prefer :func:`_coerce_int`; this helper
    mirrors the inline ``try: int(value) except (TypeError, ValueError)``
    pattern that recurs across set/score parsing.
    """
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return default


def _result_score(record: dict, team: int) -> int | None:
    """Pull the post-action score for *team* out of an audit ``result`` blob."""
    block = (record.get("result") or {}).get(f"team_{team}") or {}
    return _coerce_int(block.get("score"))


def _result_set(record: dict) -> int | None:
    """Set number this audit record applies to (1-indexed).

    Prefers ``result.score_set`` when present: a set-winning
    ``add_point`` advances ``current_set`` to the next set, but the
    scores in the record (e.g. 25-23) belong to the *previous* set,
    and ``score_set`` tags that explicitly. Falls back to
    ``current_set`` for older audit records that predate the
    ``score_set`` field.
    """
    result = record.get("result") or {}
    for key in ("score_set", "current_set"):
        n = _coerce_int(result.get(key))
        if n is not None and n > 0:
            return n
    return None


def _is_score_action(record: dict) -> bool:
    return record.get("action") in ("add_point", "set_score")


def _first_scoring_index(audit: list[dict]) -> int | None:
    """Index of the first non-undo ``add_point`` / ``set_score`` record.

    The audit log starts with whatever the operator did first — often a
    ``reset`` to clear the previous match's state — but a "match" only
    really begins once someone scores. Until the UI exposes a dedicated
    "match start" marker, every report-side time anchor (relative
    timestamps, duration, set durations, stats) snaps to this index.
    Returns ``None`` when the audit has no scoring action at all.
    """
    for index, record in enumerate(audit):
        if (record.get("params") or {}).get("undo"):
            continue
        if _is_score_action(record):
            return index
    return None


def _trim_pregame(audit: list[dict]) -> list[dict]:
    """Drop pre-first-scoring records (``reset``, stray timeouts, …).

    Keeps everything from the first scoring action onward. When the
    audit has no scoring action at all we return ``[]`` — the timeline
    renderer already understands the empty case and shows "no audit
    records", and falling through to the unfiltered list would let the
    pregame noise leak back into the report.
    """
    idx = _first_scoring_index(audit)
    return audit[idx:] if idx is not None else []


def _played_set_count(final_state: dict, fallback: int) -> int:
    """Highest set N with non-zero scoring data, clamped to *fallback*.

    The match-history archive bundles ``team_X.scores.set_N`` for every
    set up to ``sets_limit``, even sets that were never played (best
    of 3 ending 2-0 still has ``set_3``: 0/0). Render only the sets
    that actually saw points so empty trailing columns don't dilute
    the report. When no set has scores yet (fresh archive) we collapse
    to a single set frame rather than painting all ``sets_limit``
    columns full of ``—``s.

    *fallback* is honoured only as an upper bound — corrupt snapshots
    reporting set N > sets_limit shouldn't paint a column the rules
    don't allow.
    """
    teams = (final_state.get("team_1") or {}, final_state.get("team_2") or {})
    highest = 0
    for team in teams:
        scores = team.get("scores") or {}
        for key, value in scores.items():
            if not isinstance(key, str) or not key.startswith("set_"):
                continue
            n = _safe_int(key.removeprefix("set_"))
            if n is None:
                continue
            v = 0 if value is None else _safe_int(value, 0)
            if v > 0:
                highest = max(highest, n)
    if highest == 0:
        return 1
    return min(highest, fallback) if fallback > 0 else highest


def _collapse_undos(audit: list[dict]) -> list[dict]:
    """Drop both halves of every ``undo`` pair from the rendered
    timeline so undone actions never appear in the report.

    Two cases reach this function:

    * Live unified-undo logs (the common case), where
      ``action_log.pop_last_forward`` already removed the original
      forward physically and the audit-log just carries the
      trailing undo record. The orphan undo is dropped because
      the action it referenced no longer exists.
    * Legacy / archived audit logs that still hold both a forward
      record and the explicit undo that reversed it — typically
      from pre-unification snapshots or replay-style fixtures. We
      walk back to the most recent matching forward by
      ``(action, team)`` and remove **both** the forward and the
      undo, mirroring the live behaviour.

    Net result: the report renders "as if the undone action never
    happened". State-level aggregates already reflect the inverse
    (the score / set / timeout counters never recorded the popped
    increment), so the timeline can stay equally clean.
    """
    out: list[dict] = []
    for record in audit:
        params = record.get("params") or {}
        if not params.get("undo"):
            out.append(dict(record))
            continue
        # Walk back for the most recent forward record with the same
        # ``(action, team)`` and remove it. The undo itself never
        # reaches the output either — both halves disappear.
        action = record.get("action")
        team = params.get("team")
        for index in range(len(out) - 1, -1, -1):
            prior = out[index]
            prior_params = prior.get("params") or {}
            if (
                prior.get("action") == action
                and prior_params.get("team") == team
                and not prior_params.get("undo")
            ):
                del out[index]
                break
        # No matching forward → orphan undo. Already not appended
        # above; nothing else to do.
    return out


def _set_durations_from_audit(audit: list[dict]) -> dict[int, float]:
    """Per-set duration in seconds derived from audit timestamps.

    For each set we take ``max_ts - min_ts`` over records whose
    ``current_set`` matches. Sets with fewer than two timestamps fall
    out of the result map (no meaningful duration).
    """
    by_set: dict[int, list[float]] = {}
    for record in audit:
        if record.get("params", {}).get("undo"):
            continue
        set_num = _result_set(record)
        ts = record.get("ts")
        if set_num is None or not isinstance(ts, (int, float)):
            continue
        by_set.setdefault(set_num, []).append(float(ts))
    durations: dict[int, float] = {}
    for set_num, stamps in by_set.items():
        if len(stamps) < 2:
            continue
        durations[set_num] = max(stamps) - min(stamps)
    return durations


def _running_score_pair(record: dict) -> tuple[int, int] | None:
    """``(team1, team2)`` running score after this audit record, if known."""
    s1 = _result_score(record, 1)
    s2 = _result_score(record, 2)
    if s1 is None or s2 is None:
        return None
    return (s1, s2)


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


def _timeouts_per_set(audit: list[dict]) -> dict[int, dict[int, int]]:
    """Count ``add_timeout`` actions per (set, team) from the audit log.

    Per-team timeout counters reset to zero on every set transition
    (see :meth:`GameManager.add_set`), so timeouts are intrinsically
    per-set and the audit log carries enough to rebuild that table
    even though the snapshot's ``team_X.timeouts`` only reflects the
    final set. Returns ``{set_num: {team: count}}``; callers consult
    ``.get(set, {}).get(team, 0)`` for safe lookup.
    """
    out: dict[int, dict[int, int]] = {}
    for record in audit:
        if record.get("action") != "add_timeout":
            continue
        params = record.get("params") or {}
        if params.get("undo"):
            continue
        team = params.get("team")
        set_num = _result_set(record)
        if team not in (1, 2) or set_num is None:
            continue
        out.setdefault(set_num, {}).setdefault(team, 0)
        out[set_num][team] += 1
    return out


def _compute_stats(audit: list[dict]) -> dict:
    """Compute the Highlights block (longest streak, biggest comeback, totals).

    All metrics derive purely from the audit log so the report stays
    consistent with the "scoring trajectory" the audit promises. Set
    points are scored per-set. Comebacks are tracked per-team and
    split into two flavours:

    * ``set_win``: the largest deficit a team erased *and* went on to
      win the set with — i.e. the deficit faced by the eventual set
      winner.
    * ``partial``: the largest deficit reduction (peak deficit minus
      the smallest subsequent deficit) achieved by a team that
      ultimately *lost* the set. This surfaces near-comebacks that
      didn't quite finish.

    Storing both per team lets the renderer detect a tie when both
    sides happen to share the same maximum.
    """
    longest_streak = {"team": None, "n": 0, "set": None}
    # Per-team peak deficit erased by the eventual set winner.
    set_win_comeback: dict[int, dict] = {
        1: {"deficit": 0, "set": None},
        2: {"deficit": 0, "set": None},
    }
    # Per-team peak deficit reduction by a losing team (partial recovery).
    partial_comeback: dict[int, dict] = {
        1: {"deficit": 0, "set": None},
        2: {"deficit": 0, "set": None},
    }
    longest_rally = {"duration_s": 0.0, "set": None}
    total_points = 0

    by_set: dict[int, list[dict]] = {}
    for record in audit:
        if record.get("params", {}).get("undo"):
            continue
        set_num = _result_set(record)
        if set_num is None:
            continue
        by_set.setdefault(set_num, []).append(record)

    for set_num, set_records in by_set.items():
        # Longest streak: count consecutive ``add_point`` actions by
        # the same team. Manual set_score breaks the streak.
        streak_team: int | None = None
        streak_n = 0
        for r in set_records:
            if r.get("action") != "add_point":
                streak_team, streak_n = None, 0
                continue
            team = (r.get("params") or {}).get("team")
            if team == streak_team:
                streak_n += 1
            else:
                streak_team, streak_n = team, 1
            if streak_n > longest_streak["n"]:
                longest_streak = {"team": team, "n": streak_n, "set": set_num}
            total_points += 1

        # Comebacks. Walk the running scores once, then split:
        #   * winner's peak deficit  → set_win comeback for the winner
        #   * loser's peak deficit minus the smallest subsequent deficit
        #     → partial comeback for the loser (they trimmed the gap
        #     but didn't close it).
        if not set_records:
            continue
        last_score = _running_score_pair(set_records[-1])
        if not last_score:
            continue
        winner = 1 if last_score[0] > last_score[1] else 2
        loser = 2 if winner == 1 else 1
        winner_peak_deficit = 0
        loser_peak_deficit = 0
        loser_min_after_peak = 0
        loser_max_recovery = 0
        for r in set_records:
            pair = _running_score_pair(r)
            if not pair:
                continue
            t1, t2 = pair
            winner_deficit = (t2 - t1) if winner == 1 else (t1 - t2)
            loser_deficit = -winner_deficit
            if winner_deficit > winner_peak_deficit:
                winner_peak_deficit = winner_deficit
            if loser_deficit > loser_peak_deficit:
                loser_peak_deficit = loser_deficit
                loser_min_after_peak = loser_deficit
            elif loser_deficit < loser_min_after_peak:
                loser_min_after_peak = loser_deficit
                recovery = loser_peak_deficit - loser_min_after_peak
                if recovery > loser_max_recovery:
                    loser_max_recovery = recovery
        if winner_peak_deficit > set_win_comeback[winner]["deficit"]:
            set_win_comeback[winner] = {
                "deficit": winner_peak_deficit, "set": set_num,
            }
        if loser_max_recovery > partial_comeback[loser]["deficit"]:
            partial_comeback[loser] = {
                "deficit": loser_max_recovery, "set": set_num,
            }

        # Longest rally: the gap between consecutive scoring actions
        # within the set is a proxy for "longest point" — without
        # ball-in-play instrumentation that's the closest the audit
        # log can give us. Restrict to ``add_point`` only: a manual
        # ``set_score`` override is an editorial action (operator
        # correcting a score after the fact) and including it would
        # report the *editing* delay as a rally. The audit log is
        # append-only so ``set_records`` is already in chronological
        # order — no extra sort needed.
        scoring_ts: list[float] = []
        for r in set_records:
            if r.get("action") != "add_point":
                continue
            ts = r.get("ts")
            if isinstance(ts, (int, float)):
                scoring_ts.append(float(ts))
        for i in range(1, len(scoring_ts)):
            delta = scoring_ts[i] - scoring_ts[i - 1]
            if delta > longest_rally["duration_s"]:
                longest_rally = {"duration_s": delta, "set": set_num}

    return {
        "longest_streak": longest_streak,
        "set_win_comeback": set_win_comeback,
        "partial_comeback": partial_comeback,
        "longest_rally": longest_rally,
        "total_points": total_points,
        "set_durations": _set_durations_from_audit(audit),
    }


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

    # Decide axis mode. Time mode requires every record to carry a
    # timestamp *and* no gap between consecutive records to exceed
    # the trust threshold — anything bigger means the operator was
    # AFK and the wallclock no longer tracks play, so we fall back
    # to rally-number indexing rather than compress the whole set
    # into a thin slice on the left.
    times: list[float] | None = None
    if all(t is not None for t in timestamps):
        # ``timestamps`` is structurally ``list[Optional[float]]``;
        # the ``all(...)`` check above narrows it but mypy can't see
        # through it, so build the float-only list explicitly.
        times = [float(t) for t in timestamps if t is not None]
        for i in range(1, len(times)):
            gap = times[i] - times[i - 1]
            # ``gap > threshold``: operator was AFK, wallclock no
            # longer tracks play. ``gap < 0``: non-monotonic
            # timestamps (clock skew, NTP correction) — would
            # otherwise plot points outside the SVG viewport. Both
            # downgrade to the rally-number fallback.
            if gap > _TIME_AXIS_MAX_GAP_S or gap < 0:
                times = None
                break

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
            # Dashed guide spanning the plot height + a small
            # downward triangle perched 6 px above the plot area
            # so it doesn't collide with the polylines or the
            # ``max_score`` Y label.
            items.append(
                f'<line class="set-chart-timeout" data-team="{team}" '
                f'x1="{x:.1f}" y1="{pad_y_top:.1f}" '
                f'x2="{x:.1f}" y2="{pad_y_top + plot_h:.1f}" '
                f'stroke="{color_safe}" stroke-width="1" '
                f'stroke-dasharray="3,3" opacity="0.55" />'
                f'<polygon class="set-chart-timeout-glyph" '
                f'data-team="{team}" '
                f'points="{x - 3:.1f},{pad_y_top - 6:.1f} '
                f'{x + 3:.1f},{pad_y_top - 6:.1f} '
                f'{x:.1f},{pad_y_top:.1f}" '
                f'fill="{color_safe}" />'
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
    # When both teams' best erased deficit is the same, render a single
    # tied-card instead of arbitrarily picking one team.
    set_win = stats.get("set_win_comeback") or {}
    sw1 = (set_win.get(1) or {}).get("deficit", 0)
    sw2 = (set_win.get(2) or {}).get("deficit", 0)
    sw_max = max(sw1, sw2)
    if sw_max >= 5:
        if sw1 == sw2:
            _card(
                _t(locale, "highlightComeback"),
                _t(locale, "pointsValue", n=sw_max),
                _t(locale, "comebackTie"),
            )
        else:
            winner_team = 1 if sw1 > sw2 else 2
            entry = set_win[winner_team]
            _card(
                _t(locale, "highlightComeback"),
                _t(locale, "deltaValue",
                   n=entry["deficit"], set=entry.get("set") or "?"),
                _team_label(winner_team),
            )

    # Partial comeback: a deficit a team trimmed but couldn't close.
    # Threshold > 3 pts so we don't celebrate a one-rally swing.
    partial = stats.get("partial_comeback") or {}
    p1 = (partial.get(1) or {}).get("deficit", 0)
    p2 = (partial.get(2) or {}).get("deficit", 0)
    p_max = max(p1, p2)
    if p_max > 3:
        if p1 == p2:
            _card(
                _t(locale, "highlightPartialComeback"),
                _t(locale, "pointsValue", n=p_max),
                _t(locale, "comebackTie"),
            )
        else:
            loser_team = 1 if p1 > p2 else 2
            entry = partial[loser_team]
            _card(
                _t(locale, "highlightPartialComeback"),
                _t(locale, "partialDeltaValue",
                   n=entry["deficit"], set=entry.get("set") or "?"),
                _team_label(loser_team),
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


@match_report_router.get(
    "/match/{match_id}/report",
    response_class=HTMLResponse,
    summary="Print-friendly HTML report for an archived match",
)
async def match_report(
    match_id: str,
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None,
                                 description="OVERLAY_MANAGER_PASSWORD; "
                                             "alternative to Bearer header."),
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
    _check_access(
        authorization, token, match_id=match_id, exp=exp, sig=sig,
    )
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


# ---------------------------------------------------------------------------
# Matches index — browseable list of every archived match for an OID
# ---------------------------------------------------------------------------

_INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Match history — {oid_label}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root {{
    --fg: #1a1a1a;
    --muted: #666;
    --border: #d0d0d0;
    --hover: #f5f5f5;
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
  header .meta {{ color: var(--muted); font-size: 14px; margin-bottom: 16px; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
  }}
  th, td {{
    text-align: left;
    padding: 10px 8px;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
  }}
  th {{ font-weight: 600; color: var(--muted); }}
  tbody tr:hover {{ background: var(--hover); }}
  td.score {{
    text-align: center;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }}
  td.score .winner {{ color: #2e7d32; }}
  a.report-link, button.row-delete {{
    display: inline-block;
    padding: 4px 10px;
    border: 1px solid var(--border);
    border-radius: 4px;
    text-decoration: none;
    color: var(--fg);
    font-size: 13px;
    background: transparent;
    cursor: pointer;
    font-family: inherit;
  }}
  a.report-link:hover, button.row-delete:hover {{ background: var(--hover); }}
  button.row-delete {{ color: #b71c1c; border-color: #ef9a9a; }}
  button.row-delete:hover {{ background: #fdecea; }}
  th.checkbox-col, td.checkbox-col {{ width: 28px; text-align: center; padding-left: 0; padding-right: 0; }}
  .toolbar {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;
    font-size: 13px;
    color: var(--muted);
  }}
  .toolbar button {{
    padding: 6px 14px;
    border-radius: 4px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--fg);
    cursor: pointer;
    font-family: inherit;
    font-size: 13px;
  }}
  .toolbar button.danger {{
    color: #b71c1c;
    border-color: #ef9a9a;
  }}
  .toolbar button.danger:hover:not(:disabled) {{ background: #fdecea; }}
  .toolbar button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .empty {{
    text-align: center;
    color: var(--muted);
    font-style: italic;
    padding: 32px;
    border: 1px dashed var(--border);
    border-radius: 6px;
  }}
  .footer {{
    margin-top: 24px;
    font-size: 12px;
    color: var(--muted);
    border-top: 1px solid var(--border);
    padding-top: 12px;
  }}
</style>
</head>
<body>
<header>
  <h1>Match history</h1>
  <div class="meta">OID: <code>{oid_label}</code> &middot; {count} match{plural}</div>
</header>

{body_html}

<div class="footer">
  Generated by Volley Overlay Control. Each row links to a print-friendly report.
</div>
</body>
</html>
"""


def _render_match_row(summary: dict, token_qs: str) -> str:
    """Render one row of the index table."""
    match_id = summary.get("match_id") or ""
    t1_sets = summary.get("team_1_sets")
    t2_sets = summary.get("team_2_sets")
    winner = summary.get("winning_team")
    ended = _fmt_ts(summary.get("ended_at"))
    duration = _fmt_seconds(summary.get("duration_s"))

    def _sets_cell(team: int) -> str:
        v = (t1_sets if team == 1 else t2_sets)
        text = "—" if v is None else str(v)
        if winner == team:
            return f'<span class="winner">{html.escape(text)}</span>'
        return html.escape(text)

    safe_id = html.escape(match_id)
    href = f"/match/{safe_id}/report{token_qs}"
    return (
        f'<tr data-match-id="{safe_id}">'
        f'<td class="checkbox-col">'
        f'<input type="checkbox" class="match-checkbox" '
        f'aria-label="Select match {safe_id}" '
        f'data-match-id="{safe_id}"></td>'
        f"<td>{html.escape(ended)}</td>"
        f'<td class="score">{_sets_cell(1)} – {_sets_cell(2)}</td>'
        f"<td>{html.escape(duration)}</td>"
        f'<td><a class="report-link" href="{href}">View report</a></td>'
        f'<td><button type="button" class="row-delete" '
        f'data-match-id="{safe_id}">Delete</button></td>'
        "</tr>"
    )


# Static client-side script for the index page. Pure JS — does not go
# through ``str.format``, so curly braces stay single. Reads the
# operator's token from the page URL (when present) and forwards it to
# DELETE /matches/{id} as a Bearer header so the request authenticates
# the same way the page itself did.
_INDEX_SCRIPT = """
<script>
(function() {
  const url = new URL(window.location.href);
  const token = url.searchParams.get('token');
  const tokenQuery = token ? ('?token=' + encodeURIComponent(token)) : '';
  const headers = {};
  if (token) headers['Authorization'] = 'Bearer ' + token;

  const checkboxes = () =>
    Array.from(document.querySelectorAll('input.match-checkbox'));
  const selectedIds = () =>
    checkboxes().filter(cb => cb.checked).map(cb => cb.dataset.matchId);

  function refreshToolbar() {
    const ids = selectedIds();
    const btn = document.getElementById('delete-selected');
    const counter = document.getElementById('selected-count');
    if (btn) btn.disabled = ids.length === 0;
    if (counter) counter.textContent = ids.length;
    const all = document.getElementById('select-all');
    if (all) {
      const total = checkboxes().length;
      all.checked = total > 0 && ids.length === total;
      all.indeterminate = ids.length > 0 && ids.length < total;
    }
  }

  async function deleteOne(id) {
    const res = await fetch(
      '/matches/' + encodeURIComponent(id) + tokenQuery,
      { method: 'DELETE', headers }
    );
    return res.ok;
  }

  async function deleteIds(ids) {
    if (ids.length === 0) return;
    const label = ids.length === 1 ? '1 match' : (ids.length + ' matches');
    if (!confirm('Delete ' + label + '? This cannot be undone.')) return;
    let failed = 0;
    for (const id of ids) {
      try {
        if (!(await deleteOne(id))) failed++;
      } catch (e) {
        failed++;
      }
    }
    if (failed > 0) {
      alert('Failed to delete ' + failed + ' of ' + ids.length + ' matches.');
    }
    window.location.reload();
  }

  document.addEventListener('change', (e) => {
    if (e.target.matches('input.match-checkbox')) refreshToolbar();
    if (e.target.id === 'select-all') {
      checkboxes().forEach(cb => { cb.checked = e.target.checked; });
      refreshToolbar();
    }
  });

  document.addEventListener('click', (e) => {
    if (e.target.id === 'delete-selected') {
      deleteIds(selectedIds());
    } else if (e.target.matches('button.row-delete')) {
      deleteIds([e.target.dataset.matchId]);
    }
  });

  refreshToolbar();
})();
</script>
"""


@match_report_router.get(
    "/matches/index.html",
    response_class=HTMLResponse,
    summary="Browseable HTML list of archived matches for an OID",
)
async def matches_index(
    oid: str = Query(..., description="Overlay ID to list matches for."),
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None,
                                 description="OVERLAY_MANAGER_PASSWORD; "
                                             "alternative to Bearer header."),
):
    # Signed-URL auth deliberately not honoured on the index — a
    # signature pins one specific match_id; the index would need a
    # separate "list-all" capability that's a different feature
    # (and intentionally not provided yet, since the index gives
    # destructive access via per-row Delete).
    _check_access(authorization, token)
    summaries = match_archive.list_matches(oid=oid)

    # Forward the same token to the per-match report links so the
    # operator can click through without re-entering it. Bearer
    # users will need to attach the header on each navigation —
    # acceptable since they're already using a header-aware client.
    token_qs = f"?token={html.escape(token)}" if token else ""

    if summaries:
        rows = "\n".join(
            _render_match_row(s, token_qs=token_qs) for s in summaries
        )
        toolbar_html = (
            '<div class="toolbar">'
            '<button type="button" id="delete-selected" class="danger" disabled>'
            'Delete selected (<span id="selected-count">0</span>)'
            '</button>'
            '<span>Tip: tick the boxes to select rows, then use this button '
            'or the per-row Delete to remove them.</span>'
            '</div>'
        )
        table_html = (
            "<table>"
            "<thead><tr>"
            '<th class="checkbox-col">'
            '<input type="checkbox" id="select-all" '
            'aria-label="Select all matches"></th>'
            "<th>Ended</th><th>Sets</th><th>Duration</th>"
            "<th>Report</th><th>Actions</th>"
            "</tr></thead>"
            f"<tbody>{rows}</tbody>"
            "</table>"
        )
        body_html = toolbar_html + table_html + _INDEX_SCRIPT
    else:
        body_html = '<div class="empty">No matches archived yet for this OID.</div>'

    plural = "" if len(summaries) == 1 else "es"
    rendered = _INDEX_TEMPLATE.format(
        oid_label=html.escape(oid),
        count=len(summaries),
        plural=plural,
        body_html=body_html,
    )
    return HTMLResponse(content=rendered)


@match_report_router.delete(
    "/matches/{match_id}",
    summary="Delete an archived match snapshot",
    status_code=204,
)
async def delete_archived_match(
    match_id: str,
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None,
                                 description="OVERLAY_MANAGER_PASSWORD; "
                                             "alternative to Bearer header."),
):
    """Delete a single archived match by id.

    Requires a valid admin token unless ``MATCH_REPORT_PUBLIC_DELETE``
    is set — that flag is independent from ``MATCH_REPORT_PUBLIC``
    (public read does *not* imply public delete) and lets operators
    expose the per-row Delete button on the matches index without
    sharing the admin password. Returns 204 on success, 404 when the
    match does not exist, and 401/403/503 for the various
    authentication failure modes when the flag is off.
    """
    if not _public_delete_enabled():
        _check_admin_access(authorization, token)
    if not match_archive.delete_match(match_id):
        raise HTTPException(status_code=404, detail="Match not found.")
    return Response(status_code=204)
