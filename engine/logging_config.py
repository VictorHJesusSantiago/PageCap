"""Structured (JSON) logging setup. Level is configurable via PAGECAP_LOG_LEVEL
(default INFO); output goes to stderr as one JSON object per line, which is
what every log aggregator (journald, Docker, CloudWatch, etc.) expects.

This does NOT change PageCap's existing per-file resilience pattern —
extractors still swallow individual download failures and continue — it just
gives those failures (and server lifecycle events) a durable, greppable trail
instead of vanishing into job.message strings that die with the job.

Correlation: `request_id` and `job_id` are ambient (contextvars), so a log line
emitted deep inside an extractor carries the identifiers of the request and job
that caused it without every function having to thread them through its
signature. Use `log_context(...)` to bind them.
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from contextlib import contextmanager
from typing import Optional

_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
_job_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("job_id", default=None)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = _request_id.get()
        if request_id:
            payload["request_id"] = request_id
        job_id = _job_id.get()
        if job_id:
            payload["job_id"] = job_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    from config import settings

    level = getattr(logging, settings.log_level, logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())

    root = logging.getLogger("pagecap")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"pagecap.{name}")


def set_request_id(value: Optional[str]) -> None:
    _request_id.set(value)


def set_job_id(value: Optional[str]) -> None:
    _job_id.set(value)


def current_request_id() -> Optional[str]:
    return _request_id.get()


@contextmanager
def log_context(*, request_id: Optional[str] = None, job_id: Optional[str] = None):
    """Binds correlation identifiers for the duration of the block, restoring
    whatever was bound before on the way out."""
    tokens = []
    if request_id is not None:
        tokens.append((_request_id, _request_id.set(request_id)))
    if job_id is not None:
        tokens.append((_job_id, _job_id.set(job_id)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
