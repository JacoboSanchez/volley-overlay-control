// Headless screenshot capture for the project README.
//
// Assumes a dev/staging instance of volley-overlay-control is running at
// SCREENSHOT_BASE_URL (default http://localhost:8181) with:
//   - OVERLAY_MANAGER_PASSWORD set to SCREENSHOT_ADMIN_PASSWORD (default "demo")
//   - the built frontend mounted at /
//   - the bundled overlay engine available at /overlay/{id}
//
// The companion run.sh boots an isolated backend with these settings and
// pre-creates the demo overlay used here.

import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { mkdir } from 'node:fs/promises';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const REPO_ROOT = resolve(__dirname, '..', '..');
const OUT_DIR = resolve(REPO_ROOT, 'docs', 'screenshots');

const BASE = process.env.SCREENSHOT_BASE_URL || 'http://localhost:8181';
const ADMIN_PW = process.env.SCREENSHOT_ADMIN_PASSWORD || 'demo';
const DEMO_OID = process.env.SCREENSHOT_DEMO_OID || 'centercourt';

// Invented match data — deliberately not the operator's real teams.
//
// The overlay engine's <img> sanitizer (overlay_static/js/app.js,
// `sanitizeImageUrl`) intentionally rejects everything except http(s)
// to defend against javascript:/data:/vbscript: XSS, so the logos must
// be served as http URLs. We anchor them at the backend's own origin
// so the control UI's strict CSP (`img-src 'self' data: https:`) treats
// them as same-origin; Playwright's route handler intercepts the
// request and returns the inline SVG, so no actual network call is
// made and no real /screenshot-logos/* path needs to exist on the
// backend.
const LOGO_HOST = `${BASE}/screenshot-logos`;
const TEAM_1 = {
  name: 'Thunder Wolves',
  color: '#1e3a8a',
  textColor: '#ffffff',
  logo: `${LOGO_HOST}/team-thunder-wolves.svg`,
  logoSvg:
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">' +
      '<circle cx="50" cy="50" r="48" fill="#1e3a8a" stroke="#ffffff" stroke-width="3"/>' +
      '<text x="50" y="63" font-family="Arial Black,Arial,sans-serif" font-size="34" font-weight="900" fill="#ffffff" text-anchor="middle">TW</text>' +
    '</svg>',
};
const TEAM_2 = {
  name: 'Solar Hawks',
  color: '#f59e0b',
  textColor: '#1f2937',
  logo: `${LOGO_HOST}/team-solar-hawks.svg`,
  logoSvg:
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">' +
      '<circle cx="50" cy="50" r="48" fill="#f59e0b" stroke="#1f2937" stroke-width="3"/>' +
      '<text x="50" y="63" font-family="Arial Black,Arial,sans-serif" font-size="34" font-weight="900" fill="#1f2937" text-anchor="middle">SH</text>' +
    '</svg>',
};

async function installLogoRouter(context) {
  // Intercept every request to the synthetic logo host and return the
  // matching SVG inline. Both the React control UI and the overlay
  // browser pages live in this context, so a single handler covers both.
  await context.route(`${LOGO_HOST}/**`, (route) => {
    const url = route.request().url();
    if (url.endsWith('team-thunder-wolves.svg')) {
      return route.fulfill({
        status: 200,
        contentType: 'image/svg+xml',
        body: TEAM_1.logoSvg,
      });
    }
    if (url.endsWith('team-solar-hawks.svg')) {
      return route.fulfill({
        status: 200,
        contentType: 'image/svg+xml',
        body: TEAM_2.logoSvg,
      });
    }
    return route.fulfill({ status: 404, body: '' });
  });
}

