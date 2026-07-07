"""Shared HTTP download helpers used by every extractor that streams files to
disk: bounded concurrency (a configurable worker pool instead of one download
at a time), retry with exponential backoff, HTTP Range resume across retries,
an optional hard byte-size cap, and a live progress callback. Also computes a
streaming SHA-256 so callers can dedupe by content."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Callable, Optional

import httpx

ProgressCallback = Callable[[int, Optional[int]], None]


class DownloadResult:
    __slots__ = ("bytes_written", "content_type", "sha256")

    def __init__(self, bytes_written: int, content_type: str, sha256: str):
        self.bytes_written = bytes_written
        self.content_type = content_type
        self.sha256 = sha256


class MaxSizeExceeded(Exception):
    pass


async def download_with_retry(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    min_size_bytes: int = 0,
    max_size_bytes: Optional[int] = None,
    max_retries: int = 2,
    backoff_base: float = 0.5,
    on_progress: Optional[ProgressCallback] = None,
) -> Optional[DownloadResult]:
    """Streams `url` to `dest`, retrying transient failures with exponential
    backoff (backoff_base * 2**attempt seconds).

    On a failed attempt, the partially-written file is kept (not deleted) and
    the next attempt resumes it with a `Range: bytes=<size>-` request instead
    of restarting from zero — meaningful for large video/archive downloads
    interrupted mid-stream. The sha256 hash is seeded from the bytes already
    on disk before hashing the newly-streamed continuation, so the final
    digest is always over the complete file regardless of how many resumes
    it took.

    Returns None if every attempt failed, the final file is smaller than
    `min_size_bytes`, or the server reports a size over `max_size_bytes`.
    """
    last_error: Optional[BaseException] = None

    for attempt in range(max_retries + 1):
        resume_from = dest.stat().st_size if dest.exists() else 0
        headers = {"Range": f"bytes={resume_from}-"} if resume_from > 0 else {}
        hasher = hashlib.sha256()
        if resume_from > 0:
            with open(dest, "rb") as existing:
                for chunk in iter(lambda: existing.read(1 << 20), b""):
                    hasher.update(chunk)

        total = resume_from
        content_type = "application/octet-stream"
        mode = "ab" if resume_from > 0 else "wb"

        try:
            async with client.stream("GET", url, headers=headers) as resp:
                resumed = resume_from > 0 and resp.status_code == 206
                if resp.status_code == 416:
                    # Server says our resumed range is already complete.
                    break
                if resp.status_code not in (200, 206):
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request, response=resp
                    )
                if resume_from > 0 and not resumed:
                    # Server ignored our Range header (200 = full body) —
                    # restart clean instead of appending a duplicate prefix.
                    total = 0
                    hasher = hashlib.sha256()
                    mode = "wb"

                content_type = resp.headers.get("content-type", content_type)
                content_length = resp.headers.get("content-length")
                declared_total = (
                    total + int(content_length) if content_length and content_length.isdigit() else None
                )

                with open(dest, mode) as f:
                    async for chunk in resp.aiter_bytes(65536):
                        f.write(chunk)
                        hasher.update(chunk)
                        total += len(chunk)
                        if max_size_bytes and total > max_size_bytes:
                            raise MaxSizeExceeded(f"{total} > {max_size_bytes} bytes")
                        if on_progress:
                            on_progress(total, declared_total)

            if total < min_size_bytes:
                dest.unlink(missing_ok=True)
                return None
            return DownloadResult(total, content_type, hasher.hexdigest())

        except MaxSizeExceeded:
            dest.unlink(missing_ok=True)
            return None  # exceeding the cap is not retried — it'll always exceed it
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                await asyncio.sleep(backoff_base * (2 ** attempt))
                continue
            dest.unlink(missing_ok=True)
            return None

    # Fell through via the 416 "already complete" branch.
    if dest.exists():
        with open(dest, "rb") as f:
            hasher = hashlib.sha256()
            total = 0
            for chunk in iter(lambda: f.read(1 << 20), b""):
                hasher.update(chunk)
                total += len(chunk)
        if total < min_size_bytes:
            dest.unlink(missing_ok=True)
            return None
        return DownloadResult(total, "application/octet-stream", hasher.hexdigest())
    return None


async def run_bounded(coros, concurrency: int):
    """Runs an iterable of coroutines with at most `concurrency` in flight at
    once, yielding each result as soon as it completes (order not preserved)."""
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _wrap(coro):
        async with sem:
            return await coro

    tasks = [asyncio.create_task(_wrap(c)) for c in coros]
    for finished in asyncio.as_completed(tasks):
        yield await finished


def sort_by_priority(items: list, key: Callable[[object], str], priority: list[str]) -> list:
    """Stable-sorts `items` so those whose key() is in `priority` come first,
    in priority-list order; everything else keeps its original relative order."""
    if not priority:
        return items
    rank = {cat: i for i, cat in enumerate(priority)}
    return sorted(items, key=lambda it: rank.get(key(it), len(priority)))
