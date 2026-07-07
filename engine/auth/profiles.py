"""Resolves a saved CredentialProfile by name so a job's AuthConfig can
reference reusable per-domain logins instead of repeating username/password
in every request. Profiles live in the same SQLite file as jobs (see
stores.py); this module just knows how to look one up by name."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from models import CredentialProfile

_DB_PATH = Path(os.getenv("PAGECAP_DB_PATH", "pagecap.db"))


async def resolve_credential_profile(profile_name: Optional[str]) -> Optional[CredentialProfile]:
    """Looks up a stored CredentialProfile by name. Returns None if no
    profile name was given or none is stored under that name."""
    if not profile_name:
        return None
    from stores import make_stores

    credentials, _templates, _schedules = make_stores(_DB_PATH)
    return await credentials.get(profile_name)
