#!/usr/bin/env bash
# Boot an isolated backend, capture README screenshots, tear down.
#
# Uses a temporary data dir for overlay state so the operator's real
# overlays (in <repo>/data/) are left alone. Skips loading .env so the
# operator's UNO_OVERLAY_OID, REMOTE_CONFIG_URL etc. do not leak into
# the demo. Invented teams + logos are applied via the REST API by
# capture.mjs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

PORT="${SCREENSHOT_PORT:-8181}"
# Must satisfy the app's MIN_PASSWORD_LENGTH (8); the demo admin is throwaway.
ADMIN_PW="${SCREENSHOT_ADMIN_PASSWORD:-demo-password}"
BASE_URL="http://localhost:${PORT}"

# The backend now depends on SQLAlchemy/Alembic, which live in the project's
# virtualenv — the bare system ``python`` will fail to import the app. Prefer
# the repo venv, fall back to whatever ``python`` is on PATH.
PYTHON_BIN="${SCREENSHOT_PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python"
  fi
fi

# Use a scratch data dir so persisted overlay JSON does not collide with
# the operator's working overlays. The backend reads its data dir from
# ``app/overlay/__init__.py`` which resolves relative to the repo root,
# so we redirect by temporarily symlinking ``./data`` to a tmpfs path.
#
# Declare the cleanup state up front and install the trap *before* the
# filesystem manipulations below, so a Ctrl+C in between cannot strand
# the operator's real data/ directory in a /tmp backup. Each cleanup
# branch is guarded so it is a no-op when the corresponding setup step
# has not run yet.
SCRATCH_DATA=""
ORIGINAL_DATA_BACKUP=""
SERVER_PID=""

