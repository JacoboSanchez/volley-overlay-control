"""Small helpers shared by the overlay backend strategies."""


def is_custom_overlay(oid: str) -> bool:
    """Check whether an OID refers to a custom (local) overlay."""
    return oid is not None and str(oid).upper().startswith("C-")


def _mock_response(status_code=200, payload=None):
    """Create a minimal response-like object for error paths."""
    body = payload or {}
    return type('MockResponse', (object,), {
        'status_code': status_code,
        'text': '',
        'json': lambda self: body,
    })()


def split_custom_oid(oid: str):
    """Extract base_id and optional style from a custom OID (``C-id[/style]``)."""
    raw_id = str(oid)[2:]  # Strip the ``C-`` prefix
    parts = raw_id.split('/', 1)
    return parts[0], (parts[1] if len(parts) > 1 else None)
