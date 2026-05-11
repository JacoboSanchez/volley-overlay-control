/*
 * Spectator page — read-only WebSocket consumer for /follow/{id}.
 *
 * Connects to the same /ws/{output_key} feed the OBS templates use
 * and renders into a mobile-friendly layout. No GSAP / no dependencies
 * to keep the page lightweight for end viewers who pop it open on
 * their phones during a match.
 */

(function () {
    const OUTPUT_KEY = window.OVERLAY_OUTPUT_KEY;
    if (!OUTPUT_KEY) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${OUTPUT_KEY}`;

    const $ = (id) => document.getElementById(id);

    const status = $('conn-status');
    function setStatus(text, state) {
        if (!status) return;
        status.textContent = text;
        if (state) status.dataset.state = state;
        else delete status.dataset.state;
    }

    function setText(id, value) {
        const el = $(id);
        if (el && el.textContent !== String(value)) el.textContent = String(value);
    }

    function setLogo(id, url) {
        const el = $(id);
        if (!el) return;
        if (url && /^(https?:|data:image\/)/i.test(url)) {
            if (el.getAttribute('src') !== url) el.setAttribute('src', url);
        } else {
            el.removeAttribute('src');
        }
    }

    function setHidden(id, hidden) {
        const el = $(id);
        if (!el) return;
        el.hidden = !!hidden;
    }

    function setStatsRow(id, label, value) {
        const row = $(id);
        if (!row) return;
        row.dataset.empty = value ? 'false' : 'true';
        if (!value) {
            row.textContent = '';
            return;
        }
        row.textContent = '';
        const labelEl = document.createElement('span');
        labelEl.className = 'label';
        labelEl.textContent = label;
        const valueEl = document.createElement('span');
        valueEl.className = 'value';
        valueEl.textContent = value;
        row.appendChild(labelEl);
        row.appendChild(valueEl);
    }

    function renderScoreboard(state) {
        const home = state.team_home || {};
        const away = state.team_away || {};
        const match = state.match_info || {};
        document.documentElement.style.setProperty(
            '--team1-color', home.color_primary || '#E21836'
        );
        document.documentElement.style.setProperty(
            '--team2-color', away.color_primary || '#0047AB'
        );
        setText('team1-name', home.name || 'Team 1');
        setText('team2-name', away.name || 'Team 2');
        setText('team1-sets', home.sets_won || 0);
        setText('team2-sets', away.sets_won || 0);
        setText('team1-score', home.points || 0);
        setText('team2-score', away.points || 0);
        setLogo('team1-logo', home.logo_url);
        setLogo('team2-logo', away.logo_url);
        setHidden('team1-serve', !home.serving);
        setHidden('team2-serve', !away.serving);
        setText('set-label', 'SET ' + (match.current_set || 1));
        setText(
            'match-title',
            `${home.name || 'Team 1'} vs ${away.name || 'Team 2'}`,
        );
        // Sync legend names with team names.
        setText('legend-name-home', home.name || 'Team 1');
        setText('legend-name-away', away.name || 'Team 2');
        const swHome = $('legend-swatch-home');
        if (swHome) swHome.style.background = home.color_primary || '#E21836';
        const swAway = $('legend-swatch-away');
        if (swAway) swAway.style.background = away.color_primary || '#0047AB';
    }

    function renderHistory(state) {
        const home = state.team_home || {};
        const away = state.team_away || {};
        const match = state.match_info || {};
        const best = Math.max(1, Math.min(7, match.best_of_sets || 5));
        const currentSet = match.current_set || 1;

        const headRow = $('history-head');
        const homeRow = $('history-row-home');
        const awayRow = $('history-row-away');
        if (!headRow || !homeRow || !awayRow) return;
        headRow.textContent = '';
        homeRow.textContent = '';
        awayRow.textContent = '';

        const teamHeader = document.createElement('th');
        teamHeader.textContent = 'Team';
        headRow.appendChild(teamHeader);

        const homeLabel = document.createElement('td');
        homeLabel.className = 'team-cell';
        homeLabel.textContent = home.name || 'Team 1';
        homeRow.appendChild(homeLabel);

        const awayLabel = document.createElement('td');
        awayLabel.className = 'team-cell';
        awayLabel.textContent = away.name || 'Team 2';
        awayRow.appendChild(awayLabel);

        for (let i = 1; i <= best; i += 1) {
            const th = document.createElement('th');
            th.textContent = `S${i}`;
            headRow.appendChild(th);

            const homeCell = document.createElement('td');
            const awayCell = document.createElement('td');
            const homeScore = (home.set_history || {})[`set_${i}`] || 0;
            const awayScore = (away.set_history || {})[`set_${i}`] || 0;
            homeCell.textContent = homeScore;
            awayCell.textContent = awayScore;
            if (i === currentSet) {
                homeCell.classList.add('live-cell');
                awayCell.classList.add('live-cell');
            }
            homeRow.appendChild(homeCell);
            awayRow.appendChild(awayCell);
        }
    }

    function renderStats(state) {
        const oc = state.overlay_control || {};
        const stats = oc.stats || {};
        const cs = stats.current_streak || {};
        const pc = stats.partial_comeback || {};
        const home = state.team_home || {};
        const away = state.team_away || {};

        if (cs.team && cs.n >= 2) {
            const name = cs.team === 1
                ? (home.name || 'Team 1')
                : (away.name || 'Team 2');
            setStatsRow('stats-streak', 'STREAK', `${name} · ${cs.n} in a row`);
        } else {
            setStatsRow('stats-streak', '', '');
        }

        if (typeof stats.total_points === 'number' && stats.total_points > 0) {
            setStatsRow('stats-totals', 'TOTAL POINTS', String(stats.total_points));
        } else {
            setStatsRow('stats-totals', '', '');
        }

        const pcHome = pc[1] || pc['1'] || {};
        const pcAway = pc[2] || pc['2'] || {};
        const peak = Math.max(pcHome.deficit || 0, pcAway.deficit || 0);
        if (peak >= 3) {
            const team = (pcHome.deficit || 0) >= (pcAway.deficit || 0) ? 1 : 2;
            const name = team === 1
                ? (home.name || 'Team 1')
                : (away.name || 'Team 2');
            setStatsRow('stats-comeback', 'COMEBACK', `${name} · -${peak}`);
        } else {
            setStatsRow('stats-comeback', '', '');
        }
    }

    function renderPoints(state) {
        const oc = state.overlay_control || {};
        const history = Array.isArray(oc.points_history) ? oc.points_history : [];
        const track = $('points-track');
        if (!track) return;
        track.textContent = '';
        const fragment = document.createDocumentFragment();
        history.forEach((p, idx) => {
            const chip = document.createElement('span');
            chip.className = 'points-chip';
            chip.dataset.team = String(p.team || 1);
            if (idx === history.length - 1) chip.dataset.fresh = 'true';
            fragment.appendChild(chip);
        });
        track.appendChild(fragment);
    }

    /*
     * Set-progression line chart.
     *
     * Builds a 2-series polyline from ``overlay_control.points_history``
     * filtered to the current set, plotting each team's running score
     * vs. event index. We project on a 600x160 viewBox with 12px padding
     * (kept in sync with the spectator.css ``.set-chart-svg`` height).
     * Each entry in points_history already carries the post-action
     * running score (``score: [t1, t2]``); we prepend a synthetic 0-0
     * baseline so the chart anchors at the origin rather than springing
     * out of the first point's vertical.
     */
    function renderSetChart(state) {
        const empty = $('set-chart-empty');
        const svg = $('set-chart-svg');
        const lineHome = $('set-chart-line-home');
        const lineAway = $('set-chart-line-away');
        const grid = $('set-chart-grid');
        if (!svg || !lineHome || !lineAway || !empty || !grid) return;

        const oc = state.overlay_control || {};
        const match = state.match_info || {};
        const currentSet = match.current_set || 1;
        const history = Array.isArray(oc.points_history) ? oc.points_history : [];

        const setEvents = history.filter(
            (p) => p && (p.set === currentSet || p.set == null),
        );

        if (setEvents.length === 0) {
            svg.setAttribute('hidden', 'hidden');
            empty.removeAttribute('hidden');
            lineHome.setAttribute('d', '');
            lineAway.setAttribute('d', '');
            grid.textContent = '';
            return;
        }

        svg.removeAttribute('hidden');
        empty.setAttribute('hidden', 'hidden');

        const W = 600;
        const H = 160;
        const PAD_X = 24;
        const PAD_Y = 14;
        const innerW = W - PAD_X * 2;
        const innerH = H - PAD_Y * 2;

        // Series: [0-0 baseline, then one point per scoring event]
        const series = [[0, 0]];
        for (const p of setEvents) {
            const s = Array.isArray(p.score) ? p.score : [0, 0];
            series.push([s[0] || 0, s[1] || 0]);
        }
        const maxIdx = Math.max(1, series.length - 1);
        const maxScore = Math.max(
            1,
            ...series.map((pair) => Math.max(pair[0], pair[1])),
        );

        function project(idx, score) {
            const x = PAD_X + (idx / maxIdx) * innerW;
            // Higher score → higher on screen → smaller y.
            const y = PAD_Y + innerH - (score / maxScore) * innerH;
            return [x, y];
        }

        function buildPath(teamIdx) {
            return series
                .map((pair, i) => {
                    const [x, y] = project(i, pair[teamIdx]);
                    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
                })
                .join(' ');
        }

        lineHome.setAttribute('d', buildPath(0));
        lineAway.setAttribute('d', buildPath(1));

        // Lightweight Y-axis ticks at 0 / mid / top so a viewer can
        // read "how many points has each team scored" at a glance.
        grid.textContent = '';
        const ticks = [0, Math.round(maxScore / 2), maxScore];
        const seen = new Set();
        for (const t of ticks) {
            if (seen.has(t)) continue;
            seen.add(t);
            const [, y] = project(0, t);
            const line = document.createElementNS(
                'http://www.w3.org/2000/svg', 'line',
            );
            line.setAttribute('x1', String(PAD_X));
            line.setAttribute('x2', String(W - PAD_X));
            line.setAttribute('y1', y.toFixed(1));
            line.setAttribute('y2', y.toFixed(1));
            grid.appendChild(line);

            const text = document.createElementNS(
                'http://www.w3.org/2000/svg', 'text',
            );
            text.setAttribute('x', '4');
            text.setAttribute('y', (y + 3).toFixed(1));
            text.textContent = String(t);
            grid.appendChild(text);
        }
    }

    function render(state) {
        if (!state || typeof state !== 'object') return;
        renderScoreboard(state);
        renderSetChart(state);
        renderHistory(state);
        renderStats(state);
        renderPoints(state);
    }

    let ws = null;
    let reconnectAttempts = 0;
    let reconnectTimer = null;

    function connect() {
        try {
            ws = new WebSocket(wsUrl);
        } catch (err) {
            setStatus('error', 'offline');
            scheduleReconnect();
            return;
        }
        setStatus('connecting…');

        ws.addEventListener('open', () => {
            setStatus('live', 'online');
            reconnectAttempts = 0;
        });
        ws.addEventListener('message', (event) => {
            try {
                const state = JSON.parse(event.data);
                render(state);
            } catch (err) {
                // ignore malformed frames
            }
        });
        ws.addEventListener('close', () => {
            setStatus('reconnecting…', 'offline');
            scheduleReconnect();
        });
        ws.addEventListener('error', () => {
            // close handler will run too; nothing extra to do here.
        });
    }

    function scheduleReconnect() {
        if (reconnectTimer) return;
        const delay = Math.min(15000, 1000 * Math.pow(2, reconnectAttempts));
        reconnectAttempts += 1;
        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            connect();
        }, delay);
    }

    connect();
})();
