"""
Universal file extractor.

Scans every attribute of every DOM element and every intercepted network
response for URLs pointing to any known file type, then downloads them.
This covers ALL 150+ registered types.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import urljoin, urlparse

import httpx
from playwright.async_api import Page

from models import ExtractedFile
from file_types import ALL_EXTENSIONS, mime_of, get_info

# HTML attributes that commonly contain resource URLs
_URL_ATTRS = [
    "src", "href", "data-src", "data-href", "data-url", "data-original",
    "data-lazy", "data-full", "data-download", "content", "action",
    "poster", "longdesc", "cite", "srcset", "data-srcset",
]

# Skip these URL patterns (tracking, analytics, tiny resources)
_SKIP_PATTERNS = [
    r"google-analytics\.com", r"googletagmanager\.com",
    r"facebook\.com/tr", r"pixel\.", r"beacon\.",
    r"\.min\.js$", r"\.min\.css$",
]
_SKIP_RE = re.compile("|".join(_SKIP_PATTERNS), re.IGNORECASE)

_MIN_SIZE = 512  # bytes — skip empty/stub responses


async def extract_universal(
    page: Page,
    url: str,
    output_dir: Path,
    wanted_categories: set[str] | None = None,
    wanted_extensions: set[str] | None = None,
    cookies: list[dict] | None = None,
    max_files: int = 500,
    already_seen: set[str] | None = None,
) -> AsyncGenerator[ExtractedFile, None]:
    """
    Scans the page for any file matching the registered types.

    Args:
        wanted_categories:  e.g. {"image","audio","video","document"} — None = all
        wanted_extensions:  explicit ext override, e.g. {".pdf",".mp3"} — None = all
        already_seen:       set of filenames already downloaded (de-dup)
    """
    already_seen = already_seen or set()

    # Intercept responses in parallel
    intercepted: dict[str, str] = {}  # url → content-type

    async def _on_response(response):
        ct = response.headers.get("content-type", "")
        response_url = response.url
        if any(ext in response_url.lower() for ext in ALL_EXTENSIONS):
            intercepted[response_url] = ct
        else:
            # Check by MIME
            mime_base = ct.split(";")[0].strip().lower()
            info = get_info(mime_base)
            if info:
                intercepted[response_url] = ct

    page.on("response", _on_response)

    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
    except Exception:
        pass

    await asyncio.sleep(3)
    page.remove_listener("response", _on_response)

    # ── Collect URLs from DOM ────────────────────────────────────────────────
    dom_urls: set[str] = set()

    # All elements, all URL-bearing attributes
    all_els = await page.query_selector_all("*")
    for el in all_els:
        for attr in _URL_ATTRS:
            try:
                val = await el.get_attribute(attr)
                if not val:
                    continue
                # srcset can have multiple entries
                if attr in ("srcset", "data-srcset"):
                    for part in val.split(","):
                        u = part.strip().split(" ")[0]
                        if u:
                            dom_urls.add(urljoin(url, u))
                else:
                    dom_urls.add(urljoin(url, val))
            except Exception:
                continue

    # Also grab <a href> links separately for thoroughness
    links = await page.query_selector_all("a[href]")
    for link in links:
        try:
            href = await link.get_attribute("href")
            if href:
                dom_urls.add(urljoin(url, href))
        except Exception:
            continue

    # ── Merge DOM + intercepted ───────────────────────────────────────────────
    all_candidate_urls: set[str] = dom_urls | set(intercepted.keys())

    # ── Filter by extension or category ─────────────────────────────────────
    def _should_download(candidate: str) -> bool:
        parsed = urlparse(candidate)
        # Only fetch real remote resources — never data:/blob:/file:/etc.
        if parsed.scheme not in ("http", "https"):
            return False
        if _SKIP_RE.search(candidate):
            return False
        # Strip query strings from path for extension detection
        path = parsed.path.split("?")[0]
        ext = Path(path).suffix.lower()

        # Multi-part extensions (.tar.gz, .tar.bz2, etc.)
        for multi in (".tar.gz", ".tar.bz2", ".tar.xz"):
            if path.endswith(multi):
                ext = multi
                break

        if ext in ALL_EXTENSIONS:
            info = get_info(ext)
        else:
            # Unknown/absent extension — fall back to the intercepted MIME type.
            ct = intercepted.get(candidate, "")
            mime_base = ct.split(";")[0].strip() if ct else ""
            info = get_info(mime_base) if mime_base else None

        if info is None:
            return False

        if wanted_extensions and ext not in wanted_extensions:
            return False
        if wanted_categories and info.category not in wanted_categories:
            return False

        return True

    candidates = [u for u in all_candidate_urls if _should_download(u)]

    # ── Download ──────────────────────────────────────────────────────────────
    headers: dict[str, str] = {"Referer": url}
    if cookies:
        headers["Cookie"] = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    seen_filenames: set[str] = set(already_seen)
    count = 0

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=120,
        limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
    ) as client:
        for candidate in candidates:
            if count >= max_files:
                break

            parsed = urlparse(candidate)
            path_no_qs = parsed.path.split("?")[0]
            ext = Path(path_no_qs).suffix.lower()

            # Multi-part ext
            for multi in (".tar.gz", ".tar.bz2", ".tar.xz"):
                if path_no_qs.endswith(multi):
                    ext = multi
                    break

            stem = re.sub(r'[^\w\-]', '_', Path(path_no_qs).stem)[:80] or "file"
            filename = _unique(stem + ext, seen_filenames)

            try:
                # HEAD first — check size / availability
                head = await client.head(candidate)
                if head.status_code not in (200, 206):
                    continue
                content_len = int(head.headers.get("content-length", "0"))
                if 0 < content_len < _MIN_SIZE:
                    continue

                dest = output_dir / filename
                total = 0
                ct = head.headers.get("content-type", mime_of(ext))

                async with client.stream("GET", candidate) as resp:
                    if resp.status_code not in (200, 206):
                        continue
                    ct = resp.headers.get("content-type", ct)
                    with open(dest, "wb") as f:
                        async for chunk in resp.aiter_bytes(65536):
                            f.write(chunk)
                            total += len(chunk)

                if total < _MIN_SIZE:
                    dest.unlink(missing_ok=True)
                    continue

                seen_filenames.add(filename)
                count += 1

                yield ExtractedFile(
                    filename=filename,
                    url=candidate,
                    content_type=ct.split(";")[0].strip(),
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
