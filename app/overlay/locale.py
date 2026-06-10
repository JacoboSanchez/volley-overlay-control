"""Locale resolution for overlay HTML templates and JS.

Split out of :mod:`app.overlay.routes`.
"""

import os

from fastapi import Request

from app.match_report_i18n import (
    SUPPORTED_LOCALES,
)
from app.match_report_i18n import (
    resolve_locale as _resolve_accept_language,
)


def _normalise_locale(raw: str | None) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    candidate = raw.strip().lower()[:2]
    return candidate if candidate in SUPPORTED_LOCALES else None


def _resolve_overlay_locale(
    query_lang: str | None,
    request: Request,
    persisted_locale: str | None = None,
) -> str:
    """Pick the locale tag the overlay templates / JS will use.

    Resolution order: ``?lang=<code>`` query param (operator override
    when embedding the overlay in OBS) → ``raw_remote_customization.locale``
    persisted with the overlay (operator's UI language, pushed live by
    the control app so OBS browser sources whose URL is fixed in the
    streaming app still follow language changes) → ``OVERLAY_LOCALE``
    env var → ``Accept-Language`` (q-weighted via
    :func:`app.match_report_i18n.resolve_locale`) → ``"en"``.
    """
    for candidate in (query_lang, persisted_locale, os.environ.get("OVERLAY_LOCALE")):
        normalised = _normalise_locale(candidate)
        if normalised is not None:
            return normalised
    return _resolve_accept_language(request.headers.get("accept-language"))