// Mobile-landscape is the primary capture viewport because the
// scoring operator's main use case is a phone held sideways during a
// match. 844×390 is the rotation of PHONE_VIEWPORT below (iPhone-class
// dimensions). The exception is /manage, which is browser-first
// (operators rarely admin from a phone) — it uses MANAGE_VIEWPORT, a
// scaled-down desktop layout.
const MOBILE_LANDSCAPE_VIEWPORT = { width: 844, height: 390 };
const PHONE_VIEWPORT = { width: 390, height: 844 };
const MANAGE_VIEWPORT = { width: 1024, height: 700 };
// /match/{id}/report is a print-friendly HTML page with a 960px max
// content width — operators read it on a desktop or share it as PDF,
// so it gets a desktop-sized viewport with enough vertical room to
// fit the hero, set-by-set table and the top of the timeline in one
// frame.
const REPORT_VIEWPORT = { width: 1024, height: 1100 };
const REPORT_OID = 'practice-hall';
// /follow/{id} is the public, mobile-first spectator page. It is a
// pure WebSocket consumer with no auth, no write paths, and a
// responsive single-column layout — header, scoreboard, set chart,
// history, stats. We capture it at phone-portrait width but full-page
// so the screenshot shows every section (scrolling) instead of just
// the above-the-fold scoreboard.
const SPECTATOR_VIEWPORT = { width: 414, height: 896 };
// Set-summary overlays are stream-overlay surfaces — captured at the
// canonical 16:9 OBS browser-source size so the cqw/cqh container
// queries resolve to their full-stage values, matching what an
// operator pipes to OBS.
const OVERLAY_HD_VIEWPORT = { width: 1280, height: 720 };

async function ensureDemoOverlay() {
  const adminHeaders = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${ADMIN_PW}`,
  };

  // Create (idempotent — ignore "already exists" 409s).
  const createRes = await fetch(`${BASE}/api/v1/admin/custom-overlays`, {
    method: 'POST',
    headers: adminHeaders,
    body: JSON.stringify({ name: DEMO_OID }),
  });
  if (!createRes.ok && createRes.status !== 409) {
    const txt = await createRes.text();
    throw new Error(`Could not create overlay ${DEMO_OID}: ${createRes.status} ${txt}`);
  }

  // Make sure a second overlay exists too, so the manager-page list isn't a
  // single row.
  const second = `practice-hall`;
  const secondRes = await fetch(`${BASE}/api/v1/admin/custom-overlays`, {
    method: 'POST',
    headers: adminHeaders,
    body: JSON.stringify({ name: second }),
  });
  if (!secondRes.ok && secondRes.status !== 409) {
    const txt = await secondRes.text();
    console.warn(`Could not create overlay ${second}: ${secondRes.status} ${txt}`);
  }

  // Initialise a session for the demo overlay so /api/v1/customization works.
  const initRes = await fetch(`${BASE}/api/v1/session/init`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ oid: DEMO_OID }),
  });
  if (!initRes.ok) {
    const txt = await initRes.text();
    throw new Error(`session/init failed: ${initRes.status} ${txt}`);
  }

  // Apply invented team customization. Pin preferredStyle to "glass" so
  // the React control UI surfaces (init / scoreboard / config / phone /
  // manage page embedded previews) all show the same overlay treatment;
  // the standalone overlay-output screenshots below override this with
  // an explicit ?style= query when they need a different look.
  const customization = {
    'Team 1 Text Name': TEAM_1.name,
    'Team 2 Text Name': TEAM_2.name,
    'Team 1 Color': TEAM_1.color,
    'Team 2 Color': TEAM_2.color,
    'Team 1 Text Color': TEAM_1.textColor,
    'Team 2 Text Color': TEAM_2.textColor,
    'Team 1 Logo': TEAM_1.logo,
    'Team 2 Logo': TEAM_2.logo,
    Logos: 'true',
    preferredStyle: 'glass',
  };
  const custRes = await fetch(
    `${BASE}/api/v1/customization?oid=${encodeURIComponent(DEMO_OID)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(customization),
    },
  );
  if (!custRes.ok) {
    const txt = await custRes.text();
    throw new Error(`customization PUT failed: ${custRes.status} ${txt}`);
  }

  // Drive a realistic match into the state — adds 12 / 8 in set 1 and a
  // serve to team A so the rendered scoreboard isn't all zeroes.
  await driveMatchState();
}

