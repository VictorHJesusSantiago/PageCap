"""API token resolution.

Auth is on by default (ADR-001). When the operator supplies no token we still
enforce one — generated on first run and persisted next to the database with
owner-only permissions — instead of falling back to "no auth". That keeps the
local-tool ergonomics (nothing to configure) without leaving the port open to
every web page the user visits.

The file is also what lets first-party callers that share the machine — the
CLI, an ad-hoc script — authenticate without the operator copying secrets
around: they read the same file the server wrote.
"""
from __future__ import annotations

import secrets
import stat
from pathlib import Path
from typing import Optional

from logging_config import get_logger

log = get_logger("auth")

_TOKEN_BYTES = 32


def _read(path: Path) -> Optional[str]:
    try:
        token = path.read_text(encoding="utf-8").strip()
        return token or None
    except OSError:
        return None


def _write(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8")
    try:
        # Owner read/write only. A no-op on Windows, where the inherited
        # directory ACL governs access instead.
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def resolve_api_token(
    configured: Optional[str], token_file: Path, require_auth: bool
) -> Optional[str]:
    """Returns the token the server should enforce, or None when auth is
    explicitly disabled.

    Precedence: PAGECAP_API_TOKEN > persisted token file > freshly generated.
    """
    if configured:
        return configured
    if not require_auth:
        log.warning(
            "PAGECAP_REQUIRE_AUTH is disabled — the API accepts unauthenticated "
            "requests. Any website the user visits can reach it. See ADR-001."
        )
        return None

    existing = _read(token_file)
    if existing:
        return existing

    token = secrets.token_urlsafe(_TOKEN_BYTES)
    _write(token_file, token)
    log.info(
        "Generated a new API token",
        extra={"extra_fields": {"token_file": str(token_file)}},
    )
    return token


def read_local_token(token_file: Path) -> Optional[str]:
    """For same-machine clients (CLI) that need the token the server enforces."""
    return _read(token_file)
