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
from pathlib import Path
from typing import AsyncGenerator, Callable

from config import settings
from logging_config import get_logger
from models import ExtractedFile

log = get_logger("plugins")

PluginExtractor = Callable[..., AsyncGenerator[ExtractedFile, None]]


def load_plugins() -> list[tuple[str, PluginExtractor]]:
    """Loads every `*.py` file in PAGECAP_PLUGINS_DIR that defines a
    top-level `extract` callable. Returns (plugin_name, extract_fn) pairs.

    SECURITY: these files are executed in-process with the engine's full
    privileges. The directory is trusted input, equivalent to installing a
    Python package — never point it at anything user-supplied or downloaded.
    """
    dir_path = settings.plugins_dir
    if not dir_path or not dir_path.is_dir():
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
            else:
                log.warning(
                    "Plugin defines no top-level `extract` callable — skipped",
                    extra={"extra_fields": {"plugin": py_file.name}},
                )
        except Exception as e:
            log.error(
                "Plugin failed to import",
                extra={"extra_fields": {"plugin": py_file.name, "error": str(e)}},
            )
            continue
    return loaded
