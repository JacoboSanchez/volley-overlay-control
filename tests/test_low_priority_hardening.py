"""Coverage for the L-1 / L-2 / L-6 hardening additions.

* L-1 — :mod:`app.api.middleware.errors` enriches its log record with
  the request id, request method, path, and exception class.
* L-2 — every 401 response from the auth ladders carries
  ``WWW-Authenticate: Bearer realm="..."`` per RFC 7235 §4.1.
* L-6 — :mod:`app.api.webhooks` refuses to call URLs that resolve
  to private / loopback / link-local IPs unless the operator opts
  in via ``WEBHOOKS_ALLOW_PRIVATE_IPS=true``.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import api_router
from app.api.middleware.errors import ExceptionLoggingMiddleware
from app.api.middleware.logging import RequestContextMiddleware
from app.api.webhooks import WebhookDispatcher, WebhookTarget
from app.net_guard import is_private_ip as _is_private_ip
from app.net_guard import is_target_safe as _is_target_safe

# ---------------------------------------------------------------------------
# L-1 — exception logging enrichment
# ---------------------------------------------------------------------------


def test_exception_log_includes_method_path_class_and_request_id(caplog):
    """An unhandled exception logs ``method``, ``path``, ``request_id``,
    and the exception class — both in the message text and as
    structured ``extra`` fields.
    """
    app = FastAPI()

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    # Outermost-first: RequestContext sets the contextvars before the
    # exception logger reads them.
    app.add_middleware(ExceptionLoggingMiddleware)
    app.add_middleware(RequestContextMiddleware)

    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="app.api.middleware.errors"):
        res = client.get(
            "/boom", headers={"X-Request-ID": "test-rid-42"},
        )
    assert res.status_code == 500
    error_records = [
        r for r in caplog.records
        if r.name == "app.api.middleware.errors"
    ]
    assert error_records, "expected an error log record"
    rec = error_records[-1]
    msg = rec.getMessage()
    assert "GET" in msg
    assert "/boom" in msg
    assert "RuntimeError" in msg
    assert "test-rid-42" in msg
    # And the same fields as structured ``extra`` so JSON formatters
    # surface them as queryable keys, not just inside the free-form
    # message.
    assert getattr(rec, "exc_class", None) == "RuntimeError"
    assert getattr(rec, "http_method", None) == "GET"
    assert getattr(rec, "http_path", None) == "/boom"


# ---------------------------------------------------------------------------
# L-2 — WWW-Authenticate on 401
# ---------------------------------------------------------------------------


def test_scoreboard_401_carries_cookie_challenge():
    """An unauthenticated scoreboard request gets a 401 with a
    ``WWW-Authenticate`` challenge (now the cookie-session scheme)."""
    app = FastAPI()
    app.include_router(api_router)
    client = TestClient(app)

    res = client.get("/api/v1/state?oid=test_overlay")
    assert res.status_code == 401
    assert res.headers.get("www-authenticate") == "Cookie"


# NOTE: the legacy OVERLAY_MANAGER_PASSWORD admin Bearer realm was removed
# in the multi-user refactor — admin access is now cookie + role gated (403),
# not a Bearer 401. The overlay-server realm below is the only remaining
# Bearer ladder.


# ---------------------------------------------------------------------------
# L-6 — webhook SSRF guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "127.255.255.255",   # loopback
    "::1",                              # loopback v6
    "10.0.0.1", "10.255.255.254",       # RFC1918
    "172.16.0.1", "172.31.255.254",
    "192.168.0.1",
    "169.254.169.254",                  # link-local (cloud metadata)
    "224.0.0.1",                        # multicast
    "0.0.0.0",                          # unspecified
    "fc00::1",                          # IPv6 ULA
    "fe80::1",                          # IPv6 link-local
    "::ffff:127.0.0.1",                 # IPv4-mapped loopback (SSRF bypass)
    "::ffff:169.254.169.254",           # IPv4-mapped cloud metadata
    "::ffff:10.0.0.5",                  # IPv4-mapped RFC1918
    "::ffff:192.168.1.1",               # IPv4-mapped RFC1918
    "not-an-ip",                        # non-parseable → suspicious
])
def test_is_private_ip_classifies_correctly(ip):
    assert _is_private_ip(ip) is True


@pytest.mark.parametrize("ip", [
    "8.8.8.8",            # Google DNS
    "1.1.1.1",            # Cloudflare DNS
    "9.9.9.9",            # Quad9 DNS
    "2606:4700::1111",    # public IPv6 (Cloudflare)
])
def test_is_private_ip_allows_public(ip):
    assert _is_private_ip(ip) is False


def test_is_private_ip_blocks_documentation_ranges():
    """RFC 5737 / RFC 3849 documentation ranges shouldn't be reachable
    in production either — ``ipaddress`` flags them as reserved and
    our guard rolls them in with private/loopback rejections.
    """
    for ip in ("192.0.2.1", "198.51.100.1", "203.0.113.1", "2001:db8::1"):
        assert _is_private_ip(ip) is True


def test_is_target_safe_rejects_loopback_literal():
    safe, reason = _is_target_safe("http://127.0.0.1/admin")
    assert safe is False
    assert "loopback" in reason.lower() or "private" in reason.lower()


def test_is_target_safe_rejects_cloud_metadata_literal():
    safe, _reason = _is_target_safe("http://169.254.169.254/latest/meta-data/")
    assert safe is False


def test_is_target_safe_accepts_public_literal():
    safe, reason = _is_target_safe("http://1.1.1.1/")
    assert safe is True
    assert reason == ""


def test_is_target_safe_rejects_non_http_scheme():
    safe, reason = _is_target_safe("file:///etc/passwd")
    assert safe is False
    assert "scheme" in reason.lower()


def test_is_target_safe_rejects_missing_host():
    safe, _reason = _is_target_safe("http:///")
    assert safe is False


def test_is_target_safe_passes_through_dns_failure():
    """A non-resolving public hostname must pass through the guard so
    ``requests.post`` can surface the actual network error rather
    than this guard masking it as an SSRF rejection."""
    safe, _reason = _is_target_safe("http://this-does-not-resolve.invalid/")
    assert safe is True


def test_webhook_delivery_blocks_private_ip(monkeypatch):
    """End-to-end: a webhook target on 127.0.0.1 must not be POSTed."""
    monkeypatch.setenv(
        "WEBHOOKS_URL", "http://127.0.0.1:9/should-not-be-called",
    )
    monkeypatch.delenv("WEBHOOKS_ALLOW_PRIVATE_IPS", raising=False)
    d = WebhookDispatcher()
    with patch("app.api.webhooks.requests.post") as post:
        post.return_value.status_code = 200
        d.dispatch("set_end", "oid", {})
        if d._executor is not None:
            d._executor.shutdown(wait=True)
            d._executor = None
        post.assert_not_called()


def test_webhook_delivery_allows_private_ip_when_opted_in(monkeypatch):
    """``WEBHOOKS_ALLOW_PRIVATE_IPS=true`` lets internal targets through."""
    monkeypatch.setenv(
        "WEBHOOKS_URL", "http://127.0.0.1:9/internal",
    )
    monkeypatch.setenv("WEBHOOKS_ALLOW_PRIVATE_IPS", "true")
    d = WebhookDispatcher()
    with patch("app.api.webhooks.requests.post") as post:
        post.return_value.status_code = 200
        d.dispatch("set_end", "oid", {})
        if d._executor is not None:
            d._executor.shutdown(wait=True)
            d._executor = None
        post.assert_called_once()


def test_webhook_blocked_emits_warning(monkeypatch, caplog):
    monkeypatch.setenv(
        "WEBHOOKS_URL", "http://127.0.0.1:9/blocked",
    )
    monkeypatch.delenv("WEBHOOKS_ALLOW_PRIVATE_IPS", raising=False)
    d = WebhookDispatcher()
    with caplog.at_level(logging.WARNING, logger="app.api.webhooks"), patch("app.api.webhooks.requests.post"):
        d.dispatch("set_end", "oid", {})
        if d._executor is not None:
            d._executor.shutdown(wait=True)
            d._executor = None
    assert any(
        "blocked by SSRF guard" in r.getMessage()
        for r in caplog.records
    )


def test_webhook_target_can_be_constructed_with_any_url():
    """Constructing a ``WebhookTarget`` does not run the SSRF guard —
    the guard fires at delivery time only. This keeps config-time
    parsing cheap and lets unit tests exercise the dispatcher with
    URLs that need DNS in the test sandbox.
    """
    t = WebhookTarget("http://localhost:9/x")
    assert t.url == "http://localhost:9/x"