async function ensureFinishedMatchForReport() {
  // Drive ``REPORT_OID`` (the second overlay already created above) to
  // a complete 4-set match so its archive is available at
  // ``/match/{match_id}/report``. Uses ``set_score`` to fast-forward
  // the loser's count in each set and ``add_point`` for the
  // set-winning point — that way the audit log has a real point-by-
  // point transition the report timeline can render, instead of just
  // four bulk score-overrides.
  const initRes = await fetch(`${BASE}/api/v1/session/init`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ oid: REPORT_OID }),
  });
  if (!initRes.ok) {
    const txt = await initRes.text();
    throw new Error(`session/init for ${REPORT_OID} failed: ${initRes.status} ${txt}`);
  }

  // Same invented teams so the report shares the visual identity of
  // the scoreboard shots. Note ``Team N Text Name`` drives the React
  // scoreboard while ``Team N Name`` is what ``app.match_report``
  // looks up — both keys point to the same string here so either
  // surface picks the right label.
  const customization = {
    'Team 1 Text Name': TEAM_1.name,
    'Team 2 Text Name': TEAM_2.name,
    'Team 1 Name': TEAM_1.name,
    'Team 2 Name': TEAM_2.name,
    'Team 1 Color': TEAM_1.color,
    'Team 2 Color': TEAM_2.color,
    'Team 1 Text Color': TEAM_1.textColor,
    'Team 2 Text Color': TEAM_2.textColor,
    'Team 1 Logo': TEAM_1.logo,
    'Team 2 Logo': TEAM_2.logo,
    Logos: 'true',
  };
  const custRes = await fetch(
    `${BASE}/api/v1/customization?oid=${encodeURIComponent(REPORT_OID)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(customization),
    },
  );
  if (!custRes.ok) {
    const txt = await custRes.text();
    throw new Error(`customization for ${REPORT_OID} failed: ${custRes.status} ${txt}`);
  }

  const post = (path, body) =>
    fetch(`${BASE}${path}?oid=${encodeURIComponent(REPORT_OID)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body == null ? undefined : JSON.stringify(body),
    });

  // Arm the live timer first so the archive carries a non-zero match
  // duration and the report renders a meaningful "Duration: …" cell.
  await post('/api/v1/game/start-match', null);

  // Drive a set with the eventual winner pre-set first so the
  // "biggest comeback" highlight is computed against realistic
  // running scores instead of an artificial ``(0, loserEnd)``
  // transient. Set the winner to ``loserEnd`` (tied), then bring
  // the loser up to ``loserEnd``, optionally fire some in-set
  // ``add_timeout`` calls (they must land BEFORE the closing
  // add_point because the set-winning point advances
  // ``current_set`` and any timeout after that would be recorded
  // against the next set), then drive the winning team's remaining
  // points via ``add_point`` so the audit log carries real
  // point-by-point transitions.
  async function closeSet(setNum, winner, winnerEnd, loserEnd, timeouts = {}) {
    const loser = winner === 1 ? 2 : 1;
    await post('/api/v1/game/set-score', {
      team: winner, set_number: setNum, value: loserEnd,
    });
    await post('/api/v1/game/set-score', {
      team: loser, set_number: setNum, value: loserEnd,
    });
    for (let i = 0; i < (timeouts[1] || 0); i++) {
      await post('/api/v1/game/add-timeout', { team: 1 });
    }
    for (let i = 0; i < (timeouts[2] || 0); i++) {
      await post('/api/v1/game/add-timeout', { team: 2 });
    }
    for (let i = 0; i < winnerEnd - loserEnd; i++) {
      await post('/api/v1/game/add-point', { team: winner });
    }
  }

  // TW wins 3-1 in four sets. Sets 1-3 use the boring closeSet helper
  // (tight back-and-forth, no notable deficit). Set 4 is driven
  // explicitly so the "biggest comeback" highlight has a real story
  // to tell: SH jumps to 0-5, TW catches up and closes 25-22.
  //
  // The 700-ms gaps between sets give the audit log a non-zero
  // wall-clock spread so the report's "Duration" cell and the
  // score-evolution charts' time axis aren't compressed to 0m 00s.
  const setBreak = () => new Promise((r) => setTimeout(r, 700));

  // Set 1 — TW 25-23 with both teams calling 1 timeout each.
  //   set-by-set cells: TW "25 (1)"  /  SH "23 (1)".
  await closeSet(1, /*winner=*/1, /*winnerEnd=*/25, /*loserEnd=*/23,
                 /*timeouts=*/{ 1: 1, 2: 1 });
  await setBreak();

  // Set 2 — SH 25-21. SH burns both timeouts while consolidating the
  // lead. TW had no timeouts.
  //   set-by-set cells: TW "21"  /  SH "25 (2)".
  await closeSet(2, /*winner=*/2, /*winnerEnd=*/25, /*loserEnd=*/21,
                 /*timeouts=*/{ 2: 2 });
  await setBreak();

  // Set 3 — TW 25-19, dominant. No timeouts called.
  await closeSet(3, /*winner=*/1, /*winnerEnd=*/25, /*loserEnd=*/19);
  await setBreak();

  // Set 4 — TW comes back from 0-5 to win 25-22.
  // ``set_score`` jumps SH to 5 first; the next 5 add_points pull TW
  // even at 5-5. From there we tied-fast-forward to 22-22 and TW
  // closes the match with three more add_points. The eventual
  // winner (TW) faces a real 5-point deficit during the early phase,
  // which is what the "biggest comeback" stat is meant to highlight.
  // Both sides call one timeout mid-comeback.
  await post('/api/v1/game/set-score', { team: 2, set_number: 4, value: 5 });
  for (let i = 0; i < 5; i++) {
    await post('/api/v1/game/add-point', { team: 1 });
  }
  await post('/api/v1/game/add-timeout', { team: 1 });
  await post('/api/v1/game/add-timeout', { team: 2 });
  await post('/api/v1/game/set-score', { team: 1, set_number: 4, value: 22 });
  await post('/api/v1/game/set-score', { team: 2, set_number: 4, value: 22 });
  for (let i = 0; i < 3; i++) {
    await post('/api/v1/game/add-point', { team: 1 });
  }
}

