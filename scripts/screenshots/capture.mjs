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

// Mobile-landscape is the primary capture viewport because the
// scoring operator's main use case is a phone held sideways during a
// match. 844×390 is the rotation of PHONE_VIEWPORT below (iPhone-class
// dimensions). The exception is /manage, which is browser-first
// (operators rarely admin from a phone) — it uses MANAGE_VIEWPORT, a
// scaled-down desktop layout.
const MOBILE_LANDSCAPE_VIEWPORT = { width: 844, height: 390 };
const PHONE_VIEWPORT = { width: 390, height: 844 };
const MANAGE_VIEWPORT = { width: 1024, height: 700 };

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

  // Drive a realistic mid-match state: tied 1-1 going into set 3 with the
  // current set in progress. Always set the loser's value first so
  // set-score's auto-set-win check doesn't promote the wrong team
  // (current_score - rival_score > 1 trips at 25-0 otherwise).

  // Set 1 — Thunder Wolves 25, Solar Hawks 23. TW takes the set.
  await post('/api/v1/game/set-score', { team: 2, set_number: 1, value: 23 });
  await post('/api/v1/game/set-score', { team: 1, set_number: 1, value: 25 });

  // Set 2 — Thunder Wolves 22, Solar Hawks 25. SH levels 1-1.
  await post('/api/v1/game/set-score', { team: 1, set_number: 2, value: 22 });
  await post('/api/v1/game/set-score', { team: 2, set_number: 2, value: 25 });

  // Set 3 (current) — mid-rally, 18-15 with TW serving.
  await post('/api/v1/game/set-score', { team: 1, set_number: 3, value: 18 });
  await post('/api/v1/game/set-score', { team: 2, set_number: 3, value: 15 });
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
  await page.setViewportSize(MOBILE_LANDSCAPE_VIEWPORT);
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

async function captureOverlayMosaic(page, filename) {
  // Mosaic is a full-page grid of every selectable style; needs a wider
  // viewport and enough vertical room to fit every cell, plus extra
  // wait time so each iframe finishes its postMessage handshake and
  // shrinks to its overlay-only bounds.
  const MOSAIC_VIEWPORT = { width: 1600, height: 1800 };
  await page.setViewportSize(MOSAIC_VIEWPORT);
  await page.goto(`${BASE}/overlay/${encodeURIComponent(DEMO_OID)}?style=mosaic`, {
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

  const browser = await chromium.launch({ headless: true });
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
  const page = await context.newPage();

  try {
    await captureInitScreen(page);
    await captureScoreboard(page);
    await captureScoreboardPhone(page);
    await captureConfigPanel(page);
    await captureManagePage(page);
    // Mosaic captured twice — once with the full match data, once with
    // simple mode toggled on so the "show only current set" treatment
    // is visible across every style.
    await setSimpleMode(false);
    await captureOverlayMosaic(page, '06-overlay-mosaic-full.png');
    await setSimpleMode(true);
    await captureOverlayMosaic(page, '07-overlay-mosaic-simple.png');
    await setSimpleMode(false);
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
