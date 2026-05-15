/* ─────────────────────────────────────────────────────────────────
   Set summary overlay — runtime renderer.

   Each variant ships its own DOM (built per-render from the live
   state broadcast) and its own CSS rules in
   overlay_static/css/set_summary.css. The dispatcher reads
   match_info.set_summary_style and calls the matching builder
   below; unknown styles fall back to "brand_ledger".

   Designs are ported from docs/mockups/set-summary/*.html. The
   wrapper centres the stage in a 16:9 box that fills roughly two
   thirds of the viewport height (with equal margins above/below),
   driven from CSS in set_summary.css (.ss-stage rule).
   ───────────────────────────────────────────────────────────────── */

(function () {
  'use strict';

  // ── i18n ────────────────────────────────────────────────────────
  const LABELS = {
    en: {
      set: 'Set', final: 'Final', duration: 'Duration',
      longestStreak: 'Longest streak', servicesWon: 'Services won',
      timeoutsUsed: 'Timeouts used', totalPoints: 'Total points',
      home: 'Home', away: 'Away',
      progression: 'Point progression', recap: 'Set recap',
      streak: 'Streak', services: 'Services', timeouts: 'Timeouts',
      points: 'Points', match: 'Match', bestOf: 'Best of',
      setWinner: 'Set winner', runnerUp: 'Runner-up',
      live: 'LIVE', vs: 'VS', pointsShort: 'pts',
      empty: 'No points yet this set',
    },
    es: {
      set: 'Set', final: 'Final', duration: 'Duración',
      longestStreak: 'Racha más larga', servicesWon: 'Servicios ganados',
      timeoutsUsed: 'Tiempos muertos', totalPoints: 'Puntos totales',
      home: 'Local', away: 'Visitante',
      progression: 'Progresión de puntos', recap: 'Resumen del set',
      streak: 'Racha', services: 'Servicios', timeouts: 'Tiempos',
      points: 'Puntos', match: 'Partido', bestOf: 'Mejor de',
      setWinner: 'Ganador del set', runnerUp: 'Segundo',
      live: 'EN VIVO', vs: 'VS', pointsShort: 'pts',
      empty: 'Aún sin puntos en este set',
    },
    pt: {
      set: 'Set', final: 'Final', duration: 'Duração',
      longestStreak: 'Maior sequência', servicesWon: 'Serviços ganhos',
      timeoutsUsed: 'Tempos pedidos', totalPoints: 'Pontos totais',
      home: 'Casa', away: 'Visitante',
      progression: 'Progressão de pontos', recap: 'Resumo do set',
      streak: 'Sequência', services: 'Serviços', timeouts: 'Tempos',
      points: 'Pontos', match: 'Partida', bestOf: 'Melhor de',
      setWinner: 'Vencedor do set', runnerUp: 'Segundo',
      live: 'AO VIVO', vs: 'VS', pointsShort: 'pts',
      empty: 'Ainda sem pontos neste set',
    },
    it: {
      set: 'Set', final: 'Finale', duration: 'Durata',
      longestStreak: 'Striscia più lunga', servicesWon: 'Servizi vinti',
      timeoutsUsed: 'Timeout usati', totalPoints: 'Punti totali',
      home: 'Casa', away: 'Ospiti',
      progression: 'Progressione punti', recap: 'Riepilogo set',
      streak: 'Striscia', services: 'Servizi', timeouts: 'Timeout',
      points: 'Punti', match: 'Partita', bestOf: 'Al meglio di',
      setWinner: 'Vincitore del set', runnerUp: 'Secondo',
      live: 'LIVE', vs: 'VS', pointsShort: 'pti',
      empty: 'Nessun punto in questo set',
    },
    fr: {
      set: 'Set', final: 'Final', duration: 'Durée',
      longestStreak: 'Plus longue série', servicesWon: 'Services gagnés',
      timeoutsUsed: 'Temps morts', totalPoints: 'Points totaux',
      home: 'Domicile', away: 'Visiteur',
      progression: 'Progression des points', recap: 'Récap. du set',
      streak: 'Série', services: 'Services', timeouts: 'Temps morts',
      points: 'Points', match: 'Match', bestOf: 'Au meilleur de',
      setWinner: 'Vainqueur du set', runnerUp: 'Finaliste',
      live: 'EN DIRECT', vs: 'VS', pointsShort: 'pts',
      empty: 'Pas encore de points dans ce set',
    },
    de: {
      set: 'Satz', final: 'Final', duration: 'Dauer',
      longestStreak: 'Längste Serie', servicesWon: 'Aufschläge gewonnen',
      timeoutsUsed: 'Auszeiten', totalPoints: 'Punkte gesamt',
      home: 'Heim', away: 'Auswärts',
      progression: 'Punktverlauf', recap: 'Satzrückblick',
      streak: 'Serie', services: 'Aufschläge', timeouts: 'Auszeiten',
      points: 'Punkte', match: 'Spiel', bestOf: 'Best of',
      setWinner: 'Satzgewinner', runnerUp: 'Zweiter',
      live: 'LIVE', vs: 'VS', pointsShort: 'Pkt',
      empty: 'Noch keine Punkte in diesem Satz',
    },
  };

  function t(key) {
    const locale = (window.OVERLAY_LOCALE || 'en').slice(0, 2).toLowerCase();
    const dict = LABELS[locale] || LABELS.en;
    return dict[key] || LABELS.en[key] || key;
  }

  // ── Generic helpers ─────────────────────────────────────────────
  function formatDuration(seconds) {
    if (!seconds || !isFinite(seconds) || seconds < 0) return '–:––';
    const s = Math.round(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
    return `${m}:${String(sec).padStart(2, '0')}`;
  }

  // ── Live duration tick ──────────────────────────────────────────
  // Two independent anchors keep the set and match clocks ticking
  // between server broadcasts:
  //
  // * ``setAnchorMs`` — wall-clock ms at the first scoring event of
  //   the displayed set. Used when the recap is showing a *live*
  //   set; left null otherwise so the rendered total stays frozen.
  // * ``matchAnchorMs`` — wall-clock ms at ``match_info.match_started_at``.
  //   Always ticks while the match has not finished, regardless of
  //   which set the recap displays.
  let _liveTickHandle = null;
  let _liveTickState = null;

  function ensureLiveTick() {
    if (_liveTickHandle != null) return;
    _liveTickHandle = setInterval(applyLiveTick, 1000);
  }

  function applyLiveTick() {
    if (!_liveTickState) return;
    const panel = document.getElementById('set-summary-panel');
    if (!panel || panel.hasAttribute('hidden')) return;
    const now = Date.now();
    if (_liveTickState.setAnchorMs) {
      _updateClockNodes(panel, '[data-live-duration]',
        (now - _liveTickState.setAnchorMs) / 1000);
    }
    if (_liveTickState.matchAnchorMs) {
      _updateClockNodes(panel, '[data-live-match]',
        (now - _liveTickState.matchAnchorMs) / 1000);
    }
  }

  function _updateClockNodes(panel, selector, elapsedSec) {
    if (!isFinite(elapsedSec) || elapsedSec < 0) return;
    const formatted = formatDuration(elapsedSec);
    panel.querySelectorAll(selector).forEach((node) => {
      const prefix = node.getAttribute('data-live-prefix') || '';
      node.textContent = prefix + formatted;
    });
  }

  // Build a duration display element that the live-tick loop will
  // refresh in place. Pass ``prefix`` (e.g. ``"⏱ "``) when the
  // variant wants an icon/label baked into the same node.
  function durationNode(seconds, opts) {
    opts = opts || {};
    const node = el(opts.tag || 'span', {
      class: opts.class,
      attrs: { 'data-live-duration': '' },
    });
    const prefix = opts.prefix || '';
    if (prefix) node.setAttribute('data-live-prefix', prefix);
    node.textContent = prefix + formatDuration(seconds);
    return node;
  }

  // Match-elapsed clock counterpart of ``durationNode``. Ticks
  // off the operator's ``match_started_at`` anchor independently
  // of the per-set duration above.
  function matchClockNode(seconds, opts) {
    opts = opts || {};
    const node = el(opts.tag || 'span', {
      class: opts.class,
      attrs: { 'data-live-match': '' },
    });
    const prefix = opts.prefix || '';
    if (prefix) node.setAttribute('data-live-prefix', prefix);
    node.textContent = prefix + formatDuration(seconds);
    return node;
  }

  // Deliberately *no* ``html:`` escape hatch. Every text-bearing
  // node uses ``textContent`` (or a typed child node) so operator-
  // editable values like team names / scores can never round-trip
  // through ``innerHTML``. Composite values (e.g. the two-team
  // ``home · away`` stat readouts) are assembled from DOM nodes via
  // ``dualValueNode`` below.
  function el(tag, opts) {
    const n = document.createElement(tag);
    if (!opts) return n;
    if (opts.class) n.className = opts.class;
    if (opts.text != null) n.textContent = opts.text;
    if (opts.style) {
      for (const k in opts.style) n.style.setProperty(k, opts.style[k]);
    }
    if (opts.attrs) {
      for (const k in opts.attrs) n.setAttribute(k, opts.attrs[k]);
    }
    if (opts.children) opts.children.forEach((c) => c && n.appendChild(c));
    return n;
  }

  // <span><span class="home">X</span> · <span class="away">Y</span></span>
  // built from DOM nodes (no innerHTML). The colour-coded home/away
  // dual readout that several variants use for per-team stats.
  function dualValueNode(homeVal, awayVal) {
    return el('span', {
      children: [
        el('span', { class: 'home', text: String(homeVal) }),
        document.createTextNode(' · '),
        el('span', { class: 'away', text: String(awayVal) }),
      ],
    });
  }

  // <span>label <strong>value</strong></span> as DOM nodes.
  function labelStrongNode(label, value) {
    return el('span', {
      children: [
        document.createTextNode(`${label} `),
        el('strong', { text: String(value) }),
      ],
    });
  }

  function teamInitials(team, side) {
    return (team.short_name || team.name || side[0] || '?')
      .slice(0, 2).toUpperCase();
  }

  function teamLogoNode(team, side, className) {
    const node = el('div', { class: className || 'ss-logo' });
    if (team.logo_url) {
      const img = el('img', { attrs: { src: team.logo_url, alt: team.name || side } });
      node.appendChild(img);
    } else {
      node.textContent = teamInitials(team, side);
    }
    return node;
  }

  function svgEl(tag, attrs) {
    const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    if (attrs) for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }

  // Build polyline points from an array of cumulative scores within
  // [0, maxScore]. ``viewBox`` controls the coordinate space; the
  // helper plots y = (1 - score / maxY) * vbH so 0 sits at the
  // bottom and ``maxY`` at the top, padded to keep axes legible.
  function chartPolylinePoints(events, team, opts) {
    const vbW = opts.width;
    const vbH = opts.height;
    const padTop = opts.padTop != null ? opts.padTop : 6;
    const padBottom = opts.padBottom != null ? opts.padBottom : 6;
    const padLeft = opts.padLeft != null ? opts.padLeft : 0;
    const padRight = opts.padRight != null ? opts.padRight : 0;
    const maxY = Math.max(opts.maxY || 25, 1);
    const teamIdx = team === 1 ? 0 : 1;
    const drawableW = vbW - padLeft - padRight;
    const drawableH = vbH - padTop - padBottom;

    const points = [];
    // Anchor at 0,0 (left baseline).
    points.push(`${padLeft},${vbH - padBottom}`);
    const total = events.length;
    if (total === 0) {
      return points.join(' ');
    }
    events.forEach((ev, idx) => {
      const x = padLeft + ((idx + 1) / total) * drawableW;
      const score = Array.isArray(ev.score) ? (ev.score[teamIdx] || 0) : 0;
      const y = vbH - padBottom - (Math.min(score, maxY) / maxY) * drawableH;
      points.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    });
    return points.join(' ');
  }

  function maxScoreInEvents(events) {
    let mx = 0;
    events.forEach((ev) => {
      if (Array.isArray(ev.score)) {
        if (ev.score[0] > mx) mx = ev.score[0];
        if (ev.score[1] > mx) mx = ev.score[1];
      }
    });
    return mx;
  }

  // Pull all the values a renderer needs out of the live state once.
  function deriveViewModel(state) {
    const matchInfo = state.match_info || {};
    const home = state.team_home || {};
    const away = state.team_away || {};
    const oc = state.overlay_control || {};
    const stats = oc.stats || {};
    const setNum = matchInfo.summary_set_num
      || matchInfo.current_set
      || 1;
    const setKey = `set_${setNum}`;
    // A set is "finished" when the backend has written a final score
    // into the team's set_history. While the set is still in play the
    // entry is absent and we fall back to live points — used below to
    // pick the right pill label ("Final" vs "Live").
    const setFinished = !!(
      (home.set_history && home.set_history[setKey] != null)
      || (away.set_history && away.set_history[setKey] != null)
    );
    const homeScore = (home.set_history && home.set_history[setKey] != null)
      ? home.set_history[setKey]
      : (home.points || 0);
    const awayScore = (away.set_history && away.set_history[setKey] != null)
      ? away.set_history[setKey]
      : (away.points || 0);

    const pbs = oc.points_by_set || {};
    const tbs = oc.timeouts_by_set || {};
    const setPointsRaw = pbs[setNum] || pbs[String(setNum)] || [];
    const setTimeouts = tbs[setNum] || tbs[String(setNum)] || [];
    // Filter to real point events (set_score edits don't represent
    // rallies — see the resolver in backend.py/game_service.py).
    const setPoints = setPointsRaw.filter(
      (p) => !p || p.action !== 'set_score',
    );

    // Per-set variants of the stats so the recap surfaces values
    // that actually belong to the displayed set instead of match-
    // wide totals. Backend ships these in stats.<name>_by_set with
    // string keys (JSON round-trip safety).
    const longestBySet = stats.longest_streak_by_set || {};
    const setLongest = longestBySet[setNum] || longestBySet[String(setNum)] || {};
    const longestSet = {
      1: Number((setLongest['1'] != null ? setLongest['1'] : setLongest[1]) || 0),
      2: Number((setLongest['2'] != null ? setLongest['2'] : setLongest[2]) || 0),
    };

    const servicesBySet = stats.services_by_set || {};
    const setServicesRaw = servicesBySet[setNum] || servicesBySet[String(setNum)] || {};
    const servicesSet = {
      1: (setServicesRaw['1'] || setServicesRaw[1] || { served: 0, won: 0 }),
      2: (setServicesRaw['2'] || setServicesRaw[2] || { served: 0, won: 0 }),
    };

    // Total points in the displayed set = sum of both team scores.
    const setTotalPoints = (homeScore || 0) + (awayScore || 0);

    const setDurations = stats.set_durations || {};
    const durationSec = setDurations[setNum] || setDurations[String(setNum)] || 0;

    // Match-elapsed time so every variant can show both clocks
    // (set vs match). When the match has finished the elapsed value
    // freezes at the final wall-clock delta; otherwise the live
    // tick interpolates from match_started_at.
    const matchStartedAt = matchInfo.match_started_at;
    const matchFinishedAt = matchInfo.match_finished_at;
    let matchElapsedSec = 0;
    if (typeof matchStartedAt === 'number' && matchStartedAt > 0) {
      const end = (typeof matchFinishedAt === 'number' && matchFinishedAt > 0)
        ? matchFinishedAt
        : (Date.now() / 1000);
      matchElapsedSec = Math.max(0, end - matchStartedAt);
    }

    return {
      setNum,
      durationSec,
      matchElapsedSec,
      matchStartedAt: typeof matchStartedAt === 'number' ? matchStartedAt : null,
      matchFinishedAt: typeof matchFinishedAt === 'number' ? matchFinishedAt : null,
      home, away, homeScore, awayScore,
      setPoints, setTimeouts,
      stats,
      // Per-set values (preferred over match-wide so the recap
      // matches what the operator just watched).
      longestSet, servicesSet, setTotalPoints,
      setFinished,
      matchFinished: !!matchInfo.match_finished,
      bestOf: matchInfo.best_of_sets || 5,
      team1Sets: home.sets_won || 0,
      team2Sets: away.sets_won || 0,
    };
  }

  // ── Stage management ────────────────────────────────────────────
  function ensurePanel() {
    let panel = document.getElementById('set-summary-panel');
    if (panel) return panel;
    panel = el('div', { class: 'set-summary-panel', attrs: { id: 'set-summary-panel' } });
    // Initial visual state is fully transparent + click-through;
    // the show/hide helpers below flip both via inline styles so
    // the CSS ``opacity`` transition has a guaranteed "from"
    // value (attribute-driven rules sometimes skip the transition
    // on freshly-inserted elements).
    panel.style.opacity = '0';
    panel.style.pointerEvents = 'none';
    const stage = el('div', { class: 'ss-stage', attrs: { id: 'set-summary-stage' } });
    stage.dataset.style = 'brand_ledger';
    panel.appendChild(stage);
    // Sibling zone for layout pieces that need to break out of the
    // centred 16:9 stage frame — e.g. the bento ledger that spans
    // nearly the whole viewport width. Variants that don't need it
    // leave the zone empty and it collapses to zero height.
    const extras = el('div', { class: 'ss-extras', attrs: { id: 'set-summary-extras' } });
    panel.appendChild(extras);
    document.body.appendChild(panel);
    return panel;
  }

  // Parse a #rgb or #rrggbb hex into [r,g,b] (0-255). Returns null
  // for anything we can't parse (named colours, rgb(), data URIs).
  function parseHex(value) {
    if (typeof value !== 'string') return null;
    let h = value.trim().replace(/^#/, '');
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    if (!/^[0-9a-fA-F]{6}$/.test(h)) return null;
    return [
      parseInt(h.substring(0, 2), 16),
      parseInt(h.substring(2, 4), 16),
      parseInt(h.substring(4, 6), 16),
    ];
  }

  function relativeLuminance(rgb) {
    if (!rgb) return null;
    const transform = (c) => {
      const v = c / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * transform(rgb[0]) + 0.7152 * transform(rgb[1]) + 0.0722 * transform(rgb[2]);
  }

  // Many variants pour the team colour into a coloured panel
  // background OR use it as a chart line / text colour over a glass
  // tile. If the operator picked pure (or near-) white as the
  // team's primary, those uses all break (white text on white panel,
  // or vice versa). Fall back to a saturated accent colour so the
  // panel still reads and the chart line is visible against both
  // dark glass and light panels. Prefer the team's secondary only
  // when it lands in a mid-tone range — pure black secondaries are
  // common (default for unset overlays) and would invert the
  // problem on dark backgrounds (chart line invisible).
  function resolveTeamColour(team, fallback) {
    const primary = team && team.color_primary;
    const rgb = parseHex(primary);
    if (!rgb) return primary || fallback;
    const lum = relativeLuminance(rgb);
    if (lum != null && lum > 0.82) {
      const sec = parseHex(team && team.color_secondary);
      if (sec) {
        const secLum = relativeLuminance(sec);
        if (secLum != null && secLum > 0.12 && secLum < 0.7) {
          return team.color_secondary;
        }
      }
      return fallback;
    }
    return primary;
  }

  // Weighted RGB distance — cheaper than Lab ΔE but still tracks
  // perceptual similarity well enough to flag "close colour" cases
  // where two team primaries would render as overlapping chart lines.
  // Threshold ≈ 80 covers same-hue siblings (navy vs royal blue) while
  // letting clearly different palettes (orange vs blue) pass through.
  function colorsAreSimilar(c1, c2) {
    const a = parseHex(c1);
    const b = parseHex(c2);
    if (!a || !b) return false;
    const dr = a[0] - b[0];
    const dg = a[1] - b[1];
    const db = a[2] - b[2];
    const dist = Math.sqrt(2 * dr * dr + 4 * dg * dg + 3 * db * db);
    return dist < 80;
  }

  function applyTeamColours(stage, home, away) {
    stage.style.setProperty('--ss-home', resolveTeamColour(home, '#d4314c'));
    stage.style.setProperty('--ss-away', resolveTeamColour(away, '#f0a020'));
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  // ─────────────────────────────────────────────────────────────────
  // Renderer: brand_ledger
  // ─────────────────────────────────────────────────────────────────
  function renderBrandLedger(stage, vm) {
    const homeStats = el('div', { class: 'ss-team-stat-list' });
    homeStats.appendChild(buildStat(t('longestStreak'), vm.longestSet[1] || 0));
    homeStats.appendChild(buildStat(t('servicesWon'),
      formatServices(vm.servicesSet, 1)));

    const awayStats = el('div', { class: 'ss-team-stat-list' });
    awayStats.appendChild(buildStat(t('longestStreak'), vm.longestSet[2] || 0));
    awayStats.appendChild(buildStat(t('servicesWon'),
      formatServices(vm.servicesSet, 2)));

    const homeCol = el('div', {
      class: 'ss-team ss-team-home',
      children: [
        el('div', {
          class: 'ss-team-header',
          children: [
            teamLogoNode(vm.home, 'home'),
            el('div', {
              children: [
                el('div', { class: 'ss-team-name', text: vm.home.name || '' }),
                el('div', { class: 'ss-team-tag', text: t('home') }),
              ],
            }),
          ],
        }),
        el('div', { class: 'ss-team-score', text: String(vm.homeScore) }),
        homeStats,
      ],
    });

    const awayCol = el('div', {
      class: 'ss-team ss-team-away',
      children: [
        el('div', {
          class: 'ss-team-header',
          children: [
            teamLogoNode(vm.away, 'away'),
            el('div', {
              children: [
                el('div', { class: 'ss-team-name', text: vm.away.name || '' }),
                el('div', { class: 'ss-team-tag', text: t('away') }),
              ],
            }),
          ],
        }),
        el('div', { class: 'ss-team-score', text: String(vm.awayScore) }),
        awayStats,
      ],
    });

    const centre = el('div', {
      class: 'ss-centre',
      children: [
        el('div', {
          class: 'ss-set-group',
          children: [
            el('span', { class: 'ss-set-label', text: t('set') }),
            el('span', { class: 'ss-set-number', text: String(vm.setNum) }),
          ],
        }),
        el('div', {
          class: 'ss-duration-group',
          children: [
            el('span', { class: 'ss-duration-label', text: t('duration') }),
            durationNode(vm.durationSec, { class: 'ss-duration' }),
            el('span', { class: 'ss-duration-label ss-match-label', text: t('match') }),
            matchClockNode(vm.matchElapsedSec, { class: 'ss-duration ss-match-duration' }),
          ],
        }),
      ],
    });

    const ledger = buildLedger(vm);

    stage.appendChild(homeCol);
    stage.appendChild(ledger.home);
    stage.appendChild(centre);
    stage.appendChild(ledger.away);
    stage.appendChild(awayCol);
  }

  function buildStat(label, value) {
    return el('div', {
      class: 'ss-team-stat',
      children: [
        el('span', { class: 'ss-label', text: label }),
        el('span', { class: 'ss-value', text: value === 0 || value === '0' ? '–' : String(value) }),
      ],
    });
  }

  function formatServices(services, team) {
    const block = services && (services[team] || services[String(team)]);
    if (!block || !block.served) return '–';
    return `${block.won || 0} / ${block.served}`;
  }

  function buildLedger(vm) {
    const merged = [];
    vm.setPoints.forEach((p) => merged.push({ ...p, kind: 'point' }));
    vm.setTimeouts.forEach((tx) => merged.push({ ...tx, kind: 'timeout' }));
    merged.sort((a, b) => (a.ts || 0) - (b.ts || 0));

    const homeBody = el('div', { class: 'ss-ledger-col ss-ledger-col-home' });
    const awayBody = el('div', { class: 'ss-ledger-col ss-ledger-col-away' });

    const rowCount = Math.max(merged.length, 1);
    homeBody.style.gridTemplateRows = `repeat(${rowCount}, 1fr)`;
    awayBody.style.gridTemplateRows = `repeat(${rowCount}, 1fr)`;

    let lastPointIdx = -1;
    for (let i = merged.length - 1; i >= 0; i--) {
      if (merged[i].kind === 'point') { lastPointIdx = i; break; }
    }

    if (merged.length === 0) {
      homeBody.appendChild(el('span', { class: 'ss-point ss-empty', text: '·' }));
      awayBody.appendChild(el('span', { class: 'ss-point ss-empty', text: '·' }));
    } else {
      merged.forEach((ev, idx) => {
        const isHome = ev.team === 1;
        const empty = () => el('span', { class: 'ss-point ss-empty', text: '·' });
        if (ev.kind === 'point') {
          const score = Array.isArray(ev.score) ? ev.score : [0, 0];
          const teamScore = isHome ? score[0] : score[1];
          const chip = el('span', { class: 'ss-point', text: String(teamScore) });
          if (idx === lastPointIdx) chip.classList.add('ss-final');
          if (isHome) { homeBody.appendChild(chip); awayBody.appendChild(empty()); }
          else { homeBody.appendChild(empty()); awayBody.appendChild(chip); }
        } else {
          const marker = el('span', { class: 'ss-point ss-timeout', text: 'T' });
          if (isHome) { homeBody.appendChild(marker); awayBody.appendChild(empty()); }
          else { homeBody.appendChild(empty()); awayBody.appendChild(marker); }
        }
      });
    }
    return { home: homeBody, away: awayBody };
  }

  // ─────────────────────────────────────────────────────────────────
  // Renderer: brand_columns (3 columns + chart in centre)
  // ─────────────────────────────────────────────────────────────────
  function renderBrandColumns(stage, vm) {
    const homeStats = el('div', { class: 'ss-team-stat-list' });
    homeStats.appendChild(buildStat(t('longestStreak'),
      vm.longestSet[1] ? `${vm.longestSet[1]} ${t('pointsShort')}` : '–'));
    homeStats.appendChild(buildStat(t('servicesWon'), formatServices(vm.servicesSet, 1)));

    const awayStats = el('div', { class: 'ss-team-stat-list' });
    awayStats.appendChild(buildStat(t('longestStreak'),
      vm.longestSet[2] ? `${vm.longestSet[2]} ${t('pointsShort')}` : '–'));
    awayStats.appendChild(buildStat(t('servicesWon'), formatServices(vm.servicesSet, 2)));

    stage.appendChild(el('div', {
      class: 'ss-team ss-team-home',
      children: [
        el('div', {
          class: 'ss-team-header',
          children: [
            teamLogoNode(vm.home, 'home'),
            el('div', {
              children: [
                el('div', { class: 'ss-team-name', text: vm.home.name || '' }),
                el('div', { class: 'ss-team-tag', text: t('home') }),
              ],
            }),
          ],
        }),
        el('div', { class: 'ss-team-score', text: String(vm.homeScore) }),
        homeStats,
      ],
    }));

    const centre = el('div', {
      class: 'ss-centre',
      children: [
        el('span', {
          class: `ss-set-pill ${vm.setFinished ? 'is-final' : 'is-live'}`,
          text: `${t('set')} ${vm.setNum} · ${vm.setFinished ? t('final') : t('live')}`,
        }),
        buildChartWrap(vm, 'brand_columns'),
        el('div', { class: 'ss-vs', text: t('vs') }),
        el('div', {
          class: 'ss-duration-block',
          children: [
            el('span', { class: 'ss-label', text: t('duration') }),
            durationNode(vm.durationSec, { class: 'ss-value' }),
            el('span', { class: 'ss-label ss-match-label', text: t('match') }),
            matchClockNode(vm.matchElapsedSec, { class: 'ss-value ss-match-duration' }),
          ],
        }),
      ],
    });
    stage.appendChild(centre);

    stage.appendChild(el('div', {
      class: 'ss-team ss-team-away',
      children: [
        el('div', {
          class: 'ss-team-header',
          children: [
            teamLogoNode(vm.away, 'away'),
            el('div', {
              children: [
                el('div', { class: 'ss-team-name', text: vm.away.name || '' }),
                el('div', { class: 'ss-team-tag', text: t('away') }),
              ],
            }),
          ],
        }),
        el('div', { class: 'ss-team-score', text: String(vm.awayScore) }),
        awayStats,
      ],
    }));
  }

  function buildChartWrap(vm, variant) {
    const wrap = el('div', { class: 'ss-chart-wrap' });
    wrap.appendChild(buildSvgChart(vm, { width: 300, height: 380, padLeft: 6, padRight: 6 }));
    return wrap;
  }

  function buildSvgChart(vm, opts) {
    const w = opts.width;
    const h = opts.height;
    const svg = svgEl('svg', {
      viewBox: `0 0 ${w} ${h}`,
      preserveAspectRatio: 'none',
    });
    // grid
    svg.appendChild(svgEl('line', {
      class: 'ss-grid-main', x1: 0, y1: h - 4, x2: w, y2: h - 4,
    }));
    svg.appendChild(svgEl('line', {
      class: 'ss-grid-faint', x1: 0, y1: h / 2, x2: w, y2: h / 2,
    }));
    svg.appendChild(svgEl('line', {
      class: 'ss-grid-faint', x1: 0, y1: 4, x2: w, y2: 4,
    }));

    const maxY = Math.max(maxScoreInEvents(vm.setPoints), 25);
    const homePts = chartPolylinePoints(vm.setPoints, 1, {
      width: w, height: h, maxY,
      padTop: 6, padBottom: 6,
      padLeft: opts.padLeft || 0, padRight: opts.padRight || 0,
    });
    const awayPts = chartPolylinePoints(vm.setPoints, 2, {
      width: w, height: h, maxY,
      padTop: 6, padBottom: 6,
      padLeft: opts.padLeft || 0, padRight: opts.padRight || 0,
    });
    svg.appendChild(svgEl('polyline', { class: 'ss-line-home', points: homePts }));
    // When the two team primaries are visually close, the polylines
    // would overlap into a single confused trace. Tag the away line
    // so CSS can render it dashed — preserving the colour intent
    // while keeping the two series distinguishable.
    const homeCol = resolveTeamColour(vm.home, '#d4314c');
    const awayCol = resolveTeamColour(vm.away, '#f0a020');
    const awayClass = colorsAreSimilar(homeCol, awayCol)
      ? 'ss-line-away ss-line-away--dashed'
      : 'ss-line-away';
    svg.appendChild(svgEl('polyline', { class: awayClass, points: awayPts }));
    return svg;
  }

  // ─────────────────────────────────────────────────────────────────
  // Renderer: bento
  // ─────────────────────────────────────────────────────────────────
  function renderBento(stage, vm, extras) {
    if (extras) renderBentoExtras(extras, vm);
    stage.appendChild(el('div', {
      class: 'ss-header',
      children: [
        el('div', {
          class: 'ss-title',
          children: [
            document.createTextNode(`${t('set')} ${vm.setNum} · `),
            el('small', { text: t('recap').toLowerCase() }),
          ],
        }),
        el('div', {
          class: 'ss-clocks',
          children: [
            el('span', {
              class: 'ss-clock-block',
              children: [
                el('span', { class: 'ss-clock-label', text: t('set') }),
                durationNode(vm.durationSec, { class: 'ss-duration' }),
              ],
            }),
            el('span', {
              class: 'ss-clock-block ss-clock-match',
              children: [
                el('span', { class: 'ss-clock-label', text: t('match') }),
                matchClockNode(vm.matchElapsedSec, { class: 'ss-duration ss-match-duration' }),
              ],
            }),
          ],
        }),
      ],
    }));

    // Score tile (top-left). Team names ride on a brand tag for
    // legibility regardless of the underlying team colour. The
    // big scores ARE the "final points" so the redundant header
    // label was dropped — the tile centres the teams vertically.
    stage.appendChild(el('div', {
      class: 'ss-tile ss-tile-score',
      children: [
        el('div', {
          class: 'ss-teams',
          children: [
            el('div', {
              class: 'ss-team home',
              children: [
                el('span', { class: 'ss-tag', text: t('home') }),
                el('span', { class: 'ss-name', text: vm.home.name || t('home') }),
                el('span', { class: 'ss-score', text: String(vm.homeScore) }),
              ],
            }),
            el('span', { class: 'ss-sep', text: '·' }),
            el('div', {
              class: 'ss-team away',
              children: [
                el('span', { class: 'ss-tag', text: t('away') }),
                el('span', { class: 'ss-name', text: vm.away.name || t('away') }),
                el('span', { class: 'ss-score', text: String(vm.awayScore) }),
              ],
            }),
          ],
        }),
      ],
    }));

    // Stats tile (top-right) — replaces the old chart tile.
    stage.appendChild(buildBentoStatsTile(vm));
  }

  function renderBentoExtras(extras, vm) {
    // Decoupled bottom ledger — lives outside the 16:9 stage so
    // it can span nearly the full viewport width and keep room
    // for 25+ chips per team without resizing.
    const eventInfo = buildBumperEvents(vm);
    extras.appendChild(el('div', {
      class: 'ss-bento-ledger',
      children: [
        buildBumperRow(vm, 'home', eventInfo),
        buildBumperRow(vm, 'away', eventInfo),
      ],
    }));
  }

  function buildBentoStatsTile(vm) {
    // All stats below scope to the displayed set (per-team streak,
    // per-team service efficiency, set total). Two-team values
    // render with a 60%-tinted blend so the team origin reads at
    // a glance without hurting contrast on the dark tile.
    const rows = [
      buildBentoStatRowDual('🔥', t('streak'),
        vm.longestSet[1] || 0, vm.longestSet[2] || 0),
      buildBentoStatRowDual('🏐', t('services'),
        formatServices(vm.servicesSet, 1), formatServices(vm.servicesSet, 2)),
      buildBentoStatRowDual('⏱', t('timeouts'),
        vm.home.timeouts_taken || 0, vm.away.timeouts_taken || 0),
      buildBentoStatRow('∑', t('totalPoints'), vm.setTotalPoints),
    ];
    return el('div', { class: 'ss-tile ss-tile-stats', children: rows });
  }

  function buildBentoStatRow(icon, label, value) {
    return el('div', {
      class: 'ss-stat-row',
      children: [
        el('span', { class: 'ss-stat-icon', text: icon }),
        el('span', { class: 'ss-stat-label', text: label }),
        el('span', {
          class: 'ss-stat-value',
          text: String(value),
        }),
      ],
    });
  }

  function buildBentoStatRowDual(icon, label, homeVal, awayVal) {
    const value = dualValueNode(homeVal, awayVal);
    value.className = 'ss-stat-value';
    return el('div', {
      class: 'ss-stat-row',
      children: [
        el('span', { class: 'ss-stat-icon', text: icon }),
        el('span', { class: 'ss-stat-label', text: label }),
        value,
      ],
    });
  }

  // ─────────────────────────────────────────────────────────────────
  // Renderer: glass
  // ─────────────────────────────────────────────────────────────────
  function renderGlass(stage, vm) {
    // Background colour blobs.
    stage.appendChild(el('span', { class: 'ss-blob ss-blob-1' }));
    stage.appendChild(el('span', { class: 'ss-blob ss-blob-2' }));
    stage.appendChild(el('span', { class: 'ss-blob ss-blob-3' }));

    stage.appendChild(el('div', {
      class: 'ss-glass ss-header',
      children: [
        el('div', {
          class: 'ss-title',
          children: [
            el('span', {
              class: `ss-pill ${vm.setFinished ? 'is-final' : 'is-live'}`,
              text: `${t('set')} ${vm.setNum} · ${vm.setFinished ? t('final') : t('live')}`,
            }),
            el('span', { text: t('recap') }),
          ],
        }),
        // Match score on its own, prominently sized — used to be
        // tucked into ``ss-meta`` as small grey text and was easy
        // to miss. Set + match clocks live beside it.
        el('div', {
          class: 'ss-match-score',
          children: [
            el('span', { class: 'ss-match-score-label', text: t('match') }),
            el('span', {
              class: 'ss-match-score-value',
              children: [
                el('span', { class: 'home', text: String(vm.team1Sets) }),
                document.createTextNode(' – '),
                el('span', { class: 'away', text: String(vm.team2Sets) }),
              ],
            }),
          ],
        }),
        el('div', {
          class: 'ss-meta',
          children: [
            el('span', {
              class: 'ss-clock-block',
              children: [
                el('span', { class: 'ss-clock-label', text: t('set') }),
                durationNode(vm.durationSec, { class: 'ss-clock' }),
              ],
            }),
            el('span', {
              class: 'ss-clock-block ss-clock-match',
              children: [
                el('span', { class: 'ss-clock-label', text: t('match') }),
                matchClockNode(vm.matchElapsedSec, { class: 'ss-clock ss-match-duration' }),
              ],
            }),
          ],
        }),
      ],
    }));

    // Stats now live inside the score tile (below the team rows)
    // so the operator scans "team + their stats" in a single
    // column. Per-set values for streak/services/total so the recap
    // doesn't conflate match totals.
    const stats = el('div', {
      class: 'ss-stats-block',
      children: [
        buildGlassStatRowDual(t('longestStreak'),
          vm.longestSet[1] || 0, vm.longestSet[2] || 0),
        buildGlassStatRowDual(t('servicesWon'),
          formatServices(vm.servicesSet, 1), formatServices(vm.servicesSet, 2)),
        buildGlassStatRowDual(t('timeoutsUsed'),
          vm.home.timeouts_taken || 0, vm.away.timeouts_taken || 0),
        buildGlassStatRow(t('totalPoints'), vm.setTotalPoints),
      ],
    });

    stage.appendChild(el('div', {
      class: 'ss-glass ss-score-tile',
      children: [
        el('div', {
          class: 'ss-teams',
          children: [
            buildGlassTeamRow(vm, 'home'),
            buildGlassTeamRow(vm, 'away'),
          ],
        }),
        stats,
      ],
    }));

    const chartTile = el('div', {
      class: 'ss-glass ss-chart-tile',
      children: [
        el('div', {
          class: 'ss-head',
          children: [
            el('span', { class: 'ss-label', text: t('progression') }),
            durationNode(vm.durationSec, { class: 'ss-duration' }),
          ],
        }),
      ],
    });
    const box = el('div', { class: 'ss-chart-box' });
    box.appendChild(buildSvgChart(vm, { width: 480, height: 360, padTop: 8, padBottom: 6 }));
    chartTile.appendChild(box);
    stage.appendChild(chartTile);
  }

  function buildGlassStatRow(label, value) {
    return el('div', {
      class: 'ss-stat-row',
      children: [
        el('span', { class: 'ss-label', text: label }),
        el('span', { class: 'ss-value', text: String(value) }),
      ],
    });
  }

  function buildGlassStatRowDual(label, homeVal, awayVal) {
    const value = dualValueNode(homeVal, awayVal);
    value.className = 'ss-value';
    return el('div', {
      class: 'ss-stat-row',
      children: [
        el('span', { class: 'ss-label', text: label }),
        value,
      ],
    });
  }

  function buildGlassTeamRow(vm, side) {
    const team = side === 'home' ? vm.home : vm.away;
    const score = side === 'home' ? vm.homeScore : vm.awayScore;
    return el('div', {
      class: `ss-team-row ${side}`,
      children: [
        teamLogoNode(team, side),
        el('div', {
          class: 'ss-name',
          children: [
            el('strong', { text: team.name || side.toUpperCase() }),
            el('span', { class: 'ss-tag', text: side === 'home' ? t('home') : t('away') }),
          ],
        }),
        el('div', { class: 'ss-pts', text: String(score) }),
      ],
    });
  }

  // ─────────────────────────────────────────────────────────────────
  // Renderer: podium
  // ─────────────────────────────────────────────────────────────────
  function renderPodium(stage, vm) {
    const homeWins = vm.homeScore >= vm.awayScore;
    const winner = homeWins ? vm.home : vm.away;
    const winnerScore = homeWins ? vm.homeScore : vm.awayScore;
    const loser = homeWins ? vm.away : vm.home;
    const loserScore = homeWins ? vm.awayScore : vm.homeScore;

    // Apply per-pillar colour via custom props so the gradient picks
    // up the actual winner/runner-up team colour. Goes through the
    // contrast-aware resolver so a near-white team palette doesn't
    // turn the pillar into a white-on-white block.
    stage.style.setProperty('--ss-winner',
      homeWins ? resolveTeamColour(vm.home, '#d4314c') : resolveTeamColour(vm.away, '#f0a020'));
    stage.style.setProperty('--ss-loser',
      homeWins ? resolveTeamColour(vm.away, '#f0a020') : resolveTeamColour(vm.home, '#d4314c'));

    const winnerStreak = vm.longestSet[homeWins ? 1 : 2] || 0;
    const loserStreak = vm.longestSet[homeWins ? 2 : 1] || 0;

    stage.appendChild(el('div', {
      class: 'ss-header',
      children: [
        el('span', {
          class: 'ss-badge',
          text: `${t('set')} ${vm.setNum} · ${winner.name || ''}`,
        }),
        el('div', {
          class: 'ss-meta',
          children: [
            labelStrongNode(t('match'), `${vm.team1Sets} – ${vm.team2Sets}`),
            labelStrongNode(t('bestOf'), vm.bestOf),
            el('span', {
              class: 'ss-clock-block',
              children: [
                el('span', { class: 'ss-clock-label', text: t('set') }),
                durationNode(vm.durationSec, { class: 'ss-clock' }),
              ],
            }),
            el('span', {
              class: 'ss-clock-block ss-clock-match',
              children: [
                el('span', { class: 'ss-clock-label', text: t('match') }),
                matchClockNode(vm.matchElapsedSec, { class: 'ss-clock ss-match-duration' }),
              ],
            }),
          ],
        }),
      ],
    }));

    stage.appendChild(el('div', {
      class: 'ss-podium',
      children: [
        el('div', {
          class: 'ss-pillar winner',
          children: [
            el('span', { class: 'ss-team-name', text: winner.name || '' }),
            el('span', { class: 'ss-score', text: String(winnerScore) }),
            el('div', {
              class: 'ss-pillar-stat',
              children: [
                el('strong', { text: winnerStreak ? `${winnerStreak}-${t('pointsShort')}` : '—' }),
                document.createTextNode(t('longestStreak')),
              ],
            }),
          ],
        }),
        el('div', {
          class: 'ss-pillar runner-up',
          children: [
            el('span', { class: 'ss-team-name', text: loser.name || '' }),
            el('span', { class: 'ss-score', text: String(loserScore) }),
            el('div', {
              class: 'ss-pillar-stat',
              children: [
                el('strong', { text: loserStreak ? `${loserStreak}-${t('pointsShort')}` : '—' }),
                document.createTextNode(t('longestStreak')),
              ],
            }),
          ],
        }),
      ],
    }));

    const floor = el('div', {
      class: 'ss-floor',
      children: [
        el('span', { class: 'ss-floor-label', text: t('progression') }),
      ],
    });
    const chartHolder = el('div', { class: 'ss-chart' });
    chartHolder.appendChild(buildSvgChart(vm, { width: 800, height: 80, padTop: 4, padBottom: 4 }));
    floor.appendChild(chartHolder);
    floor.appendChild(durationNode(vm.durationSec, { class: 'ss-duration', prefix: '⏱ ' }));
    stage.appendChild(floor);
  }

  // ─────────────────────────────────────────────────────────────────
  // Renderer: bumper
  // ─────────────────────────────────────────────────────────────────
  function renderBumper(stage, vm) {
    // Core card (centred). Top ribbon + hero scores; no stats strip
    // here — the histogram-style ledger below replaces it.
    const ribbon = el('div', {
      class: 'ss-ribbon',
      children: [
        el('div', {
          class: 'ss-set-badge',
          children: [
            el('span', { class: 'ss-tagline', text: t('recap') }),
            el('span', {
              class: 'ss-num',
              children: [
                el('small', { text: t('set') }),
                document.createTextNode(String(vm.setNum)),
              ],
            }),
          ],
        }),
        el('div', {
          class: 'ss-clocks',
          children: [
            el('span', {
              class: 'ss-clock-block',
              children: [
                el('span', { class: 'ss-clock-label', text: t('set') }),
                durationNode(vm.durationSec, { class: 'ss-duration' }),
              ],
            }),
            el('span', {
              class: 'ss-clock-block ss-clock-match',
              children: [
                el('span', { class: 'ss-clock-label', text: t('match') }),
                matchClockNode(vm.matchElapsedSec, { class: 'ss-duration ss-match-duration' }),
              ],
            }),
          ],
        }),
      ],
    });

    // Stats panel for the centre column of the hero. Per-set
    // streak / services / total so the recap shows the just-played
    // set instead of match-wide cumulatives.
    const stats = el('div', {
      class: 'ss-hero-stats',
      children: [
        buildBumperStatCellDual(t('streak'),
          vm.longestSet[1] || 0, vm.longestSet[2] || 0),
        buildBumperStatCellDual(t('services'),
          formatServices(vm.servicesSet, 1), formatServices(vm.servicesSet, 2)),
        buildBumperStatCellDual(t('timeouts'),
          vm.home.timeouts_taken || 0, vm.away.timeouts_taken || 0),
        buildBumperStatCell(t('totalPoints'), vm.setTotalPoints),
      ],
    });

    const hero = el('div', {
      class: 'ss-hero',
      children: [
        el('div', {
          class: 'ss-team home',
          children: [
            el('span', { class: 'ss-team-tag', text: t('home') }),
            el('span', { class: 'ss-team-name', text: vm.home.name || t('home') }),
            el('span', { class: 'ss-team-score', text: String(vm.homeScore) }),
          ],
        }),
        stats,
        el('div', {
          class: 'ss-team away',
          children: [
            el('span', { class: 'ss-team-tag', text: t('away') }),
            el('span', { class: 'ss-team-name', text: vm.away.name || t('away') }),
            el('span', { class: 'ss-team-score', text: String(vm.awayScore) }),
          ],
        }),
      ],
    });

    const core = el('div', {
      class: 'ss-bumper-core',
      children: [ribbon, hero],
    });

    // Bottom ledger — full stage width so 25+ chips fit per team
    // without resizing. Each row: [logo] [per-event chips] [final].
    const eventInfo = buildBumperEvents(vm);
    const ledger = el('div', {
      class: 'ss-bumper-ledger',
      children: [
        buildBumperRow(vm, 'home', eventInfo),
        buildBumperRow(vm, 'away', eventInfo),
      ],
    });

    stage.appendChild(core);
    stage.appendChild(ledger);
  }

  function buildBumperStatCell(label, value) {
    return el('div', {
      class: 'ss-stat-row',
      children: [
        el('span', { class: 'ss-label', text: label }),
        el('span', { class: 'ss-value', text: String(value) }),
      ],
    });
  }

  function buildBumperStatCellDual(label, homeVal, awayVal) {
    const value = dualValueNode(homeVal, awayVal);
    value.className = 'ss-value';
    return el('div', {
      class: 'ss-stat-row',
      children: [
        el('span', { class: 'ss-label', text: label }),
        value,
      ],
    });
  }

  function buildBumperEvents(vm) {
    const merged = [];
    (vm.setPoints || []).forEach((p) => merged.push({ ...p, kind: 'point' }));
    (vm.setTimeouts || []).forEach((tx) => merged.push({ ...tx, kind: 'timeout' }));
    merged.sort((a, b) => (a.ts || 0) - (b.ts || 0));
    let lastPointIdx = -1;
    for (let i = merged.length - 1; i >= 0; i--) {
      if (merged[i].kind === 'point') { lastPointIdx = i; break; }
    }
    return { events: merged, lastPointIdx };
  }

  function buildBumperRow(vm, side, eventInfo) {
    const team = side === 'home' ? vm.home : vm.away;
    const rowTotal = side === 'home' ? vm.homeScore : vm.awayScore;
    const teamNum = side === 'home' ? 1 : 2;
    const teamScoreIdx = side === 'home' ? 0 : 1;
    const { events, lastPointIdx } = eventInfo;

    const track = el('div', { class: 'ss-track' });
    if (events.length === 0) {
      // Placeholder so the row still has a definite height.
      track.appendChild(el('span', { class: 'ss-chip ss-empty', text: '·' }));
    } else {
      events.forEach((ev, idx) => {
        if (ev.kind === 'point' && ev.team === teamNum) {
          const running = Array.isArray(ev.score) ? ev.score[teamScoreIdx] : 0;
          const chip = el('span', { class: 'ss-chip', text: String(running) });
          if (idx === lastPointIdx) chip.classList.add('ss-final');
          track.appendChild(chip);
        } else if (ev.kind === 'timeout' && ev.team === teamNum) {
          track.appendChild(el('span', { class: 'ss-chip ss-timeout', text: 'T' }));
        } else {
          track.appendChild(el('span', { class: 'ss-chip ss-empty', text: '·' }));
        }
      });
    }

    return el('div', {
      class: `ss-bumper-row ${side}`,
      children: [
        teamLogoNode(team, side, 'ss-row-logo'),
        track,
        el('span', { class: 'ss-row-score', text: String(rowTotal) }),
      ],
    });
  }

  // ─────────────────────────────────────────────────────────────────

  // ── Dispatcher ──────────────────────────────────────────────────
  const RENDERERS = {
    brand_ledger: renderBrandLedger,
    brand_columns: renderBrandColumns,
    bento: renderBento,
    glass: renderGlass,
    podium: renderPodium,
    bumper: renderBumper,
  };

  function renderSetSummary(state) {
    if (!state || !state.match_info) return;
    const panel = ensurePanel();
    const stage = panel.querySelector('.ss-stage');
    const extras = panel.querySelector('.ss-extras');

    // Resolve the requested variant against the known dispatcher
    // keys. Anything else (typo, stale state, malicious payload)
    // collapses to the default — guarded with ``Object.hasOwn`` so
    // static analysis can prove the dispatch target is bounded.
    const requested = state.match_info.set_summary_style;
    const known = typeof requested === 'string'
      && Object.prototype.hasOwnProperty.call(RENDERERS, requested);
    const style = known ? requested : 'brand_ledger';
    const renderer = RENDERERS[style];
    stage.dataset.style = style;
    extras.dataset.style = style;

    // Wipe previous render — every variant rebuilds the markup from
    // scratch so we never inherit attribute/class leftovers from the
    // previous style on a hot-swap.
    clear(stage);
    clear(extras);

    const vm = deriveViewModel(state);
    applyTeamColours(stage, vm.home, vm.away);
    applyTeamColours(extras, vm.home, vm.away);

    renderer(stage, vm, extras);

    // Configure / start the live-duration tick. Two independent
    // anchors:
    //   * setAnchorMs ticks only when the displayed set is the
    //     active one (so a recap of a finished set freezes at the
    //     real set length).
    //   * matchAnchorMs ticks whenever the match has not finished
    //     (regardless of which set is being recapped), so the
    //     "match elapsed" clock reflects real wall time even when
    //     showing a previous set's recap.
    const currentSet = state.match_info.current_set || vm.setNum;
    const setIsLive = vm.setNum === currentSet && !vm.matchFinished;
    const firstTs = vm.setPoints && vm.setPoints[0] && vm.setPoints[0].ts;
    const setAnchorMs = (setIsLive && firstTs) ? Number(firstTs) * 1000 : null;
    const matchAnchorMs = (vm.matchStartedAt && !vm.matchFinished)
      ? Number(vm.matchStartedAt) * 1000
      : null;
    _liveTickState = (setAnchorMs || matchAnchorMs)
      ? { setAnchorMs, matchAnchorMs }
      : null;
    ensureLiveTick();

    // Defer the opacity flip to the next animation frame so the
    // browser paints the freshly-built panel at opacity:0 first;
    // without this the very first activation skips the cross-fade
    // because creation + show fall inside the same paint and the
    // browser has no "from" value to interpolate from.
    if (panel.style.opacity !== '1') {
      requestAnimationFrame(() => {
        panel.style.opacity = '1';
        panel.style.pointerEvents = 'auto';
      });
    }
  }

  function hideSetSummary() {
    const panel = document.getElementById('set-summary-panel');
    if (panel) {
      panel.style.opacity = '0';
      panel.style.pointerEvents = 'none';
    }
    _liveTickState = null;
  }

  window.SetSummary = { render: renderSetSummary, hide: hideSetSummary };
})();
