"""Password hashing + helpers for the account model.

Thin layer over :mod:`app.password_hash` (scrypt, stdlib-only) so the auth
package has a single import surface, plus a temporary-password generator for
the admin "reset to a temp password" flow.
"""

from __future__ import annotations

import secrets
import string

from app.password_hash import hash_password, is_hashed, verify_password

__all__ = [
    "generate_temp_password",
    "hash_password",
    "is_hashed",
    "verify_password",
]

# Unambiguous alphabet for temp passwords read off a screen/log: no
# 0/O/1/l/I to avoid transcription errors when an admin reads one out.
_TEMP_ALPHABET = "".join(
    c for c in (string.ascii_letters + string.digits) if c not in "0O1lI"
)


def generate_temp_password(length: int = 14) -> str:
    """Return a random, human-transcribable temporary password."""
    return "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(length))
