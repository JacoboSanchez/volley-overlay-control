"""Compatibility forwarding for :mod:`app.match_report.stats`."""

from __future__ import annotations

from typing import Any

from app.match_report import stats as _stats


def __getattr__(name: str) -> Any:
    return getattr(_stats, name)
