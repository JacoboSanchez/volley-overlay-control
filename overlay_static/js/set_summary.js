/* ─────────────────────────────────────────────────────────────────
   Set summary overlay — renders the recap panel from the live state
   broadcast (no extra fetches). Called by app.js whenever the panel
   is visible (match_info.show_set_summary === true).
   ───────────────────────────────────────────────────────────────── */

(function () {
  'use strict';

  // ── i18n ────────────────────────────────────────────────────────
  // Static label dictionary — mirrors the frontend i18n keys for the
  // few strings this panel renders. The active locale comes from
  // window.OVERLAY_LOCALE (set by base.html or the operator UI). If
  // missing, falls back to English.
  const LABELS = {
    en: {
      set: 'Set', final: 'Final', duration: 'Duration',
      longestStreak: 'Longest streak', servicesWon: 'Services won',
      timeoutsUsed: 'Timeouts used', totalPoints: 'Total points',
      home: 'Home', away: 'Away', empty: 'No points yet this set',
    },
    es: {
      set: 'Set', final: 'Final', duration: 'Duración',
      longestStreak: 'Racha más larga', servicesWon: 'Servicios ganados',
      timeoutsUsed: 'Tiempos muertos', totalPoints: 'Puntos totales',
      home: 'Local', away: 'Visitante', empty: 'Aún sin puntos en este set',
    },
    pt: {
      set: 'Set', final: 'Final', duration: 'Duração',
      longestStreak: 'Maior sequência', servicesWon: 'Serviços ganhos',
      timeoutsUsed: 'Tempos pedidos', totalPoints: 'Pontos totais',
      home: 'Casa', away: 'Visitante', empty: 'Ainda sem pontos neste set',
    },
    it: {
      set: 'Set', final: 'Finale', duration: 'Durata',
      longestStreak: 'Striscia più lunga', servicesWon: 'Servizi vinti',
      timeoutsUsed: 'Timeout usati', totalPoints: 'Punti totali',
      home: 'Casa', away: 'Ospiti', empty: 'Nessun punto in questo set',
    },
    fr: {
      set: 'Set', final: 'Final', duration: 'Durée',
      longestStreak: 'Plus longue série', servicesWon: 'Services gagnés',
      timeoutsUsed: 'Temps morts', totalPoints: 'Points totaux',
      home: 'Domicile', away: 'Visiteur', empty: 'Pas encore de points dans ce set',
    },
    de: {
      set: 'Satz', final: 'Final', duration: 'Dauer',
      longestStreak: 'Längste Serie', servicesWon: 'Aufschläge gewonnen',
      timeoutsUsed: 'Auszeiten', totalPoints: 'Punkte gesamt',
      home: 'Heim', away: 'Auswärts', empty: 'Noch keine Punkte in diesem Satz',
    },
  };

  function t(key) {
    const locale = (window.OVERLAY_LOCALE || 'en').slice(0, 2).toLowerCase();
    const dict = LABELS[locale] || LABELS.en;
    return dict[key] || LABELS.en[key] || key;
  }

  // ── Helpers ─────────────────────────────────────────────────────
  function formatDuration(seconds) {
    if (!seconds || !isFinite(seconds) || seconds < 0) return '–:––';
    const s = Math.round(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
    return `${m}:${String(sec).padStart(2, '0')}`;
  }

  function clearChildren(el) {
    while (el && el.firstChild) el.removeChild(el.firstChild);
  }

  function makeEl(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text != null) el.textContent = text;
    return el;
  }

  // ── Build the panel markup once (idempotent) ────────────────────
  function ensurePanel() {
    let panel = document.getElementById('set-summary-panel');
    if (panel) return panel;
    panel = makeEl('div', 'set-summary-panel');
    panel.id = 'set-summary-panel';
    panel.setAttribute('hidden', '');
    panel.dataset.style = 'brand_ledger';
    panel.innerHTML = `
      <div class="ss-team ss-team-home">
        <div class="ss-team-header">
          <div class="ss-logo" data-team="home"></div>
          <div>
            <div class="ss-team-name" data-team-name="home"></div>
            <div class="ss-team-tag" data-team-tag="home"></div>
          </div>
        </div>
        <div class="ss-team-score" data-team-score="home"></div>
        <div class="ss-team-stat-list" data-team-stats="home"></div>
      </div>

      <div class="ss-centre">
        <div class="ss-set-header">
          <span class="ss-set-label" data-i18n="set"></span>
          <span class="ss-set-number" data-set-number></span>
          <span class="ss-duration-label" data-i18n="duration"></span>
          <span class="ss-duration" data-duration></span>
        </div>
        <div class="ss-ledger">
          <div class="ss-ledger-col ss-ledger-col-home">
            <div class="ss-col-head"><div class="ss-badge" data-team="home"></div></div>
            <div class="ss-col-body" data-ledger="home"></div>
          </div>
          <div class="ss-ledger-col ss-ledger-col-away">
            <div class="ss-col-head"><div class="ss-badge" data-team="away"></div></div>
            <div class="ss-col-body" data-ledger="away"></div>
          </div>
        </div>
      </div>

      <div class="ss-team ss-team-away">
        <div class="ss-team-header">
          <div class="ss-logo" data-team="away"></div>
          <div>
            <div class="ss-team-name" data-team-name="away"></div>
            <div class="ss-team-tag" data-team-tag="away"></div>
          </div>
        </div>
        <div class="ss-team-score" data-team-score="away"></div>
        <div class="ss-team-stat-list" data-team-stats="away"></div>
      </div>
    `;
    document.body.appendChild(panel);
    return panel;
  }

  function fillTeam(panel, side, team, stats, setNum) {
    const initials = (team.short_name || team.name || side[0] || '?')
      .slice(0, 2).toUpperCase();

    const logoEl = panel.querySelector(`.ss-logo[data-team="${side}"]`);
    if (logoEl) {
      clearChildren(logoEl);
      if (team.logo_url) {
        const img = makeEl('img');
        img.src = team.logo_url;
        img.alt = team.name || side;
        logoEl.appendChild(img);
      } else {
        logoEl.textContent = initials;
      }
    }
    const badgeEl = panel.querySelector(`.ss-badge[data-team="${side}"]`);
    if (badgeEl) {
      clearChildren(badgeEl);
      if (team.logo_url) {
        const img = makeEl('img');
        img.src = team.logo_url;
        img.alt = '';
        badgeEl.appendChild(img);
      } else {
        badgeEl.textContent = initials;
      }
    }

    const nameEl = panel.querySelector(`[data-team-name="${side}"]`);
    if (nameEl) nameEl.textContent = team.name || '';
    const tagEl = panel.querySelector(`[data-team-tag="${side}"]`);
    if (tagEl) tagEl.textContent = side === 'home' ? t('home') : t('away');

    const scoreEl = panel.querySelector(`[data-team-score="${side}"]`);
    if (scoreEl) {
      const setKey = `set_${setNum}`;
      const value = team.set_history && team.set_history[setKey];
      scoreEl.textContent = value != null ? value : (team.points || 0);
    }

    const statsEl = panel.querySelector(`[data-team-stats="${side}"]`);
    if (statsEl) {
      clearChildren(statsEl);
      const longest = (stats && stats.longest_streak) || {};
      const services = (stats && stats.services) || {};
      const teamNum = side === 'home' ? 1 : 2;
      const longestForSide = longest && longest.team === teamNum
        ? longest.n
        : 0;
      const svc = services && services[teamNum];
      const stat1 = makeEl('div', 'ss-team-stat');
      stat1.appendChild(makeEl('span', 'ss-label', t('longestStreak')));
      stat1.appendChild(makeEl('span', 'ss-value', String(longestForSide || '–')));
      statsEl.appendChild(stat1);
      const stat2 = makeEl('div', 'ss-team-stat');
      stat2.appendChild(makeEl('span', 'ss-label', t('servicesWon')));
      const svcText = svc && svc.served
        ? `${svc.won || 0} / ${svc.served}`
        : '–';
      stat2.appendChild(makeEl('span', 'ss-value', svcText));
      statsEl.appendChild(stat2);
    }
  }

  function buildLedger(panel, points, timeouts, setNum) {
    // ``points`` is an array of point events (in chronological order)
    // each with shape { team, ts, score: [h, a], action }. ``timeouts``
    // is an array of { team, ts }. Together they form the row sequence
    // we render — each row is one event (point or timeout), every row
    // the same height (grid `repeat(N, 1fr)`).

    // Merge points and timeouts in chronological order.
    const events = [];
    (points || []).forEach((p) => events.push({ ...p, kind: 'point' }));
    (timeouts || []).forEach((to) => events.push({ ...to, kind: 'timeout' }));
    events.sort((a, b) => (a.ts || 0) - (b.ts || 0));

    const homeBody = panel.querySelector('[data-ledger="home"]');
    const awayBody = panel.querySelector('[data-ledger="away"]');
    if (!homeBody || !awayBody) return;

    const rowCount = Math.max(events.length, 1);
    const tracks = `repeat(${rowCount}, 1fr)`;
    homeBody.style.gridTemplateRows = tracks;
    awayBody.style.gridTemplateRows = tracks;
    clearChildren(homeBody);
    clearChildren(awayBody);

    // Detect the final winning point — the last point in the set.
    let lastPointIdx = -1;
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].kind === 'point') { lastPointIdx = i; break; }
    }

    events.forEach((ev, idx) => {
      const isHome = ev.team === 1;
      const homeCell = makeEl('span', 'ss-point ss-empty', '·');
      const awayCell = makeEl('span', 'ss-point ss-empty', '·');
      if (ev.kind === 'point') {
        // Cumulative score for the scoring team at this point.
        const score = Array.isArray(ev.score) ? ev.score : [0, 0];
        const teamScore = isHome ? score[0] : score[1];
        const cell = makeEl('span', 'ss-point', String(teamScore));
        if (idx === lastPointIdx) cell.classList.add('ss-final');
        if (isHome) {
          homeBody.appendChild(cell);
          awayBody.appendChild(awayCell);
        } else {
          homeBody.appendChild(homeCell);
          awayBody.appendChild(cell);
        }
      } else {
        // Timeout marker on the team that called it.
        const marker = makeEl('span', 'ss-point ss-timeout', 'T');
        if (isHome) {
          homeBody.appendChild(marker);
          awayBody.appendChild(awayCell);
        } else {
          homeBody.appendChild(homeCell);
          awayBody.appendChild(marker);
        }
      }
    });

    if (events.length === 0) {
      // Placeholder row when the set has no events yet.
      const empty = makeEl('span', 'ss-point ss-empty', t('empty'));
      homeBody.appendChild(empty.cloneNode(true));
      awayBody.appendChild(empty);
    }
  }

  // ── Public entry point ──────────────────────────────────────────
  function renderSetSummary(state) {
    if (!state || !state.match_info) return;
    const panel = ensurePanel();
    panel.dataset.style = state.match_info.set_summary_style || 'brand_ledger';

    // Resolve the set number to display (server-side computed).
    const setNum = state.match_info.summary_set_num
      || state.match_info.current_set
      || 1;

    // Update i18n labels on the panel.
    panel.querySelectorAll('[data-i18n]').forEach((el) => {
      el.textContent = t(el.dataset.i18n);
    });

    // Set number + duration.
    const setNumEl = panel.querySelector('[data-set-number]');
    if (setNumEl) setNumEl.textContent = String(setNum);
    const durEl = panel.querySelector('[data-duration]');
    if (durEl) {
      const setDurations = (state.overlay_control
        && state.overlay_control.stats
        && state.overlay_control.stats.set_durations) || {};
      const seconds = setDurations[setNum] || setDurations[String(setNum)];
      durEl.textContent = formatDuration(seconds);
    }

    // Apply team colours via CSS custom properties so the brand
    // panels and ledger badges pick them up automatically.
    const home = state.team_home || {};
    const away = state.team_away || {};
    if (home.color_primary) panel.style.setProperty('--ss-home', home.color_primary);
    if (away.color_primary) panel.style.setProperty('--ss-away', away.color_primary);

    const stats = (state.overlay_control && state.overlay_control.stats) || {};
    fillTeam(panel, 'home', home, stats, setNum);
    fillTeam(panel, 'away', away, stats, setNum);

    // Ledger entries for the resolved set.
    const pbs = (state.overlay_control && state.overlay_control.points_by_set) || {};
    const tbs = (state.overlay_control && state.overlay_control.timeouts_by_set) || {};
    const setPoints = pbs[setNum] || pbs[String(setNum)] || [];
    const setTimeouts = tbs[setNum] || tbs[String(setNum)] || [];
    buildLedger(panel, setPoints, setTimeouts, setNum);

    panel.removeAttribute('hidden');
  }

  function hideSetSummary() {
    const panel = document.getElementById('set-summary-panel');
    if (panel) panel.setAttribute('hidden', '');
  }

  // Export for app.js.
  window.SetSummary = { render: renderSetSummary, hide: hideSetSummary };
})();
