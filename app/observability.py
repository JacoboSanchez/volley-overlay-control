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
from collections.abc import Callable
from urllib.parse import urlparse, urlunparse

from app.env_vars_manager import EnvVarsManager
from app.logging_context import get_request_id, get_trace_id
from app.logging_utils import mask_capability_tokens

logger = logging.getLogger(__name__)


# Set once by init_error_tracking; None means "no reporter wired".
_capture_hook: Callable[[BaseException], object] | None = None
_initialised = False


# ---------------------------------------------------------------------------
# Event scrubbing
#
# ``send_default_pii=False`` is necessary but NOT sufficient. It withholds
# cookies, the client IP and sensitive headers — it does **not** strip the
# request URL, the query string, or the request body, all of which carry
# live credentials in this app:
#
# * ``/overlay/<public_token>``, ``/follow/<…>``, ``/ws/<…>``,
#   ``/matches/<…>`` and ``/match/<match_id>/report`` put an unguessable
#   capability token in the *path*.
# * ``?c=<control_token>`` (shareable operator board link) and the report
#   ``?exp=&sig=`` signature live in the *query string*, and ``?u=`` is a
#   username.
# * ``POST /api/v1/auth/login`` carries a plaintext password in the *body*.
#
# Any unhandled exception on those routes would otherwise hand a working
# credential to a third-party service, where anyone with event access could
# replay it. So the event is scrubbed here, in ``before_send``, which is
# version-independent — doing it through init options would mean guessing
# which of ``max_request_body_size`` / ``request_bodies`` the installed
# sentry-sdk major accepts, and an unknown option makes ``init`` raise.
#
# ``request`` is not the only channel, and this is the part that is easy to
# get wrong. Sentry's logging integration promotes ``ERROR`` records into
# events in their own right, so the formatted message (``logentry``) and the
# ``extra`` payload carry whatever a log call passed them — and the project's
# own ``redact`` filter does **not** apply, because it is registered on the
# stdout/file *handlers* rather than on a logger, and Sentry installs its own
# handler. ``_scrub_event`` therefore sweeps ``logentry``, ``extra``,
# ``breadcrumbs``, ``transaction`` and ``message`` as well. Call sites help by
# not putting a raw path on the record in the first place (see
# ``app.api.middleware.errors``), but this hook is the backstop that does not
# depend on every future call site remembering.
#
# Scrubbing is unconditional, deliberately NOT tied to ``LOG_REDACT``. That
# flag exists so a developer can read raw values in their *own* terminal;
# letting it also open a channel to an external service would be a footgun.
# ---------------------------------------------------------------------------

_MASK = "[redacted]"

# Dropped outright: Sentry filters most of these itself when PII is off,
# but repeating it here is cheap and does not depend on that behaviour.
_SENSITIVE_HEADERS = frozenset(
    {"authorization", "cookie", "set-cookie", "x-control-token",
     "x-webhook-signature", "proxy-authorization"},
)


def _scrub_url(url: str) -> str:
    """Drop userinfo, query and fragment; mask capability path segments."""
    try:
        parts = urlparse(url)
    except ValueError:
        return _MASK
    netloc = parts.netloc.rpartition("@")[-1]
    return urlunparse(
        (parts.scheme, netloc, mask_capability_tokens(parts.path), "", "", ""),
    )


def _scrub_value(value: object) -> object:
    """Recursively mask capability tokens in strings inside *value*."""
    if isinstance(value, str):
        return mask_capability_tokens(value)
    if isinstance(value, dict):
        return {k: _scrub_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        scrubbed = [_scrub_value(v) for v in value]
        return tuple(scrubbed) if isinstance(value, tuple) else scrubbed
    return value


def _scrub_request(request: dict) -> None:
    """Strip credential-bearing fields from an event's request context."""
    url = request.get("url")
    if isinstance(url, str):
        request["url"] = _scrub_url(url)
    # The query string and body are removed rather than filtered
    # key-by-key: an allow-list would silently start leaking the first
    # time a new credential-bearing parameter is added.
    for field in ("query_string", "data", "cookies"):
        if field in request:
            request[field] = _MASK
    headers = request.get("headers")
    if isinstance(headers, dict):
        for name in list(headers):
            if isinstance(name, str) and name.lower() in _SENSITIVE_HEADERS:
                headers[name] = _MASK


def _scrub_event(event: dict) -> None:
    """Mask capability tokens everywhere they can reach an event.

    ``request`` is not the only channel. Sentry's logging integration
    promotes ``ERROR`` records into events of their own, carrying the
    formatted message under ``logentry`` and the ``extra`` payload
    alongside it — and our ``redact`` filter cannot help there, because it
    is attached to *handlers*, which Sentry's own handler is not. So every
    field that can hold a request path is swept, not just the request
    context.
    """
    request = event.get("request")
    if isinstance(request, dict):
        _scrub_request(request)

    for field in ("logentry", "extra", "transaction", "message"):
        if field in event:
            event[field] = _scrub_value(event[field])

    # Breadcrumbs are either a bare list or {"values": [...]}.
    crumbs = event.get("breadcrumbs")
    if isinstance(crumbs, dict) and "values" in crumbs:
        crumbs["values"] = _scrub_value(crumbs["values"])
    elif isinstance(crumbs, list):
        event["breadcrumbs"] = _scrub_value(crumbs)


def _sample_rate() -> float | None:
    """Parse ``SENTRY_TRACES_SAMPLE_RATE`` into ``[0.0, 1.0]``, or ``None``."""
    raw = (EnvVarsManager.get_env_var("SENTRY_TRACES_SAMPLE_RATE", "") or "").strip()
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


def _before_send(event: dict, _hint: object) -> dict | None:
    """Scrub credentials from an outgoing event, then tag it for correlation.

    Tagging lets an operator pivot from an aggregated exception straight to
    the matching log lines (``request_id``) or to the upstream trace
    (``trace_id``, only when an inbound ``traceparent`` supplied one).
    Scrubbing keeps capability tokens and passwords from leaving the
    process — see the module comment above.
    """
    try:
        _scrub_event(event)
    except Exception:
        # A scrubber that fails must not ship the unscrubbed event. There
        # is no safe partial state to fall back to, so the event is
        # dropped entirely (``before_send`` returning None) rather than
        # sent with fields we could not verify.
        logger.warning("Failed to scrub error report; dropping it", exc_info=True)
        return None
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

    dsn = (EnvVarsManager.get_env_var("SENTRY_DSN", "") or "").strip()
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
    environment = (
        EnvVarsManager.get_env_var("SENTRY_ENVIRONMENT", "") or ""
    ).strip()
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
