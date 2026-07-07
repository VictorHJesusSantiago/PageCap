"""Helpers for recursive crawling: same-domain link discovery and infinite-scroll."""
from __future__ import annotations

from urllib.parse import urldefrag, urljoin, urlparse

from playwright.async_api import Page


async def discover_same_domain_links(page: Page, base_url: str) -> list[str]:
    """Return absolute, same-domain, fragment-stripped links found on the page."""
    base_domain = urlparse(base_url).netloc
    try:
        hrefs = await page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.getAttribute('href'))"
        )
    except Exception:
        return []

    links: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        if not href:
            continue
        full = urljoin(base_url, href)
        full, _ = urldefrag(full)
        parsed = urlparse(full)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc != base_domain:
            continue
        if full in seen:
            continue
        seen.add(full)
        links.append(full)
    return links


async def auto_scroll(page: Page, max_steps: int = 20, pause_ms: int = 250) -> None:
    """Scroll to the bottom repeatedly so lazy-loaded content (infinite scroll
    feeds, deferred images/video) has a chance to mount before the DOM is scanned.
    Stops early once scrolling no longer changes the page height."""
    try:
        last_height = await page.evaluate("document.body.scrollHeight")
    except Exception:
        return

    for _ in range(max_steps):
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(pause_ms)
            new_height = await page.evaluate("document.body.scrollHeight")
        except Exception:
            return
        if new_height <= last_height:
            break
        last_height = new_height
