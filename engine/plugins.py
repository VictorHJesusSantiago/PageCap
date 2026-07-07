"""Minimal plugin system for custom extractors.

Drop a `.py` file into the directory pointed to by the `PAGECAP_PLUGINS_DIR`
env var, exposing:

    async def extract(page, url, output_dir, **kwargs) -> AsyncGenerator[ExtractedFile, None]:
        yield ExtractedFile(...)

and it runs as an extra extraction stage automatically, after the built-in
universal scanner — no core code changes needed. A broken or misbehaving
plugin is isolated (import errors and exceptions during extraction are
caught) so it can never take down a job or the server.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import AsyncGenerator, Callable

from models import ExtractedFile

PluginExtractor = Callable[..., AsyncGenerator[ExtractedFile, None]]


def load_plugins() -> list[tuple[str, PluginExtractor]]:
    """Loads every `*.py` file in PAGECAP_PLUGINS_DIR that defines a
    top-level `extract` callable. Returns (plugin_name, extract_fn) pairs."""
    plugins_dir = os.getenv("PAGECAP_PLUGINS_DIR")
    if not plugins_dir:
        return []
    dir_path = Path(plugins_dir)
    if not dir_path.is_dir():
        return []

    loaded: list[tuple[str, PluginExtractor]] = []
    for py_file in sorted(dir_path.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"pagecap_plugin_{py_file.stem}", py_file)
            if not spec or not spec.loader:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            extract_fn = getattr(module, "extract", None)
            if callable(extract_fn):
                loaded.append((py_file.stem, extract_fn))
        except Exception:
            continue
    return loaded
