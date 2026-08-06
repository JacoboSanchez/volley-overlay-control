"""The read path for operator-tunable environment configuration.

:class:`EnvVarsManager` layers the (optional) ``REMOTE_CONFIG_URL`` payload
over ``os.environ``, so anything read directly from ``os.environ`` is
invisible to remote-config deployments. The typed accessors —
:meth:`get_str_env`, :meth:`get_bool_env`, :meth:`get_int_env`,
:meth:`get_float_env`, :meth:`get_enum_env` — validate *where the value is
read*, so a malformed or
out-of-range setting degrades to the caller's default with one warning
rather than crashing a request or being clamped somewhere the reader cannot
see. Prefer them for anything new, and add a missing shape here rather than
writing a second parser in a consumer module.

A few readers stay on ``os.environ`` by design, because they run before or
independently of a remote fetch — a value needed to *reach* the remote
config cannot come from it: ``DATABASE_URL`` (:mod:`app.db.engine`, read at
import), the cookie ``SESSION_SECRET`` and the report signing key
(:mod:`app.security_bootstrap`), ``ADMIN_BOOTSTRAP_TOKEN``, the
``TRUSTED_HOSTS`` / ``CORS_ALLOWED_ORIGINS`` middleware lists, and
``LOG_REDACT``. So do the two knobs governing the fetch itself
(``REMOTE_CONFIG_URL``, ``REMOTE_CONFIG_ALLOW_PRIVATE_IPS``) — what decides
*how* the remote config is fetched must not come from the remote config.
That list is exhaustive; ``tests/test_env_read_path.py`` keeps it that way.
"""

import json
import logging
import math
import os
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

import requests

from app.logging_utils import redact_url
from app.net_guard import is_target_safe
from app.trace_context import outbound_trace_headers

logger = logging.getLogger(__name__)

_TRUTHY_VALUES = ("1", "true", "t", "yes", "on")

_Number = TypeVar("_Number", int, float)


def is_truthy(value: object) -> bool:
    """Return True when *value* parses as a truthy boolean string."""
    return isinstance(value, str) and value.strip().lower() in _TRUTHY_VALUES


def _bound_violation(
    value: float,
    minimum: float | None,
    exclusive_minimum: float | None,
    maximum: float | None,
) -> str | None:
    """Return the breached constraint as operator-readable text, else None."""
    if minimum is not None and value < minimum:
        return f">= {minimum}"
    if exclusive_minimum is not None and value <= exclusive_minimum:
        return f"> {exclusive_minimum}"
    if maximum is not None and value > maximum:
        return f"<= {maximum}"
    return None


