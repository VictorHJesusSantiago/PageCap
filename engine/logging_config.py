"""Structured (JSON) logging setup. Level is configurable via PAGECAP_LOG_LEVEL
(default INFO); output goes to stderr as one JSON object per line, which is
what every log aggregator (journald, Docker, CloudWatch, etc.) expects.

This does NOT change PageCap's existing per-file resilience pattern —
extractors still swallow individual download failures and continue — it just
gives those failures (and server lifecycle events) a durable, greppable trail
instead of vanishing into job.message strings that die with the job.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    level_name = os.getenv("PAGECAP_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())

    root = logging.getLogger("pagecap")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"pagecap.{name}")
