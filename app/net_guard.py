"""SSRF guard for outbound HTTP requests triggered by user-supplied URLs.

Shared by webhook delivery (``app/api/webhooks.py``) and the icon
batch-import download path. The posture is fail-closed: a URL whose host
resolves to a private / loopback / link-local / multicast / reserved IP
is refused before any HTTP request fires, blocking classic SSRF
(``http://localhost/admin``, ``http://169.254.169.254`` cloud metadata,
``http://10.0.0.5/``).

DNS failures deliberately pass through: a temporarily unreachable real
domain must not be mistaken for a malicious one — the actual HTTP call
surfaces the network error a moment later. The check-then-connect gap
(DNS rebinding) is an accepted risk, matching the webhook delivery
posture; callers mitigate redirects by re-validating every hop
(``allow_redirects=False`` + manual loop) instead of following blindly.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests


class GuardedFetchError(ValueError):
    """A guarded download failed for a caller-reportable reason."""


def is_private_ip(ip_str: str) -> bool:
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


def resolve_target_addresses(host: str) -> list[str] | None:
    """Return every IP the *host* resolves to, or ``None`` on failure.

    The resolution is intentionally fresh on every call so a CDN
    that swaps IPs doesn't accumulate stale entries. ``None`` (a
    DNS failure) is distinct from ``[]`` (resolution succeeded but
    yielded no addresses, which would be unusual): the caller passes
    through on ``None`` so a temporarily unreachable real domain
    isn't mistaken for a malicious one — the actual HTTP request
    will surface the network error a moment later.
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
    # only cares about the unique address set. ``sockaddr[0]`` is typed
    # as a union (IPv4 vs IPv6 record shapes); narrow to ``str`` so the
    # SSRF allowlist comparison never sees a non-string slip through.
    addresses: set[str] = set()
    for _, _, _, _, sockaddr in addrinfo:
        addr = sockaddr[0]
        if isinstance(addr, str):
            addresses.add(addr)
    return list(addresses)


def is_target_safe(url: str) -> tuple[bool, str]:
    """Return ``(safe, reason)`` for the given outbound *url*.

    The ``reason`` string is empty when ``safe`` is True; otherwise
    it explains the rejection so the operator can debug from log
    output. The function only refuses targets whose host resolves
    to a positively-private IP — DNS failures pass through so
    flaky resolvers don't silently break legitimate deliveries.
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
        if is_private_ip(str(literal_ip)):
            return False, f"host literal {host} is private/loopback"
        return True, ""
    addresses = resolve_target_addresses(host)
    if addresses is None:
        # DNS failure — let the HTTP client surface the error.
        return True, ""
    for addr in addresses:
        if is_private_ip(addr):
            return False, f"host resolves to private/loopback IP {addr}"
    return True, ""


def fetch_guarded(
    url: str,
    *,
    max_bytes: int,
    timeout: float,
    max_redirects: int = 3,
) -> bytes:
    """Download *url* with SSRF checks re-applied on every redirect hop.

    Redirects are followed manually (``allow_redirects=False``) because a
    public host may 302 to ``http://169.254.169.254/`` — following blindly
    would reopen exactly the hole :func:`is_target_safe` closes. The body
    is streamed with a hard byte cap so a huge (or endless) response
    cannot exhaust memory or disk.

    Raises :class:`GuardedFetchError` with an operator-readable reason on
    any refusal or failure.
    """
    current = url
    for _ in range(max_redirects + 1):
        safe, reason = is_target_safe(current)
        if not safe:
            raise GuardedFetchError(reason)
        # The try must span the WHOLE exchange: ``stream=True`` defers the
        # body to ``iter_content``, so a timeout / connection reset mid-body
        # raises RequestException during iteration, not at ``get()``.
        try:
            response = requests.get(
                current,
                stream=True,
                allow_redirects=False,
                timeout=(5.0, timeout),
            )
            with response:
                if response.is_redirect:
                    location = response.headers.get("Location")
                    if not location:
                        raise GuardedFetchError("redirect without a Location header")
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    raise GuardedFetchError(f"HTTP {response.status_code}")
                declared = response.headers.get("Content-Length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise GuardedFetchError("response larger than the allowed size")
                chunks: list[bytes] = []
                received = 0
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    received += len(chunk)
                    if received > max_bytes:
                        raise GuardedFetchError("response larger than the allowed size")
                    chunks.append(chunk)
                return b"".join(chunks)
        except requests.RequestException as exc:
            raise GuardedFetchError(f"download failed: {exc}") from exc
    raise GuardedFetchError(f"too many redirects (max {max_redirects})")
