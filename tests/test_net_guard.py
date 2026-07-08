"""Coverage for ``app.net_guard.fetch_guarded`` — the SSRF-guarded,
size-capped downloader behind the icon batch import.

The address-classification primitives (``is_private_ip`` /
``is_target_safe``) are covered in ``test_low_priority_hardening.py``;
here we exercise the redirect re-validation loop and the byte caps with
``requests.get`` stubbed out (no real network).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app import net_guard
from app.net_guard import GuardedFetchError, fetch_guarded


class FakeResponse:
    def __init__(self, *, status=200, headers=None, chunks=(b"data",), redirect=False):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks
        self.is_redirect = redirect

    def iter_content(self, chunk_size):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_rejects_private_literal_before_any_request():
    with patch.object(net_guard.requests, "get") as get, pytest.raises(GuardedFetchError, match="private/loopback"):
        fetch_guarded("http://127.0.0.1/x.png", max_bytes=1024, timeout=1)
    get.assert_not_called()


def test_fetch_rejects_non_http_scheme():
    with pytest.raises(GuardedFetchError, match="scheme"):
        fetch_guarded("file:///etc/passwd", max_bytes=1024, timeout=1)


def test_fetch_returns_body_on_200():
    with patch.object(
        net_guard.requests, "get", return_value=FakeResponse(chunks=(b"ab", b"cd")),
    ) as get:
        body = fetch_guarded("http://93.184.216.34/x.png", max_bytes=1024, timeout=1)
    assert body == b"abcd"
    # allow_redirects must stay False — redirects are validated manually.
    assert get.call_args.kwargs["allow_redirects"] is False
    assert get.call_args.kwargs["stream"] is True


def test_fetch_revalidates_every_redirect_hop():
    """A public host 302-ing to a private IP must be refused mid-flight."""
    hops = [
        FakeResponse(redirect=True, headers={"Location": "http://127.0.0.1/steal"}),
    ]
    with (
        patch.object(net_guard.requests, "get", side_effect=hops),
        pytest.raises(GuardedFetchError, match="private/loopback"),
    ):
        fetch_guarded("http://93.184.216.34/x.png", max_bytes=1024, timeout=1)


def test_fetch_follows_safe_redirects_to_completion():
    hops = [
        FakeResponse(redirect=True, headers={"Location": "http://93.184.216.35/y.png"}),
        FakeResponse(chunks=(b"ok",)),
    ]
    with patch.object(net_guard.requests, "get", side_effect=hops):
        assert fetch_guarded("http://93.184.216.34/x.png", max_bytes=1024, timeout=1) == b"ok"


def test_fetch_gives_up_after_max_redirects():
    hop = FakeResponse(redirect=True, headers={"Location": "http://93.184.216.34/loop"})
    with (
        patch.object(net_guard.requests, "get", return_value=hop),
        pytest.raises(GuardedFetchError, match="too many redirects"),
    ):
        fetch_guarded("http://93.184.216.34/x.png", max_bytes=1024, timeout=1, max_redirects=2)


def test_fetch_rejects_declared_oversize_without_reading():
    resp = FakeResponse(headers={"Content-Length": "999999"})
    with patch.object(net_guard.requests, "get", return_value=resp), pytest.raises(GuardedFetchError, match="larger than"):
        fetch_guarded("http://93.184.216.34/x.png", max_bytes=1024, timeout=1)


def test_fetch_caps_streamed_bytes_even_when_length_lies():
    resp = FakeResponse(headers={"Content-Length": "10"}, chunks=(b"x" * 600, b"x" * 600))
    with patch.object(net_guard.requests, "get", return_value=resp), pytest.raises(GuardedFetchError, match="larger than"):
        fetch_guarded("http://93.184.216.34/x.png", max_bytes=1024, timeout=1)


def test_fetch_surfaces_http_errors():
    with (
        patch.object(net_guard.requests, "get", return_value=FakeResponse(status=404)),
        pytest.raises(GuardedFetchError, match="HTTP 404"),
    ):
        fetch_guarded("http://93.184.216.34/x.png", max_bytes=1024, timeout=1)


def test_fetch_wraps_mid_body_stream_failures():
    """stream=True defers the body: a reset during iter_content must land in
    GuardedFetchError, not escape as a raw RequestException (PR #392 review)."""

    class BrokenBody(FakeResponse):
        def iter_content(self, chunk_size):
            yield b"partial"
            raise net_guard.requests.ConnectionError("reset mid-body")

    with (
        patch.object(net_guard.requests, "get", return_value=BrokenBody()),
        pytest.raises(GuardedFetchError, match="download failed"),
    ):
        fetch_guarded("http://93.184.216.34/x.png", max_bytes=4096, timeout=1)


def test_fetch_wraps_request_exceptions():
    with patch.object(
        net_guard.requests, "get",
        side_effect=net_guard.requests.ConnectionError("boom"),
    ), pytest.raises(GuardedFetchError, match="download failed"):
        fetch_guarded("http://93.184.216.34/x.png", max_bytes=1024, timeout=1)


# ---- DNS-rebinding pin ------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_environ_proxies(monkeypatch):
    """Neutralize HTTP(S)_PROXY from the test environment: with an egress
    proxy configured, fetch_guarded deliberately skips IP pinning (the
    proxy resolves DNS itself), which is not the path under test here."""
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)


