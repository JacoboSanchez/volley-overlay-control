// Headless screenshot capture for the project README (multi-user app).
//
// Assumes a dev/staging instance of volley-overlay-control is running at
// SCREENSHOT_BASE_URL (default http://localhost:8181) with:
//   - a FRESH database (no admin yet) and ADMIN_BOOTSTRAP_TOKEN set, so this
//     script can claim the first admin and obtain a session cookie
//   - SESSION_COOKIE_SECURE=false (the harness runs over http)
//   - MATCH_REPORT_PUBLIC=true (so the report shot needs no credential)
//   - the built frontend mounted at /
//
// The companion run.sh boots an isolated backend with these settings.
//
// Auth model: the app is cookie-session + role based (no Bearer admin
// password anymore). We claim/login once for a `vsession` cookie, send it on
// every REST seeding call, AND inject it into the Playwright browser context
// so the authenticated SPA pages render. OBS output pages are addressed by the
// per-overlay `public_token`, not the raw oid.

import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { mkdir } from 'node:fs/promises';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const REPO_ROOT = resolve(__dirname, '..', '..');
const OUT_DIR = resolve(REPO_ROOT, 'docs', 'screenshots');

const BASE = process.env.SCREENSHOT_BASE_URL || 'http://localhost:8181';
const ADMIN_USER = process.env.SCREENSHOT_ADMIN_USER || 'demo';
// Must satisfy the app's MIN_PASSWORD_LENGTH (8).
const ADMIN_PW = process.env.SCREENSHOT_ADMIN_PASSWORD || 'demo-password';
const BOOTSTRAP_TOKEN = process.env.ADMIN_BOOTSTRAP_TOKEN || '';
const DEMO_OID = process.env.SCREENSHOT_DEMO_OID || 'centercourt';
const REPORT_OID = 'practice-hall';

// The session cookie ("vsession=<token>") captured at bootstrap and replayed
// on every REST call + injected into the browser context.
let SESSION_COOKIE = null;
// public_token per overlay, filled by createOverlay() and used for OBS URLs.
const PUBLIC_TOKEN = {};

// Invented match data — deliberately not the operator's real teams.
//
// The overlay engine's <img> sanitizer (overlay_static/js/app.js,
// `sanitizeImageUrl`) intentionally rejects everything except http(s)
// to defend against javascript:/data:/vbscript: XSS, so the logos must
// be served as http URLs. We anchor them at the backend's own origin
// so the control UI's strict CSP (`img-src 'self' data: https:`) treats
// them as same-origin; Playwright's route handler intercepts the
// request and returns the inline SVG, so no actual network call is made.
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

// ---------------------------------------------------------------------------
// Cookie-aware REST helpers
// ---------------------------------------------------------------------------

function cookieHeaders(extra = {}) {
  return {
    'Content-Type': 'application/json',
    ...(SESSION_COOKIE ? { Cookie: SESSION_COOKIE } : {}),
    ...extra,
  };
}

async function apiFetch(path, { method = 'GET', body } = {}) {
  return fetch(`${BASE}${path}`, {
    method,
    headers: cookieHeaders(),
    body: body == null ? undefined : JSON.stringify(body),
  });
}

function oidPost(path, oid, body) {
  return apiFetch(`${path}?oid=${encodeURIComponent(oid)}`, { method: 'POST', body });
}

function extractSessionCookie(res) {
  const jar = typeof res.headers.getSetCookie === 'function'
    ? res.headers.getSetCookie()
    : [res.headers.get('set-cookie')].filter(Boolean);
  const vs = jar
    .map((c) => (c || '').split(';')[0])
    .find((c) => c.startsWith('vsession='));
  return vs || null;
}

async function bootstrapAdmin() {
  // Fresh DB: claim the first admin with the known bootstrap token. If the DB
  // already has an admin (re-run against a warm instance), fall back to login.
  let res = await fetch(`${BASE}/api/v1/auth/claim-admin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: BOOTSTRAP_TOKEN, username: ADMIN_USER, password: ADMIN_PW }),
  });
  if (res.status === 410) {
    // Already claimed (warm re-run) → log in instead.
    res = await fetch(`${BASE}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: ADMIN_USER, password: ADMIN_PW }),
    });
    if (!res.ok) {
      throw new Error(`admin login failed: ${res.status} ${await res.text()}`);
    }
  } else if (!res.ok) {
    throw new Error(`admin claim failed: ${res.status} ${await res.text()}`);
  }
  SESSION_COOKIE = extractSessionCookie(res);
  if (!SESSION_COOKIE) {
    throw new Error('no vsession cookie returned from claim-admin/login');
  }
}

