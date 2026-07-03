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
