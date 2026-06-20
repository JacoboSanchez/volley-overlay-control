# README screenshots

Tooling to regenerate the screenshots referenced from the project [README.md](../../README.md).

The capture pipeline boots a fresh backend instance with isolated environment
variables (no `.env` is loaded), **claims the first admin** with a known
bootstrap token to obtain a session cookie, creates two demo overlays via the
authenticated API (each minting a `public_token`), applies invented "Thunder
Wolves" / "Solar Hawks" team customization + match state, and walks Playwright
(Chromium headless) through the authenticated SPA pages and the
`public_token`-addressed OBS pages. The cookie is sent on every REST seeding
call and injected into the browser context so the account/board pages render.

## Usage

From the repository root:

```bash
# Build the frontend once.
(cd frontend && npm ci && npm run build)

# Capture (installs Playwright + Chromium on first run).
bash scripts/screenshots/run.sh
```

Output PNGs are written to `docs/screenshots/`. The orchestrator:

* Runs the backend (with the repo's `.venv/bin/python`, since the app now needs
  SQLAlchemy/Alembic) on port `8181` (override with `SCREENSHOT_PORT`).
* Sets `ADMIN_BOOTSTRAP_TOKEN` to a known value and `SESSION_COOKIE_SECURE=false`
  + `MATCH_REPORT_PUBLIC=true`, then `capture.mjs` claims the first admin
  (username `demo`, password `SCREENSHOT_ADMIN_PASSWORD`, default `demo-password`
  — must be ≥8 chars) to get a `vsession` cookie used for all seeding + the
  authenticated SPA pages.
* Symlinks `<repo>/data/` to a temp directory while running so the operator's
  real overlay state + database are never touched, then restores it on exit
  (each run therefore starts from a fresh DB with no admin).
* Skips loading `.env` (`PYTEST_CURRENT_TEST=1`) and unsets every operator
  variable that might pull in real teams, OIDs, or remote configurators.
* Captures each shot independently — one failed shot is logged and the run
  continues, exiting non-zero if any shot failed.

## What is captured

(Filenames are kept stable so the README image links don't churn; a couple no
longer match their original captions — `01` is now the sign-in page and `05` is
the account overlays page.)

| File | Description | Viewport |
|------|-------------|----------|
| `01-init-screen.png` | Sign-in page at `/login` (unauthenticated). | 1024×700 (compact desktop) |
| `02-scoreboard.png` | Control board at `/board?oid=`. | 844×390 (mobile-landscape) |
| `03-scoreboard-phone.png` | Control board in portrait, preview hidden so the points-history strip renders in the centre slot. | 390×844 (mobile-portrait) |
| `04-config-panel.png` | Customization tab inside the control board. | 844×390 (mobile-landscape) |
| `05-manage-page.png` | Account **My overlays** page at `/overlays` — the signed-in user's overlays with their copyable `public_token` OBS output URLs. | 1024×700 (compact desktop) |
| `06-overlay-mosaic-full.png` | `/overlay/{public_token}?style=mosaic` preview grid showing every selectable style with full match data. | 1600×1800 (mosaic grid) |
| `07-overlay-mosaic-simple.png` | `?style=mosaic` preview grid in simple mode (current set only). | 1600×1800 (mosaic grid) |
| `08-match-report.png` | Print-friendly match report at `/match/{id}/report` for a finished 3-1 demo match (read via `MATCH_REPORT_PUBLIC`). | 1024×1100 (compact desktop) |
| `09-spectator-page.png` | Public spectator (follow) page at `/follow/{public_token}` — header, scoreboard, set chart, history table, and live stats. Captured `fullPage` so every section is in-frame. | 414×896 (phone portrait) |
| `10-overlay-set-summary.png` | Set-summary recap overlay (`brand_columns` variant) at `/overlay/{public_token}`, at the canonical OBS browser-source size. | 1280×720 (overlay HD) |
| `11-point-type-picker.png` | Control board with the opt-in per-point classification dialog open (ace / kill / block / opponent error / quick point), shown after tapping a team's score with "Track point types" enabled. | 844×390 (mobile-landscape) |

The control board shots default to **844×390** because the operator's
primary use case is a phone held sideways during a match. The account pages
(sign-in, overlays) keep a (compact) desktop layout because they are
browser-first — account/overlay admin is rarely done on a phone. Mosaic uses
its own larger viewport to fit every style in one frame. The spectator page is
captured at phone-portrait width with `fullPage:true` because it is mobile-first
and read-only: a fan opens the share link on their phone and scrolls through the
full single-column layout.

PNGs are rendered at `deviceScaleFactor: 1` so they stay small enough to
ship in-tree alongside the README. Bump the factor in `capture.mjs` only
if a future change needs retina-quality assets — at 2× the mosaic alone
weighs more than 1 MB.
