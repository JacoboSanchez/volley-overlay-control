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
    # Reclaim when the directory itself is wrong, OR when any file inside
    # is. The first condition catches a freshly-mounted root-owned volume;
    # the second catches the upgrade case where the directory was already
    # 1000-owned but the previous root-running image wrote root-owned
    # state files into it (the app user could then read them but not
    # atomically replace them, silently losing config).
    #
    # ``find ... -print -quit`` short-circuits on the first stale entry
    # so a healthy volume still pays only one syscall.
    if [ "$(stat -c '%u' "$DATA_DIR")" != "1000" ] \
       || [ "$(stat -c '%g' "$DATA_DIR")" != "1000" ] \
       || [ -n "$(find "$DATA_DIR" \( -not -uid 1000 -o -not -gid 1000 \) -print -quit 2>/dev/null)" ]; then
      echo "[entrypoint] Reclaiming $DATA_DIR for app:app (UID 1000)..."
      chown -R app:app "$DATA_DIR"
    fi
  fi
  exec runuser -u app -- "$@"
fi

exec "$@"
