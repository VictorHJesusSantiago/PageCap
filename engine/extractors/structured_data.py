"""Extracts structured page metadata — JSON-LD blocks, Open Graph / Twitter
meta tags, and generic <meta> tags — and saves it as a single JSON file
alongside the downloaded assets. Useful for cataloguing/attribution without
having to re-scrape the page."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, AsyncGenerator

from playwright.async_api import Page

from models import ExtractedFile
from utils import unique_filename

_EXTRACT_JS = r"""
() => {
  const jsonLd = [];
  for (const el of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { jsonLd.push(JSON.parse(el.textContent)); }
    catch (e) { /* malformed block — skip it */ }
  }

  const meta = {};
  const openGraph = {};
  const twitter = {};
  for (const el of document.querySelectorAll('meta')) {
    const name = el.getAttribute('name');
    const property = el.getAttribute('property');
    const content = el.getAttribute('content');
    if (!content) continue;
    if (property && property.startsWith('og:')) openGraph[property.slice(3)] = content;
    else if (name && name.startsWith('twitter:')) twitter[name.slice(8)] = content;
    else if (name) meta[name] = content;
  }

  return {
    title: document.title || null,
    canonical: document.querySelector('link[rel="canonical"]')?.href || null,
    json_ld: jsonLd,
    open_graph: openGraph,
    twitter,
    meta,
  };
}
"""


def _flatten(prefix: str, value: Any, rows: list[tuple[str, str, str]]) -> None:
    """Flattens nested dicts/lists into (section, key, value) rows for CSV —
    JSON-LD blocks especially are arbitrarily nested schema.org objects."""
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}.{k}" if prefix else k, v, rows)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _flatten(f"{prefix}[{i}]", v, rows)
    else:
        section = prefix.split(".", 1)[0].split("[", 1)[0] or "value"
        rows.append((section, prefix, "" if value is None else str(value)))


async def extract_structured_data(
    page: Page,
    url: str,
    output_dir: Path,
    already_seen: set[str] | None = None,
    export_csv: bool = False,
) -> AsyncGenerator[ExtractedFile, None]:
    """Pulls JSON-LD / Open Graph / Twitter card / meta tags from the already-
    loaded `page` and writes them to a single `structured_data.json` file
    (plus a flattened `structured_data.csv` when `export_csv=True`)."""
    already_seen = already_seen or set()
    try:
        data = await page.evaluate(_EXTRACT_JS)
    except Exception:
        return

    if not any([data.get("json_ld"), data.get("open_graph"), data.get("twitter"), data.get("meta")]):
        return

    seen = set(already_seen)

    filename = unique_filename("structured_data.json", seen)
    seen.add(filename)
    dest = output_dir / filename
    payload = {"url": url, **data}
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    yield ExtractedFile(
        filename=filename,
        url=url,
        content_type="application/json",
        size_bytes=dest.stat().st_size,
        local_path=str(dest),
    )

    if export_csv:
        rows: list[tuple[str, str, str]] = [("meta", "url", url), ("meta", "title", data.get("title") or "")]
        for section in ("json_ld", "open_graph", "twitter", "meta"):
            _flatten(section, data.get(section), rows)

        csv_filename = unique_filename("structured_data.csv", seen)
        seen.add(csv_filename)
        csv_dest = output_dir / csv_filename
        with open(csv_dest, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["section", "key", "value"])
            writer.writerows(rows)

        yield ExtractedFile(
            filename=csv_filename,
            url=url,
            content_type="text/csv",
            size_bytes=csv_dest.stat().st_size,
            local_path=str(csv_dest),
        )
