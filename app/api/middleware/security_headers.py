"""ASGI middleware that adds baseline HTTP security response headers.

The middleware is configured with conservative defaults that work for
the bundled SPA, the ``/manage`` admin page, the ``/match/{id}/report``
print page, and the OBS-facing ``/overlay/{id}`` templates without
forcing a CSP nonce migration. Operators can override the defaults via
environment variables when they want a stricter posture (e.g. drop
``'unsafe-inline'`` after auditing inline scripts).

Headers applied to every response:

* ``X-Content-Type-Options: nosniff`` — disables MIME-type guessing.
* ``Referrer-Policy: strict-origin-when-cross-origin`` — keeps the path
  out of cross-origin referers.
* ``Permissions-Policy`` — denies geolocation/microphone/camera by
  default; the app does not use them.

Headers applied only to HTML responses:

* ``Content-Security-Policy`` — locks ``default-src``/``script-src`` to
  ``'self'`` plus ``'unsafe-inline'`` so the existing inline match-report
  styles keep rendering. ``img-src`` allows ``https:`` and ``data:`` so
  team logos still load from arbitrary CDNs and embedded data URLs.
  Overlay routes (``/overlay/*``) get a relaxed ``frame-ancestors *``
  because OBS browser sources embed them off-origin.
* ``X-Frame-Options: SAMEORIGIN`` for non-overlay routes (legacy
  fallback for browsers that ignore CSP ``frame-ancestors``).

Headers applied to ``/api/v1/`` responses:

* ``Cache-Control: no-store`` — authenticated API responses must not
  be cached by intermediaries. Existing endpoints that already set
  ``Cache-Control`` (e.g. the SPA shell) are not overridden.
"""

from __future__ import annotations

import os
from collections.abc import Iterable


def _env(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip()


_DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    # ``http:`` deliberately omitted: HTTPS deployments would block
    # mixed-content images anyway, and ``'self'`` already covers
    # plain-HTTP localhost dev servers. Operators that genuinely need
    # third-party HTTP logos can override via ``SECURITY_CSP``.
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "connect-src 'self' ws: wss: https:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'self'"
)

_OVERLAY_CSP_FRAME_ANCESTORS = "frame-ancestors *"
# Overlay templates pull webfonts from Google Fonts (Outfit, Inter,
# Roboto, Oswald, Montserrat, Rajdhani, Barlow Condensed, Chakra Petch,
# Rubik). The stylesheet is served from fonts.googleapis.com and the
# woff2 files from fonts.gstatic.com — both must be allowed for the
# OBS-rendered overlays to keep their intended typography. We only
# relax this on /overlay/* paths; the control UI, /manage, and the
# match report stay locked to 'self'.
_OVERLAY_CSP_STYLE_HOSTS = "https://fonts.googleapis.com"
_OVERLAY_CSP_FONT_HOSTS = "https://fonts.gstatic.com"
_DEFAULT_PERMISSIONS_POLICY = (
    "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
)
_DEFAULT_REFERRER_POLICY = "strict-origin-when-cross-origin"

# Paths whose responses are HTML and therefore receive CSP / X-Frame-Options.
# We treat the catch-all SPA mount, the manage page, the match report, and
# the overlay templates as HTML; explicit "html=True" responses elsewhere
# still get the headers because we sniff the Content-Type at send time.
_OVERLAY_PREFIXES: tuple[str, ...] = ("/overlay/",)


def _augment_directive(parts: list[str], name: str, *extras: str) -> None:
    """Append *extras* to the CSP directive *name* in-place.

    If the directive is missing, a new one is appended that starts at
    ``'self'`` and adds *extras*. Existing tokens are preserved so an
    operator-supplied ``SECURITY_CSP`` override never loses entries.
    """
    lower = name.lower()
    for i, part in enumerate(parts):
        tokens = part.split()
        if tokens and tokens[0].lower() == lower:
            for extra in extras:
                if extra not in tokens:
                    tokens.append(extra)
            parts[i] = " ".join(tokens)
            return
    parts.append(" ".join((name, "'self'", *extras)))


