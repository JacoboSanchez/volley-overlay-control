"""Logging configuration built on :func:`logging.config.dictConfig`.

Environment variables:

- ``LOGGING_LEVEL``: ``DEBUG|INFO|WARNING|ERROR|CRITICAL`` (default ``WARNING``).
- ``LOG_FORMAT``: ``text`` (default, ANSI-coloured for dev) or ``json``
  (one JSON object per line, suitable for log aggregators).

The text formatter renders ``[rid=… oid=…]`` when either value is set
by :class:`app.api.middleware.logging.RequestContextMiddleware`; JSON
always emits both fields. Uvicorn's access logger is routed through the
same pipeline with a filter that drops periodic liveness probes so they
don't drown the signal.
"""

import json
import logging
import logging.config


_ANSI_COLORS = {
    "DEBUG": "\033[39m",
    "INFO": "\033[1;33m",
    "WARNING": "\033[1;43m",
    "ERROR": "\033[1;31m",
    "CRITICAL": "\033[1;41m",
}
_ANSI_RESET = "\033[1;0m"
_ANSI_NAME = "\033[32m"
_ANSI_TIME = "\033[1;36m"


# Derived from stdlib so it tracks Python-version changes (e.g. ``taskName``
# was added in 3.12). Anything the JSON formatter emits explicitly is added
# back so it cannot leak into the "extras" sweep.
_STANDARD_LOGRECORD_ATTRS = (
    frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
)


class TextFormatter(logging.Formatter):
    """ANSI-coloured human-readable formatter."""

    default_time_format = "%Y-%m-%d %H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        colour = _ANSI_COLORS.get(record.levelname, "")
        ts = self.formatTime(record, self.datefmt)
        rid = getattr(record, "request_id", "-")
        oid = getattr(record, "oid", "-")
        ctx = f" [rid={rid} oid={oid}]" if rid != "-" or oid != "-" else ""
        line = (
            f"{_ANSI_TIME}{ts}{_ANSI_RESET} "
            f"{colour}{record.levelname}{_ANSI_RESET} "
            f"{_ANSI_NAME}[{record.name}]{_ANSI_RESET}{ctx}:  "
            f"{record.getMessage()}"
        )
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class JsonFormatter(logging.Formatter):
    """One JSON object per record, safe for log aggregators."""

    default_time_format = "%Y-%m-%dT%H:%M:%S"
    # Override stdlib's ``"%s,%03d"`` so we emit strict ISO-8601 with a
    # ``.`` separator — what log aggregators (Loki, Datadog) expect.
    default_msec_format = "%s.%03d"

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "oid": getattr(record, "oid", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOGRECORD_ATTRS or key in payload:
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


class HealthEndpointFilter(logging.Filter):
    """Drop noisy uvicorn.access records for periodic probes.

    Uvicorn emits access records whose ``record.args`` is the
    ``(client, method, path, version, status)`` tuple; anything else
    (custom handler, non-access use) passes through untouched.
    """

    _PATHS = ("/health", "/manifest.webmanifest", "/favicon.ico")

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) < 3:
            return True
        path = args[2]
        if not isinstance(path, str):
            return True
        return not path.startswith(self._PATHS)


def _resolve_level() -> str:
    from app.env_vars_manager import EnvVarsManager

    raw = EnvVarsManager.get_env_var("LOGGING_LEVEL", "warning").upper()
    if raw not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        raw = "WARNING"
    return raw


def _resolve_format() -> str:
    from app.env_vars_manager import EnvVarsManager

    raw = EnvVarsManager.get_env_var("LOG_FORMAT", "text").strip().lower()
    return "json" if raw == "json" else "text"


def build_dict_config(
    level: str | None = None, fmt: str | None = None,
) -> dict:
    """Return a fully-resolved :func:`dictConfig` payload.

    Exposed so tests (and ``uvicorn.run(log_config=…)``) can consume the
    same config object the app uses.
    """
    level = (level or _resolve_level()).upper()
    fmt = fmt or _resolve_format()

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "text": {"()": "app.logging_config.TextFormatter"},
            "json": {"()": "app.logging_config.JsonFormatter"},
        },
        "filters": {
            "context": {"()": "app.logging_context.ContextFilter"},
            "health": {"()": "app.logging_config.HealthEndpointFilter"},
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": fmt,
                "filters": ["context"],
            },
            "access": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": fmt,
                "filters": ["context", "health"],
            },
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["default"], "level": level, "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["default"], "level": level, "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["access"], "level": "INFO", "propagate": False,
            },
        },
        "root": {"handlers": ["default"], "level": level},
    }


def setup_logging() -> None:
    """Apply the dict config to the ``logging`` module."""
    logging.config.dictConfig(build_dict_config())


def get_uvicorn_log_config() -> dict:
    """Return the dict suitable for ``uvicorn.run(log_config=…)``."""
    return build_dict_config()
