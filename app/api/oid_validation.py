"""Centralised OID validation pattern (API tier).

Re-exports from :mod:`app.id_validation` for backward compatibility.
"""

from app.id_validation import API_OID_PATTERN as OID_PATTERN
from app.id_validation import is_valid_api_oid as is_valid_oid

__all__ = ["OID_PATTERN", "is_valid_oid"]
