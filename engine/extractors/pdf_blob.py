"""Captures PDFs rendered by in-page JS viewers (PDF.js and similar) that
load the document into a `blob:` URL instead of linking to a real HTTP PDF.
Network interception and the universal scanner both explicitly skip blob:
URLs (they aren't fetchable over HTTP), so this is the only path that can
recover that content: it re-fetches the blob from *inside* the page's own
JS context (where the blob object still lives) and ships the bytes out via
page.evaluate rather than a network request.
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import AsyncGenerator, Optional

from playwright.async_api import Page

from models import ExtractedFile
from utils import unique_filename

_FIND_PDF_BLOBS_JS = r"""
() => {
  const urls = new Set();
  const selectors = [
    'iframe[src^="blob:"]', 'embed[src^="blob:"]', 'object[data^="blob:"]',
    'embed[type="application/pdf"]', 'object[type="application/pdf"]',
  ];
  for (const sel of selectors) {
    for (const el of document.querySelectorAll(sel)) {
      const src = el.getAttribute('src') || el.getAttribute('data');
      if (src) urls.add(src);
    }
  }
  return Array.from(urls);
}
"""

_FETCH_BLOB_AS_BASE64_JS = r"""
async (blobUrl) => {
  const res = await fetch(blobUrl);
  const buf = await res.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let binary = '';
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}
"""

_MIN_PDF_BYTES = 512


async def extract_pdf_blobs(
    page: Page,
    url: str,
    output_dir: Path,
    already_seen: Optional[set[str]] = None,
) -> AsyncGenerator[ExtractedFile, None]:
    already_seen = already_seen or set()
    try:
        blob_urls = await page.evaluate(_FIND_PDF_BLOBS_JS)
    except Exception:
        return

    seen = set(already_seen)
    for i, blob_url in enumerate(blob_urls):
        try:
            b64 = await page.evaluate(_FETCH_BLOB_AS_BASE64_JS, blob_url)
            data = base64.b64decode(b64)
        except Exception:
            continue
        if len(data) < _MIN_PDF_BYTES or not data.startswith(b"%PDF-"):
            continue

        filename = unique_filename(f"pdf_viewer_{i + 1}.pdf", seen)
        seen.add(filename)
        dest = output_dir / filename
        try:
            dest.write_bytes(data)
        except OSError:
            continue

        yield ExtractedFile(
            filename=filename,
            url=url,
            content_type="application/pdf",
            size_bytes=len(data),
            local_path=str(dest),
            content_hash=hashlib.sha256(data).hexdigest(),
        )
