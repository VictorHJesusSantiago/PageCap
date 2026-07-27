"""Resolves a saved CredentialProfile by name so a job's AuthConfig can
reference reusable per-domain logins instead of repeating username/password
in every request. Profiles live in the same SQLite file as jobs (see
stores.py); this module just knows how to look one up by name.

The database path comes from `config.settings`, not from a second `os.getenv`
call — reading the variable independently meant that pointing PAGECAP_DB_PATH
elsewhere gave this module and api.py different files (and, once secrets were
encrypted, different keys), so a saved profile silently stopped resolving.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from config import settings
from models import CredentialProfile


@lru_cache(maxsize=1)
def _credential_store():
    """One store instance per process. `make_stores` opens no long-lived
    connection, but it does run CREATE TABLE IF NOT EXISTS and build a
    SecretBox, neither of which needs repeating on every lookup."""
    from stores import make_stores

    credentials, _templates, _schedules = make_stores(settings.db_path)
    return credentials


async def resolve_credential_profile(profile_name: Optional[str]) -> Optional[CredentialProfile]:
    """Looks up a stored CredentialProfile by name. Returns None if no
    profile name was given or none is stored under that name."""
    if not profile_name:
        return None
    return await _credential_store().get(profile_name)
