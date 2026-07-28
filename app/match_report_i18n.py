"""Compatibility forwarding for :mod:`app.match_report.i18n`."""

from __future__ import annotations

from typing import Any

from app.match_report import i18n as _i18n
from app.match_report.i18n import SUPPORTED_LOCALES as SUPPORTED_LOCALES
from app.match_report.i18n import resolve_locale as resolve_locale
from app.match_report.i18n import t as t


def __getattr__(name: str) -> Any:
    return getattr(_i18n, name)
