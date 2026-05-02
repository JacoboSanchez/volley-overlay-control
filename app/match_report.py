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
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Response
from fastapi.responses import HTMLResponse

from app.api import match_archive
from app.env_vars_manager import EnvVarsManager
from app.match_report_i18n import resolve_locale
from app.match_report_i18n import t as _t

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


def _admin_password() -> Optional[str]:
    raw = EnvVarsManager.get_env_var("OVERLAY_MANAGER_PASSWORD", None)
    if raw is None:
        return None
    raw = str(raw).strip()
    return raw or None


def _require_admin_token(
    authorization: Optional[str],
    token: Optional[str],
    *,
    missing_password_detail: str,
) -> None:
    """Raise unless the caller presents the admin token.

    Shared between :func:`_check_access` and :func:`_check_admin_access`.
    Both flows need the same Bearer-or-``?token=`` resolution and the
    same 503/401/403 ladder; only the 503 detail differs (read vs.
    destructive copy), so callers pass that in.
    """
    expected = _admin_password()
    if expected is None:
        raise HTTPException(status_code=503, detail=missing_password_detail)
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
    _require_admin_token(
        authorization, token,
        missing_password_detail=(
            "Match reports are disabled. Set OVERLAY_MANAGER_PASSWORD "
            "for gated access or MATCH_REPORT_PUBLIC=true for open "
            "access."
        ),
    )


