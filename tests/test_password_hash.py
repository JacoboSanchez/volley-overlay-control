"""Coverage for :mod:`app.password_hash`.

Pins the wire format, the round-trip behaviour, the plaintext-fallback
contract that lets deployments migrate without a flag day, and the
defensive ``False``-on-malformed behaviour that callers rely on to
treat the verifier as a black box.
"""

from __future__ import annotations

import re
import subprocess
import sys

import pytest

from app import password_hash as ph

# ---------------------------------------------------------------------------
# hash_password / verify_password round-trip
# ---------------------------------------------------------------------------


def test_hash_format_matches_documented_regex():
    record = ph.hash_password("hunter2")
    assert ph.is_hashed(record)
    assert ph._HASH_RE.match(record) is not None


def test_round_trip_default_params():
    record = ph.hash_password("correct horse battery staple")
    assert ph.verify_password("correct horse battery staple", record)
    assert ph.verify_password("wrong", record) is False


def test_round_trip_custom_params():
    record = ph.hash_password("pw", n=4096, r=4, p=2)
    assert ph.verify_password("pw", record)
    # The stored params must be honoured on verify; verifying with a
    # different password still fails.
    assert ph.verify_password("nope", record) is False


def test_each_hash_uses_a_fresh_salt():
    a = ph.hash_password("same")
    b = ph.hash_password("same")
    assert a != b
    # Both hashes verify the same password, despite different salts.
    assert ph.verify_password("same", a)
    assert ph.verify_password("same", b)


def test_hash_rejects_empty_password():
    with pytest.raises(ValueError):
        ph.hash_password("")


def test_hash_rejects_non_string_password():
    with pytest.raises(TypeError):
        ph.hash_password(b"bytes")


def test_hash_rejects_non_power_of_two_n():
    with pytest.raises(ValueError):
        ph.hash_password("pw", n=12345)


# ---------------------------------------------------------------------------
# Plaintext fallback (legacy compatibility)
# ---------------------------------------------------------------------------


def test_verify_falls_through_to_constant_time_compare_for_plaintext():
    """``verify_password`` accepts a plaintext stored value too.

    This is the migration path: existing deployments keep working even
    when individual entries have not been re-encoded as hashes yet.
    """
    assert ph.verify_password("hunter2", "hunter2")
    assert ph.verify_password("hunter2", "different") is False


def test_is_hashed_only_recognises_the_documented_prefix():
    assert ph.is_hashed("scrypt$n=16384,r=8,p=1$ab$cd")
    assert not ph.is_hashed("hunter2")
    assert not ph.is_hashed("$argon2id$v=19$...")  # other formats are not ours
    assert not ph.is_hashed(123)
    assert not ph.is_hashed(None)


# ---------------------------------------------------------------------------
# Defensive failure modes — never raise
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("malformed", [
    "scrypt$",
    "scrypt$n=16384",
    "scrypt$n=16384,r=8,p=1$",
    "scrypt$n=16384,r=8,p=1$nothex$nothex",
    "scrypt$n=12345,r=8,p=1$abcd$abcd",         # non-power-of-2 n
    "scrypt$n=16384,r=0,p=1$abcd$abcd",         # r < 1
    "scrypt$n=16384,r=8,p=0$abcd$abcd",         # p < 1
    "scrypt$n=99999999,r=8,p=1$abcd$abcd",      # huge n — exceeds maxmem
    "",
])
def test_verify_returns_false_on_malformed_record(malformed):
    assert ph.verify_password("any", malformed) is False


def test_verify_returns_false_for_non_string_inputs():
    assert ph.verify_password(123, "scrypt$n=16384,r=8,p=1$ab$cd") is False
    assert ph.verify_password("pw", None) is False


def test_verify_rejects_n_above_max_log2_cap():
    """A record with ``n=2**32`` must fail closed before scrypt allocates GiBs."""
    record = f"scrypt$n={1 << 32},r=8,p=1${'ab' * 8}${'cd' * 16}"
    assert ph.verify_password("any", record) is False


# ---------------------------------------------------------------------------
# CLI helper (``python -m app.password_hash``)
# ---------------------------------------------------------------------------


def test_cli_stdin_mode_round_trips():
    """Mint a hash via ``--stdin`` and verify it inline."""
    proc = subprocess.run(
        [sys.executable, "-m", "app.password_hash", "--stdin"],
        input="cli-pw",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    record = proc.stdout.strip()
    assert ph.is_hashed(record)
    assert ph.verify_password("cli-pw", record)
    assert not ph.verify_password("other", record)


def test_cli_rejects_empty_password():
    proc = subprocess.run(
        [sys.executable, "-m", "app.password_hash", "--stdin"],
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 2
    assert "non-empty" in proc.stderr.lower()


def test_cli_respects_custom_n():
    proc = subprocess.run(
        [sys.executable, "-m", "app.password_hash",
         "--stdin", "--n", "4096"],
        input="pw",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
    record = proc.stdout.strip()
    m = re.match(r"scrypt\$n=(\d+),", record)
    assert m is not None
    assert int(m.group(1)) == 4096
