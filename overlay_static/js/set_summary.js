/* ─────────────────────────────────────────────────────────────────
   Set summary overlay — runtime renderer.

   Each variant ships its own DOM (built per-render from the live
   state broadcast) and its own CSS rules in
   overlay_static/css/set_summary.css. The dispatcher reads
   match_info.set_summary_style and calls the matching builder
   below; unknown styles fall back to "brand_ledger".

   The wrapper centres the stage in a 16:9 box that fills roughly
   two thirds of the viewport height (with equal margins
   above/below), driven from CSS in set_summary.css (.ss-stage rule).
   ───────────────────────────────────────────────────────────────── */

(function () {
  'use strict';

  // Accent colours used when a team's palette can't be used as-is
  // (unparseable, or near-white with no usable secondary — see
  // ``resolveTeamColour``). Keep in sync with the ``--ss-home`` /
  // ``--ss-away`` defaults in set_summary.css.
  const FALLBACK_HOME = '#d4314c';
  const FALLBACK_AWAY = '#f0a020';

  // ── i18n ────────────────────────────────────────────────────────
  const LABELS = {
    en: {
      final: 'Final', duration: 'Duration',
      longestStreak: 'Longest streak', servicesWon: 'Services won',
      timeoutsUsed: 'Timeouts used',
      home: 'Home', away: 'Away',
      progression: 'Point progression', recap: 'Set recap',
      streak: 'Streak', services: 'Services', timeouts: 'Timeouts',
      points: 'Points', bestOf: 'Best of',
      setWinner: 'Set winner', runnerUp: 'Runner-up',
      live: 'LIVE', vs: 'VS', pointsShort: 'pts',
      empty: 'No points yet this set',
      statsGeneral: 'Overall', statsPointTypes: 'Point types',
      pointDiff: 'Point difference', setPoint: 'Set point',
      chipAce: 'Ace', chipOppErr: 'Opp. err',
    },
    es: {
      final: 'Final', duration: 'Duración',
      longestStreak: 'Racha más larga', servicesWon: 'Servicios ganados',
      timeoutsUsed: 'Tiempos muertos',
      home: 'Local', away: 'Visitante',
      progression: 'Progresión de puntos', recap: 'Resumen del set',
      streak: 'Racha', services: 'Servicios', timeouts: 'Tiempos',
      points: 'Puntos', bestOf: 'Mejor de',
      setWinner: 'Ganador del set', runnerUp: 'Segundo',
      live: 'EN VIVO', vs: 'VS', pointsShort: 'pts',
      empty: 'Aún sin puntos en este set',
      statsGeneral: 'Generales', statsPointTypes: 'Tipos de punto',
      pointDiff: 'Diferencia de puntos', setPoint: 'Punto de set',
      chipAce: 'Saque', chipOppErr: 'Err. riv',
    },
    pt: {
      final: 'Final', duration: 'Duração',
      longestStreak: 'Maior sequência', servicesWon: 'Serviços ganhos',
      timeoutsUsed: 'Tempos pedidos',
      home: 'Casa', away: 'Visitante',
      progression: 'Progressão de pontos', recap: 'Resumo do set',
      streak: 'Sequência', services: 'Serviços', timeouts: 'Tempos',
      points: 'Pontos', bestOf: 'Melhor de',
      setWinner: 'Vencedor do set', runnerUp: 'Segundo',
      live: 'AO VIVO', vs: 'VS', pointsShort: 'pts',
      empty: 'Ainda sem pontos neste set',
      statsGeneral: 'Gerais', statsPointTypes: 'Tipos de ponto',
      pointDiff: 'Diferença de pontos', setPoint: 'Ponto de set',
      chipAce: 'Saque', chipOppErr: 'Err. adv',
    },
    it: {
      final: 'Finale', duration: 'Durata',
      longestStreak: 'Striscia più lunga', servicesWon: 'Servizi vinti',
      timeoutsUsed: 'Timeout usati',
      home: 'Casa', away: 'Ospiti',
      progression: 'Progressione punti', recap: 'Riepilogo set',
      streak: 'Striscia', services: 'Servizi', timeouts: 'Timeout',
      points: 'Punti', bestOf: 'Al meglio di',
      setWinner: 'Vincitore del set', runnerUp: 'Secondo',
      live: 'LIVE', vs: 'VS', pointsShort: 'pti',
      empty: 'Nessun punto in questo set',
      statsGeneral: 'Generali', statsPointTypes: 'Tipi di punto',
      pointDiff: 'Differenza punti', setPoint: 'Set point',
      chipAce: 'Ace', chipOppErr: 'Err. avv',
    },
    fr: {
      final: 'Final', duration: 'Durée',
      longestStreak: 'Plus longue série', servicesWon: 'Services gagnés',
      timeoutsUsed: 'Temps morts',
      home: 'Domicile', away: 'Visiteur',
      progression: 'Progression des points', recap: 'Récap. du set',
      streak: 'Série', services: 'Services', timeouts: 'Temps morts',
      points: 'Points', bestOf: 'Au meilleur de',
      setWinner: 'Vainqueur du set', runnerUp: 'Finaliste',
      live: 'EN DIRECT', vs: 'VS', pointsShort: 'pts',
      empty: 'Pas encore de points dans ce set',
      statsGeneral: 'Général', statsPointTypes: 'Types de point',
      pointDiff: 'Écart de points', setPoint: 'Balle de set',
      chipAce: 'Ace', chipOppErr: 'Faute adv',
    },
    de: {
      final: 'Final', duration: 'Dauer',
      longestStreak: 'Längste Serie', servicesWon: 'Aufschläge gewonnen',
      timeoutsUsed: 'Auszeiten',
      home: 'Heim', away: 'Auswärts',
      progression: 'Punktverlauf', recap: 'Satzrückblick',
      streak: 'Serie', services: 'Aufschläge', timeouts: 'Auszeiten',
      points: 'Punkte', bestOf: 'Best of',
      setWinner: 'Satzgewinner', runnerUp: 'Zweiter',
      live: 'LIVE', vs: 'VS', pointsShort: 'Pkt',
      empty: 'Noch keine Punkte in diesem Satz',
      statsGeneral: 'Gesamt', statsPointTypes: 'Punktarten',
      pointDiff: 'Punktdifferenz', setPoint: 'Satzball',
      chipAce: 'Ass', chipOppErr: 'Geg.-F.',
    },
  };

  // Local key → key in the shared ``window.OVERLAY_LABELS`` bundle
  // (overlay_static/js/i18n_labels.js, loaded before this script by
  // overlay_templates/base.html). Keys not listed here resolve under
  // their own name; keys present in LABELS never reach the bundle.
  const SHARED_KEY_ALIASES = { chipKill: 'kill', chipBlock: 'block' };

  function t(key) {
    const locale = (window.OVERLAY_LOCALE || 'en').slice(0, 2).toLowerCase();
    const dict = LABELS[locale] || LABELS.en;
    if (dict[key] != null) return dict[key];
    // Shared bundle, looked up defensively: a cached page that
    // missed i18n_labels.js degrades to English / the raw key.
    const shared = window.OVERLAY_LABELS || {};
    const sharedKey = SHARED_KEY_ALIASES[key] || key;
    const bundle = shared[locale] || shared.en || {};
    if (bundle[sharedKey] != null) return bundle[sharedKey];
    if (shared.en && shared.en[sharedKey] != null) return shared.en[sharedKey];
    return LABELS.en[key] || key;
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

  // ── Clock skew tracking ─────────────────────────────────────────
  // Every broadcast carries ``match_info.server_time`` (server wall
  // clock at compose time). On arrival we derive a skew offset
  // ``skew = serverNow - Date.now()`` so every ``Date.now()`` here is
  // routed through ``clientNow()`` and the rendered elapsed times
  // track the server even when the operator's system clock is wrong.
  let _clockSkewMs = 0;

  function applyClockSkew(serverTimeSec) {
    if (typeof serverTimeSec !== 'number' || !isFinite(serverTimeSec)) return;
    _clockSkewMs = serverTimeSec * 1000 - Date.now();
  }

  function clientNow() {
    return Date.now() + _clockSkewMs;
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
    const now = clientNow();
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

    // Per-set point-type tallies (opt-in scouting tags). One readout
    // row per type that has at least one tagged point in the displayed
    // set, so a set scored without tags adds nothing to the recap.
    const pointTypesBySet = stats.point_types_by_set || {};
    const setPtRaw = pointTypesBySet[setNum] || pointTypesBySet[String(setNum)] || {};
    const ptHome = setPtRaw['1'] || setPtRaw[1] || {};
    const ptAway = setPtRaw['2'] || setPtRaw[2] || {};
    // Per-team counts for all four types (zeros kept — rendered dimmed),
    // shown as a compact chip strip rather than one row per type so the
    // fixed-size recap panel can't overflow. ``hasPointTypes`` gates the
    // whole block off when the set was scored without any tags.
    const pointTypes = [
      ['ace', 'chipAce'],
      ['kill', 'chipKill'],
      ['block', 'chipBlock'],
      ['opp_error', 'chipOppErr'],
    ].map(([key, labelKey]) => ({
      key,
      label: t(labelKey),
      home: Number(ptHome[key] || 0),
      away: Number(ptAway[key] || 0),
    }));
    const hasPointTypes = pointTypes.some((p) => (p.home + p.away) > 0);

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
        : (clientNow() / 1000);
      matchElapsedSec = Math.max(0, end - matchStartedAt);
    }

    const bestOf = matchInfo.best_of_sets || 5;
    // Points target of the displayed set under the active rules —
    // 21 for beach, 15/25 for a deciding/regular indoor set. Used
    // as the progression chart's vertical scale so short-format
    // sets fill the chart instead of topping out at 25's height.
    const setTarget = Number(
      (setNum >= bestOf
        ? matchInfo.points_limit_last_set
        : matchInfo.points_limit) || 25,
    );

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
      longestSet, servicesSet, setTotalPoints, pointTypes, hasPointTypes,
      setFinished,
      matchFinished: !!matchInfo.match_finished,
      bestOf,
      setTarget,
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
    stage.style.setProperty('--ss-home', resolveTeamColour(home, FALLBACK_HOME));
    stage.style.setProperty('--ss-away', resolveTeamColour(away, FALLBACK_AWAY));
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

    if (vm.hasPointTypes) {
      homeStats.appendChild(buildPtChipStrip(vm, 1));
      awayStats.appendChild(buildPtChipStrip(vm, 2));
    }

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
        emptyNote(vm, { inline: true }),
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

  // ── Point-type breakdown (compact chips) ───────────────────────
  // A bounded chip strip (one chip per type, short label + count, zeros
  // dimmed) replaces the per-type stat rows so the fixed-size recap
  // panel can never overflow no matter how many types were tagged.

  function buildPtChip(label, value, teamClass) {
    return el('span', {
      class: 'ss-pt-chip' + (value === 0 ? ' is-zero' : ''),
      children: [
        el('span', { class: 'ss-pt-chip-k', text: label }),
        el('span', { class: 'ss-pt-chip-n ' + (teamClass || ''), text: String(value) }),
      ],
    });
  }

  function buildPtChipStrip(vm, team) {
    const teamClass = team === 1 ? 'home' : 'away';
    return el('div', {
      class: 'ss-pt-chips',
      children: (vm.pointTypes || []).map((p) =>
        buildPtChip(p.label, team === 1 ? p.home : p.away, teamClass)),
    });
  }

  // Combined two-row breakdown (team logo + chip strip per side) for the
  // tile / centre variants. Returns ``null`` when nothing was tagged so
  // the block disappears entirely; always exactly two lines otherwise.
  function buildPtBreakdown(vm) {
    if (!vm.hasPointTypes) return null;
    const row = (team, side) => el('div', {
      class: 'ss-pt-row',
      children: [
        teamLogoNode(team === 1 ? vm.home : vm.away, side, 'ss-pt-logo'),
        buildPtChipStrip(vm, team),
      ],
    });
    return el('div', {
      class: 'ss-pt-breakdown',
      children: [row(1, 'home'), row(2, 'away')],
    });
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

    if (vm.hasPointTypes) {
      homeStats.appendChild(buildPtChipStrip(vm, 1));
      awayStats.appendChild(buildPtChipStrip(vm, 2));
    }

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

  // Localized "no points yet" note, or null once the set has events.
  // Variants drop it over their empty chart area (absolute overlay)
  // or into normal flow with ``inline: true``.
  function emptyNote(vm, opts) {
    if (vm.setPoints.length) return null;
    const inline = opts && opts.inline;
    return el('div', {
      class: inline ? 'ss-empty-note ss-empty-note--inline' : 'ss-empty-note',
      text: t('empty'),
    });
  }

  function buildChartWrap(vm, variant) {
    const wrap = el('div', { class: 'ss-chart-wrap' });
    wrap.appendChild(buildSvgChart(vm, { width: 300, height: 380, padLeft: 6, padRight: 6 }));
    const note = emptyNote(vm);
    if (note) wrap.appendChild(note);
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

    const maxY = Math.max(maxScoreInEvents(vm.setPoints), vm.setTarget || 25);
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
    const homeCol = resolveTeamColour(vm.home, FALLBACK_HOME);
    const awayCol = resolveTeamColour(vm.away, FALLBACK_AWAY);
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
    const tile = el('div', { class: 'ss-tile ss-tile-stats', children: rows });
    const breakdown = buildPtBreakdown(vm);
    if (breakdown) tile.appendChild(breakdown);
    return tile;
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

    const scoreTileChildren = [
      el('div', {
        class: 'ss-teams',
        children: [
          buildGlassTeamRow(vm, 'home'),
          buildGlassTeamRow(vm, 'away'),
        ],
      }),
      stats,
    ];

    stage.appendChild(el('div', {
      class: 'ss-glass ss-score-tile',
      children: scoreTileChildren,
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
    const glassNote = emptyNote(vm);
    if (glassNote) box.appendChild(glassNote);
    chartTile.appendChild(box);
    stage.appendChild(chartTile);

    // Full-width breakdown band below both tiles — mirrors the top
    // header strip. Spans the score + chart columns so the two-line
    // chip strip gets the whole width instead of cramming the tile.
    const glassBreakdown = buildPtBreakdown(vm);
    // Flag the stage so the CSS tightens the score tile only when the
    // band is present — it consumes a chunk of the fixed-height body
    // row, which would otherwise clip the lower stats (timeouts / total
    // points). Without the band the tile keeps its roomier layout.
    stage.classList.toggle('ss-has-breakdown', !!glassBreakdown);
    if (glassBreakdown) {
      // ``ss-glass`` gives the band the same frosted-dark tile backing
      // as the score/chart tiles so its labels stay legible over any
      // scene; ``ss-pt-breakdown-wide`` makes it span both columns.
      glassBreakdown.classList.add('ss-glass', 'ss-pt-breakdown-wide');
      stage.appendChild(glassBreakdown);
    }
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
  // Renderer: ledger_diff (scoresheet + point-difference graph)
  // ─────────────────────────────────────────────────────────────────
  // A comparative box-score on top — one row per stat with the home
  // value, a bar tinted toward whichever side leads, and the away
  // value — over a full-width "point difference" area graph that
  // swings up toward the home team and down toward the away team as
  // the lead changes through the set. When the set carries per-point
  // scouting tags the stats split into two columns (general | point
  // types); otherwise a single centred column shows and the graph
  // gets the extra room.

  function buildLdRow(label, homeText, awayText, homeShare, awayShare) {
    const h = Number(homeShare) || 0;
    const a = Number(awayShare) || 0;
    const total = h + a;
    const hp = total > 0 ? Math.round((h / total) * 100) : 50;
    const bar = el('div', {
      class: 'ss-ld-bar',
      children: [
        el('span', { class: 'ss-ld-fh', style: { width: hp + '%' } }),
        el('span', { class: 'ss-ld-fa', style: { width: (100 - hp) + '%' } }),
        el('span', { class: 'ss-ld-cap', text: label }),
      ],
    });
    return el('div', {
      class: 'ss-ld-row',
      children: [
        el('span', { class: 'ss-ld-hv', text: String(homeText) }),
        bar,
        el('span', { class: 'ss-ld-av', text: String(awayText) }),
      ],
    });
  }

  // Left column: the four match-wide-per-set comparisons every set has.
  // Service share is driven by rallies won-on-serve; a zero timeout
  // count keeps a 0.4 sliver so the bar still reads as "0 vs n".
  function buildLdGeneralCol(vm) {
    const sH = (vm.servicesSet && (vm.servicesSet[1] || vm.servicesSet['1'])) || {};
    const sA = (vm.servicesSet && (vm.servicesSet[2] || vm.servicesSet['2'])) || {};
    const toH = vm.home.timeouts_taken || 0;
    const toA = vm.away.timeouts_taken || 0;
    const col = el('div', { class: 'ss-ld-col' });
    col.appendChild(buildLdRow(
      t('points'), vm.homeScore, vm.awayScore, vm.homeScore, vm.awayScore));
    col.appendChild(buildLdRow(
      t('streak'), vm.longestSet[1] || 0, vm.longestSet[2] || 0,
      vm.longestSet[1] || 0, vm.longestSet[2] || 0));
    col.appendChild(buildLdRow(
      t('services'),
      formatServices(vm.servicesSet, 1), formatServices(vm.servicesSet, 2),
      sH.won || 0, sA.won || 0));
    col.appendChild(buildLdRow(t('timeouts'), toH, toA, toH || 0.4, toA || 0.4));
    return col;
  }

  // Right column: the opt-in point-type tallies, shown attack / block /
  // serve / opp-error. Only built when ``vm.hasPointTypes`` is set.
  function buildLdPointTypesCol(vm) {
    const byKey = {};
    (vm.pointTypes || []).forEach((p) => { byKey[p.key] = p; });
    const col = el('div', { class: 'ss-ld-col ss-ld-col-right' });
    ['kill', 'block', 'ace', 'opp_error'].forEach((k) => {
      const p = byKey[k] || { label: k, home: 0, away: 0 };
      col.appendChild(buildLdRow(p.label, p.home, p.away, p.home, p.away));
    });
    return col;
  }

  function buildLdTeamCard(vm, side) {
    const team = side === 'home' ? vm.home : vm.away;
    const score = side === 'home' ? vm.homeScore : vm.awayScore;
    return el('div', {
      class: `ss-ld-team ${side}`,
      children: [
        teamLogoNode(team, side, 'ss-ld-logo'),
        el('div', {
          class: 'ss-ld-meta',
          children: [
            el('div', {
              class: 'ss-ld-name',
              text: team.name || (side === 'home' ? t('home') : t('away')),
            }),
            el('div', {
              class: 'ss-ld-tag',
              text: side === 'home' ? t('home') : t('away'),
            }),
          ],
        }),
        el('div', { class: 'ss-ld-score', text: String(score) }),
      ],
    });
  }

  // Point-difference area: a margin (home − away) line over the rally
  // axis, filled from a centre baseline with a vertical gradient (home
  // colour above, away below) so a glance shows who led and by how
  // much. Timeout ticks mark where each timeout fell; the trailing dot
  // flags the final (set-deciding) point.
  function buildLdDiffChart(vm) {
    const W = 1000, H = 240, pad = 12, cy = H / 2;
    const events = vm.setPoints || [];
    const total = events.length;
    let maxM = 4;
    const margins = events.map((ev) => {
      const s = Array.isArray(ev.score) ? ev.score : [0, 0];
      const m = (s[0] || 0) - (s[1] || 0);
      if (Math.abs(m) > maxM) maxM = Math.abs(m);
      return m;
    });
    const X = (i) => pad + (total > 0 ? (i / total) * (W - 2 * pad) : 0);
    const Y = (m) => cy - (m / maxM) * (cy - pad);

    const svg = svgEl('svg', {
      viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none', class: 'ss-ld-svg',
    });
    const defs = svgEl('defs');
    const grad = svgEl('linearGradient', {
      id: 'ssLdGrad', x1: '0', y1: '0', x2: '0', y2: '1',
    });
    grad.appendChild(svgEl('stop', { offset: '0', class: 'ss-ld-grad-top' }));
    grad.appendChild(svgEl('stop', {
      offset: '0.5', 'stop-color': '#ffffff', 'stop-opacity': '0.05',
    }));
    grad.appendChild(svgEl('stop', { offset: '1', class: 'ss-ld-grad-bot' }));
    defs.appendChild(grad);
    svg.appendChild(defs);

    (vm.setTimeouts || []).forEach((tx) => {
      let c = 0;
      for (const ev of events) {
        if ((ev.ts || 0) <= (tx.ts || 0)) c++; else break;
      }
      const x = X(c);
      svg.appendChild(svgEl('line', {
        class: 'ss-ld-to', x1: x.toFixed(1), y1: pad, x2: x.toFixed(1), y2: H - pad,
      }));
    });

    if (total > 0) {
      const linePts = [`${pad},${cy}`];
      margins.forEach((m, idx) => {
        linePts.push(`${X(idx + 1).toFixed(1)},${Y(m).toFixed(1)}`);
      });
      const lineStr = linePts.join(' ');
      svg.appendChild(svgEl('polygon', {
        class: 'ss-ld-area',
        points: `${lineStr} ${X(total).toFixed(1)},${cy.toFixed(1)}`,
        fill: 'url(#ssLdGrad)',
      }));
      svg.appendChild(svgEl('polyline', { class: 'ss-ld-line', points: lineStr }));
    }
    svg.appendChild(svgEl('line', {
      class: 'ss-ld-zero', x1: pad, y1: cy, x2: W - pad, y2: cy,
    }));
    if (total > 0) {
      svg.appendChild(svgEl('circle', {
        class: 'ss-ld-dot',
        cx: X(total).toFixed(1), cy: Y(margins[total - 1]).toFixed(1), r: '5',
      }));
    }
    return svg;
  }

  function renderLedgerDiff(stage, vm) {
    stage.appendChild(el('div', {
      class: 'ss-ld-header',
      children: [
        el('span', {
          class: `ss-ld-pill ${vm.setFinished ? 'is-final' : 'is-live'}`,
          text: `${t('set')} ${vm.setNum} · ${vm.setFinished ? t('final') : t('live')}`,
        }),
        el('div', {
          class: 'ss-ld-matchscore',
          children: [
            el('span', { class: 'ss-ld-ms-label', text: t('match') }),
            el('span', {
              class: 'ss-ld-ms-value',
              children: [
                el('span', { class: 'home', text: String(vm.team1Sets) }),
                document.createTextNode(' – '),
                el('span', { class: 'away', text: String(vm.team2Sets) }),
              ],
            }),
          ],
        }),
        el('div', {
          class: 'ss-ld-clocks',
          children: [
            el('span', {
              class: 'ss-clock-block',
              children: [
                el('span', { class: 'ss-clock-label', text: t('set') }),
                durationNode(vm.durationSec, { class: 'ss-ld-clock' }),
              ],
            }),
            el('span', {
              class: 'ss-clock-block ss-clock-match',
              children: [
                el('span', { class: 'ss-clock-label', text: t('match') }),
                matchClockNode(vm.matchElapsedSec, {
                  class: 'ss-ld-clock ss-match-duration',
                }),
              ],
            }),
          ],
        }),
      ],
    }));

    stage.appendChild(el('div', {
      class: 'ss-ld-teams',
      children: [buildLdTeamCard(vm, 'home'), buildLdTeamCard(vm, 'away')],
    }));

    let cols;
    if (vm.hasPointTypes) {
      const general = buildLdGeneralCol(vm);
      general.insertBefore(
        el('div', { class: 'ss-ld-colcap', text: t('statsGeneral') }),
        general.firstChild);
      const types = buildLdPointTypesCol(vm);
      types.insertBefore(
        el('div', { class: 'ss-ld-colcap', text: t('statsPointTypes') }),
        types.firstChild);
      cols = el('div', { class: 'ss-ld-cols two', children: [general, types] });
    } else {
      cols = el('div', { class: 'ss-ld-cols one', children: [buildLdGeneralCol(vm)] });
    }
    stage.appendChild(cols);

    const body = el('div', {
      class: 'ss-ld-graph-body',
      children: [
        buildLdDiffChart(vm),
        el('span', { class: 'ss-ld-annot ss-ld-annot-top', text: `▲ ${t('home')}` }),
        el('span', { class: 'ss-ld-annot ss-ld-annot-bot', text: `▼ ${t('away')}` }),
      ],
    });
    const note = emptyNote(vm);
    if (note) body.appendChild(note);

    const title = el('div', {
      class: 'ss-ld-graph-title',
      children: [el('span', { class: 'ss-ld-gt', text: t('pointDiff') })],
    });
    if (vm.setFinished && (vm.setPoints || []).length) {
      title.appendChild(el('span', {
        class: 'ss-ld-sp-leg', text: `● ${t('setPoint')}`,
      }));
    }
    stage.appendChild(el('div', { class: 'ss-ld-graph', children: [title, body] }));
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

    const coreChildren = [ribbon, hero];
    const bumperBreakdown = buildPtBreakdown(vm);
    if (bumperBreakdown) coreChildren.push(bumperBreakdown);
    const core = el('div', {
      class: 'ss-bumper-core',
      children: coreChildren,
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
  // ``pickRenderer`` resolves the operator-selected variant key to
  // its concrete renderer function via an explicit ``switch``. The
  // shape is deliberately exhaustive (no fall-through ``return
  // table[key]``) so static analysis can prove the call target is
  // bounded — bracket-notation dispatch on a user-controlled key
  // trips CodeQL's "unvalidated dynamic method call" rule even when
  // the key has been validated against ``Object.hasOwn``.
  const KNOWN_VARIANTS = [
    'brand_ledger',
    'brand_columns',
    'bento',
    'glass',
    'ledger_diff',
    'bumper',
  ];

  function pickRenderer(style) {
    switch (style) {
      case 'brand_ledger': return renderBrandLedger;
      case 'brand_columns': return renderBrandColumns;
      case 'bento': return renderBento;
      case 'glass': return renderGlass;
      case 'ledger_diff': return renderLedgerDiff;
      case 'bumper': return renderBumper;
      default: return renderBrandLedger;
    }
  }

  function renderSetSummary(state) {
    if (!state || !state.match_info) return;
    // Refresh the client/server clock-skew offset from the freshly
    // arrived broadcast, then every ``Date.now()`` below routes
    // through ``clientNow()`` so the rendered durations track the
    // server clock even when the operator's machine is wrong.
    applyClockSkew(state.match_info.server_time);
    const panel = ensurePanel();
    const stage = panel.querySelector('.ss-stage');
    const extras = panel.querySelector('.ss-extras');

    // Resolve the requested variant against the known dispatcher
    // keys. Anything else (typo, stale state, malicious payload)
    // collapses to the default. ``pickRenderer`` returns a concrete
    // function reference via ``switch`` so we never invoke through a
    // bracket-notation dispatch table.
    const requested = state.match_info.set_summary_style;
    const style = (typeof requested === 'string'
      && KNOWN_VARIANTS.indexOf(requested) !== -1)
      ? requested
      : 'brand_ledger';
    const renderer = pickRenderer(style);
    stage.dataset.style = style;
    extras.dataset.style = style;

    // Wipe previous render — every variant rebuilds the markup from
    // scratch so we never inherit attribute/class leftovers from the
    // previous style on a hot-swap. Resetting className (not just the
    // children) drops per-variant marker classes like
    // ``ss-has-breakdown`` so they can't linger when switching to a
    // style that never sets them.
    stage.className = 'ss-stage';
    extras.className = 'ss-extras';
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
