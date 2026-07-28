"""Compatibility forwarding for :mod:`app.match_report.render`."""

from __future__ import annotations

from typing import Any

from app.match_report import render as _render


def __getattr__(name: str) -> Any:
    return getattr(_render, name)
