"""Match-report package with a lazy compatibility surface."""

from __future__ import annotations

from typing import Any

__all__ = ["match_report_router"]


def __getattr__(name: str) -> Any:
    """Resolve historical package-level helpers without eager import cycles."""
    if name in {"match_report_router", "_REPORT_TEMPLATE"}:
        from app.match_report import routes

        return getattr(routes, name)
    if name == "_render_highlights":
        from app.match_report import render

        return render._render_highlights
    if name in {"_collapse_undos", "_compute_stats"}:
        from app.match_report import stats

        return getattr(stats, name)
    raise AttributeError(name)