async function fetchLatestMatchId() {
  // /api/v1/matches is admin-gated and returns {count, matches}.
  const res = await fetch(
    `${BASE}/api/v1/matches?oid=${encodeURIComponent(REPORT_OID)}`,
    { headers: { Authorization: `Bearer ${ADMIN_PW}` } },
  );
  if (!res.ok) {
    throw new Error(`Could not list matches for ${REPORT_OID}: ${res.status}`);
  }
  const body = await res.json();
  const matches = Array.isArray(body) ? body : body.matches;
  if (!Array.isArray(matches) || matches.length === 0) {
    throw new Error(`No archived matches for ${REPORT_OID}`);
  }
  return matches[0].match_id;
}

async function setSimpleMode(enabled) {
  const res = await fetch(
    `${BASE}/api/v1/display/simple-mode?oid=${encodeURIComponent(DEMO_OID)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    },
  );
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`simple-mode toggle failed: ${res.status} ${txt}`);
  }
}

async function driveMatchState() {
  const post = (path, body) =>
    fetch(`${BASE}${path}?oid=${encodeURIComponent(DEMO_OID)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body == null ? undefined : JSON.stringify(body),
    });

  // Arm ``match_started_at`` so the HUD shows the Reset button + live
  // timer instead of the unarmed "Start match" call-to-action. The
  // implicit auto-arm only fires on ``add_point`` (not ``set_score``),
  // and we drive scores via set-score below — so the explicit start
  // endpoint is the one that matches the operator's "press Start, then
  // play" flow this fixture is meant to depict.
  await post('/api/v1/game/start-match', null);

  // Drive a realistic mid-match state: tied 1-1 going into set 3 with the
  // current set in progress. Always set the loser's value first so
  // set-score's auto-set-win check doesn't promote the wrong team
  // (current_score - rival_score > 1 trips at 25-0 otherwise).

  // Set 1 — Thunder Wolves 25, Solar Hawks 23. TW takes the set.
  await post('/api/v1/game/set-score', { team: 2, set_number: 1, value: 23 });
  await post('/api/v1/game/set-score', { team: 1, set_number: 1, value: 25 });

  // Set 2 — Thunder Wolves 22, Solar Hawks 25. SH levels 1-1.
  // Driven through real add_point events (instead of the fast
  // set-score back-fill) so the audit log captures a rally-by-rally
  // sequence — required for the set-summary recap screenshot to
  // render a populated chart, per-set longest-streak / services-won
  // values, and a non-zero set duration. The interleaved pattern
  // mimics a real back-and-forth set with a couple of mini-streaks
  // before SH closes it out.
  const SET2_SEQUENCE = [
    // T1 = Thunder Wolves, T2 = Solar Hawks. Final tally: T1=22, T2=25.
    2, 1, 2, 2, 1, 1, 2, 1, 2, 2,
    1, 1, 1, 2, 1, 2, 2, 1, 1, 2,
    1, 2, 1, 1, 2, 2, 1, 2, 1, 2,
    1, 2, 1, 2, 1, 2, 2, 1, 1, 2,
    1, 2, 1, 2, 2, 2, 2,
  ];
  for (const team of SET2_SEQUENCE) {
    await post('/api/v1/game/add-point', { team });
  }

  // Set 3 (current) — 18-24 with SH on set point. The control UI's
  // MatchAlertIndicator surfaces a "set point" badge in the centre
  // HUD whenever a team is one point from closing the set, so this
  // makes the alert visible in the regenerated scoreboard shot.
  await post('/api/v1/game/set-score', { team: 1, set_number: 3, value: 18 });
  await post('/api/v1/game/set-score', { team: 2, set_number: 3, value: 24 });
  await post('/api/v1/game/change-serve', { team: 2 });
}

