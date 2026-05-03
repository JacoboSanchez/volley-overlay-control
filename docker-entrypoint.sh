#!/bin/sh
# Container entrypoint that ensures the data directory is writable by the
# unprivileged ``app`` user and then drops privileges before exec'ing the
# real command.
#
# This is the migration path for upgrades from images that ran as root: any
# files left behind in the ``/app/data`` volume are reclaimed before the
# new non-root process tries to touch them.

set -e

DATA_DIR="${DATA_DIR:-/app/data}"

if [ "$(id -u)" = "0" ]; then
  if [ -d "$DATA_DIR" ]; then
    # Only chown when ownership is wrong, so a 1M-file volume on a slow
    # disk doesn't pay the recursive walk cost on every restart.
    if [ "$(stat -c '%u' "$DATA_DIR")" != "1000" ] \
       || [ "$(stat -c '%g' "$DATA_DIR")" != "1000" ]; then
      echo "[entrypoint] Reclaiming $DATA_DIR for app:app (UID 1000)..."
      chown -R app:app "$DATA_DIR"
    fi
  fi
  exec runuser -u app -- "$@"
fi

exec "$@"
