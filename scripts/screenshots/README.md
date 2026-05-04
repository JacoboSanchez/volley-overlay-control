# README screenshots

Tooling to regenerate the screenshots referenced from the project [README.md](../../README.md).

The capture pipeline boots a fresh backend instance with isolated environment
variables (no `.env` is loaded), creates two demo custom overlays, applies
invented "Thunder Wolves" / "Solar Hawks" team customization via the REST API,
and walks Playwright (Chromium headless) through each public surface.

## Usage

From the repository root:

```bash
# Build the frontend once.
(cd frontend && npm ci && npm run build)

# Capture (installs Playwright + Chromium on first run).
bash scripts/screenshots/run.sh
```

Output PNGs are written to `docs/screenshots/`. The orchestrator:

* Runs the backend on port `8181` (override with `SCREENSHOT_PORT`).
* Sets `OVERLAY_MANAGER_PASSWORD=demo` (override with `SCREENSHOT_ADMIN_PASSWORD`).
* Symlinks `<repo>/data/` to a temp directory while running so the
  operator's real overlay state is never touched, then restores it on exit.
* Skips loading `.env` (`PYTEST_CURRENT_TEST=1`) and unsets every operator
  variable that might pull in real teams, OIDs, or remote configurators.

## What is captured

| File | Description | Viewport |
|------|-------------|----------|
| `01-init-screen.png` | Connect screen at `/`. | 844×390 (mobile-landscape) |
| `02-scoreboard.png` | Main control UI. | 844×390 (mobile-landscape) |
| `03-scoreboard-phone.png` | Main control UI in portrait, preview hidden so the points-history strip renders in the centre slot. | 390×844 (mobile-portrait) |
| `04-config-panel.png` | Customization tab inside the React control UI. | 844×390 (mobile-landscape) |
| `05-manage-page.png` | Custom overlay manager at `/manage`. | 1024×700 (compact desktop) |
| `06-overlay-mosaic-full.png` | `?style=mosaic` preview grid showing every selectable style with full match data. | 1600×1800 (mosaic grid) |
| `07-overlay-mosaic-simple.png` | `?style=mosaic` preview grid in simple mode (current set only). | 1600×1800 (mosaic grid) |
| `08-match-report.png` | Print-friendly match report at `/match/{id}/report` for a finished 3-1 demo match. | 1024×1100 (compact desktop) |

The control UI shots default to **844×390** because the operator's
primary use case is a phone held sideways during a match. `/manage`
keeps a (compact) desktop layout because it is browser-first — admin
work is rarely done on a phone. Mosaic uses its own larger viewport
to fit every style in one frame.

PNGs are rendered at `deviceScaleFactor: 1` so they stay small enough to
ship in-tree alongside the README. Bump the factor in `capture.mjs` only
if a future change needs retina-quality assets — at 2× the mosaic alone
weighs more than 1 MB.