def test_environ_proxy_bypasses_pinning_but_still_validates(monkeypatch):
    """With an egress proxy, the original URL goes to the proxy (it does
    the resolution) — but the guard still refuses private targets."""
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.local:3128")
    monkeypatch.setattr(
        net_guard, "resolve_target_addresses", lambda host: ["93.184.216.34"],
    )
    with patch.object(
        net_guard.requests, "get", return_value=FakeResponse(chunks=(b"ok",)),
    ) as get:
        fetch_guarded("http://cdn.example.com/logo.png", max_bytes=64, timeout=1)
    assert get.call_args.args[0] == "http://cdn.example.com/logo.png"

    monkeypatch.setattr(
        net_guard, "resolve_target_addresses", lambda host: ["127.0.0.1"],
    )
    with pytest.raises(GuardedFetchError, match="private/loopback"):
        fetch_guarded("http://evil.example.com/x.png", max_bytes=64, timeout=1)


def test_hostname_fetch_pins_the_validated_ip(monkeypatch):
    """The request must target the IP the guard validated (URL rewrite +
    Host header), never re-resolve the hostname."""
    monkeypatch.setattr(
        net_guard, "resolve_target_addresses", lambda host: ["93.184.216.34"],
    )
    with patch.object(
        net_guard.requests, "get", return_value=FakeResponse(chunks=(b"ok",)),
    ) as get:
        body = fetch_guarded("http://cdn.example.com/logo.png", max_bytes=64, timeout=1)
    assert body == b"ok"
    assert get.call_args.args[0] == "http://93.184.216.34/logo.png"
    assert get.call_args.kwargs["headers"]["Host"] == "cdn.example.com"


def test_hostname_fetch_preserves_explicit_port(monkeypatch):
    monkeypatch.setattr(
        net_guard, "resolve_target_addresses", lambda host: ["93.184.216.34"],
    )
    with patch.object(
        net_guard.requests, "get", return_value=FakeResponse(chunks=(b"ok",)),
    ) as get:
        fetch_guarded("http://cdn.example.com:8080/a.png", max_bytes=64, timeout=1)
    assert get.call_args.args[0] == "http://93.184.216.34:8080/a.png"
    assert get.call_args.kwargs["headers"]["Host"] == "cdn.example.com:8080"


