"""HTML shell template for the print-friendly match report page."""

REPORT_TEMPLATE = """<!doctype html>
<html lang="{locale}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{og_description}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Volley Overlay Control">
<meta name="twitter:card" content="summary">
<style>
  :root {{
    color-scheme: light dark;
    --bg: #ffffff;
    --fg: #1a1a1a;
    --muted: #666;
    --border: #d0d0d0;
    --surface: #fafafa;
    --btn-bg: #ffffff;
    --chart-grid: #e0e0e0;
    --chart-axis: #999999;
    --t1: {team1_color};
    --t1-fg: {team1_fg};
    --t2: {team2_color};
    --t2-fg: {team2_fg};
    /* Scheme-aware chart palette. The SVG fragments carry the light
       values as presentation attributes (the no-CSS fallback); these
       vars win via the class rules below, and the dark block simply
       re-points them at the dark-surface-safe pair. */
    --t1-chart: {team1_chart};
    --t2-chart: {team2_chart};
  }}
  /* Scoped to screen so print keeps the light palette regardless of
     the OS theme — the report is a paper artefact when printed. */
  @media screen and (prefers-color-scheme: dark) {{
    :root {{
      --bg: #121212;
      --fg: #e8e8e8;
      --muted: #9aa0a6;
      --border: #3a3a3a;
      --surface: #1e1e1e;
      --btn-bg: #1e1e1e;
      --chart-grid: #3a3a3a;
      --chart-axis: #9aa0a6;
      --t1-chart: {team1_chart_dark};
      --t2-chart: {team2_chart_dark};
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: var(--fg);
    background: var(--bg);
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
  .toolbar button,
  .toolbar .toolbar-link {{
    cursor: pointer;
    font: inherit;
    padding: 6px 12px;
    border: 1px solid var(--border);
    background: var(--btn-bg);
    border-radius: 4px;
    transition: background 0.1s ease;
  }}
  .toolbar .toolbar-link {{
    display: inline-block;
    color: inherit;
    text-decoration: none;
  }}
  .toolbar button:hover,
  .toolbar .toolbar-link:hover {{ background: var(--surface); }}
  .toolbar button:disabled {{ opacity: 0.6; cursor: default; }}
  .scoreboard {{
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    /* Default (stretch) row alignment on purpose: both team panels fill
       the same row height, so the winner badge can't make one panel
       taller than the other. The panels centre their own content. */
    gap: 16px;
    margin: 24px 0;
    padding: 16px;
    border: 1px solid var(--border);
    border-radius: 8px;
  }}
  .team {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
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
  /* currentColor keeps the pill readable on any brand panel colour
     and survives monochrome print without a background dependency. */
  .winner-badge {{
    display: inline-block;
    margin-top: 6px;
    padding: 2px 10px;
    border: 1px solid currentColor;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
  }}
  td.set-won {{ font-weight: 700; }}
  /* align-self restores the vertical centring the row-level ``align-items:
     center`` used to give (dropped so the team panels stretch evenly). */
  .vs {{ align-self: center; font-size: 24px; font-weight: 600; color: var(--muted); }}
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
  /* Scheme-aware chart colours: these rules beat the inline
     presentation attributes the SVG fragments carry, so the polylines
     and markers follow --t1-chart/--t2-chart in both schemes. The
     timeout guides/glyphs are addressed by their existing data-team
     attribute (their class list is pinned by tests). */
  .set-chart .chart-grid {{ stroke: var(--chart-grid); }}
  .set-chart .chart-axis {{ fill: var(--chart-axis); }}
  .set-chart .t1-stroke {{ stroke: var(--t1-chart); }}
  .set-chart .t2-stroke {{ stroke: var(--t2-chart); }}
  .set-chart .t1-fill {{ fill: var(--t1-chart); }}
  .set-chart .t2-fill {{ fill: var(--t2-chart); }}
  .set-chart .set-chart-timeout[data-team="1"],
  .set-chart .set-chart-timeout-glyph[data-team="1"] {{ stroke: var(--t1-chart); }}
  .set-chart .set-chart-timeout[data-team="2"],
  .set-chart .set-chart-timeout-glyph[data-team="2"] {{ stroke: var(--t2-chart); }}
  .chart-card .legend .swatch-t1 {{ background: var(--t1-chart); }}
  .chart-card .legend .swatch-t2 {{ background: var(--t2-chart); }}
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
    <a class="toolbar-link" href="{csv_href}" download>{btn_csv}</a>
  </div>
</header>

<section class="scoreboard">
  <div class="team t1">
    {team1_logo}
    <div class="name">{team1_name}</div>
    <div class="sets">{team1_sets}</div>
    {team1_badge}
  </div>
  <div class="vs">{versus}</div>
  <div class="team t2">
    {team2_logo}
    <div class="name">{team2_name}</div>
    <div class="sets">{team2_sets}</div>
    {team2_badge}
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
  // Progressive enhancement: rewrite the server-rendered UTC
  // timestamps into the viewer's locale/timezone. The UTC original
  // moves to the tooltip; without JS the UTC text simply stands.
  document.querySelectorAll('[data-utc-ts]').forEach(function (el) {{
    const epoch = parseFloat(el.getAttribute('data-utc-ts'));
    if (!isFinite(epoch)) return;
    el.title = el.textContent;
    el.textContent = new Date(epoch * 1000).toLocaleString(undefined, {{
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    }});
  }});

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
