"""Sitemap.xml discovery: seed extra same-domain URLs to crawl without relying
on link-following alone (useful for SPAs whose nav isn't plain <a href>)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx

_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


async def _fetch(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        resp = await client.get(url, timeout=15)
        if resp.status_code == 200 and resp.text.strip():
            return resp.text
    except Exception:
        pass
    return None


def _parse_locs(xml_text: str) -> tuple[list[str], list[str]]:
    """Returns (page_urls, nested_sitemap_urls)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return [], []

    tag = root.tag.rsplit("}", 1)[-1]
    locs = [el.text.strip() for el in root.findall(".//sm:loc", _NS) if el.text]
    if not locs:
        # tolerate sitemaps served without the namespace declared
        locs = [el.text.strip() for el in root.findall(".//loc") if el.text]

    if tag == "sitemapindex":
        return [], locs
    return locs, []


async def discover_sitemap_urls(base_url: str, max_urls: int = 200) -> list[str]:
    """Best-effort discovery of same-domain URLs via /sitemap.xml (and any
    nested sitemaps referenced by a sitemap index, one level deep)."""
    parsed = urlparse(base_url)
    domain = parsed.netloc
    root_url = f"{parsed.scheme}://{domain}"

    urls: list[str] = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        text = await _fetch(client, f"{root_url}/sitemap.xml")
        if text is None:
            # fall back to robots.txt's "Sitemap:" directive
            robots = await _fetch(client, f"{root_url}/robots.txt")
            if robots:
                for line in robots.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sm_url = line.split(":", 1)[1].strip()
                        text = await _fetch(client, sm_url)
                        if text:
                            break
        if text is None:
            return []

        pages, nested = _parse_locs(text)
        urls.extend(pages)

        for nested_url in nested[:5]:  # cap nested sitemap fan-out
            if len(urls) >= max_urls:
                break
            nested_text = await _fetch(client, nested_url)
            if nested_text:
                nested_pages, _ = _parse_locs(nested_text)
                urls.extend(nested_pages)

    same_domain = [u for u in urls if urlparse(u).netloc == domain]
    return same_domain[:max_urls]
