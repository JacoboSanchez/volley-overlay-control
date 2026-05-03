/**
 * Centralised tunable constants for the React control UI.
 *
 * Anything time-based or capacity-based that a future reader might want to
 * tweak should live here so it can be discovered with one grep instead of
 * scattered across components and hooks.
 */

// --- Press-gesture detection (`useDoubleTap`) ----------------------------

/** Window used to distinguish a single tap from a double tap (ms).
 *  Short enough that single taps feel snappy; long enough to clear a typical
 *  human double-tap (~150 ms). */
export const DOUBLE_TAP_MS = 280;

/** Hold duration before a long-press fires (ms). */
export const LONG_PRESS_MS = 1000;

// --- HUD chrome ---------------------------------------------------------

/** Pointer-inactivity window before the bottom HUD auto-hides on phones (ms). */
export const HUD_AUTO_HIDE_MS = 5000;

// --- WebSocket ----------------------------------------------------------

/** Heartbeat interval — frontend pings the WebSocket so the server can
 *  detect zombie connections (ms). */
export const WS_PING_INTERVAL_MS = 25000;

/** Delay before attempting to reconnect after an unexpected close (ms).
 *  Excludes intentional close codes such as 4004 ("no session"). */
export const WS_RECONNECT_MS = 3000;

/** Initial delay for the exponential reconnect backoff (ms). */
export const WS_RECONNECT_BASE_MS = 1000;

/** Upper bound for the exponential reconnect backoff (ms). Prevents the
 *  retry interval from growing unboundedly while the server is down. */
export const WS_RECONNECT_MAX_MS = 60000;

/** Multiplicative factor between successive reconnect attempts. */
export const WS_RECONNECT_FACTOR = 2;
