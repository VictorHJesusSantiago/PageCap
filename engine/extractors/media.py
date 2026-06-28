"""Extract videos and audio from a URL using yt-dlp."""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import AsyncGenerator, Optional
from urllib.parse import urlparse

from models import ExtractedFile


async def extract_media(
    url: str,
    output_dir: Path,
    content_types: list[str],
    quality: str = "best",
    cookies_file: Optional[Path] = None,
    progress_cb=None,
) -> AsyncGenerator[ExtractedFile, None]:
    """
    Use yt-dlp to download videos and/or audio from the given URL.
    Yields ExtractedFile for each downloaded item.
    """
    want_video = "videos" in content_types or "all" in content_types
    want_audio = "audio" in content_types or "all" in content_types

    if not want_video and not want_audio:
        return

    base_cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--print-json"]

    if cookies_file and cookies_file.exists():
        base_cmd += ["--cookies", str(cookies_file)]

    tasks = []
    if want_video:
        fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" if quality == "best" else "worst"
        tasks.append(("video", fmt, "mp4"))
    if want_audio and not want_video:
        tasks.append(("audio", "bestaudio/best", "mp3"))

    for kind, fmt, ext in tasks:
        out_tmpl = str(output_dir / f"%(title)s_%(id)s.{ext}")
        cmd = base_cmd + [
            "--format", fmt,
            "--output", out_tmpl,
            "--no-playlist" if kind == "audio" else "--yes-playlist",
        ]
        if kind == "audio":
            cmd += ["--extract-audio", "--audio-format", "mp3"]

        cmd.append(url)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        downloaded_files: list[Path] = []
        pre_existing = {f for f in output_dir.glob(f"*.{ext}")}
        async for line in proc.stdout:
            try:
                info = json.loads(line.decode())
                title = info.get("title", "media")
                file_id = info.get("id", "")
                filename = f"{_safe_name(title)}_{file_id}.{ext}"
                dest = output_dir / filename
                if dest.exists():
                    downloaded_files.append(dest)
                    yield ExtractedFile(
                        filename=dest.name,
                        url=info.get("webpage_url", url),
                        content_type="video/mp4" if kind == "video" else "audio/mpeg",
                        size_bytes=dest.stat().st_size,
                        local_path=str(dest),
                        thumbnail=info.get("thumbnail"),
                    )
            except (json.JSONDecodeError, KeyError):
                continue

        await proc.wait()

        # Fallback: yield only files that appeared during this yt-dlp run
        if not downloaded_files:
            for f in output_dir.glob(f"*.{ext}"):
                if f not in pre_existing:
                    yield ExtractedFile(
                        filename=f.name,
                        url=url,
                        content_type="video/mp4" if ext == "mp4" else "audio/mpeg",
                        size_bytes=f.stat().st_size,
                        local_path=str(f),
                    )


def _safe_name(s: str) -> str:
    return re.sub(r'[^\w\-.]', '_', s)[:80]
