"""Generates small preview thumbnails for downloaded images and videos,
returned as `data:image/jpeg;base64,...` URIs so the UI can render them
directly in an <img> tag with zero extra API endpoints or files on disk.

Previously `ExtractedFile.thumbnail` was only ever populated by yt-dlp with
a *remote* URL to the platform's own thumbnail — every other extractor left
it null. This module actually generates one locally for any downloaded
image or video.
"""
from __future__ import annotations

import asyncio
import base64
import io
import shutil
import tempfile
from pathlib import Path
from typing import Optional

_THUMB_SIZE = (160, 160)


async def generate_thumbnail(path: Path, category: str) -> Optional[str]:
    if category == "image":
        return await asyncio.to_thread(_thumb_from_image, path)
    if category == "video":
        return await _thumb_from_video(path)
    return None


def _thumb_from_image(path: Path) -> Optional[str]:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail(_THUMB_SIZE)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=60)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


async def _thumb_from_video(path: Path) -> Optional[str]:
    if not shutil.which("ffmpeg"):
        return None
    with tempfile.TemporaryDirectory() as td:
        frame_path = Path(td) / "frame.jpg"
        cmd = [
            "ffmpeg", "-y", "-ss", "1", "-i", str(path),
            "-frames:v", "1", "-vf", "scale=160:-1",
            str(frame_path),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=30)
        except Exception:
            return None
        if not frame_path.exists():
            return None
        try:
            data = frame_path.read_bytes()
            return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")
        except OSError:
            return None
