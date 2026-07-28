"""Shared ``limit``/``offset`` paging for the account-level list endpoints.

Every listing that reads a table whose size grows with usage — the team
catalog, groups, overlays, the global icon library, presets — takes these
two query parameters and pushes them into SQL, so no request can ever
materialise a whole table. Callers that pass nothing get the first
``LIST_DEFAULT_LIMIT`` rows, which is well above any realistic catalog and
therefore invisible to existing clients.

The response body shape is deliberately **unchanged** (a bare JSON array
stays a bare JSON array): the full in-scope total travels in the
``X-Total-Count`` response header instead, so a client can tell a complete
page from a truncated one and keep requesting until it has everything,
without every existing consumer having to learn a new envelope.

Export endpoints (``/admin/teams/export``, ``/admin/presets/export``) are
intentionally *not* paginated — they are backup/round-trip surfaces where a
silently truncated page would mean silently losing data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar

from fastapi import Depends, Query, Response

from app.constants import LIST_DEFAULT_LIMIT, LIST_MAX_LIMIT

# ``Select``/``Query`` are both accepted; only ``.limit()``/``.offset()`` and
# slicing are used, so the helpers stay statement-flavour agnostic.
_S = TypeVar("_S")

TOTAL_COUNT_HEADER = "X-Total-Count"

# Every paginated route passes this as its ``responses=`` so the header is part
# of the *committed* contract, not just the runtime response. Without it an
# integrator reading ``frontend/schema/openapi.json`` has no way to discover
# the one signal that distinguishes a complete listing from a default-limited
# page — and the generated frontend types would not mention it either.
PAGINATED_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "headers": {
            TOTAL_COUNT_HEADER: {
                "description": (
                    "Total rows in scope, ignoring `limit`/`offset`. Page until "
                    "the accumulated row count reaches this value."
                ),
                "schema": {"type": "integer", "minimum": 0},
            },
        },
    },
}


@dataclass(frozen=True)
class Page:
    """A resolved ``limit``/``offset`` window."""

    limit: int
    offset: int

    def apply(self, stmt: _S) -> _S:
        """Push this window into a SQLAlchemy ``select()``."""
        return stmt.offset(self.offset).limit(self.limit)  # type: ignore[attr-defined]

    def slice(self, rows: list[_S]) -> list[_S]:
        """Apply the window in Python.

        For the handful of listings whose ordering cannot be expressed in SQL
        without changing the established sort. Still bounds the *response*;
        it does not bound the query, so prefer :meth:`apply`.
        """
        return rows[self.offset : self.offset + self.limit]


def page_params(
    limit: int = Query(
        LIST_DEFAULT_LIMIT, ge=1, le=LIST_MAX_LIMIT, description="Page size",
    ),
    offset: int = Query(0, ge=0, description="Rows to skip"),
) -> Page:
    return Page(limit=limit, offset=offset)


PageDep = Depends(page_params)


def with_total(response: Response, total: int) -> None:
    """Report the full in-scope row count on a paginated response."""
    response.headers[TOTAL_COUNT_HEADER] = str(total)
