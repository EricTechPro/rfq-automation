"""
Structured Logging

Dual-format logger factory: JSON for production, colored pretty-print for local dev.
Format controlled by LOG_FORMAT env var: "json" (default) or "pretty".
Level controlled by LOG_LEVEL env var (default: INFO).
Supports request-scoped correlation IDs via contextvars.
"""

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

# ── Correlation ID propagation ──────────────────────────────────────

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def set_request_id(rid: str) -> None:
    _request_id.set(rid)


def get_request_id() -> str:
    return _request_id.get()


# ── Formatters ──────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """Format log records as JSON lines for production."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include correlation ID when available
        rid = get_request_id()
        if rid:
            log_entry["request_id"] = rid
        # Include structured extra fields
        extras = getattr(record, "_structured_extras", None)
        if extras:
            log_entry.update(extras)
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


# ANSI color codes
_COLORS = {
    "DEBUG": "\033[36m",     # cyan
    "INFO": "\033[32m",      # green
    "WARNING": "\033[33m",   # yellow
    "ERROR": "\033[31m",     # red
    "CRITICAL": "\033[1;31m",  # bold red
}
_RESET = "\033[0m"
_DIM = "\033[2m"


class PrettyFormatter(logging.Formatter):
    """Colored, human-readable formatter for local development."""

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, "")
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        rid = get_request_id()
        rid_str = f" [{rid}]" if rid else ""

        parts = [
            f"{_DIM}{ts}{_RESET}",
            f"{color}{record.levelname:<7}{_RESET}",
            f"{_DIM}{record.name}{_RESET}{rid_str}",
            record.getMessage(),
        ]

        # Append structured extras as key=value
        extras = getattr(record, "_structured_extras", None)
        if extras:
            kv = " ".join(f"{color}{k}{_RESET}={v}" for k, v in extras.items())
            parts.append(kv)

        line = " ".join(parts)
        if record.exc_info and record.exc_info[0] is not None:
            line += "\n" + self.formatException(record.exc_info)
        return line


# ── StructuredLogger wrapper ────────────────────────────────────────

class StructuredLogger:
    """Wrapper that accepts **kwargs as structured extra fields.

    Usage:
        logger.info("Scrape complete", nsn="5306-00-373-3291", duration_ms=450)
    """

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    # Proxy standard attributes so callers can do logger.level, logger.name, etc.
    def __getattr__(self, name):
        return getattr(self._logger, name)

    def _log(self, level: int, msg: str, args, kwargs):
        extras = {k: v for k, v in kwargs.items() if k not in ("exc_info", "stack_info", "stacklevel")}
        std_kwargs = {k: v for k, v in kwargs.items() if k in ("exc_info", "stack_info", "stacklevel")}
        record = self._logger.makeRecord(
            self._logger.name, level, "(unknown)", 0, msg, args, None,
        )
        if extras:
            record._structured_extras = extras
        # Re-handle exc_info if provided
        if std_kwargs.get("exc_info"):
            record.exc_info = sys.exc_info() if std_kwargs["exc_info"] is True else std_kwargs["exc_info"]
        self._logger.handle(record)

    def debug(self, msg, *args, **kwargs):
        if self._logger.isEnabledFor(logging.DEBUG):
            self._log(logging.DEBUG, msg, args, kwargs)

    def info(self, msg, *args, **kwargs):
        if self._logger.isEnabledFor(logging.INFO):
            self._log(logging.INFO, msg, args, kwargs)

    def warning(self, msg, *args, **kwargs):
        if self._logger.isEnabledFor(logging.WARNING):
            self._log(logging.WARNING, msg, args, kwargs)

    def error(self, msg, *args, **kwargs):
        if self._logger.isEnabledFor(logging.ERROR):
            self._log(logging.ERROR, msg, args, kwargs)

    def critical(self, msg, *args, **kwargs):
        if self._logger.isEnabledFor(logging.CRITICAL):
            self._log(logging.CRITICAL, msg, args, kwargs)


# ── Factory ─────────────────────────────────────────────────────────

def get_logger(name: str) -> StructuredLogger:
    """
    Get a configured logger for the given module.

    Respects LOG_FORMAT ("json" or "pretty") and LOG_LEVEL env vars.
    Returns a StructuredLogger that supports both:
      - Traditional: logger.info("msg %s", val)
      - Structured:  logger.info("msg", key=val)
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, level, logging.INFO))

        handler = logging.StreamHandler(sys.stderr)
        fmt = os.getenv("LOG_FORMAT", "json").lower()
        if fmt == "pretty":
            handler.setFormatter(PrettyFormatter())
        else:
            handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

        logger.propagate = False

    return StructuredLogger(logger)
