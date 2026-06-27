"""
Screen + audio recording extractor.

Uses ffmpeg to record what is actually rendered on screen while Playwright
plays the page. This is the fallback for content that cannot be intercepted
at the network level (e.g., some DRM implementations that don't block screen
capture at the OS level, Flash-era players, obfuscated streams, etc.).

Requirements:
  - ffmpeg in PATH
  - Linux: Xvfb + pulseaudio (for headless virtual display + virtual audio)
  - Windows: uses GDI desktop capture (gdigrab)
  - macOS: uses avfoundation

Usage note: records a real-time window, so duration must be specified or
the user triggers stop. Default: records for `duration` seconds.
"""
from __future__ import annotations

import asyncio
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import AsyncGenerator, Optional

from playwright.async_api import Page, BrowserContext

from models import ExtractedFile


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _ffmpeg_input_args() -> list[str]:
    """Return platform-specific ffmpeg screen capture input arguments."""
    system = platform.system()
    if system == "Linux":
        display = ":99"  # Xvfb display
        return [
            "-f", "x11grab",
            "-video_size", "1280x900",
            "-framerate", "30",
            "-i", display,
            "-f", "pulse",
            "-i", "default",
        ]
    elif system == "Windows":
        return [
            "-f", "gdigrab",
            "-framerate", "30",
            "-i", "desktop",
            "-f", "dshow",
            "-i", "audio=virtual-audio-capturer",   # requires VB-Cable or similar
        ]
    elif system == "Darwin":  # macOS
        return [
            "-f", "avfoundation",
            "-framerate", "30",
            "-capture_cursor", "0",
            "-i", "1:0",   # screen:audio — adjust device indices if needed
        ]
    else:
        return ["-f", "x11grab", "-video_size", "1280x900", "-framerate", "30", "-i", ":0"]


async def extract_screen_record(
    page: Page,
    context: BrowserContext,
    url: str,
    output_dir: Path,
    duration: int = 60,
    wait_before: int = 3,
) -> AsyncGenerator[ExtractedFile, None]:
    """
    Navigate to URL, wait for content to start, record screen for `duration` seconds.
    Yields one ExtractedFile (the recording).
    """
    if not _has_ffmpeg():
        raise RuntimeError(
            "ffmpeg não encontrado no PATH. Instale em https://ffmpeg.org/download.html"
        )

    filename = f"screen_record_{int(time.time())}.mp4"
    dest = output_dir / filename

    input_args = _ffmpeg_input_args()

    cmd = [
        "ffmpeg", "-y",
        *input_args,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        str(dest),
    ]

    # Navigate first, wait for page to settle
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
    except Exception:
        pass

    # Try to auto-play (click play buttons if found)
    for sel in ['button[aria-label*="play" i]', 'button[class*="play" i]', '[data-testid*="play" i]', ".play-button", "#play-button"]:
        try:
            el = await page.query_selector(sel)
            if el:
                await el.click()
                break
        except Exception:
            continue

    await asyncio.sleep(wait_before)

    # Start recording
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    await asyncio.sleep(duration + 2)

    try:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=10)
    except Exception:
        pass

    if dest.exists() and dest.stat().st_size > 10_000:
        yield ExtractedFile(
            filename=filename,
            url=url,
            content_type="video/mp4",
            size_bytes=dest.stat().st_size,
            local_path=str(dest),
        )


async def extract_screen_record_interactive(
    page: Page,
    url: str,
    output_dir: Path,
    stop_event: asyncio.Event,
) -> AsyncGenerator[ExtractedFile, None]:
    """
    Records until stop_event is set (used when duration is unknown).
    """
    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg não encontrado no PATH.")

    filename = f"screen_record_{int(time.time())}.mp4"
    dest = output_dir / filename
    input_args = _ffmpeg_input_args()

    cmd = ["ffmpeg", "-y", *input_args, "-c:v", "libx264", "-preset", "ultrafast",
           "-crf", "23", "-c:a", "aac", "-b:a", "128k", str(dest)]

    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
    except Exception:
        pass

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )

    await stop_event.wait()

    try:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=15)
    except Exception:
        pass

    if dest.exists() and dest.stat().st_size > 10_000:
        yield ExtractedFile(
            filename=filename, url=url, content_type="video/mp4",
            size_bytes=dest.stat().st_size, local_path=str(dest),
        )
