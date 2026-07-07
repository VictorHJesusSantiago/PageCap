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
from utils import unique_filename, build_cookie_header
from download import download_with_retry, run_bounded


# Extensions we actively scan for beyond the other extractors
_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".opus", ".weba"}
_VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".m4v", ".ogv", ".ts", ".m3u8"}
_ALL_EXTS = _AUDIO_EXTS | _VIDEO_EXTS

# When a <video>/<audio> offers the same content in multiple codecs via
# sibling <source type="..."> tags (the standard HTML fallback pattern), we
# only want ONE of them — downloading every codec variant of the same clip
# wastes bandwidth/disk for no benefit. Lower index = more broadly playable /
# preferred; unlisted codecs sort last but are still downloaded as a fallback.
_CODEC_PRIORITY = [
    "video/mp4", "audio/mpeg", "audio/mp4",       # near-universal support
    "video/webm", "audio/ogg", "audio/webm",
    "video/ogg",
]


def _codec_rank(mime_type: str) -> int:
    base = mime_type.split(";")[0].strip().lower()
    try:
        return _CODEC_PRIORITY.index(base)
    except ValueError:
        return len(_CODEC_PRIORITY)


async def extract_generic_media(
    page: Page,
    url: str,
    output_dir: Path,
    content_types: list[str],
    cookies: list[dict] | None = None,
    concurrency: int = 6,
    max_retries: int = 2,
    wait_until: str = "networkidle",
    wait_timeout_ms: int = 60000,
) -> AsyncGenerator[ExtractedFile, None]:
    """
    Scan the DOM for <audio>, <video>, <source> tags and any <a href> pointing
    to audio/video files. Downloads them directly without yt-dlp.
    """
    want_video = "videos" in content_types or "all" in content_types
    want_audio = "audio" in content_types or "all" in content_types

    if not want_video and not want_audio:
        return

    await page.goto(url, wait_until=wait_until, timeout=wait_timeout_ms)

    media_urls: set[str] = set()

    # <audio src> and <video src>
    for tag in ["audio", "video"]:
        els = await page.query_selector_all(tag)
        for el in els:
            src = await el.get_attribute("src")
            if src:
                media_urls.add(urljoin(url, src))

    # <source src type="..."> — when a <video>/<audio> lists several codec
    # variants of the same clip via sibling <source> tags, pick the single
    # best-supported codec instead of downloading every variant.
    for parent_tag in ["video", "audio"]:
        parents = await page.query_selector_all(parent_tag)
        for parent in parents:
            children = await parent.query_selector_all("source[src]")
            candidates: list[tuple[int, str]] = []
            for child in children:
                src = await child.get_attribute("src")
                if not src:
                    continue
                mime = await child.get_attribute("type") or ""
                candidates.append((_codec_rank(mime), urljoin(url, src)))
            if candidates:
                candidates.sort(key=lambda c: c[0])
                media_urls.add(candidates[0][1])

    # <source src> not inside a <video>/<audio> parent (malformed/loose markup) —
    # fall back to grabbing all of them since there's no group to pick a "best" from.
    loose_sources = await page.query_selector_all(
        "source[src]:not(video source, audio source)"
    )
    for el in loose_sources:
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
        headers["Cookie"] = build_cookie_header(cookies)

    seen: set[str] = set()
    jobs: list[tuple[str, str, Path]] = []
    for media_url in filtered:
        parsed_path = Path(urlparse(media_url).path)
        ext = parsed_path.suffix.lower()
        stem = re.sub(r'[^\w\-]', '_', parsed_path.stem)[:60] or "media"
        filename = unique_filename(stem + ext, seen)
        seen.add(filename)
        jobs.append((media_url, filename, output_dir / filename))

    async with httpx.AsyncClient(
        headers=headers, follow_redirects=True, timeout=120,
        limits=httpx.Limits(max_connections=max(8, concurrency), max_keepalive_connections=4),
    ) as client:

        async def _fetch_one(media_url: str, filename: str, dest: Path) -> ExtractedFile | None:
            result = await download_with_retry(client, media_url, dest, max_retries=max_retries)
            if result is None:
                return None
            return ExtractedFile(
                filename=filename,
                url=media_url,
                content_type=result.content_type,
                size_bytes=result.bytes_written,
                local_path=str(dest),
                content_hash=result.sha256,
            )

        coros = (_fetch_one(u, f, d) for u, f, d in jobs)
        async for result in run_bounded(coros, concurrency):
            if result is not None:
                yield result