async function seedDemoUsers() {
  // Extra accounts so the admin "global configuration" page shows a
  // representative roster rather than the lone bootstrap admin. Explicit
  // passwords keep the table clean (no "must change password" pills).
  const roster = [
    { username: 'coach-martinez', role: 'user' },
    { username: 'scorekeeper', role: 'user' },
    { username: 'club-admin', role: 'admin' },
  ];
  for (const u of roster) {
    const res = await apiFetch('/api/v1/admin/users', {
      method: 'POST',
      body: { username: u.username, password: ADMIN_PW, role: u.role },
    });
    // 400 → username already exists on a warm re-run; keep the run idempotent.
    if (!res.ok && res.status !== 400) {
      throw new Error(`seed user ${u.username} failed: ${res.status} ${await res.text()}`);
    }
  }
}

async function createOverlay(oid) {
  const res = await apiFetch('/api/v1/overlays', { method: 'POST', body: { oid } });
  if (res.status === 201) {
    PUBLIC_TOKEN[oid] = (await res.json()).public_token;
    return;
  }
  // Already exists (warm re-run) → read its public_token from the list.
  const list = await (await apiFetch('/api/v1/overlays')).json();
  const found = Array.isArray(list) ? list.find((o) => o.oid === oid) : null;
  if (found) {
    PUBLIC_TOKEN[oid] = found.public_token;
    return;
  }
  throw new Error(`could not create/find overlay ${oid}: ${res.status} ${await res.text()}`);
}

async function initSession(oid) {
  const res = await apiFetch('/api/v1/session/init', { method: 'POST', body: { oid } });
  if (!res.ok) {
    throw new Error(`session/init for ${oid} failed: ${res.status} ${await res.text()}`);
  }
}

async function putCustomization(oid, customization) {
  const res = await apiFetch(
    `/api/v1/customization?oid=${encodeURIComponent(oid)}`,
    { method: 'PUT', body: customization },
  );
  if (!res.ok) {
    throw new Error(`customization for ${oid} failed: ${res.status} ${await res.text()}`);
  }
}

// ---------------------------------------------------------------------------
// Playwright helpers + viewports
// ---------------------------------------------------------------------------

async function installLogoRouter(context) {
  // Intercept every request to the synthetic logo host and return the
  // matching SVG inline. Both the React control UI and the overlay browser
  // pages live in this context, so a single handler covers both.
  await context.route(`${LOGO_HOST}/**`, (route) => {
    const url = route.request().url();
    if (url.endsWith('team-thunder-wolves.svg')) {
      return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: TEAM_1.logoSvg });
    }
    if (url.endsWith('team-solar-hawks.svg')) {
      return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: TEAM_2.logoSvg });
    }
    return route.fulfill({ status: 404, body: '' });
  });
}

// Mobile-landscape is the primary capture viewport because the scoring
// operator's main use case is a phone held sideways during a match.
const MOBILE_LANDSCAPE_VIEWPORT = { width: 844, height: 390 };
const PHONE_VIEWPORT = { width: 390, height: 844 };
// The account pages (login, overlays, admin) are browser-first — operators
// manage accounts/overlays from a desktop — so they use a scaled desktop view.
const ACCOUNT_VIEWPORT = { width: 1024, height: 700 };
const REPORT_VIEWPORT = { width: 1024, height: 1100 };
const SPECTATOR_VIEWPORT = { width: 414, height: 896 };
const OVERLAY_HD_VIEWPORT = { width: 1280, height: 720 };

// ---------------------------------------------------------------------------
// Seeding (drive realistic match state via the cookie-authenticated API)
// ---------------------------------------------------------------------------