async function dismissPwaPrompt(page) {
  // Hide the vite-pwa "new content available" toast if it sneaks in mid-shot.
  await page.addStyleTag({
    content: `
      [data-pwa-prompt], #pwa-toast, .pwa-toast { display: none !important; }
    `,
  });
}

async function captureInitScreen(page) {
  // Visit / with no oid -> InitScreen
  // Use a fresh storage state so localStorage doesn't auto-fill an OID.
  await page.context().clearCookies();
  await page.evaluate(() => {
    try { localStorage.clear(); } catch (_) {}
  });
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await dismissPwaPrompt(page);
  // Wait for the overlay-id form field to appear.
  await page.waitForSelector('input', { timeout: 10000 });
  await page.screenshot({ path: resolve(OUT_DIR, '01-init-screen.png'), fullPage: false });
}

async function captureScoreboard(page) {
  await page.goto(`${BASE}/?oid=${encodeURIComponent(DEMO_OID)}`, {
    waitUntil: 'networkidle',
  });
  await dismissPwaPrompt(page);
  // Wait until the score buttons are rendered (they show e.g. "12" / "8").
  await page.waitForFunction(
    (oid) => document.body && document.body.textContent && document.body.textContent.includes(oid),
    DEMO_OID,
    { timeout: 5000 },
  ).catch(() => {});
  // Wait for the match-alert pill to render so the set-point indicator
  // is in-frame. The pill is a `data-testid="match-alert-indicator"`
  // span inside `.match-alerts-row` — present whenever any team holds
  // set or match point. We tolerate timeout (matches without an alert
  // — e.g. the connect-screen-only mode — should still capture).
  await page.waitForSelector('[data-testid="match-alert-indicator"]', {
    timeout: 3000,
  }).catch(() => {});
  await page.waitForTimeout(400);
  await page.screenshot({ path: resolve(OUT_DIR, '02-scoreboard.png'), fullPage: false });
}

async function captureScoreboardPhone(page) {
  await page.setViewportSize(PHONE_VIEWPORT);
  // First nav establishes the SPA's localStorage origin so the
  // ``volley_showPreview`` flag can be written, then a reload picks
  // it up. With the preview hidden the centre column renders the
  // points-history strip in the slot the iframe would have occupied
  // — same toggle the operator flips via the tv/tv_off button. The
  // strip is the more useful at-a-glance surface on a phone (no
  // micro-iframe to squint at), so the portrait shot leads with it.
  await page.goto(`${BASE}/?oid=${encodeURIComponent(DEMO_OID)}`, {
    waitUntil: 'domcontentloaded',
  });
  await page.evaluate(() => {
    try {
      localStorage.setItem('volley_showPreview', JSON.stringify(false));
    } catch (_) { /* ignore */ }
  });
  await page.reload({ waitUntil: 'networkidle' });
  await dismissPwaPrompt(page);
  // The strip is populated from the audit log via a fetch, so wait
  // until at least one chip has rendered before snapping. Fail open
  // — the screenshot still proceeds if the selector times out.
  await page.waitForSelector('[data-testid="points-history-strip"] .phs-chip', {
    timeout: 5000,
  }).catch(() => {});
  await page.waitForTimeout(800);
  await page.screenshot({ path: resolve(OUT_DIR, '03-scoreboard-phone.png'), fullPage: false });
  // Restore the default so subsequent captures (config panel etc.)
  // don't inherit the preview-hidden state.
  await page.evaluate(() => {
    try {
      localStorage.removeItem('volley_showPreview');
    } catch (_) { /* ignore */ }
  });
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
}

