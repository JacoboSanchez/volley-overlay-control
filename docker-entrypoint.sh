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
    # Reclaim when ``$DATA_DIR`` or anything inside it is not 1000-owned.
    # ``find`` evaluates the starting directory itself first, so this also
    # catches the freshly-mounted root-owned-volume case without a separate
    # ``stat`` check.
    #
    # ``-print -quit`` short-circuits on the first stale entry. A healthy
    # volume is still walked end-to-end to confirm — fine for the dozens
    # of JSON files this app writes; an operator running with a huge data
    # volume can override DATA_DIR or pre-chown out of band.
    if [ -n "$(find "$DATA_DIR" \( -not -uid 1000 -o -not -gid 1000 \) -print -quit 2>/dev/null)" ]; then
      echo "[entrypoint] Reclaiming $DATA_DIR for app:app (UID 1000)..."
      chown -R app:app "$DATA_DIR"
    fi
  fi
  exec runuser -u app -- "$@"
fi

exec "$@"
