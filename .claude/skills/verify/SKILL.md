---
name: verify
description: Boot an isolated backend and drive the real SPA with Playwright to verify a change end-to-end.
---

# Verifying changes against the running app

Recipe learned from a cold start; the screenshot rig
(`scripts/screenshots/run.sh` + `capture.mjs`) is the reference
implementation for all of this.

## Build / launch

```bash
# One-time: backend venv + frontend bundle (the backend serves frontend/dist).
uv venv .venv && uv pip install -p .venv/bin/python -r requirements.lock
(cd frontend && npm ci && npm run build)

# Isolated boot — scratch data dir so real overlays/DB are untouched:
# back up ./data, then `ln -s $(mktemp -d) data` (see run.sh's trap-guarded
# version), and export:
#   PYTEST_CURRENT_TEST=1        # skips dotenv loading in main.py
#   APP_PORT=8281 LOGGING_LEVEL=warning
#   ADMIN_BOOTSTRAP_TOKEN=<known> SESSION_COOKIE_SECURE=false
.venv/bin/python main.py &   # poll /health until 200
```

## Seed + authenticate

- `POST /api/v1/auth/claim-admin` with `{token, username, password}` →
  `vsession` cookie (empty DB always allows the claim).
- Create boards with `POST /api/v1/overlays {oid, description}` (cookie).
- Inject the cookie into the Playwright context (`ctx.addCookies`).

## Drive (Playwright)

- Chromium: `ls /opt/pw-browsers/chromium-*/chrome-linux/chrome | sort -V | tail -1`
  → pass as `executablePath`. Reuse `scripts/screenshots/node_modules`
  for the `playwright` package: ESM resolves from the **script's own
  path**, so place (or copy) the drive script inside `scripts/screenshots/`.
- **Gotcha:** dismiss the first-run gesture tour before clicking anything:
  `ctx.addInitScript(() => localStorage.setItem('volley_gestureTourSeen', 'true'))`.
- Board control: `/board?oid=<oid>` (owner), `/board?c=<control_token>`
  (operator). Config panel via `data-testid="config-tab-button"`; back via
  `scoreboard-tab-button`.
- Score a point by clicking `team-1-score` — it sits behind a double-tap
  discriminator, so poll `GET /api/v1/audit?oid=<oid>&limit=5` (cookie) for
  `"action":"add_point"` instead of asserting immediately.
- Unsaved-changes prompts are `window.confirm` → handle `page.on('dialog')`.
