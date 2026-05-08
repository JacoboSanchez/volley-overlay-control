import os


class Constants:
    """
    Centralized location for hardcoded strings, configuration constants, and URLs.
    This prevents clutter in the main logic files and makes updates easier.
    """

    # The SVG string used for the application favicon
    CUSTOM_FAVICON = '<svg xmlns="http://www.w3.org/2000/svg" enable-background="new 0 0 24 24" height="24px" viewBox="0 0 24 24" width="24px" fill="#5f6368"><g><rect fill="none" height="24" width="24"/></g><g><g><path d="M12,2C6.48,2,2,6.48,2,12c0,5.52,4.48,10,10,10s10-4.48,10-10C22,6.48,17.52,2,12,2z M13,4.07 c3.07,0.38,5.57,2.52,6.54,5.36L13,5.65V4.07z M8,5.08c1.18-0.69,3.33-1.06,3-1.02v7.35l-3,1.73V5.08z M4.63,15.1 C4.23,14.14,4,13.1,4,12c0-2.02,0.76-3.86,2-5.27v7.58L4.63,15.1z M5.64,16.83L12,13.15l3,1.73l-6.98,4.03 C7.09,18.38,6.28,17.68,5.64,16.83z M10.42,19.84 M12,20c-0.54,0-1.07-0.06-1.58-0.16l6.58-3.8l1.36,0.78 C16.9,18.75,14.6,20,12,20z M13,11.42V7.96l7,4.05c0,1.1-0.23,2.14-0.63,3.09L13,11.42z"/></g></g></svg>'

    # Base URL for the overlays.uno API
    API_BASE_URL = 'https://app.overlays.uno/apiv2/controlapps'


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _env_float_nonneg(key: str, default: float) -> float:
    """Like :func:`_env_float` but accepts 0 as a valid disable signal.

    Used by knobs where ``0`` has a meaningful "off" interpretation
    (heartbeat interval, optional rate-limit window) — the strict
    ``> 0`` filter on :func:`_env_float` would otherwise silently
    upgrade ``KEY=0`` to the default and confuse the operator.
    """
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


# Idle game sessions are evicted after this many seconds. Override with
# the ``SESSION_TTL_SECONDS`` env var.
SESSION_TTL_SECONDS = _env_int("SESSION_TTL_SECONDS", 24 * 60 * 60)

# Per-socket WebSocket broadcast timeout used by ``WSHub``. A slow
# subscriber must not stall delivery to the rest. Override with
# ``WS_BROADCAST_SEND_TIMEOUT_SECONDS``.
WS_BROADCAST_SEND_TIMEOUT_SECONDS = _env_float(
    "WS_BROADCAST_SEND_TIMEOUT_SECONDS", 2.0,
)

# Per-OID audit log file rotation. The active log rotates to
# ``audit_<hash>.jsonl.1`` once it exceeds ``AUDIT_LOG_MAX_BYTES``,
# bumping older rotations down by one suffix; anything above
# ``AUDIT_LOG_MAX_FILES`` (counting the active file) is dropped.
# Keeps long-running per-OID logs from growing unbounded while still
# letting ``read_all`` / ``read_page`` walk the rotated set transparently.
AUDIT_LOG_MAX_BYTES = _env_int("AUDIT_LOG_MAX_BYTES", 5 * 1024 * 1024)
AUDIT_LOG_MAX_FILES = _env_int("AUDIT_LOG_MAX_FILES", 5)

# Maximum number of concurrent WebSocket subscribers per OID. Once an
# OID hits this cap, ``WSHub.connect`` rejects further upgrades with a
# 1013 ("Try Again Later") close so a runaway tab loop or scripted
# attacker cannot exhaust file descriptors on the box. Override with
# ``WSHUB_MAX_CLIENTS_PER_OID``.
WSHUB_MAX_CLIENTS_PER_OID = _env_int("WSHUB_MAX_CLIENTS_PER_OID", 200)

# Server-side WebSocket heartbeat. ``WSHUB_HEARTBEAT_INTERVAL_SECONDS``
# defaults to 0 (disabled) because the existing browser client does not
# yet respond to application-level pings — enabling without first
# updating the frontend would churn live tabs every
# ``WSHUB_CLIENT_TIMEOUT_SECONDS``. Operators that have a heartbeat-
# aware client (e.g. a custom OBS bridge) can opt in by setting
# ``WSHUB_HEARTBEAT_INTERVAL_SECONDS=30`` and tuning the timeout.
# Constraint: ``CLIENT_TIMEOUT > 2 * INTERVAL`` so a single dropped
# pong does not churn the connection (mirrors the WSControlClient rule).
WSHUB_HEARTBEAT_INTERVAL_SECONDS = _env_float_nonneg(
    "WSHUB_HEARTBEAT_INTERVAL_SECONDS", 0.0,
)
WSHUB_CLIENT_TIMEOUT_SECONDS = _env_float(
    "WSHUB_CLIENT_TIMEOUT_SECONDS", 60.0,
)

# Outbound webhook retry policy. Exponential backoff between attempts:
# ``RETRY_BASE * 2**attempt`` capped at ``RETRY_MAX``. Only 5xx
# responses and ``requests.RequestException`` (timeouts, connect
# errors) trigger a retry — 4xx is treated as a permanent client
# rejection and goes straight to the dead-letter (well, it does not:
# 4xx is logged and dropped, see ``app/api/webhooks.py``).
# ``RETRY_ATTEMPTS`` counts retries *after* the first attempt, so
# the default of 3 means up to 4 total POSTs per delivery.
WEBHOOK_RETRY_ATTEMPTS = _env_int("WEBHOOK_RETRY_ATTEMPTS", 3)
WEBHOOK_RETRY_BASE_SECONDS = _env_float("WEBHOOK_RETRY_BASE_SECONDS", 1.0)
WEBHOOK_RETRY_MAX_SECONDS = _env_float("WEBHOOK_RETRY_MAX_SECONDS", 8.0)

# ``WSControlClient`` reconnect/heartbeat tuning. ``WS_ZOMBIE_DEADLINE``
# must stay > 2 * ``WS_HEARTBEAT_INTERVAL`` so a single dropped pong
# does not churn the connection.
WS_RECONNECT_BASE_SECONDS = _env_float("WS_RECONNECT_BASE_SECONDS", 1.0)
WS_RECONNECT_MAX_SECONDS = _env_float("WS_RECONNECT_MAX_SECONDS", 30.0)
WS_HEARTBEAT_INTERVAL_SECONDS = _env_float(
    "WS_HEARTBEAT_INTERVAL_SECONDS", 25.0,
)
WS_ZOMBIE_DEADLINE_SECONDS = _env_float(
    "WS_ZOMBIE_DEADLINE_SECONDS", 55.0,
)