class EnvVarsManager:
    _remote_config_cache: dict[str, Any] = {}
    _cache_timestamp: float = 0
    _CACHE_EXPIRATION_SECONDS = 10
    # Serialises the refetch so concurrent callers (request pool + webhook
    # executor) don't each fire a duplicate HTTP fetch and race on the cache.
    _lock = threading.Lock()
    # True while a background revalidation thread is running.
    _refresh_in_flight = False

    @classmethod
    def get_env_var(
        cls,
        key: str,
        default: Any = None,
    ) -> Any:
        cls._load_remote_config_if_needed()
        return cls._remote_config_cache.get(key, os.environ.get(key, default))

    @classmethod
    def get_bool_env(cls, key: str, default: bool = False) -> bool:
        """Return *key* parsed as a truthy string. Unset env falls back to *default*."""
        raw = cls.get_env_var(key, None)
        if raw is None:
            return default
        return is_truthy(raw if isinstance(raw, str) else str(raw))

    @classmethod
    def get_str_env(cls, key: str, default: str = "") -> str:
        """Return *key* as a stripped ``str``, treating blank as unset.

        Prefer this over raw :meth:`get_env_var` wherever the caller goes on
        to use string methods. A remote payload is JSON, so a value can
        arrive as a number or bool; ``get_env_var`` hands that back as-is
        and the caller's ``.strip()`` would raise ``AttributeError``.
        """
        raw = cls.get_env_var(key, None)
        if raw is None:
            return default
        text = str(raw).strip()
        return text or default

    @classmethod
    def get_int_env(
        cls,
        key: str,
        default: int,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:
        """Return *key* as an ``int``, degrading to *default* when unusable.

        ``minimum`` / ``maximum`` are inclusive. A value that is unset,
        blank, unparseable or out of range logs one warning and yields
        *default* — a typo in an operator's ``.env`` must never take a
        board down with a 500. A remote-config JSON number is accepted
        only when it converts losslessly (``5.0`` yes, ``1.9`` no).
        """
        return cls._get_number_env(
            key, default, int, minimum=minimum, maximum=maximum,
        )

    @classmethod
    def get_float_env(
        cls,
        key: str,
        default: float,
        *,
        minimum: float | None = None,
        exclusive_minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        """Return *key* as a ``float``, degrading to *default* when unusable.

        ``minimum`` / ``maximum`` are inclusive; ``exclusive_minimum``
        rejects the bound itself. Timeouts and intervals use
        ``exclusive_minimum=0`` (a 0s timeout is never what the operator
        meant), knobs where zero means "disabled" use ``minimum=0``.
        Non-finite values (``nan``, ``inf``) are rejected regardless of
        the bounds.
        """
        return cls._get_number_env(
            key,
            default,
            float,
            minimum=minimum,
            exclusive_minimum=exclusive_minimum,
            maximum=maximum,
        )

    @classmethod
    def get_enum_env(
        cls,
        key: str,
        default: str,
        allowed: Sequence[str],
    ) -> str:
        """Return *key* lower-cased and constrained to *allowed*.

        *allowed* is expected to be lower-case; an unrecognised value logs
        a warning and yields *default*.
        """
        raw = cls.get_env_var(key, None)
        if raw is None:
            return default
        value = str(raw).strip().lower()
        if not value:
            return default
        if value not in allowed:
            logger.warning(
                "Invalid %s %r: must be one of %s — using default %r",
                key, raw, ", ".join(allowed), default,
            )
            return default
        return value

    @classmethod
    def _get_number_env(
        cls,
        key: str,
        default: _Number,
        parse: Callable[[Any], _Number],
        *,
        minimum: float | None = None,
        exclusive_minimum: float | None = None,
        maximum: float | None = None,
    ) -> _Number:
        raw = cls.get_env_var(key, None)
        if raw is None:
            return default
        if isinstance(raw, str):
            raw = raw.strip()
            if not raw:
                return default
        if isinstance(raw, bool):
            # ``bool`` is an ``int`` subclass, so a JSON ``true`` would
            # otherwise convert to 1 rather than being rejected the way the
            # local string "true" is.
            logger.warning(
                "Invalid %s %r: expected a number — using default %r",
                key, raw, default,
            )
            return default
        try:
            value = parse(raw)
        except (TypeError, ValueError, OverflowError):
            # OverflowError: a JSON literal too large for a float decodes to
            # ``inf`` (``1e400``), and ``int(inf)`` raises it rather than
            # ValueError — which would escape an import-time constant.
            logger.warning(
                "Invalid %s %r: not a valid %s — using default %r",
                key, raw, parse.__name__, default,
            )
            return default
        # ``float()`` happily accepts "nan" and "inf", and every bound
        # comparison against NaN is False — so an unchecked NaN would sail
        # past the range check and reach an ``asyncio.wait_for`` timeout or
        # a backoff computation. Neither is ever a meaningful setting.
        if isinstance(value, float) and not math.isfinite(value):
            logger.warning(
                "Invalid %s %r: not a finite number — using default %r",
                key, raw, default,
            )
            return default
        # A remote-config payload is JSON, so ``raw`` may already be a number
        # rather than a string: ``int(1.9)`` would truncate to 1 where the
        # local string "1.9" is rejected. An integral float still converts
        # cleanly (a configurator that serialises 5 as 5.0), so compare
        # instead of refusing every float.
        if isinstance(raw, (int, float)) and value != raw:
            logger.warning(
                "Invalid %s %r: not a whole number — using default %r",
                key, raw, default,
            )
            return default
        violation = _bound_violation(value, minimum, exclusive_minimum, maximum)
        if violation is not None:
            logger.warning(
                "Invalid %s %r: must be %s — using default %r",
                key, raw, violation, default,
            )
            return default
        return value

    @classmethod
    def _load_remote_config_if_needed(cls) -> None:
        remote_config_url = os.environ.get("REMOTE_CONFIG_URL", None)
        if remote_config_url is None:
            cls._remote_config_cache = {}
            return
        # Fast path: serve the cache without locking while it is still fresh.
        if time.time() - cls._cache_timestamp <= cls._CACHE_EXPIRATION_SECONDS:
            return
        if cls._cache_timestamp == 0:
            # Very first load: fetch synchronously (under the lock) so
            # startup reads see the remote values rather than defaults.
            with cls._lock:
                if cls._cache_timestamp == 0:
                    cls._refresh(remote_config_url)
            return
        # Stale-while-revalidate: callers get the (stale) cache immediately —
        # get_env_var runs inside async handlers, and a synchronous 5s fetch
        # under the lock would stall the event loop and serialize every
        # other caller behind it. A single daemon thread revalidates.
        with cls._lock:
            if cls._refresh_in_flight or (time.time() - cls._cache_timestamp <= cls._CACHE_EXPIRATION_SECONDS):
                return
            cls._refresh_in_flight = True
        threading.Thread(
            target=cls._background_refresh,
            args=(remote_config_url,),
            name="remote-config-refresh",
            daemon=True,
        ).start()

    @classmethod
    def _background_refresh(cls, remote_config_url: str) -> None:
        """Revalidate off the request path.

        The fetch runs **without** ``_lock`` held, and the lock is taken
        only to swap the finished payload in. Holding it across the network
        round-trip would mean any caller that reaches the stale-while-
        revalidate branch — which happens once the fetch outlives the cache
        TTL — blocks on the socket inside an async handler. That is the
        exact stall this whole code path exists to avoid.
        """
        try:
            payload = cls._fetch(remote_config_url)
            with cls._lock:
                cls._remote_config_cache = payload
                cls._cache_timestamp = time.time()
        finally:
            cls._refresh_in_flight = False

    @classmethod
    def _is_fetch_allowed(cls, remote_config_url: str) -> bool:
        """Return True when the SSRF guard permits fetching *remote_config_url*.

        Whatever answers gets to set most of this app's configuration,
        including security-relevant values: the match-report signing key,
        ``METRICS_TOKEN``, the ``MATCH_REPORT_PUBLIC`` gate, the webhook
        destination match state is POSTed to, and the ``OVERLAY_PUBLIC_URL``
        origin that widens the CSP ``frame-src``. So a config source that
        resolves onto the private network is refused by default, same
        posture as webhook delivery. Trusted-LAN deployments (a Compose
        sidecar, an intranet file server) opt back in with
        ``REMOTE_CONFIG_ALLOW_PRIVATE_IPS=true``.
        """
        if is_truthy(os.environ.get("REMOTE_CONFIG_ALLOW_PRIVATE_IPS", "")):
            return True
        try:
            safe, reason = is_target_safe(remote_config_url)
        except ValueError as exc:
            # ``urlparse`` rejects some malformed inputs outright (e.g. the
            # unterminated IPv6 literal ``http://[::1``). This runs outside
            # the fetch's ``except RequestException`` boundary, and
            # ``get_env_var`` is called during module import — so letting it
            # escape would abort startup over a typo instead of falling back
            # to the local environment.
            safe, reason = False, f"not a valid URL ({exc})"
        if not safe:
            logger.error(
                "Refusing to fetch remote config from %s: %s. Set "
                "REMOTE_CONFIG_ALLOW_PRIVATE_IPS=true to opt into "
                "private-network config sources.",
                redact_url(remote_config_url), reason,
            )
            return False
        return True

    @classmethod
    def _refresh(cls, remote_config_url: str) -> None:
        """Fetch and install the remote config. Callers hold ``_lock``.

        Only the very first (synchronous) load takes this path, where
        holding the lock across the fetch is the point: concurrent callers
        must wait for the real values rather than racing ahead on defaults.
        Revalidation goes through :meth:`_background_refresh` instead.
        """
        cls._cache_timestamp = time.time()
        cls._remote_config_cache = cls._fetch(remote_config_url)

    @classmethod
    def _fetch(cls, remote_config_url: str) -> dict[str, Any]:
        """Return the remote payload, or ``{}`` if it cannot be used.

        Performs network I/O, so it must never be called while holding
        ``_lock`` on the revalidation path — see :meth:`_background_refresh`.
        Every failure mode (refused target, redirect, HTTP error, malformed
        body) degrades to ``{}`` so the caller falls back to ``os.environ``.
        """
        if not cls._is_fetch_allowed(remote_config_url):
            return {}
        try:
            logger.info("Fetching remote config from %s", redact_url(remote_config_url))
            response = requests.get(
                remote_config_url,
                timeout=5,
                headers=outbound_trace_headers() or None,
                # Never follow redirects: the guard above only validated the
                # configured host, so a 30x to loopback / 169.254.169.254
                # would hand the whole environment to whoever controls the
                # redirect (cloud-metadata SSRF).
                allow_redirects=False,
            )
            logger.debug("Remote config response status: %s", response.status_code)
            if 300 <= response.status_code < 400:
                logger.error(
                    "Remote config %s answered %s: refusing to follow the "
                    "redirect — point REMOTE_CONFIG_URL at the final URL.",
                    redact_url(remote_config_url), response.status_code,
                )
                return {}
            response.raise_for_status()
            return cls._unwrap_remote_config(response.json())
        except (requests.exceptions.RequestException, json.JSONDecodeError):
            logger.exception("Error loading remote configuration")
            return {}

    @staticmethod
    def _unwrap_remote_config(payload: Any) -> dict[str, Any]:
        """Return the flat env-var mapping from a remote config payload.

        The remote config is expected to be a flat ``{KEY: value}`` object
        whose keys are env-var names. The companion configurator exports it
        wrapped in a ``{"configuration": {...}}`` envelope, so unwrap that
        single key transparently; otherwise the nested config keys (e.g.
        ``APP_TEAMS``) would never be found and the app would silently fall
        back to its defaults.

        Always returns a dict: a non-dict payload (a JSON list, string or
        bool the endpoint might serve) is dropped to ``{}`` so later
        ``cache.get(...)`` lookups can't raise ``AttributeError``.
        """
        if not isinstance(payload, dict):
            return {}
        if len(payload) == 1 and "configuration" in payload:
            inner = payload["configuration"]
            if isinstance(inner, dict):
                return inner
        return payload