def _build_html_csp(path: str) -> str:
    """Return the CSP string for an HTML response on *path*.

    Overlay routes are embedded in OBS browser sources, which load the
    page off-origin; ``frame-ancestors 'self'`` would break them, and
    several templates pull webfonts from Google Fonts. The overlay
    branch relaxes ``frame-ancestors``, ``style-src``, and ``font-src``
    only — every other ``script-src`` / ``img-src`` / ``connect-src``
    policy stays in force.
    """
    csp = _env("SECURITY_CSP", _DEFAULT_CSP)
    if any(path.startswith(prefix) for prefix in _OVERLAY_PREFIXES):
        parts = [p.strip() for p in csp.split(";") if p.strip()]
        replaced = False
        for i, p in enumerate(parts):
            if p.lower().startswith("frame-ancestors"):
                parts[i] = _OVERLAY_CSP_FRAME_ANCESTORS
                replaced = True
                break
        if not replaced:
            parts.append(_OVERLAY_CSP_FRAME_ANCESTORS)
        _augment_directive(parts, "style-src", _OVERLAY_CSP_STYLE_HOSTS)
        _augment_directive(parts, "font-src", _OVERLAY_CSP_FONT_HOSTS)
        csp = "; ".join(parts)
    return csp


def _is_html_content_type(content_type: bytes) -> bool:
    return content_type.lower().startswith(b"text/html")


def _has_header(headers: Iterable[tuple[bytes, bytes]], name: bytes) -> bool:
    target = name.lower()
    return any(k.lower() == target for k, _ in headers)


class SecurityHeadersMiddleware:
    """Pure-ASGI middleware that injects baseline security response headers.

    Hooks into ``http.response.start`` so it can inspect the outgoing
    Content-Type and tailor CSP / X-Frame-Options to HTML responses
    only. Non-HTTP scopes (lifespan, websocket) are passed through
    untouched.

    Existing ``Cache-Control`` headers are preserved; the middleware
    only sets ``no-store`` on ``/api/v1/`` responses that don't already
    carry the directive (so explicit ``no-cache`` choices in
    ``bootstrap`` are respected).
    """

    def __init__(self, app, *, hsts_seconds: int | None = None) -> None:
        self.app = app
        # HSTS is opt-in: setting it on a deployment that's not HTTPS-only
        # will lock browsers out. Operators enable it via env var.
        env_hsts = _env("SECURITY_HSTS_SECONDS", "")
        if hsts_seconds is None and env_hsts:
            try:
                hsts_seconds = max(0, int(env_hsts))
            except ValueError:
                hsts_seconds = None
        self._hsts_seconds = hsts_seconds

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "") or ""

        async def send_wrapper(message):
            if message.get("type") != "http.response.start":
                await send(message)
                return

            headers: list[tuple[bytes, bytes]] = list(
                message.get("headers") or []
            )
            content_type = b""
            for k, v in headers:
                if k.lower() == b"content-type":
                    content_type = v
                    break

            # Always-on headers.
            if not _has_header(headers, b"x-content-type-options"):
                headers.append((b"x-content-type-options", b"nosniff"))
            if not _has_header(headers, b"referrer-policy"):
                headers.append((
                    b"referrer-policy",
                    _env(
                        "SECURITY_REFERRER_POLICY",
                        _DEFAULT_REFERRER_POLICY,
                    ).encode("latin-1"),
                ))
            if not _has_header(headers, b"permissions-policy"):
                headers.append((
                    b"permissions-policy",
                    _env(
                        "SECURITY_PERMISSIONS_POLICY",
                        _DEFAULT_PERMISSIONS_POLICY,
                    ).encode("latin-1"),
                ))

            # HSTS — opt in only.
            if self._hsts_seconds and not _has_header(
                headers, b"strict-transport-security",
            ):
                headers.append((
                    b"strict-transport-security",
                    f"max-age={self._hsts_seconds}; includeSubDomains".encode(
                        "latin-1",
                    ),
                ))

            # HTML-only headers (CSP + X-Frame-Options).
            if _is_html_content_type(content_type):
                if not _has_header(headers, b"content-security-policy"):
                    headers.append((
                        b"content-security-policy",
                        _build_html_csp(path).encode("latin-1"),
                    ))
                if not _has_header(headers, b"x-frame-options"):
                    # Overlay routes intentionally allow cross-origin
                    # framing (OBS browser source). Everything else is
                    # SAMEORIGIN as a legacy fallback for browsers that
                    # ignore CSP frame-ancestors.
                    if not any(
                        path.startswith(prefix) for prefix in _OVERLAY_PREFIXES
                    ):
                        headers.append((b"x-frame-options", b"SAMEORIGIN"))

            # API JSON responses — disable intermediary caching.
            if path.startswith("/api/v1/") and not _has_header(
                headers, b"cache-control",
            ):
                headers.append((b"cache-control", b"no-store"))

            message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
