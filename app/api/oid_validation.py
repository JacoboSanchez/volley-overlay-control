"""Centralised OID validation pattern.

Every layer that touches an OID — request schemas, audit log file
naming, session metadata, and match archives — checks against the
same regex so that a string accepted by one is accepted by all.

Custom overlay OIDs (e.g. ``C-mybroadcast/line``) include a slash,
so the pattern allows ``/``. Slashes are safe for on-disk paths
because every filesystem-backed module hashes the OID before using
it in a filename, never interpolating it directly. The negative
lookahead still rejects ``..`` substrings as defence in depth so a
caller that one day forgets to hash cannot accidentally walk up
the data directory.

Length is capped at 200 to match :class:`InitRequest.oid`'s
``max_length`` and to keep audit/persistence payloads bounded.
"""

import re

OID_PATTERN = re.compile(r"^(?!.*\.\.)[A-Za-z0-9._\-/]{1,200}$")


def is_valid_oid(value: object) -> bool:
    """Return True iff *value* is a non-empty OID string within bounds."""
    return isinstance(value, str) and OID_PATTERN.match(value) is not None
