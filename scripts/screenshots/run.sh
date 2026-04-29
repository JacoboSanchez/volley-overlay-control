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
ADMIN_PW="${SCREENSHOT_ADMIN_PASSWORD:-demo}"
BASE_URL="http://localhost:${PORT}"

# Use a scratch data dir so persisted overlay JSON does not collide with
# the operator's working overlays. The backend reads its data dir from
# ``app/overlay/__init__.py`` which resolves relative to the repo root,
# so we redirect by temporarily symlinking ``./data`` to a tmpfs path.
SCRATCH_DATA="$(mktemp -d /tmp/volley-screenshots.XXXXXX)"
ORIGINAL_DATA_BACKUP=""
if [ -e "$REPO_ROOT/data" ] || [ -L "$REPO_ROOT/data" ]; then
  ORIGINAL_DATA_BACKUP="$(mktemp -d /tmp/volley-screenshots-data.XXXXXX)/orig"
  mv "$REPO_ROOT/data" "$ORIGINAL_DATA_BACKUP"
fi
ln -s "$SCRATCH_DATA" "$REPO_ROOT/data"

cleanup() {
  set +e
  if [ -n "${SERVER_PID:-}" ]; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
  rm -f "$REPO_ROOT/data"
  rm -rf "$SCRATCH_DATA"
  if [ -n "$ORIGINAL_DATA_BACKUP" ] && [ -e "$ORIGINAL_DATA_BACKUP" ]; then
    mv "$ORIGINAL_DATA_BACKUP" "$REPO_ROOT/data"
    rmdir "$(dirname "$ORIGINAL_DATA_BACKUP")" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# Skip dotenv loading inside main.py; provide everything we need explicitly.
export PYTEST_CURRENT_TEST=1
export APP_PORT="$PORT"
export APP_TITLE="Volley Scoreboard Demo"
export OVERLAY_MANAGER_PASSWORD="$ADMIN_PW"
export LOGGING_LEVEL=warning
# Make sure no external services or operator-configured tokens bleed through.
unset UNO_OVERLAY_OID UNO_OVERLAY_OUTPUT REMOTE_CONFIG_URL APP_CUSTOM_OVERLAY_URL \
      APP_CUSTOM_OVERLAY_OUTPUT_URL PREDEFINED_OVERLAYS APP_TEAMS APP_THEMES \
      SCOREBOARD_USERS OVERLAY_SERVER_TOKEN

if [ ! -d "$REPO_ROOT/frontend/dist" ]; then
  echo "frontend/dist not found — run 'cd frontend && npm ci && npm run build' first." >&2
  exit 1
fi

if [ ! -d "$SCRIPT_DIR/node_modules/playwright" ]; then
  echo "Installing Playwright into scripts/screenshots/ ..."
  (cd "$SCRIPT_DIR" && npm install --no-audit --no-fund)
  (cd "$SCRIPT_DIR" && npx playwright install chromium)
fi

echo "Starting backend on $BASE_URL ..."
python main.py >/tmp/volley-screenshots-server.log 2>&1 &
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
