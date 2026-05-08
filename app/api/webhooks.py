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

from app.api import webhook_dead_letter
from app.constants import (
    WEBHOOK_RETRY_ATTEMPTS,
    WEBHOOK_RETRY_BASE_SECONDS,
    WEBHOOK_RETRY_MAX_SECONDS,
)
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
                self._deliver(target, body_bytes, event=event, oid=oid)
            else:
                executor.submit(
                    self._deliver, target, body_bytes,
                    event=event, oid=oid,
                )
        return queued

    @staticmethod
    def _sign(secret: str, body: bytes) -> str:
        digest = hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        return f"sha256={digest}"

    @staticmethod
    def _ssrf_check(target: WebhookTarget) -> bool:
        """Return True if *target* passes the SSRF allow-list.

        Mirrors the original guard in ``_deliver``: refuses URLs whose
        host resolves to a private/loopback/link-local/multicast/
        reserved IP unless the operator opted into private targets.
        """
        if _allow_private_targets():
            return True
        safe, reason = _is_target_safe(target.url)
        if not safe:
            logger.warning(
                "Webhook %s blocked by SSRF guard: %s. Set "
                "WEBHOOKS_ALLOW_PRIVATE_IPS=true to opt into "
                "private-network targets.",
                target.url, reason,
            )
            return False
        return True

    def _attempt_with_retries(
        self, target: WebhookTarget, body: bytes,
    ) -> tuple[bool, str]:
        """Try delivery with up to ``WEBHOOK_RETRY_ATTEMPTS`` retries.

        Retries on 5xx and ``requests.RequestException`` (timeouts,
        connect errors). 4xx is treated as a permanent client
        rejection — no retry, no dead-letter, just a warning.

        Backoff: ``WEBHOOK_RETRY_BASE_SECONDS * 2**(attempt-1)``,
        capped at ``WEBHOOK_RETRY_MAX_SECONDS``. Default is
        1 / 2 / 4 seconds between attempts (then capped at 8).

        Returns ``(success, last_error_string)``. ``last_error`` is
        empty when ``success`` is True or when the failure was a 4xx
        (the 4xx body is logged but not re-surfaced).
        """
        if not self._ssrf_check(target):
            # SSRF block is permanent: do not retry, do not DL, do not
            # leak the URL in the error string returned to the caller.
            return False, ""
        headers = {"Content-Type": "application/json"}
        if target.secret:
            headers["X-Webhook-Signature"] = self._sign(target.secret, body)
        last_err = ""
        total_attempts = WEBHOOK_RETRY_ATTEMPTS + 1
        for attempt in range(total_attempts):
            if attempt > 0:
                delay = min(
                    WEBHOOK_RETRY_BASE_SECONDS * (2 ** (attempt - 1)),
                    WEBHOOK_RETRY_MAX_SECONDS,
                )
                time.sleep(delay)
            try:
                response = requests.post(
                    target.url,
                    data=body,
                    headers=headers,
                    timeout=target.timeout_s,
                )
            except requests.RequestException as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "Webhook %s failed on attempt %d/%d: %s",
                    target.url, attempt + 1, total_attempts, exc,
                )
                continue
            if response.status_code < 400:
                return True, ""
            if 400 <= response.status_code < 500:
                # Client-side rejection: not retriable, not dead-letter
                # material — the receiver will keep saying no.
                logger.warning(
                    "Webhook %s returned %d (not retried)",
                    target.url, response.status_code,
                )
                return False, ""
            last_err = f"HTTP {response.status_code}"
            logger.warning(
                "Webhook %s returned %d on attempt %d/%d",
                target.url, response.status_code, attempt + 1, total_attempts,
            )
        return False, last_err

    def _deliver(
        self,
        target: WebhookTarget,
        body: bytes,
        event: str = "",
        oid: str = "",
    ) -> None:
        """Deliver *body* with retries; dead-letter on terminal failure.

        Called from the dispatch thread pool. Successes return
        silently; permanent 4xx / SSRF rejections also return silently
        (their warnings live in the logger). Only retriable failures
        that exhaust ``WEBHOOK_RETRY_ATTEMPTS`` end up in the
        dead-letter file for operator-initiated replay.
        """
        ok, last_err = self._attempt_with_retries(target, body)
        if ok or not last_err:
            return
        try:
            body_str = body.decode("utf-8")
        except UnicodeDecodeError:
            body_str = body.decode("utf-8", errors="replace")
        webhook_dead_letter.append({
            "url": target.url,
            "event": event,
            "oid": oid,
            "body": body_str,
            "last_error": last_err,
            "attempts": WEBHOOK_RETRY_ATTEMPTS + 1,
        })

    def replay_records(
        self, records: list[dict],
    ) -> tuple[int, list[dict], int]:
        """Re-attempt *records* against the current target config.

        Used by the admin replay endpoint. Each record is matched to a
        configured ``WebhookTarget`` by URL; missing matches mean the
        operator changed the config since the entry landed in the DL,
        and those records are kept in the DL for manual triage.

        Returns ``(succeeded, still_failing, skipped_unknown_url)``:

        * ``succeeded`` — count of records re-delivered cleanly.
        * ``still_failing`` — records to write back to the DL (failed
          deliveries plus skipped ones, so the operator does not lose
          them on replay).
        * ``skipped_unknown_url`` — count of records whose URL no
          longer matches any configured target. They're included in
          ``still_failing`` so the operator can rewrite their config
          and retry.
        """
        targets = self._ensure_loaded()
        targets_by_url = {t.url: t for t in targets}
        succeeded = 0
        still_failing: list[dict] = []
        skipped = 0
        for r in records:
            target = targets_by_url.get(r.get("url"))
            if target is None:
                skipped += 1
                still_failing.append(r)
                continue
            body_str = r.get("body") or ""
            body = body_str.encode("utf-8")
            ok, last_err = self._attempt_with_retries(target, body)
            if ok:
                succeeded += 1
                continue
            updated = dict(r)
            updated["last_error"] = last_err or r.get("last_error", "")
            updated["attempts"] = (
                int(r.get("attempts", 0)) + WEBHOOK_RETRY_ATTEMPTS + 1
            )
            still_failing.append(updated)
        return succeeded, still_failing, skipped


# Module-level singleton — mirrors the overlay/store/hub pattern.
webhook_dispatcher = WebhookDispatcher()
