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
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, Optional

import requests

from app.env_vars_manager import EnvVarsManager

logger = logging.getLogger(__name__)


KNOWN_EVENTS = frozenset({"set_end", "match_end", "timeout", "serve_change"})

_DEFAULT_TIMEOUT_S = 5.0
_MAX_WORKERS = 4


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


def _normalise_events(value) -> Optional[set[str]]:
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

    __slots__ = ("url", "secret", "events", "timeout_s")

    def __init__(self, url: str, secret: Optional[str] = None,
                 events: Optional[Iterable[str]] = None,
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
        self._targets: Optional[list[WebhookTarget]] = None
        self._executor: Optional[ThreadPoolExecutor] = None

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
