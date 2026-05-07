"""Outbound webhooks fired on game events.

Configured via environment variables:

- ``WEBHOOKS_URL`` (string)        — single endpoint that receives every
  enabled event. Pairs with ``WEBHOOKS_SECRET``.
- ``WEBHOOKS_SECRET`` (string)     — shared secret used to sign single-URL
  payloads with HMAC-SHA256.
- ``WEBHOOKS_JSON`` (JSON list)    — multiple endpoints, e.g.::

      [
        {"url": "https://hooks.example.com/scoreboard",
         "secret": "abc123",
         "events": ["set_end", "match_end"],
         "timeout_s": 5}
      ]

  ``WEBHOOKS_JSON`` takes precedence over ``WEBHOOKS_URL`` when both
  are defined.
- ``WEBHOOKS_EVENTS`` (CSV)        — restricts the *single-URL* form to a
  comma-separated subset of events. Defaults to all events.

Recognised events: ``set_end``, ``match_end``, ``timeout``,
``serve_change``. The signature header is ``X-Webhook-Signature:
sha256=<hex>`` computed over the raw JSON body. Delivery is
fire-and-forget on a small thread pool with a per-target timeout —
failures are logged but never propagate.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests

from app.env_vars_manager import EnvVarsManager

logger = logging.getLogger(__name__)


KNOWN_EVENTS = frozenset({"set_end", "match_end", "timeout", "serve_change"})

_DEFAULT_TIMEOUT_S = 5.0
_MAX_WORKERS = 4

_TRUTHY = ("1", "true", "t", "yes", "on")


def _allow_private_targets() -> bool:
    """Return True iff the operator opted into private-IP webhook targets.

    The default posture is fail-closed: a webhook URL whose host
    resolves to a private / loopback / link-local / multicast /
    reserved IP is dropped before the HTTP request fires. This blocks
    classic SSRF (``http://localhost/admin``, ``http://169.254.169.254``
    cloud metadata, ``http://10.0.0.5/``) without operator effort.

    Trusted-LAN deployments that legitimately need to call internal
    webhooks (a Home Assistant bridge on the same network, an
    on-premises Slack relay) set ``WEBHOOKS_ALLOW_PRIVATE_IPS=true``
    to opt out.
    """
    raw = EnvVarsManager.get_env_var("WEBHOOKS_ALLOW_PRIVATE_IPS", "false")
    return str(raw).strip().lower() in _TRUTHY


def _is_private_ip(ip_str: str) -> bool:
    """Return True iff *ip_str* is in any IP range we refuse to call."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        # Anything that isn't a parseable IP literal is suspicious.
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_target_addresses(host: str) -> list[str] | None:
    """Return every IP the *host* resolves to, or ``None`` on failure.

    The resolution is intentionally fresh on every delivery so a CDN
    that swaps IPs doesn't accumulate stale entries. ``None`` (a
    DNS failure) is distinct from ``[]`` (resolution succeeded but
    yielded no addresses, which would be unusual): the caller passes
    through on ``None`` so a temporarily unreachable real domain
    isn't mistaken for a malicious one — the actual ``requests.post``
    call will surface the network error a moment later.
    """
    try:
        addrinfo = socket.getaddrinfo(
            host, None, type=socket.SOCK_STREAM,
        )
    except (socket.gaierror, UnicodeError):
        return None
    # Dedupe: ``getaddrinfo`` returns one entry per (family, socktype,
    # proto) tuple, so the same IP literal can appear multiple times
    # for a host that supports several socket flavours. The caller
    # only cares about the unique address set.
    return list({sockaddr[0] for _, _, _, _, sockaddr in addrinfo})


def _is_target_safe(url: str) -> tuple[bool, str]:
    """Return ``(safe, reason)`` for the given webhook *url*.

    The ``reason`` string is empty when ``safe`` is True; otherwise
    it explains the rejection so the operator can debug from log
    output. The function only refuses targets whose host resolves
    to a positively-private IP — DNS failures pass through so
    flaky resolvers don't silently break legitimate webhook
    deliveries.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"scheme {parsed.scheme!r} not allowed (use http/https)"
    host = parsed.hostname
    if not host:
        return False, "URL has no hostname"
    # If the hostname is a literal IP, classify it directly.
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        if _is_private_ip(str(literal_ip)):
            return False, f"host literal {host} is private/loopback"
        return True, ""
    addresses = _resolve_target_addresses(host)
    if addresses is None:
        # DNS failure — let ``requests.post`` surface the error.
        return True, ""
    for addr in addresses:
        if _is_private_ip(addr):
            return False, f"host resolves to private/loopback IP {addr}"
    return True, ""


def _safe_json_list(raw: str) -> list[dict]:
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        logger.warning("WEBHOOKS_JSON is not valid JSON: %s", exc)
        return []
    if not isinstance(parsed, list):
        logger.warning("WEBHOOKS_JSON must be a list of objects")
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _normalise_events(value) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        items = [v.strip() for v in value.split(",") if v.strip()]
    elif isinstance(value, Iterable):
        items = [str(v).strip() for v in value if str(v).strip()]
    else:
        return None
    filtered = {item for item in items if item in KNOWN_EVENTS}
    return filtered or None


class WebhookTarget:
    """A single configured endpoint."""

    __slots__ = ("events", "secret", "timeout_s", "url")

    def __init__(self, url: str, secret: str | None = None,
                 events: Iterable[str] | None = None,
                 timeout_s: float = _DEFAULT_TIMEOUT_S):
        self.url = url
        self.secret = secret or None
        self.events = _normalise_events(events)
        try:
            self.timeout_s = float(timeout_s)
        except (TypeError, ValueError):
            self.timeout_s = _DEFAULT_TIMEOUT_S

    def accepts(self, event: str) -> bool:
        return self.events is None or event in self.events


class WebhookDispatcher:
    """Reads env-var config on first use and dispatches events.

    The instance caches its target list. Tests can call ``reload`` to
    pick up monkey-patched env vars between cases.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._targets: list[WebhookTarget] | None = None
        self._executor: ThreadPoolExecutor | None = None

    # -- configuration ---------------------------------------------------

    def _load_targets_locked(self) -> list[WebhookTarget]:
        targets: list[WebhookTarget] = []

        raw_json = EnvVarsManager.get_env_var("WEBHOOKS_JSON", None)
        if raw_json:
            for item in _safe_json_list(raw_json):
                url = item.get("url")
                if not isinstance(url, str) or not url:
                    continue
                targets.append(WebhookTarget(
                    url=url,
                    secret=item.get("secret"),
                    events=item.get("events"),
                    timeout_s=item.get("timeout_s", _DEFAULT_TIMEOUT_S),
                ))
            if targets:
                return targets

        url = EnvVarsManager.get_env_var("WEBHOOKS_URL", None)
        if isinstance(url, str) and url:
            targets.append(WebhookTarget(
                url=url,
                secret=EnvVarsManager.get_env_var("WEBHOOKS_SECRET", None),
                events=EnvVarsManager.get_env_var("WEBHOOKS_EVENTS", None),
                timeout_s=EnvVarsManager.get_env_var(
                    "WEBHOOKS_TIMEOUT_S", _DEFAULT_TIMEOUT_S),
            ))
        return targets

    def _ensure_loaded(self) -> list[WebhookTarget]:
        if self._targets is not None:
            return self._targets
        with self._lock:
            if self._targets is None:
                self._targets = self._load_targets_locked()
                if self._targets and self._executor is None:
                    self._executor = ThreadPoolExecutor(
                        max_workers=_MAX_WORKERS,
                        thread_name_prefix="webhooks",
                    )
        return self._targets

    def reload(self) -> None:
        """Drop cached config so the next dispatch re-reads env vars."""
        with self._lock:
            self._targets = None

    def shutdown(self) -> None:
        with self._lock:
            executor = self._executor
            self._executor = None
            self._targets = None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)

    # -- dispatch --------------------------------------------------------

    def dispatch(self, event: str, oid: str, payload: dict) -> int:
        """Send *payload* to every target subscribed to *event*.

        Returns the number of targets the event was queued for. Network
        I/O happens on a thread pool — this call returns immediately.
        """
        if event not in KNOWN_EVENTS:
            logger.debug("Ignoring unknown webhook event %r", event)
            return 0
        targets = self._ensure_loaded()
        if not targets:
            return 0

        body = {
            "event": event,
            "oid": oid,
            "ts": time.time(),
            **payload,
        }
        body_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")

        executor = self._executor
        queued = 0
        for target in targets:
            if not target.accepts(event):
                continue
            queued += 1
            if executor is None:
                # Synchronous fallback (used by tests when the executor
                # is mocked away). Keeps semantics identical.
                self._deliver(target, body_bytes)
            else:
                executor.submit(self._deliver, target, body_bytes)
        return queued

    @staticmethod
    def _sign(secret: str, body: bytes) -> str:
        digest = hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        return f"sha256={digest}"

    def _deliver(self, target: WebhookTarget, body: bytes) -> None:
        # SSRF guard: refuse to call URLs that resolve to private,
        # loopback, link-local, or otherwise non-public IPs unless
        # the operator explicitly opted in. Resolution happens here
        # rather than at config time so a target whose DNS rotates
        # between deliveries is still vetted on every send. This
        # does not fully mitigate DNS rebinding (the IP at delivery
        # could differ from the one ``requests.post`` ultimately
        # connects to), but it stops the most common foot-guns:
        # accidental ``http://localhost/...`` typos and cloud
        # metadata endpoints (``http://169.254.169.254``).
        if not _allow_private_targets():
            safe, reason = _is_target_safe(target.url)
            if not safe:
                logger.warning(
                    "Webhook %s blocked by SSRF guard: %s. Set "
                    "WEBHOOKS_ALLOW_PRIVATE_IPS=true to opt into "
                    "private-network targets.",
                    target.url, reason,
                )
                return

        headers = {"Content-Type": "application/json"}
        if target.secret:
            headers["X-Webhook-Signature"] = self._sign(target.secret, body)
        try:
            response = requests.post(
                target.url,
                data=body,
                headers=headers,
                timeout=target.timeout_s,
            )
            if response.status_code >= 400:
                logger.warning(
                    "Webhook %s returned %s",
                    target.url, response.status_code,
                )
        except requests.RequestException as exc:
            logger.warning("Webhook %s failed: %s", target.url, exc)


# Module-level singleton — mirrors the overlay/store/hub pattern.
webhook_dispatcher = WebhookDispatcher()
