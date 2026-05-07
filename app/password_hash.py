"""Credential hashing using ``hashlib.scrypt`` (zero dependencies).

The original auth ladder stored every credential as plaintext in
``.env``/compose env vars. ``secrets.compare_digest`` made the
*comparison* constant-time, but the source value still sat in cleartext
on disk where any operator with shell access could read it. This
module offers a hashed alternative without pulling in a new dependency.

Format
------

A hash string looks like::

    scrypt$n=16384,r=8,p=1$<salt-hex>$<hash-hex>

* ``n``, ``r``, ``p`` are the standard scrypt parameters.
* ``salt`` is 16 random bytes, lowercase hex (32 chars).
* ``hash`` is the 32-byte derived key, lowercase hex (64 chars).

The format is deliberately PHC-flavoured but not strictly compliant —
parsers in other languages should be straightforward to write. The
fields are bound together by the ``$``-delimited frame so a malformed
record fails closed (``verify_password`` returns ``False`` rather than
raising).

Why scrypt
----------

* It ships in the Python standard library — no new wheel to vet, no
  cross-platform build of a C extension.
* It is memory-hard, which makes mass GPU brute-force impractical at
  the chosen parameters (~16 MiB working set per guess at ``n=16384``).
* The verification cost is tunable: operators who want stronger hashes
  bump ``n`` when minting; verification reads the parameters from the
  hash itself, so existing records keep working.

CLI
---

``python -m app.password_hash`` prompts for a password (no echo) and
prints the hash string. Operators paste that into ``SCOREBOARD_USERS``,
``OVERLAY_MANAGER_PASSWORD_HASH``, or ``OVERLAY_SERVER_TOKEN_HASH``.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import logging
import re
import secrets
import sys

logger = logging.getLogger(__name__)


# scrypt parameters. Tunable via the CLI; the verifier reads whatever
# values the hash record carries, so existing hashes keep working when
# the defaults change.
DEFAULT_N = 1 << 14   # 16384 — light, ~50 ms on a modern CPU
DEFAULT_R = 8
DEFAULT_P = 1
_SALT_BYTES = 16
_HASH_BYTES = 32

# scrypt's memory footprint is ~128 * n * r bytes. At the defaults
# (n=16384, r=8) that's 16 MiB per hash. ``hashlib.scrypt`` enforces
# a ``maxmem`` ceiling so a misconfigured ``n`` cannot wedge the
# server with a multi-GiB allocation. We size the cap ten-fold above
# the default so operators can bump ``n`` to ~131072 without recompiling.
_SCRYPT_MAXMEM = 10 * (128 * (1 << 17) * 8)

_HASH_PREFIX = "scrypt$"
# ``n`` must be a power of 2 ≥ 2; cap at 2^20 so a malformed hash with
# ``n=10**12`` cannot cause a multi-GiB allocation before maxmem fires.
_MAX_N_LOG2 = 20
_HASH_RE = re.compile(
    r"^scrypt\$"
    r"n=(?P<n>\d+),r=(?P<r>\d+),p=(?P<p>\d+)\$"
    r"(?P<salt>[0-9a-f]+)\$"
    r"(?P<hash>[0-9a-f]+)$"
)


def is_hashed(value: object) -> bool:
    """Return True if *value* looks like a hash record produced by this module.

    A loose check — full validation happens inside :func:`verify_password`,
    which fails closed on any structural problem.
    """
    return isinstance(value, str) and value.startswith(_HASH_PREFIX)


def _is_power_of_two(n: int) -> bool:
    return n > 1 and (n & (n - 1)) == 0


def hash_password(
    password: str,
    *,
    n: int = DEFAULT_N,
    r: int = DEFAULT_R,
    p: int = DEFAULT_P,
    salt: bytes | None = None,
) -> str:
    """Return a freshly-salted hash string for *password*.

    Parameters mirror scrypt's; sensible defaults are documented above.
    *salt* is exposed only for tests — production callers leave it
    ``None`` so a CSPRNG-sourced salt is generated.
    """
    if not isinstance(password, str):
        raise TypeError("password must be str")
    if not password:
        raise ValueError("password must be non-empty")
    if not _is_power_of_two(n):
        raise ValueError("scrypt n must be a power of 2 ≥ 2")
    if r < 1 or p < 1:
        raise ValueError("scrypt r and p must be ≥ 1")

    salt_bytes = salt if salt is not None else secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt_bytes,
        n=n, r=r, p=p,
        dklen=_HASH_BYTES,
        maxmem=_SCRYPT_MAXMEM,
    )
    return (
        f"scrypt$n={n},r={r},p={p}$"
        f"{salt_bytes.hex()}${derived.hex()}"
    )


def verify_password(provided: str, stored: str) -> bool:
    """Return True iff *provided* matches *stored*.

    *stored* may be either a hash record produced by :func:`hash_password`
    or a plaintext credential (for backwards compatibility with
    deployments that have not migrated yet). Both paths are
    constant-time:

    * The hash branch uses :func:`hmac.compare_digest` over the derived
      key bytes (scrypt itself runs in constant time for fixed
      parameters).
    * The plaintext branch uses :func:`secrets.compare_digest` directly.

    Malformed hash records or any internal exception fail closed —
    the function returns ``False`` rather than raising so callers can
    treat it as a black-box auth check.
    """
    if not isinstance(provided, str) or not isinstance(stored, str):
        return False
    if not is_hashed(stored):
        return secrets.compare_digest(provided, stored)
    match = _HASH_RE.match(stored)
    if match is None:
        return False
    try:
        n = int(match.group("n"))
        r = int(match.group("r"))
        p = int(match.group("p"))
        salt = bytes.fromhex(match.group("salt"))
        expected = bytes.fromhex(match.group("hash"))
    except ValueError:
        return False
    if not _is_power_of_two(n) or n.bit_length() - 1 > _MAX_N_LOG2:
        return False
    if r < 1 or p < 1:
        return False
    if not salt or not expected:
        return False
    try:
        derived = hashlib.scrypt(
            provided.encode("utf-8"),
            salt=salt,
            n=n, r=r, p=p,
            dklen=len(expected),
            maxmem=_SCRYPT_MAXMEM,
        )
    except (ValueError, MemoryError):
        # Either the requested params exceeded ``maxmem`` (malformed
        # record) or the platform refused to allocate. Treat as a
        # mismatch — never raise out of the verifier.
        return False
    return hmac.compare_digest(derived, expected)


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------


def _cli(argv: list[str]) -> int:
    """Mint a hash from interactive input and print to stdout.

    Usage::

        python -m app.password_hash               # prompts twice
        python -m app.password_hash --n 32768     # heavier hash
        echo -n 'pw' | python -m app.password_hash --stdin

    Operators paste the printed line into ``SCOREBOARD_USERS``,
    ``OVERLAY_MANAGER_PASSWORD_HASH``, or ``OVERLAY_SERVER_TOKEN_HASH``.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m app.password_hash",
        description="Mint a scrypt-hashed credential string.",
    )
    parser.add_argument("--n", type=int, default=DEFAULT_N,
                        help=f"scrypt N (power of 2; default {DEFAULT_N})")
    parser.add_argument("--r", type=int, default=DEFAULT_R,
                        help=f"scrypt r (default {DEFAULT_R})")
    parser.add_argument("--p", type=int, default=DEFAULT_P,
                        help=f"scrypt p (default {DEFAULT_P})")
    parser.add_argument(
        "--stdin", action="store_true",
        help="Read the password from stdin (no terminal prompt).",
    )
    args = parser.parse_args(argv)

    if args.stdin:
        password = sys.stdin.read().rstrip("\n")
    else:
        password = getpass.getpass("Password: ")
        again = getpass.getpass("Confirm:  ")
        if password != again:
            print("Passwords do not match.", file=sys.stderr)
            return 2
    if not password:
        print("Password must be non-empty.", file=sys.stderr)
        return 2
    try:
        record = hash_password(password, n=args.n, r=args.r, p=args.p)
    except ValueError as exc:
        print(f"Invalid parameters: {exc}", file=sys.stderr)
        return 2
    print(record)
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised via subprocess in tests
    sys.exit(_cli(sys.argv[1:]))
