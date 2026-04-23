"""Utility functions and constants for Overlay ID handling.

Extracted from the former ``OidDialog`` so that the API layer can use them
without pulling in any UI dependencies.
"""

import re

UNO_CONTROL_BASE_URL = 'https://app.overlays.uno/control/'
UNO_OUTPUT_BASE_URL = 'https://app.overlays.uno/output/'


def extract_oid(url: str) -> str:
    """Extract the overlay ID from a full overlays.uno control URL.

    If *url* is not a recognised overlays.uno URL it is returned as-is
    (it may already be a bare OID or a custom-overlay identifier).
    """
    pattern = r"^https://app\.overlays\.uno/control/([a-zA-Z0-9_\-/.]+?)(?:\?.*)?$"
    match = re.match(pattern, url)
    if match:
        return match.group(1)
    return url


def compose_output(output: str) -> str:
    """Ensure *output* is a full URL, prepending the Uno base if needed."""
    if output.startswith("http://") or output.startswith("https://"):
        return output
    return UNO_OUTPUT_BASE_URL + output