cleanup() {
  set +e
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
  if [ -L "$REPO_ROOT/data" ]; then
    rm -f "$REPO_ROOT/data"
  fi
  if [ -n "$SCRATCH_DATA" ] && [ -d "$SCRATCH_DATA" ]; then
    rm -rf "$SCRATCH_DATA"
  fi
  if [ -n "$ORIGINAL_DATA_BACKUP" ] && [ -e "$ORIGINAL_DATA_BACKUP" ]; then
    mv "$ORIGINAL_DATA_BACKUP" "$REPO_ROOT/data"
    rmdir "$(dirname "$ORIGINAL_DATA_BACKUP")" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

SCRATCH_DATA="$(mktemp -d /tmp/volley-screenshots.XXXXXX)"
if [ -e "$REPO_ROOT/data" ] || [ -L "$REPO_ROOT/data" ]; then
  ORIGINAL_DATA_BACKUP="$(mktemp -d /tmp/volley-screenshots-data.XXXXXX)/orig"
  mv "$REPO_ROOT/data" "$ORIGINAL_DATA_BACKUP"
fi
ln -s "$SCRATCH_DATA" "$REPO_ROOT/data"

# Skip dotenv loading inside main.py; provide everything we need explicitly.
export PYTEST_CURRENT_TEST=1
export APP_PORT="$PORT"
export APP_TITLE="Volley Scoreboard Demo"
export LOGGING_LEVEL=warning
# Multi-user auth for the demo: capture.mjs claims the first admin with this
# known bootstrap token (the DB starts empty in the scratch data dir), then
# carries the session cookie. Cookies must not require HTTPS over the http
# harness, and the report shot reads a public match report.
export ADMIN_BOOTSTRAP_TOKEN="${ADMIN_BOOTSTRAP_TOKEN:-screenshot-bootstrap-token}"
export SESSION_COOKIE_SECURE=false
export MATCH_REPORT_PUBLIC=true
# Make sure no external services or operator-configured tokens bleed through.
unset UNO_OVERLAY_OID UNO_OVERLAY_OUTPUT REMOTE_CONFIG_URL APP_CUSTOM_OVERLAY_URL \
      APP_CUSTOM_OVERLAY_OUTPUT_URL PREDEFINED_OVERLAYS APP_TEAMS APP_THEMES \
      SCOREBOARD_USERS OVERLAY_SERVER_TOKEN

if [ ! -d "$REPO_ROOT/frontend/dist" ]; then
  echo "frontend/dist not found — run 'cd frontend && npm ci && npm run build' first." >&2
  exit 1
fi

# Rebuild the frontend if any source file under frontend/src is newer than
# the bundle. A stale dist is the most common cause of "feature X doesn't
# show up in the screenshot" bugs (the screenshot pipeline serves whatever
# the dist on disk currently has, even if the source has moved on since).
NEWEST_SRC=$(find "$REPO_ROOT/frontend/src" -type f -printf '%T@\n' 2>/dev/null \
  | sort -nr | head -1)
DIST_TIME=$(stat -c '%Y' "$REPO_ROOT/frontend/dist/index.html" 2>/dev/null || echo 0)
if [ -n "$NEWEST_SRC" ] && [ "${NEWEST_SRC%.*}" -gt "$DIST_TIME" ]; then
  echo "frontend/src is newer than the bundle — rebuilding ..."
  (cd "$REPO_ROOT/frontend" && npm run build) >/tmp/volley-screenshots-build.log 2>&1 \
    || { tail -n 40 /tmp/volley-screenshots-build.log >&2; exit 1; }
fi

# Ensure the Playwright JS package is present (this is just the npm library —
# no browser binary is downloaded here).
if [ ! -d "$SCRIPT_DIR/node_modules/playwright" ]; then
  echo "Installing Playwright (JS) into scripts/screenshots/ ..."
  (cd "$SCRIPT_DIR" && npm install --no-audit --no-fund)
fi

# Locate a Chromium binary for capture.mjs (which honours
# ``SCREENSHOT_CHROMIUM_PATH``). Prefer an explicit override, then any
# pre-installed Playwright browser — managed/CI images commonly ship these
# under /opt/pw-browsers or PLAYWRIGHT_BROWSERS_PATH — so we don't depend on
# the version-pinned download from cdn.playwright.dev, which restricted
# networks block. Only fall back to that download when nothing is found.
find_chromium() {
  if [ -n "${SCREENSHOT_CHROMIUM_PATH:-}" ] && [ -x "${SCREENSHOT_CHROMIUM_PATH}" ]; then
    printf '%s' "$SCREENSHOT_CHROMIUM_PATH"; return 0
  fi
  local root bin
  for root in "${PLAYWRIGHT_BROWSERS_PATH:-}" /opt/pw-browsers "$HOME/.cache/ms-playwright"; do
    [ -n "$root" ] && [ -d "$root" ] || continue
    bin=$(ls -1 "$root"/chromium-*/chrome-linux/chrome 2>/dev/null | sort -V | tail -1)
    [ -n "$bin" ] || bin=$(ls -1 "$root"/chromium_headless_shell-*/chrome-linux/headless_shell 2>/dev/null | sort -V | tail -1)
    if [ -n "$bin" ] && [ -x "$bin" ]; then printf '%s' "$bin"; return 0; fi
  done
  return 1
}

if CHROMIUM_BIN="$(find_chromium)"; then
  export SCREENSHOT_CHROMIUM_PATH="$CHROMIUM_BIN"
  echo "Using pre-installed Chromium: $SCREENSHOT_CHROMIUM_PATH"
else
  echo "No pre-installed Chromium found — attempting Playwright download ..."
  if ! (cd "$SCRIPT_DIR" && npx playwright install chromium); then
    echo "ERROR: no Chromium available. Set SCREENSHOT_CHROMIUM_PATH to a" >&2
    echo "Chromium binary, or install one (the cdn.playwright.dev download is" >&2
    echo "blocked on this network)." >&2
    exit 1
  fi
fi

echo "Starting backend on $BASE_URL (using $PYTHON_BIN) ..."
"$PYTHON_BIN" main.py >/tmp/volley-screenshots-server.log 2>&1 &
SERVER_PID=$!

# Wait for /health.
for _ in $(seq 1 60); do
  if curl -sf "$BASE_URL/health" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 0.5
done
if [ -z "${READY:-}" ]; then
  echo "Backend never became ready. Last 40 lines of server log:" >&2
  tail -n 40 /tmp/volley-screenshots-server.log >&2
  exit 1
fi
echo "Backend is up."

export SCREENSHOT_BASE_URL="$BASE_URL"
export SCREENSHOT_ADMIN_PASSWORD="$ADMIN_PW"

(cd "$SCRIPT_DIR" && node capture.mjs)

echo "Screenshots written to docs/screenshots/."
