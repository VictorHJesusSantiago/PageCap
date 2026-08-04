"""
Network interception extractor.

Intercepts ALL HTTP requests made by the page during load and playback,
capturing any media URLs regardless of what player/framework is used.
Works with: custom players, HLS (.m3u8), MPEG-DASH (.mpd), direct MP4/WebM,
            blob URLs via Service Workers, chunked streams, etc.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import urlparse

import httpx
from playwright.async_api import Page, Request

from models import ExtractedFile
from utils import unique_filename, build_cookie_header
from download import download_with_retry, run_bounded


_MEDIA_EXTS = {
    ".mp4", ".webm", ".mkv", ".avi", ".mov", ".m4v", ".ogv",
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".opus",
    ".ts",
}

_MEDIA_MIME_PREFIXES = [
    "video/",
    "audio/",
    "application/x-mpegurl",
    "application/vnd.apple.mpegurl",
    "application/dash+xml",
    "application/octet-stream",
]

_PLAYLIST_EXTS = {".m3u8", ".m3u", ".mpd"}

_MIN_MEDIA_BYTES = 10_000


async def extract_via_network(
    page: Page,
    url: str,
    output_dir: Path,
    content_types: list[str],
    cookies: list[dict] | None = None,
    wait_seconds: int = 12,
    max_files: int = 500,
    concurrency: int = 6,
    max_retries: int = 2,
    wait_until: str = "networkidle",
    wait_timeout_ms: int = 60000,
) -> AsyncGenerator[ExtractedFile, None]:
    """
    Navigate to the URL, intercept every network request, collect media URLs,
    then download or mux them. Yields ExtractedFile per captured media item.
    """
    want_video = "videos" in content_types or "all" in content_types
    want_audio = "audio" in content_types or "all" in content_types
    if not want_video and not want_audio:
        return

    captured: dict[str, str] = {}

    def _on_request(request: Request):
        req_url = request.url
        if req_url.startswith("data:") or req_url.startswith("blob:"):
            return
        parsed = urlparse(req_url)
        ext = Path(parsed.path).suffix.lower().split("?")[0]
        rt = request.resource_type

        is_media_type = rt in ("media", "fetch", "xhr", "other")
        is_media_ext = ext in _MEDIA_EXTS or ext in _PLAYLIST_EXTS
        is_media_mime = any(
            (request.headers.get("accept", "") or "").lower().startswith(p)
            for p in _MEDIA_MIME_PREFIXES
        )

        if is_media_type and (is_media_ext or is_media_mime):
            captured[req_url] = rt

    page.on("request", _on_request)

    captured_responses: dict[str, str] = {}

    async def _on_response(response):
        ct = response.headers.get("content-type", "")
        if any(ct.lower().startswith(p) for p in _MEDIA_MIME_PREFIXES):
            captured_responses[response.url] = ct

    page.on("response", _on_response)

    try:
        await page.goto(url, wait_until=wait_until, timeout=wait_timeout_ms)
    except Exception:
        pass

    await asyncio.sleep(wait_seconds)

    page.remove_listener("request", _on_request)
    page.remove_listener("response", _on_response)

    all_urls = {**{u: "" for u in captured}, **{u: ct for u, ct in captured_responses.items()}}

    if not all_urls:
        return

    headers: dict[str, str] = {"Referer": url}
    if cookies:
        headers["Cookie"] = build_cookie_header(cookies)

    seen: set[str] = set()
    playlists: list[str] = []
    jobs: list[tuple[str, str, Path]] = []

    for media_url, mime in all_urls.items():
        if len(jobs) >= max_files:
            break
        parsed = urlparse(media_url)
        if parsed.scheme not in ("http", "https"):
            continue
        ext = Path(parsed.path.split("?")[0]).suffix.lower()

        if ext in _PLAYLIST_EXTS or "mpegurl" in mime or "dash" in mime:
            playlists.append(media_url)
            continue

        if ext not in _MEDIA_EXTS:
            continue

        is_video = ext in {".mp4", ".webm", ".mkv", ".avi", ".mov", ".m4v", ".ogv", ".ts"}
        is_audio = ext in {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".opus"}

        if is_video and not want_video:
            continue
        if is_audio and not want_audio:
            continue

        stem = re.sub(r'[^\w\-]', '_', Path(parsed.path).stem)[:60] or "media"
        filename = unique_filename(stem + ext, seen)
        seen.add(filename)
        jobs.append((media_url, filename, output_dir / filename))

    if jobs:
        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=120,
            limits=httpx.Limits(max_connections=max(8, concurrency), max_keepalive_connections=4),
        ) as client:

            async def _fetch_one(media_url: str, filename: str, dest: Path) -> ExtractedFile | None:
                result = await download_with_retry(
                    client, media_url, dest,
                    min_size_bytes=_MIN_MEDIA_BYTES, max_retries=max_retries,
                )
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

    for pl_url in playlists:
        parsed = urlparse(pl_url)
        if parsed.scheme not in ("http", "https"):
            continue
        ext = Path(parsed.path.split("?")[0]).suffix.lower()
        is_audio_pl = "audio" in pl_url.lower()

        if is_audio_pl and not want_audio:
            continue
        if not is_audio_pl and not want_video:
            continue

        out_ext = ".mp3" if is_audio_pl else ".mp4"
        stem = re.sub(r'[^\w\-]', '_', Path(parsed.path).stem)[:60] or "stream"
        filename = unique_filename(stem + out_ext, seen)
        seen.add(filename)
        dest = output_dir / filename

        result = await _ffmpeg_download(pl_url, dest, headers)
        if result and dest.exists() and dest.stat().st_size > _MIN_MEDIA_BYTES:
            ct = "video/mp4" if out_ext == ".mp4" else "audio/mpeg"
            yield ExtractedFile(
                filename=filename,
                url=pl_url,
                content_type=ct,
                size_bytes=dest.stat().st_size,
                local_path=str(dest),
            )


_FFMPEG_PROTOCOL_WHITELIST = "http,https,tcp,tls,crypto,httpproxy"


async def _ffmpeg_download(url: str, dest: Path, headers: dict[str, str]) -> bool:
    """Use ffmpeg to download and mux an HLS/DASH stream."""
    header_args: list[str] = []
    for k, v in headers.items():
        clean = str(v).replace("\r", "").replace("\n", "")
        header_args += ["-headers", f"{k}: {clean}\r\n"]

    cmd = [
        "ffmpeg", "-y",
        "-protocol_whitelist", _FFMPEG_PROTOCOL_WHITELIST,
        *header_args,
        "-i", url,
        "-c", "copy",
        "-movflags", "+faststart",
        str(dest),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=300)
        return proc.returncode == 0
    except Exception:
        return False