async function capturePointTypePicker(page) {
  // Opt-in per-point classification turns a score tap into a quick
  // picker (ace / kill / block / opponent error / quick point) instead
  // of scoring immediately. Seed the operator setting, reload so the
  // SPA picks it up, then tap a team's score button to open the
  // dialog. The tap only opens the picker — it does not mutate match
  // state — so the scoreboard behind the modal keeps the fixture's
  // mid-match score.
  await page.goto(`${BASE}/?oid=${encodeURIComponent(DEMO_OID)}`, {
    waitUntil: 'domcontentloaded',
  });
  await page.evaluate(() => {
    try {
      localStorage.setItem('volley_trackPointTypes', JSON.stringify(true));
    } catch (_) { /* ignore */ }
  });
  await page.reload({ waitUntil: 'networkidle' });
  await dismissPwaPrompt(page);
  await page.waitForSelector('[data-testid="team-1-score"]', { timeout: 5000 });
  // A single tap fires onClick after the double-tap disambiguation
  // delay; the picker's type buttons carry point-picker-* testids, so
  // waiting on one absorbs that delay without a fixed sleep.
  await page.click('[data-testid="team-1-score"]');
  await page.waitForSelector('[data-testid="point-picker-ace"]', { timeout: 5000 });
  await page.waitForTimeout(300);
  await page.screenshot({
    path: resolve(OUT_DIR, '11-point-type-picker.png'),
    fullPage: false,
  });
  // Dismiss the dialog and clear the opt-in so later captures (config
  // panel, mosaic, …) run against the default fast-score flow.
  await page.keyboard.press('Escape').catch(() => {});
  await page.evaluate(() => {
    try {
      localStorage.removeItem('volley_trackPointTypes');
    } catch (_) { /* ignore */ }
  });
}

