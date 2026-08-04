"""Optional, best-effort file-safety checks applied after a download completes:
magic-byte sniffing (is the file actually what its extension/Content-Type
claim?) and an opt-in ClamAV scan. Neither check blocks PageCap's core
purpose (fetching arbitrary web content) — both only annotate or, for
ClamAV, delete a file the user explicitly asked to be scanned.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Optional

from file_types import category_of

_SIGNATURES: list[tuple[int, bytes, str]] = [
    (0, b"\xff\xd8\xff", "image"),
    (0, b"\x89PNG\r\n\x1a\n", "image"),
    (0, b"GIF87a", "image"),
    (0, b"GIF89a", "image"),
    (0, b"RIFF", "image"),
    (0, b"BM", "image"),
    (0, b"%PDF-", "document"),
    (0, b"PK\x03\x04", "archive"),
    (0, b"\x1f\x8b", "archive"),
    (0, b"7z\xbc\xaf\x27\x1c", "archive"),
    (0, b"Rar!\x1a\x07", "archive"),
    (0, b"\x00\x00\x00\x18ftyp", "video"),
    (0, b"\x00\x00\x00\x1cftyp", "video"),
    (0, b"\x1aE\xdf\xa3", "video"),
    (0, b"ID3", "audio"),
    (0, b"OggS", "audio"),
    (0, b"fLaC", "audio"),
    (0, b"<?xml", "text"),
    (0, b"<!DOCTYPE html", "text"),
    (0, b"<html", "text"),
]

_RIFF_CATEGORIES = {"image", "audio", "video"}


def sniff_category(path: Path) -> Optional[str]:
    """Best-effort category guess from the file's leading bytes. Returns None
    if no signature matched (not necessarily suspicious — many text/data/font
    formats have no reliable magic number)."""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
    except OSError:
        return None

    for offset, magic, category in _SIGNATURES:
        if head[offset:offset + len(magic)] == magic:
            if magic == b"RIFF":
                return "riff"
            return category
    return None


def verify_mime(declared_ext: str, path: Path) -> bool:
    """Returns True when the file's actual bytes are consistent with its
    declared extension's category (or when sniffing was inconclusive — this
    is a spoofing *detector*, not a strict allowlist)."""
    sniffed = sniff_category(path)
    if sniffed is None:
        return True
    if sniffed == "riff":
        return category_of(declared_ext) in _RIFF_CATEGORIES
    declared_category = category_of(declared_ext)
    if declared_category in ("vector",) and sniffed == "text":
        return True
    return sniffed == declared_category


def _clamav_binary() -> Optional[str]:
    for name in ("clamdscan", "clamscan"):
        path = shutil.which(name)
        if path:
            return path
    return None


async def clamav_scan(path: Path) -> Optional[bool]:
    """Runs the locally installed ClamAV CLI against `path`. Returns True if
    clean, False if infected, or None if ClamAV isn't installed (in which
    case the caller should treat the scan as skipped, not failed)."""
    binary = _clamav_binary()
    if not binary:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            binary, "--no-summary", str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode == 0:
            return True
        if proc.returncode == 1:
            return False
        return None
    except Exception:
        return None
