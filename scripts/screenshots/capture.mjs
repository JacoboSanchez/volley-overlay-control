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
// be served as http URLs. We use a synthetic localhost-style host and
// intercept the request inside Playwright (see `installLogoRouter`)
// so no actual network call is made.
const LOGO_HOST = 'http://volley-screenshot-logos.local';
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

const SCOREBOARD_VIEWPORT = { width: 1280, height: 800 };
const OVERLAY_VIEWPORT = { width: 1280, height: 720 };
const PHONE_VIEWPORT = { width: 390, height: 844 };

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

  // Apply invented team customization.
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

async function driveMatchState() {
  const post = (path, body) =>
    fetch(`${BASE}${path}?oid=${encodeURIComponent(DEMO_OID)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body == null ? undefined : JSON.stringify(body),
    });

  // 12 - 8 in the current set, with team 1 serving.
  await post('/api/v1/game/set-score', { team: 1, set_number: 1, value: 12 });
  await post('/api/v1/game/set-score', { team: 2, set_number: 1, value: 8 });
  await post('/api/v1/game/change-serve', { team: 1 });
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
  // Generic wait: a button containing two-digit numbers should be present.
  await page.waitForTimeout(800);
  await page.screenshot({ path: resolve(OUT_DIR, '02-scoreboard.png'), fullPage: false });
}

async function captureScoreboardPhone(page) {
  await page.setViewportSize(PHONE_VIEWPORT);
  await page.goto(`${BASE}/?oid=${encodeURIComponent(DEMO_OID)}`, {
    waitUntil: 'networkidle',
  });
  await dismissPwaPrompt(page);
  await page.waitForTimeout(800);
  await page.screenshot({ path: resolve(OUT_DIR, '03-scoreboard-phone.png'), fullPage: false });
  await page.setViewportSize(SCOREBOARD_VIEWPORT);
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
  await page.goto(`${BASE}/manage`, { waitUntil: 'networkidle' });
  // Fill the password and submit.
  await page.fill('input[type="password"]', ADMIN_PW);
  await page.click('button[type="submit"]');
  // Wait for the overlay table to render.
  await page.waitForSelector('table', { timeout: 5000 });
  await page.waitForTimeout(300);
  await page.screenshot({ path: resolve(OUT_DIR, '05-manage-page.png'), fullPage: false });
}

async function captureOverlayOutput(page, style, filename) {
  await page.setViewportSize(OVERLAY_VIEWPORT);
  const url = style
    ? `${BASE}/overlay/${encodeURIComponent(DEMO_OID)}?style=${encodeURIComponent(style)}`
    : `${BASE}/overlay/${encodeURIComponent(DEMO_OID)}`;
  await page.goto(url, { waitUntil: 'networkidle' });
  // OBS browser sources are transparent — render against a subtle dark
  // backdrop so the overlay graphic is visible on the README page.
  await page.addStyleTag({
    content: `
      html, body { background: #1a1a2e !important; }
      body::before {
        content: "";
        position: fixed; inset: 0;
        background-image:
          linear-gradient(45deg, rgba(255,255,255,0.04) 25%, transparent 25%),
          linear-gradient(-45deg, rgba(255,255,255,0.04) 25%, transparent 25%),
          linear-gradient(45deg, transparent 75%, rgba(255,255,255,0.04) 75%),
          linear-gradient(-45deg, transparent 75%, rgba(255,255,255,0.04) 75%);
        background-size: 24px 24px;
        background-position: 0 0, 0 12px, 12px -12px, -12px 0;
        z-index: -1;
      }
    `,
  });
  await page.waitForTimeout(1500);
  // Clip to the actual scoreboard root with a little breathing room so the
  // resulting image is dominated by the overlay graphic rather than a sea
  // of background.
  const clip = await page.evaluate(() => {
    const root =
      document.getElementById('scoreboard-container') ||
      document.querySelector('.scoreboard');
    if (!root) return null;
    const r = root.getBoundingClientRect();
    const pad = 48;
    const x = Math.max(0, Math.floor(r.left - pad));
    const y = Math.max(0, Math.floor(r.top - pad));
    const width = Math.min(window.innerWidth - x, Math.ceil(r.width + pad * 2));
    const height = Math.min(window.innerHeight - y, Math.ceil(r.height + pad * 2));
    return { x, y, width, height };
  });
  await page.screenshot({
    path: resolve(OUT_DIR, filename),
    fullPage: false,
    ...(clip ? { clip } : {}),
  });
  await page.setViewportSize(SCOREBOARD_VIEWPORT);
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  console.log(`Capturing screenshots into ${OUT_DIR}`);

  await ensureDemoOverlay();

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: SCOREBOARD_VIEWPORT,
    deviceScaleFactor: 2,
    colorScheme: 'dark',
    // Force English so the React i18n provider doesn't latch onto the
    // host's locale (which is what made the README screenshots come out
    // half in Spanish on a Spanish workstation). The /manage page is a
    // static HTML doc that is always English; aligning the SPA pins
    // every captured surface to one language.
    locale: 'en-US',
  });
  await installLogoRouter(context);
  const page = await context.newPage();

  try {
    await captureInitScreen(page);
    await captureScoreboard(page);
    await captureScoreboardPhone(page);
    await captureConfigPanel(page);
    await captureManagePage(page);
    await captureOverlayOutput(page, '', '06-overlay-default.png');
    await captureOverlayOutput(page, 'neo_jersey', '07-overlay-neo-jersey.png');
    await captureOverlayOutput(page, 'split_jersey', '08-overlay-split-jersey.png');
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
