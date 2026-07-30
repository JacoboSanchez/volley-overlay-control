"""Caller-fixable service errors with stable HTTP semantics.

Service modules raise these errors without depending on FastAPI.  The
application boundary translates them once, so route handlers do not need
copy-pasted ``try``/``except`` blocks or message-string inspection.
"""

from __future__ import annotations


class ServiceError(ValueError):
    """Base class for errors that are safe to expose to API callers."""

    status_code = 400


class NotFoundServiceError(ServiceError):
    """The requested resource does not exist in the caller's scope."""

    status_code = 404


class ConflictServiceError(ServiceError):
    """The requested write conflicts with an existing resource."""

    status_code = 409


class UnprocessableServiceError(ServiceError):
    """The request shape is valid but a semantic identifier is invalid."""

    status_code = 422
