"""Single source of truth for every environment-derived setting.

Before this module each consumer read `os.getenv` on its own — `api.py` and
`auth/profiles.py` both resolved PAGECAP_DB_PATH independently, so pointing the
database somewhere else silently gave the two of them different files (and, once
secrets were encrypted, different keys). Everything now resolves through one
frozen object.

Values are read once at import. Tests that need a different configuration
re-import the module tree (see tests/test_api.py::_fresh_api) rather than
mutating a live settings object, which keeps the "config is immutable at
runtime" property that 12-factor III assumes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    db_path: Path
    downloads_dir: Path
    job_ttl_seconds: float
    eviction_interval_seconds: float
    persist_interval_seconds: float

    api_token: Optional[str]
    require_auth: bool
    allow_null_origin: bool
    extra_cors_origins: tuple[str, ...]
    rate_limit_per_minute: int

    scheduler_interval_seconds: float
    shutdown_drain_seconds: float

    plugins_dir: Optional[Path]
    log_level: str

    @property
    def token_file(self) -> Path:
        """Where an auto-generated API token is persisted, so the CLI and any
        local script can read the same token the server is enforcing."""
        return self.db_path.parent / ".pagecap_token"

    @property
    def key_file(self) -> Path:
        """Encryption key for secrets at rest (see crypto_box.py)."""
        return self.db_path.parent / ".pagecap_key"


def load() -> Settings:
    db_path = Path(os.getenv("PAGECAP_DB_PATH", "pagecap.db"))
    plugins_dir = os.getenv("PAGECAP_PLUGINS_DIR")
    return Settings(
        db_path=db_path,
        downloads_dir=Path(os.getenv("PAGECAP_DOWNLOADS_DIR", "downloads")),
        job_ttl_seconds=_float("PAGECAP_JOB_TTL_SECONDS", 3 * 24 * 3600),
        eviction_interval_seconds=_float("PAGECAP_EVICTION_INTERVAL_SECONDS", 3600),
        persist_interval_seconds=_float("PAGECAP_PERSIST_INTERVAL_SECONDS", 2.0),
        api_token=os.getenv("PAGECAP_API_TOKEN") or None,
        require_auth=_flag("PAGECAP_REQUIRE_AUTH", True),
        allow_null_origin=_flag("PAGECAP_ALLOW_NULL_ORIGIN", False),
        extra_cors_origins=tuple(
            o for o in (p.strip() for p in os.getenv("PAGECAP_CORS_ORIGINS", "").split(","))
            if o and o != "*"
        ),
        rate_limit_per_minute=_int("PAGECAP_RATE_LIMIT_PER_MINUTE", 0),
        scheduler_interval_seconds=_float("PAGECAP_SCHEDULER_INTERVAL_SECONDS", 30),
        shutdown_drain_seconds=_float("PAGECAP_SHUTDOWN_DRAIN_SECONDS", 20.0),
        plugins_dir=Path(plugins_dir) if plugins_dir else None,
        log_level=os.getenv("PAGECAP_LOG_LEVEL", "INFO").upper(),
    )


settings = load()
