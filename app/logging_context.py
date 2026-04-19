"""Request-scoped logging context.

Holds ``request_id`` and ``oid`` in :mod:`contextvars` so that every log
record emitted during a request (whether from an HTTP handler, a
WebSocket endpoint, or a background task spawned from one) can be
correlated without having to thread the values through every function.
"""

import contextvars
import logging
import uuid

from app.logging_utils import redact_oid


request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-",
)
oid_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "oid", default="-",
)


def new_request_id() -> str:
    """Return a short hex UUID suitable for use as a correlation id."""
    return uuid.uuid4().hex


def get_request_id() -> str:
    return request_id_var.get()


def get_oid() -> str:
    return oid_var.get()


def set_request_id(value: str | None) -> contextvars.Token:
    return request_id_var.set(value or "-")


def set_oid(value: str | None) -> contextvars.Token:
    return oid_var.set(value or "-")


class ContextFilter(logging.Filter):
    """Inject ``request_id`` and ``oid`` into each :class:`LogRecord`.

    Attaching as a ``logging.Filter`` (rather than formatter override) means
    the values are also available to JSON handlers and any third-party
    formatter.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        if not hasattr(record, "oid"):
            raw = oid_var.get()
            record.oid = raw if raw == "-" else redact_oid(raw)
        return True
