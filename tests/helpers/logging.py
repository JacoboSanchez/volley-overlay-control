"""Helpers for asserting on captured log output in tests."""

import logging


def assert_logged(caplog, level: int, substring: str) -> logging.LogRecord:
    """Return the first record at *level* whose message contains *substring*.

    Raises :class:`AssertionError` (with a dump of what was actually
    captured) when no record matches — easier to debug than pytest's
    default ``"no log captured"`` message.
    """
    matches = [
        r for r in caplog.records
        if r.levelno == level and substring in r.getMessage()
    ]
    if not matches:
        captured = [(r.levelname, r.name, r.getMessage()) for r in caplog.records]
        raise AssertionError(
            f"No {logging.getLevelName(level)} record contained "
            f"'{substring}'. Captured: {captured}"
        )
    return matches[0]
