"""Extract images from a web page."""
from __future__ import annotations

import asyncio
import mimetypes
import re
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import urljoin, urlparse

import httpx
from playwright.async_api import Page

from models import ExtractedFile


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".avif", ".bmp", ".ico"}
_MIN_SIZE = 1024  # skip images smaller than 1 KB (icons/tracking pixels)


async def extract_images(
    page: Page,
    url: str,
    output_dir: Path,
    cookies: list[dict] | None = None,
) -> AsyncGenerator[ExtractedFile, None]:
    """Find and download all images on the page. Yields ExtractedFile per image."""
    await page.goto(url, wait_until="networkidle", timeout=60000)

    # Collect image URLs from <img src>, srcset, CSS background-image, <picture>
    img_urls: set[str] = set()

    # img src / srcset
    imgs = await page.query_selector_all("img")
    for img in imgs:
        src = await img.get_attribute("src")
        if src:
            img_urls.add(urljoin(url, src))
        srcset = await img.get_attribute("srcset")
        if srcset:
            for part in srcset.split(","):
                part = part.strip().split(" ")[0]
                if part:
                    img_urls.add(urljoin(url, part))

    # <picture><source srcset=...>
    sources = await page.query_selector_all("picture source")
    for src_el in sources:
        srcset = await src_el.get_attribute("srcset")
        if srcset:
            for part in srcset.split(","):
                part = part.strip().split(" ")[0]
                if part:
                    img_urls.add(urljoin(url, part))

    # CSS background images from computed styles
    bg_urls = await page.evaluate("""() => {
        const urls = [];
        document.querySelectorAll('*').forEach(el => {
            const bg = window.getComputedStyle(el).backgroundImage;
            const m = bg.match(/url\\(["']?([^"')]+)["']?\\)/);
            if (m) urls.push(m[1]);
        });
        return urls;
    }""")
    for bu in bg_urls:
        img_urls.add(urljoin(url, bu))

    # Build cookie header for downloads
    headers = {}
    if cookies:
        headers["Cookie"] = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    headers["Referer"] = url

    seen_names: set[str] = set()
    count = 0

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30) as client:
        for img_url in img_urls:
            parsed = urlparse(img_url)
            ext = Path(parsed.path).suffix.lower()
            if ext not in _IMAGE_EXTS:
                continue

            try:
                resp = await client.get(img_url)
                if resp.status_code != 200:
                    continue
                content = resp.content
                if len(content) < _MIN_SIZE:
                    continue

                ct = resp.headers.get("content-type", "image/jpeg")
                guessed_ext = mimetypes.guess_extension(ct.split(";")[0].strip()) or ext
                if guessed_ext == ".jpe":
                    guessed_ext = ".jpg"

                stem = Path(parsed.path).stem[:60] or f"image_{count}"
                stem = re.sub(r'[^\w\-]', '_', stem)
                filename = _unique_name(stem + guessed_ext, seen_names)
                seen_names.add(filename)

                dest = output_dir / filename
                dest.write_bytes(content)
                count += 1

                yield ExtractedFile(
                    filename=filename,
                    url=img_url,
                    content_type=ct,
                    size_bytes=len(content),
                    local_path=str(dest),
                )
            except Exception:
                continue


def _unique_name(name: str, seen: set[str]) -> str:
    if name not in seen:
        return name
    stem = Path(name).stem
    suffix = Path(name).suffix
    i = 1
    while f"{stem}_{i}{suffix}" in seen:
        i += 1
    return f"{stem}_{i}{suffix}"