def test_hostname_resolving_to_private_ip_is_refused(monkeypatch):
    """The rebinding payoff address never gets a connection."""
    monkeypatch.setattr(
        net_guard, "resolve_target_addresses",
        lambda host: ["93.184.216.34", "169.254.169.254"],
    )
    with patch.object(net_guard.requests, "get") as get, pytest.raises(
        GuardedFetchError, match="private/loopback IP",
    ):
        fetch_guarded("http://rebind.attacker.io/x.png", max_bytes=64, timeout=1)
    get.assert_not_called()


def test_unresolvable_host_is_refused_not_passed_through(monkeypatch):
    """fetch_guarded (user URLs) must NOT hand an unpinnable resolution to
    requests — unlike the webhook is_target_safe posture."""
    monkeypatch.setattr(net_guard, "resolve_target_addresses", lambda host: None)
    with patch.object(net_guard.requests, "get") as get, pytest.raises(
        GuardedFetchError, match="could not resolve",
    ):
        fetch_guarded("http://gone.example.com/x.png", max_bytes=64, timeout=1)
    get.assert_not_called()


def test_https_hostname_uses_pinned_tls_adapter(monkeypatch):
    """HTTPS goes through a Session with the pinned-TLS adapter so SNI and
    certificate verification still use the original hostname."""
    monkeypatch.setattr(
        net_guard, "resolve_target_addresses", lambda host: ["93.184.216.34"],
    )
    captured = {}

    class FakeSession:
        def mount(self, prefix, adapter):
            captured["prefix"] = prefix
            captured["adapter"] = adapter

        def get(self, url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs.get("headers")
            return FakeResponse(chunks=(b"ok",))

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(net_guard.requests, "Session", FakeSession)
    body = fetch_guarded("https://cdn.example.com/logo.png", max_bytes=64, timeout=1)
    assert body == b"ok"
    assert captured["url"] == "https://93.184.216.34/logo.png"
    assert captured["headers"]["Host"] == "cdn.example.com"
    assert isinstance(captured["adapter"], net_guard._PinnedTLSAdapter)
    assert captured["adapter"]._hostname == "cdn.example.com"
    assert captured["closed"] is True


def test_pinned_tls_adapter_sets_urllib3_pool_kwargs():
    """The adapter must feed server_hostname/assert_hostname into the pool
    (urllib3 v2 kwargs) — that is what keeps SNI + cert verification on
    the original name while TCP goes to the pinned IP."""
    adapter = net_guard._PinnedTLSAdapter("cdn.example.com")
    pool_kwargs = adapter.poolmanager.connection_pool_kw
    assert pool_kwargs["server_hostname"] == "cdn.example.com"
    assert pool_kwargs["assert_hostname"] == "cdn.example.com"


def test_redirect_hops_are_each_pinned(monkeypatch):
    """Every hop re-resolves and re-pins; a hop to a hostname resolving
    private is refused."""
    monkeypatch.setattr(
        net_guard, "resolve_target_addresses",
        lambda host: {"a.example.com": ["93.184.216.34"],
                      "evil.example.com": ["127.0.0.1"]}[host],
    )
    hops = [
        FakeResponse(redirect=True, headers={"Location": "http://evil.example.com/l"}),
    ]
    with patch.object(net_guard.requests, "get", side_effect=hops), pytest.raises(
        GuardedFetchError, match="private/loopback IP",
    ):
        fetch_guarded("http://a.example.com/x.png", max_bytes=64, timeout=1)


def test_ipv6_pin_is_bracketed(monkeypatch):
    monkeypatch.setattr(
        net_guard, "resolve_target_addresses", lambda host: ["2606:2800:220:1::1"],
    )
    with patch.object(
        net_guard.requests, "get", return_value=FakeResponse(chunks=(b"ok",)),
    ) as get:
        fetch_guarded("http://v6.example.com/x.png", max_bytes=64, timeout=1)
    assert get.call_args.args[0] == "http://[2606:2800:220:1::1]/x.png"
