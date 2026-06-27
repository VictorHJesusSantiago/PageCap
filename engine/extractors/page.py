"""Capture a full web page as PDF using Playwright."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import urlparse

from playwright.async_api import Page

from models import ExtractedFile


async def extract_page_pdf(
    page: Page,
    url: str,
    output_dir: Path,
) -> AsyncGenerator[ExtractedFile, None]:
    """Navigate to URL and save as PDF. Yields one ExtractedFile."""
    domain = urlparse(url).netloc.replace(":", "_")
    filename = f"{domain}_page.pdf"
    dest = output_dir / filename

    await page.goto(url, wait_until="networkidle", timeout=60000)

    # Scroll to trigger lazy-loaded content
    await _scroll_full_page(page)
    await asyncio.sleep(1)

    await page.pdf(
        path=str(dest),
        format="A4",
        print_background=True,
        margin={"top": "10mm", "right": "10mm", "bottom": "10mm", "left": "10mm"},
    )

    size = dest.stat().st_size if dest.exists() else None
    yield ExtractedFile(
        filename=filename,
        url=url,
        content_type="application/pdf",
        size_bytes=size,
        local_path=str(dest),
    )


async def _scroll_full_page(page: Page) -> None:
    """Scroll through the page to trigger lazy loaders."""
    total_height = await page.evaluate("document.body.scrollHeight")
    viewport_height = await page.evaluate("window.innerHeight")
    current = 0
    while current < total_height:
        await page.evaluate(f"window.scrollTo(0, {current})")
        await asyncio.sleep(0.15)
        current += viewport_height
    await page.evaluate("window.scrollTo(0, 0)")
