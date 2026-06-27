"""Extract downloadable documents (PDF, Word, Excel, ZIP, etc.) from a page."""
from __future__ import annotations

import re
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import urljoin, urlparse

import httpx
from playwright.async_api import Page

from models import ExtractedFile


_DOC_EXTS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp", ".csv", ".txt", ".rtf",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".epub", ".mobi",
}

_DOC_MIME_PREFIXES = [
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats",
    "application/vnd.ms-",
    "application/zip",
    "application/x-rar",
    "application/epub",
    "text/plain",
    "text/csv",
]


async def extract_documents(
    page: Page,
    url: str,
    output_dir: Path,
    cookies: list[dict] | None = None,
) -> AsyncGenerator[ExtractedFile, None]:
    """Find links to document files and download them. Yields ExtractedFile per doc."""
    await page.goto(url, wait_until="networkidle", timeout=60000)

    links = await page.query_selector_all("a[href]")
    doc_urls: set[str] = set()

    for link in links:
        href = await link.get_attribute("href")
        if not href:
            continue
        full = urljoin(url, href)
        parsed = urlparse(full)
        ext = Path(parsed.path).suffix.lower()
        if ext in _DOC_EXTS:
            doc_urls.add(full)

    headers = {"Referer": url}
    if cookies:
        headers["Cookie"] = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    seen_names: set[str] = set()

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=60) as client:
        for doc_url in doc_urls:
            try:
                # HEAD first to check content type and size
                head = await client.head(doc_url)
                ct = head.headers.get("content-type", "")
                if not _is_document_mime(ct):
                    parsed_path = Path(urlparse(doc_url).path)
                    if parsed_path.suffix.lower() not in _DOC_EXTS:
                        continue

                resp = await client.get(doc_url)
                if resp.status_code != 200:
                    continue

                parsed_path = Path(urlparse(doc_url).path)
                filename = _unique_name(
                    re.sub(r'[^\w\-.]', '_', parsed_path.name) or "document",
                    seen_names,
                )
                seen_names.add(filename)
                dest = output_dir / filename
                dest.write_bytes(resp.content)

                yield ExtractedFile(
                    filename=filename,
                    url=doc_url,
                    content_type=ct or "application/octet-stream",
                    size_bytes=len(resp.content),
                    local_path=str(dest),
                )
            except Exception:
                continue


def _is_document_mime(ct: str) -> bool:
    ct_lower = ct.lower()
    return any(ct_lower.startswith(p) for p in _DOC_MIME_PREFIXES)


def _unique_name(name: str, seen: set[str]) -> str:
    if name not in seen:
        return name
    stem = Path(name).stem
    suffix = Path(name).suffix
    i = 1
    while f"{stem}_{i}{suffix}" in seen:
        i += 1
    return f"{stem}_{i}{suffix}"