const CUSTOMIZATION = {
  'Team 1 Text Name': TEAM_1.name,
  'Team 2 Text Name': TEAM_2.name,
  // ``Team N Name`` is what app.match_report looks up; ``Team N Text Name``
  // drives the React scoreboard. Both point to the same label here.
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

async function seedDemoOverlay() {
  await createOverlay(DEMO_OID);
  await initSession(DEMO_OID);
  await putCustomization(DEMO_OID, { ...CUSTOMIZATION, preferredStyle: 'glass' });
  await driveMatchState();
}

async function driveMatchState() {
  // Arm match_started_at so the HUD shows the Reset button + live timer.
  await oidPost('/api/v1/game/start-match', DEMO_OID, null);

  // Set 1 — Thunder Wolves 25, Solar Hawks 23. Always set the loser first so
  // set-score's auto-set-win check doesn't promote the wrong team.
  await oidPost('/api/v1/game/set-score', DEMO_OID, { team: 2, set_number: 1, value: 23 });
  await oidPost('/api/v1/game/set-score', DEMO_OID, { team: 1, set_number: 1, value: 25 });

  // Set 2 — driven via real add_point events so the audit log captures a
  // rally-by-rally sequence (required for the set-summary recap chart).
  const SET2_SEQUENCE = [
    2, 1, 2, 2, 1, 1, 2, 1, 2, 2,
    1, 1, 1, 2, 1, 2, 2, 1, 1, 2,
    1, 2, 1, 1, 2, 2, 1, 2, 1, 2,
    1, 2, 1, 2, 1, 2, 2, 1, 1, 2,
    1, 2, 1, 2, 2, 2, 2,
  ];
  for (const team of SET2_SEQUENCE) {
    await oidPost('/api/v1/game/add-point', DEMO_OID, { team });
  }

  // Set 3 (current) — 18-24 with SH on set point, so the MatchAlertIndicator
  // shows a "set point" badge in the regenerated scoreboard shot.
  await oidPost('/api/v1/game/set-score', DEMO_OID, { team: 1, set_number: 3, value: 18 });
  await oidPost('/api/v1/game/set-score', DEMO_OID, { team: 2, set_number: 3, value: 24 });
  await oidPost('/api/v1/game/change-serve', DEMO_OID, { team: 2 });
}

async function seedFinishedMatchForReport() {
  await createOverlay(REPORT_OID);
  await initSession(REPORT_OID);
  await putCustomization(REPORT_OID, CUSTOMIZATION);

  const post = (path, body) => oidPost(path, REPORT_OID, body);
  await post('/api/v1/game/start-match', null);

  async function closeSet(setNum, winner, winnerEnd, loserEnd, timeouts = {}) {
    const loser = winner === 1 ? 2 : 1;
    await post('/api/v1/game/set-score', { team: winner, set_number: setNum, value: loserEnd });
    await post('/api/v1/game/set-score', { team: loser, set_number: setNum, value: loserEnd });
    for (let i = 0; i < (timeouts[1] || 0); i++) await post('/api/v1/game/add-timeout', { team: 1 });
    for (let i = 0; i < (timeouts[2] || 0); i++) await post('/api/v1/game/add-timeout', { team: 2 });
    for (let i = 0; i < winnerEnd - loserEnd; i++) await post('/api/v1/game/add-point', { team: winner });
  }

  const setBreak = () => new Promise((r) => setTimeout(r, 700));

  await closeSet(1, 1, 25, 23, { 1: 1, 2: 1 });
  await setBreak();
  await closeSet(2, 2, 25, 21, { 2: 2 });
  await setBreak();
  await closeSet(3, 1, 25, 19);
  await setBreak();

  // Set 4 — TW comes back from 0-5 to win 25-22 (the "biggest comeback" story).
  await post('/api/v1/game/set-score', { team: 2, set_number: 4, value: 5 });
  for (let i = 0; i < 5; i++) await post('/api/v1/game/add-point', { team: 1 });
  await post('/api/v1/game/add-timeout', { team: 1 });
  await post('/api/v1/game/add-timeout', { team: 2 });
  await post('/api/v1/game/set-score', { team: 1, set_number: 4, value: 22 });
  await post('/api/v1/game/set-score', { team: 2, set_number: 4, value: 22 });
  for (let i = 0; i < 3; i++) await post('/api/v1/game/add-point', { team: 1 });
}

async function fetchLatestMatchId() {
  const res = await apiFetch(`/api/v1/matches?oid=${encodeURIComponent(REPORT_OID)}`);
  if (!res.ok) throw new Error(`could not list matches for ${REPORT_OID}: ${res.status}`);
  const body = await res.json();
  const matches = Array.isArray(body) ? body : body.matches;
  if (!Array.isArray(matches) || matches.length === 0) {
    throw new Error(`no archived matches for ${REPORT_OID}`);
  }
  return matches[0].match_id;
}

async function setSimpleMode(enabled) {
  const res = await oidPost('/api/v1/display/simple-mode', DEMO_OID, { enabled });
  if (!res.ok) throw new Error(`simple-mode toggle failed: ${res.status} ${await res.text()}`);
}

// ---------------------------------------------------------------------------
// Page captures
// ---------------------------------------------------------------------------

async function dismissPwaPrompt(page) {
  await page.addStyleTag({
    content: `[data-pwa-prompt], #pwa-toast, .pwa-toast { display: none !important; }`,
  });
}

async function captureLogin(page) {
  // Unauthenticated front door. Clear any cookie/localStorage so PublicOnly
  // renders the sign-in form rather than redirecting an authed session away.
  await page.context().clearCookies();
  await page.evaluate(() => { try { localStorage.clear(); } catch (_) { /* ignore */ } });
  await page.setViewportSize(ACCOUNT_VIEWPORT);
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await dismissPwaPrompt(page);
  await page.waitForSelector('input', { timeout: 10000 });
  await page.waitForTimeout(300);
  await page.screenshot({ path: resolve(OUT_DIR, '01-init-screen.png'), fullPage: false });
}

async function gotoBoard(page, oid, waitUntil = 'networkidle') {
  await page.goto(`${BASE}/board?oid=${encodeURIComponent(oid)}`, { waitUntil });
}

async function captureScoreboard(page) {
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
  await gotoBoard(page, DEMO_OID);
  await dismissPwaPrompt(page);
  await page.waitForSelector('[data-testid="team-1-score"]', { timeout: 8000 }).catch(() => {});
  // The set-point alert pill renders whenever a team holds set/match point.
  await page.waitForSelector('[data-testid="match-alert-indicator"]', { timeout: 3000 }).catch(() => {});
  await page.waitForTimeout(400);
  await page.screenshot({ path: resolve(OUT_DIR, '02-scoreboard.png'), fullPage: false });
}

async function captureScoreboardPhone(page) {
  await page.setViewportSize(PHONE_VIEWPORT);
  await gotoBoard(page, DEMO_OID, 'domcontentloaded');
  await page.evaluate(() => {
    try { localStorage.setItem('volley_showPreview', JSON.stringify(false)); } catch (_) { /* ignore */ }
  });
  await page.reload({ waitUntil: 'networkidle' });
  await dismissPwaPrompt(page);
  await page.waitForSelector('[data-testid="points-history-strip"] .phs-chip', { timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(800);
  await page.screenshot({ path: resolve(OUT_DIR, '03-scoreboard-phone.png'), fullPage: false });
  await page.evaluate(() => {
    try { localStorage.removeItem('volley_showPreview'); } catch (_) { /* ignore */ }
  });
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
}

async function capturePointTypePicker(page) {
  await gotoBoard(page, DEMO_OID, 'domcontentloaded');
  await page.evaluate(() => {
    try { localStorage.setItem('volley_trackPointTypes', JSON.stringify(true)); } catch (_) { /* ignore */ }
  });
  await page.reload({ waitUntil: 'networkidle' });
  await dismissPwaPrompt(page);
  await page.waitForSelector('[data-testid="team-1-score"]', { timeout: 5000 });
  await page.click('[data-testid="team-1-score"]');
  await page.waitForSelector('[data-testid="point-picker-ace"]', { timeout: 5000 });
  await page.waitForTimeout(300);
  await page.screenshot({ path: resolve(OUT_DIR, '11-point-type-picker.png'), fullPage: false });
  await page.keyboard.press('Escape').catch(() => {});
  await page.evaluate(() => {
    try { localStorage.removeItem('volley_trackPointTypes'); } catch (_) { /* ignore */ }
  });
}

async function captureConfigPanel(page) {
  await gotoBoard(page, DEMO_OID);
  await dismissPwaPrompt(page);
  await page.waitForTimeout(500);
  const candidates = [
    'button[aria-label*="config" i]',
    'button[title*="config" i]',
    'button[aria-label*="Configuration" i]',
    'button[aria-label*="Configuración" i]',
    'button[aria-label*="settings" i]',
  ];
  for (const sel of candidates) {
    const el = await page.$(sel);
    if (el) { await el.click(); break; }
  }
  await page.waitForTimeout(800);
  await page.screenshot({ path: resolve(OUT_DIR, '04-config-panel.png'), fullPage: false });
}

async function captureOverlaysPage(page) {
  // The account "Overlays" page lists the signed-in user's overlays with their
  // copyable OBS output URLs — the multi-user replacement for the old /manage.
  await page.setViewportSize(ACCOUNT_VIEWPORT);
  await page.goto(`${BASE}/overlays`, { waitUntil: 'networkidle' });
  await dismissPwaPrompt(page);
  // Wait until at least one overlay row has rendered.
  await page.waitForFunction(
    (oid) => document.body && (document.body.textContent || '').includes(oid),
    DEMO_OID,
    { timeout: 8000 },
  ).catch(() => {});
  // Cards are collapsed by default; expand the first one so the screenshot
  // shows the full anatomy (output URL + control links) rather than just the
  // collapsed header list.
  await page.click('.acc-overlay-toggle').catch(() => {});
  await page.waitForTimeout(400);
  await page.screenshot({ path: resolve(OUT_DIR, '05-manage-page.png'), fullPage: false });
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
}

async function captureAdminPage(page) {
  // The "Administration" page is the app's global-configuration surface:
  // the self-registration toggle plus user management (create, reset
  // password, activate/deactivate, delete). Admin-only — the demo session is
  // the bootstrap admin, so it renders. seedDemoUsers() populated the roster.
  await page.setViewportSize(ACCOUNT_VIEWPORT);
  await page.goto(`${BASE}/admin`, { waitUntil: 'networkidle' });
  await dismissPwaPrompt(page);
  // Wait until the users table has rendered its rows (the async load resolved).
  await page.waitForSelector('.acc-table tbody tr', { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(400);
  await page.screenshot({ path: resolve(OUT_DIR, '12-admin-page.png'), fullPage: false });
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
}

async function captureMatchReport(page, matchId) {
  // MATCH_REPORT_PUBLIC=true is set by run.sh, and the browser also carries the
  // owner's session cookie — so the report renders without any ?token=.
  await page.setViewportSize(REPORT_VIEWPORT);
  await page.goto(`${BASE}/match/${encodeURIComponent(matchId)}/report`, { waitUntil: 'networkidle' });
  await page.waitForSelector('svg', { timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(400);
  await page.screenshot({ path: resolve(OUT_DIR, '08-match-report.png'), fullPage: false });
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
}

async function captureSpectator(page) {
  // /follow/{public_token} is the public, mobile-first spectator page — a
  // vanilla-JS scoreboard fed by /ws/{public_token}, no auth.
  await page.setViewportSize(SPECTATOR_VIEWPORT);
  await page.goto(`${BASE}/follow/${encodeURIComponent(PUBLIC_TOKEN[DEMO_OID])}`, { waitUntil: 'networkidle' });
  await dismissPwaPrompt(page);
  await page.waitForFunction(() => {
    const name = document.getElementById('team1-name');
    const status = document.getElementById('conn-status');
    return name && name.textContent && name.textContent !== 'Team 1'
      && status && !/connecting/i.test(status.textContent || '');
  }, null, { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(800);
  await page.screenshot({ path: resolve(OUT_DIR, '09-spectator-page.png'), fullPage: true });
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
}

async function captureSetSummary(page, filename) {
  await oidPost('/api/v1/display/set-summary-style', DEMO_OID, { style: 'brand_columns' });
  await oidPost('/api/v1/display/set-summary', DEMO_OID, { enabled: true });

  await page.setViewportSize(OVERLAY_HD_VIEWPORT);
  await page.goto(`${BASE}/overlay/${encodeURIComponent(PUBLIC_TOKEN[DEMO_OID])}?lang=en`, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => {
    const panel = document.getElementById('set-summary-panel');
    return panel && parseFloat(getComputedStyle(panel).opacity) >= 0.99;
  }, null, { timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(800);
  await page.screenshot({ path: resolve(OUT_DIR, filename) });

  await oidPost('/api/v1/display/set-summary', DEMO_OID, { enabled: false });
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
}

async function captureOverlayMosaic(page, filename, extraQuery = '') {
  const MOSAIC_VIEWPORT = { width: 1600, height: 1800 };
  await page.setViewportSize(MOSAIC_VIEWPORT);
  const extra = extraQuery ? `&${extraQuery}` : '';
  await page.goto(
    `${BASE}/overlay/${encodeURIComponent(PUBLIC_TOKEN[DEMO_OID])}?style=mosaic${extra}`,
    { waitUntil: 'networkidle' },
  );
  await page.waitForFunction(() => {
    const iframes = document.querySelectorAll('.mosaic-iframe-wrapper iframe');
    if (iframes.length === 0) return false;
    return Array.from(iframes).every((f) => {
      const h = f.parentElement && f.parentElement.clientHeight;
      return h && h > 20;
    });
  }, null, { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(2500);
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
    fullPage: true,
    ...(clip ? { clip } : {}),
  });
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  console.log(`Capturing screenshots into ${OUT_DIR}`);

  // 1. Authenticate (claim the first admin → session cookie).
  await bootstrapAdmin();
  // 2. Seed a small user roster so the admin global-config page is realistic.
  await seedDemoUsers();
  // 3. Seed demo overlays + match state via the cookie-authenticated API.
  await seedDemoOverlay();
  await seedFinishedMatchForReport();
  const reportMatchId = await fetchLatestMatchId();

  const launchOpts = {
    headless: true,
    // ``--no-sandbox`` so a root/container run (common in CI and managed
    // images) doesn't abort; ``--disable-dev-shm-usage`` avoids crashes from a
    // small /dev/shm in containers.
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  };
  if (process.env.SCREENSHOT_CHROMIUM_PATH) {
    launchOpts.executablePath = process.env.SCREENSHOT_CHROMIUM_PATH;
  }
  const browser = await chromium.launch(launchOpts);
  const context = await browser.newContext({
    viewport: MOBILE_LANDSCAPE_VIEWPORT,
    deviceScaleFactor: 1,
    colorScheme: 'dark',
    locale: 'en-US',
  });
  await installLogoRouter(context);
  // Pre-dismiss the first-use gesture coachmark for every SPA page.
  await context.addInitScript(() => {
    try { localStorage.setItem('volley_gestureTourSeen', JSON.stringify(true)); } catch (_) { /* ignore */ }
  });
  const page = await context.newPage();

  // Each shot is wrapped so one failure (a slow selector, a flaky WS handshake)
  // is logged and the rest still capture. A non-empty `failures` list exits
  // non-zero at the end so CI/operators notice.
  const failures = [];
  const step = async (name, fn) => {
    process.stdout.write(`  • ${name} ... `);
    try {
      await fn();
      console.log('ok');
    } catch (err) {
      const msg = err && err.message ? err.message : String(err);
      console.log(`FAILED: ${msg}`);
      failures.push(name);
    }
  };

  try {
    // Unauthenticated shot first (clears cookies).
    await step('01 login', () => captureLogin(page));
    // Authenticate the browser for every shot below.
    await context.addCookies([{
      name: 'vsession',
      value: SESSION_COOKIE.split('=').slice(1).join('='),
      url: BASE,
    }]);

    await step('02 scoreboard', () => captureScoreboard(page));
    await step('03 scoreboard-phone', () => captureScoreboardPhone(page));
    await step('11 point-type-picker', () => capturePointTypePicker(page));
    await step('04 config-panel', () => captureConfigPanel(page));
    await step('05 overlays-page', () => captureOverlaysPage(page));
    await step('12 admin-page', () => captureAdminPage(page));

    await setSimpleMode(false);
    await step('06 mosaic-full', () => captureOverlayMosaic(page, '06-overlay-mosaic-full.png', 'theme=light'));
    await setSimpleMode(true);
    await step('07 mosaic-simple', () => captureOverlayMosaic(page, '07-overlay-mosaic-simple.png', 'theme=dark'));
    await setSimpleMode(false);
    await step('10 set-summary', () => captureSetSummary(page, '10-overlay-set-summary.png'));
    await step('08 match-report', () => captureMatchReport(page, reportMatchId));
    await step('09 spectator', () => captureSpectator(page));
  } finally {
    await context.close();
    await browser.close();
  }

  if (failures.length) {
    console.error(`Done with ${failures.length} failed shot(s): ${failures.join(', ')}`);
    process.exitCode = 1;
  } else {
    console.log('Done — all shots captured.');
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
