"""
Generic asset scanner: finds and downloads any directly-linked or embedded file
from a page — audio tags, video tags, source tags, and arbitrary href links.
This complements yt-dlp (for platforms) and the specialized extractors.
"""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import urljoin, urlparse

import httpx
from playwright.async_api import Page

from models import ExtractedFile


# Extensions we actively scan for beyond the other extractors
_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".opus", ".weba"}
_VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".m4v", ".ogv", ".ts", ".m3u8"}
_ALL_EXTS = _AUDIO_EXTS | _VIDEO_EXTS


async def extract_generic_media(
    page: Page,
    url: str,
    output_dir: Path,
    content_types: list[str],
    cookies: list[dict] | None = None,
) -> AsyncGenerator[ExtractedFile, None]:
    """
    Scan the DOM for <audio>, <video>, <source> tags and any <a href> pointing
    to audio/video files. Downloads them directly without yt-dlp.
    """
    want_video = "videos" in content_types or "all" in content_types
    want_audio = "audio" in content_types or "all" in content_types

    if not want_video and not want_audio:
        return

    await page.goto(url, wait_until="networkidle", timeout=60000)

    media_urls: set[str] = set()

    # <audio src> and <video src>
    for tag in ["audio", "video"]:
        els = await page.query_selector_all(tag)
        for el in els:
            src = await el.get_attribute("src")
            if src:
                media_urls.add(urljoin(url, src))

    # <source src> (inside <audio>/<video>/<picture>)
    sources = await page.query_selector_all("source[src]")
    for el in sources:
        src = await el.get_attribute("src")
        if src:
            media_urls.add(urljoin(url, src))

    # <a href> pointing to media files
    links = await page.query_selector_all("a[href]")
    for el in links:
        href = await el.get_attribute("href")
        if href:
            full = urljoin(url, href)
            ext = Path(urlparse(full).path).suffix.lower()
            if ext in _ALL_EXTS:
                media_urls.add(full)

    # Filter by wanted types
    filtered: set[str] = set()
    for mu in media_urls:
        ext = Path(urlparse(mu).path).suffix.lower()
        if want_audio and ext in _AUDIO_EXTS:
            filtered.add(mu)
        if want_video and ext in _VIDEO_EXTS:
            filtered.add(mu)

    if not filtered:
        return

    headers = {"Referer": url}
    if cookies:
        headers["Cookie"] = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    seen: set[str] = set()

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=120) as client:
        for media_url in filtered:
            parsed_path = Path(urlparse(media_url).path)
            ext = parsed_path.suffix.lower()
            stem = re.sub(r'[^\w\-]', '_', parsed_path.stem)[:60] or "media"
            filename = _unique(stem + ext, seen)
            seen.add(filename)

            try:
                async with client.stream("GET", media_url) as resp:
                    if resp.status_code != 200:
                        continue
                    ct = resp.headers.get("content-type", "application/octet-stream")
                    dest = output_dir / filename
                    total = 0
                    with open(dest, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            total += len(chunk)

                yield ExtractedFile(
                    filename=filename,
                    url=media_url,
                    content_type=ct,
                    size_bytes=total,
                    local_path=str(dest),
                )
            except Exception:
                continue


def _unique(name: str, seen: set[str]) -> str:
    if name not in seen:
        return name
    stem = Path(name).stem
    suffix = Path(name).suffix
    i = 1
    while f"{stem}_{i}{suffix}" in seen:
        i += 1
    return f"{stem}_{i}{suffix}"