async function captureConfigPanel(page) {
  await page.goto(`${BASE}/?oid=${encodeURIComponent(DEMO_OID)}`, {
    waitUntil: 'networkidle',
  });
  await dismissPwaPrompt(page);
  await page.waitForTimeout(500);

  // Click the gear / config button. Selector tries a few common patterns.
  const candidates = [
    'button[aria-label*="config" i]',
    'button[title*="config" i]',
    'button[aria-label*="Configuration" i]',
    'button[aria-label*="Configuración" i]',
    'button[aria-label*="settings" i]',
  ];
  let opened = false;
  for (const sel of candidates) {
    const el = await page.$(sel);
    if (el) {
      await el.click();
      opened = true;
      break;
    }
  }
  if (!opened) {
    // Fall back to the URL hash mode the SPA uses internally.
    await page.evaluate(() => {
      window.history.pushState({}, '', '#/config');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
  }
  await page.waitForTimeout(800);
  await page.screenshot({ path: resolve(OUT_DIR, '04-config-panel.png'), fullPage: false });
}

async function captureManagePage(page) {
  // /manage is the only browser-first surface — operators don't admin
  // overlays from a phone — so it gets a scaled-down desktop viewport
  // instead of the mobile-landscape default used for the SPA shots.
  await page.setViewportSize(MANAGE_VIEWPORT);
  await page.goto(`${BASE}/manage`, { waitUntil: 'networkidle' });
  // Fill the password and submit.
  await page.fill('input[type="password"]', ADMIN_PW);
  await page.click('button[type="submit"]');
  // Wait for the overlay table to render.
  await page.waitForSelector('table', { timeout: 5000 });
  await page.waitForTimeout(300);
  await page.screenshot({ path: resolve(OUT_DIR, '05-manage-page.png'), fullPage: false });
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
}

async function captureMatchReport(page, matchId) {
  // /match/{id}/report needs the admin token — MATCH_REPORT_PUBLIC is
  // not set in the screenshot environment, so we pass it via the
  // ?token= query that the route accepts as an alias for the Bearer
  // header.
  await page.setViewportSize(REPORT_VIEWPORT);
  const url = `${BASE}/match/${encodeURIComponent(matchId)}/report?token=${encodeURIComponent(ADMIN_PW)}`;
  await page.goto(url, { waitUntil: 'networkidle' });
  // The report renders an inline SVG chart per set; wait until at
  // least one of them is mounted so the screenshot doesn't catch the
  // pre-chart layout shift.
  await page.waitForSelector('svg', { timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(400);
  await page.screenshot({
    path: resolve(OUT_DIR, '08-match-report.png'),
    fullPage: false,
  });
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
}

async function captureSpectator(page) {
  // /follow/{id} resolves either the raw OID or its output_key; we
  // pass DEMO_OID directly to keep this aligned with the other
  // captures. The page is a vanilla-JS scoreboard fed by /ws/{id}, so
  // we wait for the WS connection to flip #conn-status away from
  // "connecting…" and for the team-name slot to be populated before
  // snapping. fullPage:true so the chart, history and per-team stats
  // rows are all in-frame without compressing the scoreboard.
  await page.setViewportSize(SPECTATOR_VIEWPORT);
  await page.goto(`${BASE}/follow/${encodeURIComponent(DEMO_OID)}`, {
    waitUntil: 'networkidle',
  });
  await dismissPwaPrompt(page);
  await page.waitForFunction(
    () => {
      const name = document.getElementById('team1-name');
      const status = document.getElementById('conn-status');
      return (
        name &&
        name.textContent &&
        name.textContent !== 'Team 1' &&
        status &&
        !/connecting/i.test(status.textContent || '')
      );
    },
    null,
    { timeout: 8000 },
  ).catch(() => {});
  // Give the set-progression SVG one more tick to lay out its line
  // path so the chart panel isn't captured mid-render.
  await page.waitForTimeout(800);
  await page.screenshot({
    path: resolve(OUT_DIR, '09-spectator-page.png'),
    fullPage: true,
  });
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
}

async function captureSetSummary(page, filename) {
  // Trigger the set-summary panel for the demo overlay with a finished
  // set selected (set 2 — Solar Hawks 25-22) so the recap renders real
  // chart points + final score chips instead of an empty live set.
  const post = (path, body) =>
    fetch(`${BASE}${path}?oid=${encodeURIComponent(DEMO_OID)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body == null ? undefined : JSON.stringify(body),
    });
  await post('/api/v1/display/set-summary-style', { style: 'brand_columns' });
  await post('/api/v1/display/set-summary', { enabled: true });

  await page.setViewportSize(OVERLAY_HD_VIEWPORT);
  // ?lang=en pins the overlay's strings to English so the README
  // screenshot matches the rest of the captured surfaces (which are
  // forced to en-US via the Playwright context locale).
  await page.goto(`${BASE}/overlay/${encodeURIComponent(DEMO_OID)}?lang=en`, {
    waitUntil: 'networkidle',
  });
  // Wait for the panel to mount + opacity fade-in to finish.
  await page.waitForFunction(() => {
    const panel = document.getElementById('set-summary-panel');
    if (!panel) return false;
    return parseFloat(getComputedStyle(panel).opacity) >= 0.99;
  }, null, { timeout: 5000 }).catch(() => {});
  // One extra frame so the chart polylines + ticker clocks have
  // settled on their first paint.
  await page.waitForTimeout(800);

  await page.screenshot({ path: resolve(OUT_DIR, filename) });

  // Turn the panel back off so subsequent captures (mosaic, etc.)
  // see the scoreboard, not the recap overlay.
  await post('/api/v1/display/set-summary', { enabled: false });
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
}

async function captureOverlayMosaic(page, filename, extraQuery = '') {
  // Mosaic is a full-page grid of every selectable style; needs a wider
  // viewport and enough vertical room to fit every cell, plus extra
  // wait time so each iframe finishes its postMessage handshake and
  // shrinks to its overlay-only bounds.
  const MOSAIC_VIEWPORT = { width: 1600, height: 1800 };
  await page.setViewportSize(MOSAIC_VIEWPORT);
  const extra = extraQuery ? `&${extraQuery}` : '';
  await page.goto(`${BASE}/overlay/${encodeURIComponent(DEMO_OID)}?style=mosaic${extra}`, {
    waitUntil: 'networkidle',
  });
  // Each iframe asynchronously reports its render bounds; give the grid
  // time to lay them out before snapping.
  await page.waitForFunction(() => {
    const iframes = document.querySelectorAll('.mosaic-iframe-wrapper iframe');
    if (iframes.length === 0) return false;
    return Array.from(iframes).every((f) => {
      const h = f.parentElement && f.parentElement.clientHeight;
      return h && h > 20;
    });
  }, null, { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(2500);
  // Clip to the full grid (no viewport-height clamp, so we don't cut
  // the last rows off when the grid is taller than the viewport).
  const clip = await page.evaluate(() => {
    const grid = document.getElementById('mosaic-grid');
    if (!grid) return null;
    const r = grid.getBoundingClientRect();
    return {
      x: Math.max(0, Math.floor(r.left)),
      y: Math.max(0, Math.floor(r.top)),
      width: Math.ceil(r.width),
      height: Math.ceil(r.height),
    };
  });
  await page.screenshot({
    path: resolve(OUT_DIR, filename),
    // fullPage: true so the clip can extend below the visible viewport.
    fullPage: true,
    ...(clip ? { clip } : {}),
  });
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  console.log(`Capturing screenshots into ${OUT_DIR}`);

  await ensureDemoOverlay();
  await ensureFinishedMatchForReport();
  const reportMatchId = await fetchLatestMatchId();

  // Allow pointing at a pre-provisioned Chromium (e.g. CI / sandboxes
  // where the managed-browser download host is blocked). Unset → use
  // Playwright's bundled browser exactly as before.
  const launchOpts = { headless: true };
  if (process.env.SCREENSHOT_CHROMIUM_PATH) {
    launchOpts.executablePath = process.env.SCREENSHOT_CHROMIUM_PATH;
  }
  const browser = await chromium.launch(launchOpts);
  const context = await browser.newContext({
    viewport: MOBILE_LANDSCAPE_VIEWPORT,
    // Render at 1× to keep PNGs lightweight for the README. The captured
    // surfaces are documentation-resolution, not retina assets — going
    // higher quadruples file size for no practical benefit.
    deviceScaleFactor: 1,
    colorScheme: 'dark',
    // Force English so the React i18n provider doesn't latch onto the
    // host's locale (which is what made the README screenshots come out
    // half in Spanish on a Spanish workstation). The /manage page is a
    // static HTML doc that is always English; aligning the SPA pins
    // every captured surface to one language.
    locale: 'en-US',
  });
  await installLogoRouter(context);
  // Pre-dismiss the first-use gesture coachmark for every SPA page in
  // this context. The coachmark fires when authoritative state lands
  // and ``volley_gestureTourSeen`` is unset (see ``useSettings``); it
  // covers the scoreboard with a modal that blocks the gear button
  // and other in-frame UI from rendering in the screenshots. Seeding
  // the flag before any page script runs is invisible to the
  // captures themselves (no banner, no flicker) and matches the
  // operator's steady-state after they dismiss the tour once.
  await context.addInitScript(() => {
    try {
      localStorage.setItem('volley_gestureTourSeen', JSON.stringify(true));
    } catch (_) { /* ignore */ }
  });
  const page = await context.newPage();

  try {
    await captureInitScreen(page);
    await captureScoreboard(page);
    await captureScoreboardPhone(page);
    await capturePointTypePicker(page);
    await captureConfigPanel(page);
    await captureManagePage(page);
    // Mosaic captured twice — once with the full match data, once with
    // simple mode toggled on so the "show only current set" treatment
    // is visible across every style.
    await setSimpleMode(false);
    // The two mosaics double as the overlayTheme demo: full data is
    // captured with the forced light theme, simple mode with the
    // forced dark one, so every theme-aware style shows both
    // variants across the pair (styles without the matching palette
    // keep their native look).
    await captureOverlayMosaic(page, '06-overlay-mosaic-full.png', 'theme=light');
    await setSimpleMode(true);
    await captureOverlayMosaic(page, '07-overlay-mosaic-simple.png', 'theme=dark');
    await setSimpleMode(false);
    await captureSetSummary(page, '10-overlay-set-summary.png');
    await captureMatchReport(page, reportMatchId);
    await captureSpectator(page);
  } finally {
    await context.close();
    await browser.close();
  }

  console.log('Done.');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
