"""Optional error-tracking integration point.

The app has always logged unhandled exceptions with full request context
(:mod:`app.api.middleware.errors`), but a log line is not an aggregate:
without a reporter, an operator has no way to see "this 500 happened 40
times today, starting at 14:02". This module is the single hook where a
reporter gets wired in, kept deliberately small:

* :func:`init_error_tracking` is called once from
  :func:`app.bootstrap.create_app`. With ``SENTRY_DSN`` unset it does
  nothing at all — the default deployment gains no dependency, no
  outbound connection, and no behaviour change.
* :func:`capture_exception` is called from the exception middleware and
  is a no-op unless a reporter was wired.

``sentry-sdk`` is an **optional** import, not a pinned requirement.
Shipping it for everyone would add an always-installed dependency (and
its audit surface) to serve the minority of deployments that point it at
a DSN; operators who want reporting add ``sentry-sdk`` to their image and
set ``SENTRY_DSN``. A DSN set without the package installed logs a
warning at startup rather than failing the boot — losing telemetry must
never take the scoreboard down mid-match.

Trace correlation is separate and always on: see
:mod:`app.api.middleware.logging`, which adopts an inbound W3C
``traceparent``. Whatever is set there rides along on every report
through :func:`_before_send`, so an exception in the aggregator links
back to the same trace the upstream proxy recorded.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from app.logging_context import get_request_id, get_trace_id

logger = logging.getLogger(__name__)


# Set once by init_error_tracking; None means "no reporter wired".
_capture_hook: Callable[[BaseException], object] | None = None
_initialised = False


def _sample_rate() -> float | None:
    """Parse ``SENTRY_TRACES_SAMPLE_RATE`` into ``[0.0, 1.0]``, or ``None``."""
    raw = (os.environ.get("SENTRY_TRACES_SAMPLE_RATE") or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "Ignoring SENTRY_TRACES_SAMPLE_RATE=%r — not a number.", raw,
        )
        return None
    if not 0.0 <= value <= 1.0:
        logger.warning(
            "Ignoring SENTRY_TRACES_SAMPLE_RATE=%r — outside [0.0, 1.0].", raw,
        )
        return None
    return value


def _before_send(event: dict, _hint: object) -> dict:
    """Tag every outgoing event with our own correlation ids.

    Lets an operator pivot from an aggregated exception straight to the
    matching log lines (``request_id``) or to the upstream trace
    (``trace_id``, only when an inbound ``traceparent`` supplied one).
    """
    try:
        tags = event.setdefault("tags", {})
        if isinstance(tags, dict):
            tags.setdefault("request_id", get_request_id())
            trace_id = get_trace_id()
            if trace_id != "-":
                tags.setdefault("trace_id", trace_id)
    except Exception:  # pragma: no cover - defensive
        logger.debug("Failed to tag error report", exc_info=True)
    return event


def init_error_tracking() -> bool:
    """Wire the error reporter if one is configured. Returns whether it was.

    Idempotent: repeated calls (``create_app`` runs per test) are no-ops
    after the first. Every failure path degrades to "no reporting" and
    logs why — this must never raise into startup.
    """
    global _capture_hook, _initialised

    if _initialised:
        return _capture_hook is not None
    _initialised = True

    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if not dsn:
        return False

    try:
        import sentry_sdk
    except ImportError:
        logger.warning(
            "SENTRY_DSN is set but the 'sentry-sdk' package is not installed, "
            "so exceptions will only be logged, not reported. Install it in "
            "your image (it is deliberately not a bundled dependency).",
        )
        return False

    options: dict[str, object] = {
        "dsn": dsn,
        # The project redacts OIDs and URLs in its own logs; shipping
        # request headers, cookies and IPs to a third party by default
        # would quietly undo that. Operators who want it can layer their
        # own sentry_sdk.init before ours.
        "send_default_pii": False,
        "before_send": _before_send,
    }
    environment = (os.environ.get("SENTRY_ENVIRONMENT") or "").strip()
    if environment:
        options["environment"] = environment
    sample_rate = _sample_rate()
    if sample_rate is not None:
        options["traces_sample_rate"] = sample_rate

    try:
        sentry_sdk.init(**options)
    except Exception:
        logger.exception(
            "Failed to initialise the Sentry reporter; continuing without "
            "error tracking.",
        )
        return False

    _capture_hook = sentry_sdk.capture_exception
    logger.info(
        "Error tracking enabled (sentry-sdk, environment=%s, traces=%s)",
        environment or "unset", "unset" if sample_rate is None else sample_rate,
    )
    return True


def capture_exception(exc: BaseException) -> None:
    """Report *exc* to the configured reporter, if any.

    Never raises: a reporter that is down, misconfigured, or rate-limited
    must not turn a logged 500 into a crash inside the middleware.
    """
    hook = _capture_hook
    if hook is None:
        return
    try:
        hook(exc)
    except Exception:  # pragma: no cover - defensive
        logger.debug("Error reporter failed to capture an exception", exc_info=True)


def is_error_tracking_enabled() -> bool:
    """Whether a reporter is currently wired. Exposed for tests and probes."""
    return _capture_hook is not None


def _reset_for_tests() -> None:
    """Drop any wired reporter so the next init re-reads the environment."""
    global _capture_hook, _initialised
    _capture_hook = None
    _initialised = False
