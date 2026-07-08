"""SSRF guard for outbound HTTP requests triggered by user-supplied URLs.

Shared by webhook delivery (``app/api/webhooks.py``) and the icon
batch-import download path. The posture is fail-closed: a URL whose host
resolves to a private / loopback / link-local / multicast / reserved IP
is refused before any HTTP request fires, blocking classic SSRF
(``http://localhost/admin``, ``http://169.254.169.254`` cloud metadata,
``http://10.0.0.5/``).

Two callers, two postures:

* ``is_target_safe`` (webhooks — operator-controlled URLs): validate,
  then let ``requests`` resolve again. DNS failures pass through so a
  flaky resolver doesn't break deliveries; the residual check-then-
  connect gap (DNS rebinding) is accepted for operator-supplied targets.
* ``fetch_guarded`` (icon imports — **user**-controlled URLs): resolve
  once, validate every address, and **pin the connection to a validated
  IP** (Host header / TLS SNI+verification keep the original hostname).
  A rebinding host that answers the guard with a public IP cannot swap
  in ``169.254.169.254`` for the actual fetch, because the fetch never
  re-resolves. Redirects re-run the same plan per hop
  (``allow_redirects=False`` + manual loop) instead of following blindly.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter


class GuardedFetchError(ValueError):
    """A guarded download failed for a caller-reportable reason."""


def is_private_ip(ip_str: str) -> bool:
    """Return True iff *ip_str* is in any IP range we refuse to call."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        # Anything that isn't a parseable IP literal is suspicious.
        return True
    # Unwrap IPv4-mapped IPv6 (``::ffff:127.0.0.1``) to the embedded IPv4
    # before classifying. Before CPython 3.13 the ``is_private`` /
    # ``is_loopback`` predicates don't see through the mapping on every
    # patch release, so a mapped literal for a metadata/loopback/private
    # address could slip past the guard — a classic SSRF bypass. Checking
    # the unwrapped address closes it independent of the interpreter build.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
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


class _PinnedTLSAdapter(HTTPAdapter):
    """TLS to a pinned IP while presenting/validating the original hostname.

    The request URL carries the validated IP (so the TCP connection can
    never follow a re-resolved DNS answer); ``server_hostname`` restores
    the original name for SNI and ``assert_hostname`` keeps certificate
    verification against it (urllib3 v2 pool kwargs).
    """

    def __init__(self, hostname: str):
        self._hostname = hostname
        super().__init__()

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["server_hostname"] = self._hostname
        pool_kwargs["assert_hostname"] = self._hostname
        return super().init_poolmanager(
            connections, maxsize, block=block, **pool_kwargs
        )


def _select_pinned_ip(addresses: list[str]) -> str:
    """Deterministically pick the connect address (IPv4 preferred)."""
    ordered = sorted(addresses)
    for addr in ordered:
        if ":" not in addr:
            return addr
    return ordered[0]


def _plan_hop(current: str) -> tuple[str, dict[str, str], str | None]:
    """Validate one hop and return ``(request_url, headers, tls_hostname)``.

    A hostname URL is rewritten to a validated, pinned IP with a ``Host``
    header carrying the original name; ``tls_hostname`` is that name for
    the HTTPS adapter (``None`` for literal-IP URLs, which need no pin).
    Raises :class:`GuardedFetchError` on any refusal.
    """
    parsed = urlparse(current)
    if parsed.scheme not in ("http", "https"):
        raise GuardedFetchError(
            f"scheme {parsed.scheme!r} not allowed (use http/https)"
        )
    host = parsed.hostname
    if not host:
        raise GuardedFetchError("URL has no hostname")
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        if is_private_ip(str(literal_ip)):
            raise GuardedFetchError(f"host literal {host} is private/loopback")
        return current, {}, None

    # ``get_environ_proxies`` returns every ``*_proxy`` env var (including
    # ``no_proxy``), so ask ``select_proxy`` whether one actually applies
    # to THIS url/scheme.
    environ_proxies = requests.utils.get_environ_proxies(current)
    if environ_proxies and requests.utils.select_proxy(current, environ_proxies):
        # An egress proxy performs the DNS resolution itself, so an IP-pinned
        # URL would only break the proxy's hostname ACLs without adding
        # protection (we cannot pin what the proxy resolves). Validate our
        # view of the name and send the original URL through the proxy.
        safe, reason = is_target_safe(current)
        if not safe:
            raise GuardedFetchError(reason)
        return current, {}, None

    addresses = resolve_target_addresses(host)
    if addresses is None:
        # Unlike the webhook posture, a user-supplied import URL that we
        # cannot resolve is refused outright: pass-through would hand the
        # (unpinnable) resolution to requests and reopen the rebinding gap.
        raise GuardedFetchError(f"could not resolve host {host!r}")
    for addr in addresses:
        if is_private_ip(addr):
            raise GuardedFetchError(f"host resolves to private/loopback IP {addr}")
    ip = _select_pinned_ip(addresses)
    ip_netloc = f"[{ip}]" if ":" in ip else ip
    if parsed.port is not None:
        ip_netloc = f"{ip_netloc}:{parsed.port}"
    pinned_url = urlunparse(parsed._replace(netloc=ip_netloc))
    host_header = host if parsed.port is None else f"{host}:{parsed.port}"
    return pinned_url, {"Host": host_header}, host


def fetch_guarded(
    url: str,
    *,
    max_bytes: int,
    timeout: float,
    max_redirects: int = 3,
) -> bytes:
    """Download *url* with SSRF checks re-applied on every redirect hop.

    Hostname targets are resolved once, validated, and fetched over a
    connection pinned to the validated IP (closing the DNS-rebinding
    check-then-connect gap); redirects are followed manually
    (``allow_redirects=False``) because a public host may 302 to
    ``http://169.254.169.254/``. The body is streamed with a hard byte
    cap so a huge (or endless) response cannot exhaust memory or disk.

    Raises :class:`GuardedFetchError` with an operator-readable reason on
    any refusal or failure.
    """
    current = url
    for _ in range(max_redirects + 1):
        request_url, headers, tls_hostname = _plan_hop(current)
        # The try must span the WHOLE exchange: ``stream=True`` defers the
        # body to ``iter_content``, so a timeout / connection reset mid-body
        # raises RequestException during iteration, not at ``get()``.
        session: requests.Session | None = None
        try:
            if tls_hostname is not None and request_url.startswith("https"):
                session = requests.Session()
                session.mount("https://", _PinnedTLSAdapter(tls_hostname))
                getter = session.get
            else:
                getter = requests.get
            response = getter(
                request_url,
                stream=True,
                allow_redirects=False,
                timeout=(5.0, timeout),
                headers=headers or None,
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
        finally:
            if session is not None:
                session.close()
    raise GuardedFetchError(f"too many redirects (max {max_redirects})")
