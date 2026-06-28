"""Shared utility helpers for the extraction engine."""
from __future__ import annotations

from pathlib import Path


def unique_filename(name: str, seen: set[str]) -> str:
    """Return `name` if unseen, otherwise append _1, _2, … until unique."""
    if name not in seen:
        return name
    stem = Path(name).stem
    suffix = Path(name).suffix
    i = 1
    while f"{stem}_{i}{suffix}" in seen:
        i += 1
    return f"{stem}_{i}{suffix}"


def build_cookie_header(cookies: list[dict]) -> str:
    """Serialise Playwright cookie dicts into an HTTP Cookie header value.

    Strips CR/LF from each name and value to prevent header injection.
    """
    pairs = []
    for c in cookies:
        name  = str(c.get("name",  "")).replace("\r", "").replace("\n", "")
        value = str(c.get("value", "")).replace("\r", "").replace("\n", "")
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)