def _check_admin_access(authorization: Optional[str], token: Optional[str]) -> None:
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
        missing_password_detail=(
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
  .timeline-set ol {{ margin: 0; padding-left: 22px; }}
  .timeline-set li {{ margin: 2px 0; }}
  .timeline-set li.undone {{
    text-decoration: line-through;
    color: var(--muted);
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
    {team1_winner_badge}
  </div>
  <div class="vs">{versus}</div>
  <div class="team t2">
    {team2_logo}
    <div class="name">{team2_name}</div>
    <div class="sets">{team2_sets}</div>
    {team2_winner_badge}
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
    <tr><td>{h_timeouts_label}</td><td colspan="{set_count}">{timeouts_summary}</td></tr>
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

<div class="footer">{footer_text}</div>

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
    for key in (f"Team {team} Name", f"team_{team}_name", f"name{team}"):
        value = customization.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"Team {team}"


def _action_label(record: dict, locale: str) -> str:
    action = record.get("action", "")
    params = record.get("params") or {}
    team = params.get("team")
    undo_suffix = _t(locale, "undo") if params.get("undo") else ""
    if action == "add_point":
        return _t(locale, "actionPoint", team=team) + undo_suffix
    if action == "add_set":
        return _t(locale, "actionSet", team=team) + undo_suffix
    if action == "add_timeout":
        return _t(locale, "actionTimeout", team=team) + undo_suffix
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


# ---------------------------------------------------------------------------
# Audit-log derived helpers (running score, undo collapse, stats, charts)
# ---------------------------------------------------------------------------

def _coerce_int(raw: object) -> Optional[int]:
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


def _result_score(record: dict, team: int) -> Optional[int]:
    """Pull the post-action score for *team* out of an audit ``result`` blob."""
    block = (record.get("result") or {}).get(f"team_{team}") or {}
    return _coerce_int(block.get("score"))


def _result_set(record: dict) -> Optional[int]:
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


def _first_scoring_index(audit: list[dict]) -> Optional[int]:
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
            try:
                n = int(key.removeprefix("set_"))
            except ValueError:
                continue
            try:
                v = int(value) if value is not None else 0
            except (TypeError, ValueError):
                continue
            if v > 0:
                highest = max(highest, n)
    if highest == 0:
        return 1
    return min(highest, fallback) if fallback > 0 else highest


def _collapse_undos(audit: list[dict]) -> list[dict]:
    """Mark forward audit records whose effect was reverted by a later ``undo``.

    The audit log keeps both the original record and the explicit undo
    that reversed it; the report's job is editorial, not forensic, so
    we annotate the original as ``_was_undone=True`` and drop the
    explicit undo from the rendered timeline. Match each undo to the
    most recent matching forward record by ``(action, team)`` — same
    pairing rule the server-side undo stack uses. Records that don't
    match are left as-is (defensive: an extra undo with no pair stays
    visible so we don't hide signal during a bug investigation).
    """
    out: list[dict] = []
    for record in audit:
        params = record.get("params") or {}
        if not params.get("undo"):
            out.append(dict(record))
            continue
        # Walk back for the most recent forward record with the same
        # ``(action, team)``. Skip already-paired entries.
        action = record.get("action")
        team = params.get("team")
        for prior in reversed(out):
            if prior.get("_was_undone"):
                continue
            prior_params = prior.get("params") or {}
            if (
                prior.get("action") == action
                and prior_params.get("team") == team
                and not prior_params.get("undo")
            ):
                prior["_was_undone"] = True
                break
        else:
            # No pair found — keep the orphan undo so it doesn't
            # silently disappear from the timeline.
            out.append(dict(record))
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


def _running_score_pair(record: dict) -> Optional[tuple[int, int]]:
    """``(team1, team2)`` running score after this audit record, if known."""
    s1 = _result_score(record, 1)
    s2 = _result_score(record, 2)
    if s1 is None or s2 is None:
        return None
    return (s1, s2)


def _format_relative_ts(ts: Optional[float], base_ts: Optional[float]) -> str:
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


def _logo_url(customization: dict, team: int) -> Optional[str]:
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


def _compute_stats(audit: list[dict]) -> dict:
    """Compute the Highlights block (longest streak, biggest comeback, totals).

    All metrics derive purely from the audit log so the report stays
    consistent with the "scoring trajectory" the audit promises. Set
    points are scored per-set; biggest comeback is computed per-set
    too (the largest deficit overcome by the eventual set winner).
    """
    longest_streak = {"team": None, "n": 0, "set": None}
    biggest_comeback = {"team": None, "deficit": 0, "set": None}
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
        streak_team: Optional[int] = None
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

        # Biggest comeback: largest deficit faced by the eventual set
        # winner. Determine the winner from the final score state for
        # this set, then walk the running scores tracking the maximum
        # opponent-lead the winner ever sat at.
        if not set_records:
            continue
        last_score = _running_score_pair(set_records[-1])
        if not last_score:
            continue
        winner = 1 if last_score[0] > last_score[1] else 2
        max_deficit = 0
        for r in set_records:
            pair = _running_score_pair(r)
            if not pair:
                continue
            t1, t2 = pair
            deficit = (t2 - t1) if winner == 1 else (t1 - t2)
            if deficit > max_deficit:
                max_deficit = deficit
        if max_deficit > biggest_comeback["deficit"]:
            biggest_comeback = {
                "team": winner, "deficit": max_deficit, "set": set_num,
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
        "biggest_comeback": biggest_comeback,
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


def _hex_to_rgb(hex_color: str) -> Optional[tuple[int, int, int]]:
    """Parse ``#RGB`` / ``#RRGGBB`` into ``(r, g, b)`` ∈ [0, 255]."""
    if not isinstance(hex_color, str) or not _HEX_COLOR_RE.match(hex_color):
        return None
    body = hex_color.lstrip("#")
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    return (int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16))


def _relative_luminance(hex_color: str) -> Optional[float]:
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
    set_records: list[dict], *, t1_color: str, t2_color: str,
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
    survives "Save as PDF". Returns a placeholder string when the
    set has fewer than two scoring records (nothing to plot).
    """
    points: list[tuple[int, int]] = []
    timestamps: list[Optional[float]] = []
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

    # Decide axis mode: time when every record has a ts and no gap
    # between consecutive records exceeds the threshold; otherwise
    # rally-number with ``+0:00 → +1:00 → …`` semantics broken.
    use_time_axis = all(t is not None for t in timestamps)
    if use_time_axis:
        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i - 1]  # type: ignore[operator]
            if gap > _TIME_AXIS_MAX_GAP_S:
                use_time_axis = False
                break

    if use_time_axis:
        base_ts = timestamps[0] or 0.0
        x_values = [(t or base_ts) - base_ts for t in timestamps]
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

    def _team_label(team: Optional[int]) -> str:
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

    comeback = stats.get("biggest_comeback") or {}
    if comeback.get("deficit", 0) >= 2 and comeback.get("team"):
        _card(
            _t(locale, "highlightComeback"),
            _t(locale, "deltaValue",
               n=comeback["deficit"], set=comeback.get("set") or "?"),
            _team_label(comeback["team"]),
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
    by_set: dict[int, list[dict]] = {}
    for record in audit:
        if record.get("params", {}).get("undo"):
            continue
        if not _is_score_action(record):
            continue
        set_num = _result_set(record)
        if set_num is None:
            continue
        by_set.setdefault(set_num, []).append(record)

    cards: list[str] = []
    for i in range(1, set_count + 1):
        records = by_set.get(i, [])
        chart = _render_score_chart(
            records, t1_color=t1_color, t2_color=t2_color,
        )
        body = chart or (
            f'<p class="legend">{html.escape(_t(locale, "noScoreEvolution"))}</p>'
        )
        legend = (
            f'<div class="legend">'
            f'<span class="swatch" style="background: {html.escape(t1_color)};"></span>{html.escape(t1_name)}'
            f'<span class="swatch" style="background: {html.escape(t2_color)};"></span>{html.escape(t2_name)}'
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
    *, base_ts: Optional[float] = None,
) -> str:
    """Group the audit by set and emit running-score-aware list items.

    *base_ts* is the explicit match-start anchor (Start-match button
    or first-point auto-arm). When supplied, relative timestamps are
    measured from there — so a point scored 5 min after Start-match
    reads ``+5:00``, not ``+0:00``. Falls back to the first audit
    record's ts for legacy snapshots without an anchor.
    """
    if not audit:
        return f'<em>{html.escape(_t(locale, "noAudit"))}</em>'

    collapsed = _collapse_undos(audit)
    if base_ts is None:
        base_ts = next(
            (r.get("ts") for r in collapsed
             if isinstance(r.get("ts"), (int, float))),
            None,
        )

    by_set: dict[int, list[dict]] = {}
    orphans: list[dict] = []
    for record in collapsed:
        # ``_collapse_undos`` already drops the explicit-undo half of
        # successfully paired records (their forward sibling renders
        # with ``_was_undone=True`` strikethrough). Anything still
        # marked ``undo`` here is an orphan that ``_collapse_undos``
        # kept on purpose for forensic visibility — keep rendering it.
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
        cls = " class=\"undone\"" if record.get("_was_undone") else ""
        return (
            f'<li{cls}><span class="ts">{html.escape(rel)}</span>'
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
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None,
                                 description="OVERLAY_MANAGER_PASSWORD; "
                                             "alternative to Bearer header."),
    accept_language: Optional[str] = Header(default=None),
):
    _check_access(authorization, token)
    payload = match_archive.load_match(match_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Match not found.")

    locale = resolve_locale(accept_language)
    customization = payload.get("customization", {}) or {}
    final = payload.get("final_state", {}) or {}
    config = payload.get("config", {}) or {}
    raw_audit = payload.get("audit_log", []) or []
    # The "match" only exists from the first scored point onward — see
    # ``_first_scoring_index`` for the rationale. Every audit consumer
    # below operates on the trimmed slice so pre-game noise (resets,
    # stray clicks) doesn't skew durations, charts, or relative times.
    audit = _trim_pregame(raw_audit)

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

    def _team_set_cells(team_dict: dict) -> str:
        cells = []
        scores = team_dict.get("scores", {}) or {}
        for i in range(1, played_sets + 1):
            v = scores.get(f"set_{i}", "")
            cells.append(f"<td>{html.escape(str(v) if v != '' else '—')}</td>")
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
    first_scoring_ts: Optional[float] = None
    for record in audit:
        ts = record.get("ts")
        if isinstance(ts, (int, float)):
            first_scoring_ts = float(ts)
            break
    payload_started = payload.get("started_at")
    if isinstance(payload_started, (int, float)):
        effective_started_at: Optional[float] = float(payload_started)
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

    timeouts_t1 = team1.get("timeouts")
    timeouts_t2 = team2.get("timeouts")
    timeouts_summary = (
        f"{html.escape(team1_name)}: {timeouts_t1 if timeouts_t1 is not None else '—'} &middot; "
        f"{html.escape(team2_name)}: {timeouts_t2 if timeouts_t2 is not None else '—'}"
    )

    winning_team = payload.get("winning_team")
    winner_badge = (
        f'<div class="winner">{html.escape(_t(locale, "matchWinner"))}</div>'
    )
    team1_winner = winner_badge if winning_team == 1 else ""
    team2_winner = winner_badge if winning_team == 2 else ""

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
        team1_winner_badge=team1_winner,
        team2_winner_badge=team2_winner,
        set_count=played_sets,
        set_headers=set_headers,
        team1_set_cells=_team_set_cells(team1),
        team2_set_cells=_team_set_cells(team2),
        set_duration_cells=_render_set_durations_row(set_durations, played_sets),
        timeouts_summary=timeouts_summary,
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
        h_timeouts_label=html.escape(_t(locale, "timeoutsLabel")),
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
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None,
                                 description="OVERLAY_MANAGER_PASSWORD; "
                                             "alternative to Bearer header."),
):
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
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None,
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
