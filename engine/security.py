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

# (offset, magic bytes, category) — enough of a signature table to catch the
# common "this .jpg is actually an .html error page" / spoofed-extension case
# without pulling in a heavyweight dependency like python-magic.
_SIGNATURES: list[tuple[int, bytes, str]] = [
    (0, b"\xff\xd8\xff", "image"),                    # JPEG
    (0, b"\x89PNG\r\n\x1a\n", "image"),                # PNG
    (0, b"GIF87a", "image"),
    (0, b"GIF89a", "image"),
    (0, b"RIFF", "image"),                             # also WEBP/WAV/AVI container — see below
    (0, b"BM", "image"),                               # BMP
    (0, b"%PDF-", "document"),
    (0, b"PK\x03\x04", "archive"),                     # zip and zip-based (docx/xlsx/pptx/jar/apk)
    (0, b"\x1f\x8b", "archive"),                        # gzip
    (0, b"7z\xbc\xaf\x27\x1c", "archive"),
    (0, b"Rar!\x1a\x07", "archive"),
    (0, b"\x00\x00\x00\x18ftyp", "video"),              # mp4 (generic ftyp box)
    (0, b"\x00\x00\x00\x1cftyp", "video"),
    (0, b"\x1aE\xdf\xa3", "video"),                     # webm/mkv (EBML)
    (0, b"ID3", "audio"),                               # mp3 with ID3 tag
    (0, b"OggS", "audio"),
    (0, b"fLaC", "audio"),
    (0, b"<?xml", "text"),
    (0, b"<!DOCTYPE html", "text"),
    (0, b"<html", "text"),
]

# archive/video/image all legitimately start with RIFF (WEBP, WAV, AVI) — treat
# as a wildcard match against any of those three categories instead of a hard
# mismatch, since we can't cheaply disambiguate without parsing the container.
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
                return "riff"  # caller treats this as a wildcard, see verify_mime()
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
        return True  # SVG is XML/text at the byte level
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
        # clamscan/clamdscan exit codes: 0 = clean, 1 = infected, 2 = error
        if proc.returncode == 0:
            return True
        if proc.returncode == 1:
            return False
        return None  # scan error — don't penalize the file for our tooling failing
    except Exception:
        return None
