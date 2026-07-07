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
from typing import AsyncGenerator, Callable, Optional
from urllib.parse import urljoin, urlparse

import httpx
from playwright.async_api import Page

from models import ExtractedFile
from file_types import ALL_EXTENSIONS, mime_of, get_info, category_of
from utils import unique_filename, build_cookie_header
from extractors.links import auto_scroll
from download import download_with_retry, run_bounded, sort_by_priority
import security

# Recursively walks the light DOM *and* every open shadow root, collecting
# resolved URLs from the same attribute list Python-side code cares about.
# Playwright's query_selector_all("*") cannot see into shadow trees at all,
# so web-component-heavy sites (many design systems, video players) silently
# hid their media without this — closed shadow roots remain unreachable by
# design (the browser gives no API for that), same as a real user's browser.
_SHADOW_URLS_JS = r"""
(urlAttrs) => {
  const urls = new Set();
  const seen = new Set();

  function visit(root) {
    if (seen.has(root)) return;
    seen.add(root);
    const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
    for (const el of all) {
      for (const attr of urlAttrs) {
        const val = el.getAttribute && el.getAttribute(attr);
        if (!val) continue;
        if (attr === 'srcset' || attr === 'data-srcset') {
          for (const part of val.split(',')) {
            const u = part.trim().split(' ')[0];
            if (u) { try { urls.add(new URL(u, location.href).href); } catch (e) {} }
          }
        } else {
          try { urls.add(new URL(val, location.href).href); } catch (e) {}
        }
      }
      if (el.shadowRoot) visit(el.shadowRoot);
    }
  }
  visit(document);
  return Array.from(urls);
}
"""

# Pulls url(...) references out of every loaded stylesheet: background-image
# and other CSS background/mask/border-image properties, plus @font-face src.
# Runs in-page so it sees computed/relative stylesheets (including same-origin
# imported ones) without us having to fetch and parse CSS ourselves.
_CSS_URLS_JS = r"""
() => {
  const urls = new Set();
  const urlRe = /url\(\s*(['"]?)([^'")]+)\1\s*\)/g;
  for (const sheet of Array.from(document.styleSheets)) {
    let rules;
    try { rules = sheet.cssRules; } catch (e) { continue; } // cross-origin sheet — skip
    if (!rules) continue;
    for (const rule of Array.from(rules)) {
      let text = null;
      try { text = rule.cssText; } catch (e) { continue; }
      if (!text) continue;
      let m;
      while ((m = urlRe.exec(text)) !== null) {
        const u = m[2];
        if (u && !u.startsWith('data:')) urls.add(u);
      }
    }
  }
  return Array.from(urls);
}
"""

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
    min_size_bytes: int = _MIN_SIZE,
    url_pattern: str | None = None,
    metadata_only: bool = False,
    wait_selector: str | None = None,
    click_selector: str | None = None,
    click_max_times: int = 0,
    scroll: bool = True,
    concurrency: int = 6,
    max_retries: int = 2,
    wait_until: str = "networkidle",
    wait_timeout_ms: int = 60000,
    blocked_domains: set[str] | None = None,
    max_file_size_bytes: int | None = None,
    expected_hashes: dict[str, str] | None = None,
    download_priority: list[str] | None = None,
    verify_mime: bool = True,
    scan_with_clamav: bool = False,
    on_file_progress: Optional[Callable[[str, int, Optional[int]], None]] = None,
) -> AsyncGenerator[ExtractedFile, None]:
    """
    Scans the page for any file matching the registered types.

    Args:
        wanted_categories:  e.g. {"image","audio","video","document"} — None = all
        wanted_extensions:  explicit ext override, e.g. {".pdf",".mp3"} — None = all
        already_seen:       set of filenames already downloaded (de-dup)
        min_size_bytes:     skip candidates smaller than this (0 = no minimum)
        url_pattern:        regex the candidate URL must match (None = no filter)
        metadata_only:      HEAD-check candidates but never download the body;
                             yielded files have local_path=None, size_bytes from HEAD
        wait_selector:      CSS selector to wait for after navigation (SPA/dynamic content)
        click_selector:     "load more"/"next page" button to click repeatedly
        click_max_times:    how many times to click click_selector (0 = don't click)
        scroll:             auto-scroll to trigger lazy-loaded content before scanning
    """
    already_seen = already_seen or set()
    min_size_bytes = max(0, min_size_bytes)
    pattern_re = re.compile(url_pattern) if url_pattern else None
    blocked_domains = blocked_domains or set()
    expected_hashes = expected_hashes or {}

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
        await page.goto(url, wait_until=wait_until, timeout=wait_timeout_ms)
    except Exception:
        pass

    if wait_selector:
        try:
            await page.wait_for_selector(wait_selector, timeout=15000)
        except Exception:
            pass  # best-effort — proceed with whatever loaded

    if click_selector and click_max_times > 0:
        for _ in range(click_max_times):
            try:
                btn = await page.query_selector(click_selector)
                if not btn or not await btn.is_visible():
                    break
                await btn.click(timeout=5000)
                await page.wait_for_timeout(1500)
            except Exception:
                break

    if scroll:
        await auto_scroll(page)

    await asyncio.sleep(3)
    page.remove_listener("response", _on_response)

    # ── Collect URLs from DOM (main frame + every nested iframe) ─────────────
    dom_urls: set[str] = set()

    async def _collect_from_frame(frame, frame_url: str) -> None:
        # CSS background-image / mask-image / border-image / @font-face src
        try:
            css_urls = await frame.evaluate(_CSS_URLS_JS)
            for u in css_urls:
                dom_urls.add(urljoin(frame_url, u))
        except Exception:
            pass

        try:
            all_els = await frame.query_selector_all("*")
        except Exception:
            return  # detached/cross-origin frame we can't introspect

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
                                dom_urls.add(urljoin(frame_url, u))
                    else:
                        dom_urls.add(urljoin(frame_url, val))
                except Exception:
                    continue

        try:
            links = await frame.query_selector_all("a[href]")
        except Exception:
            links = []
        for link in links:
            try:
                href = await link.get_attribute("href")
                if href:
                    dom_urls.add(urljoin(frame_url, href))
            except Exception:
                continue

    await _collect_from_frame(page, url)
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        await _collect_from_frame(frame, frame.url or url)

    # Shadow DOM: query_selector_all("*") above never sees into open shadow
    # roots, so web-component-based sites need this dedicated in-page walk.
    for frame in page.frames:
        try:
            shadow_urls = await frame.evaluate(_SHADOW_URLS_JS, _URL_ATTRS)
            dom_urls.update(shadow_urls)
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
        if blocked_domains and parsed.netloc in blocked_domains:
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
        if pattern_re and not pattern_re.search(candidate):
            return False

        return True

    candidates = [u for u in all_candidate_urls if _should_download(u)][:max_files]

    # ── Download (bounded concurrency + retry/backoff) ────────────────────────
    headers: dict[str, str] = {"Referer": url}
    if cookies:
        headers["Cookie"] = build_cookie_header(cookies)

    seen_filenames: set[str] = set(already_seen)

    # Filenames must be allocated up front, synchronously, before any download
    # task starts — unique_filename() itself has no await points, so doing the
    # allocation here (rather than inside the concurrent coroutines) guarantees
    # two in-flight downloads never race for the same destination path.
    jobs: list[tuple[str, str, Path]] = []  # (candidate, filename, dest)
    for candidate in candidates:
        path_no_qs = urlparse(candidate).path.split("?")[0]
        ext = Path(path_no_qs).suffix.lower()
        for multi in (".tar.gz", ".tar.bz2", ".tar.xz"):
            if path_no_qs.endswith(multi):
                ext = multi
                break
        stem = re.sub(r'[^\w\-]', '_', Path(path_no_qs).stem)[:80] or "file"
        filename = unique_filename(stem + ext, seen_filenames)
        seen_filenames.add(filename)
        jobs.append((candidate, filename, output_dir / filename))

    if not jobs:
        return

    if download_priority:
        jobs = sort_by_priority(jobs, key=lambda j: category_of(Path(j[1]).suffix.lower()) or "", priority=download_priority)

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=120,
        limits=httpx.Limits(max_connections=max(8, concurrency), max_keepalive_connections=4),
    ) as client:

        async def _fetch_one(candidate: str, filename: str, dest: Path) -> ExtractedFile | None:
            ext = Path(filename).suffix.lower()
            try:
                head = await client.head(candidate)
                if head.status_code not in (200, 206):
                    return None
                content_len = int(head.headers.get("content-length", "0"))
                if 0 < content_len < min_size_bytes:
                    return None
                if max_file_size_bytes and content_len > max_file_size_bytes:
                    return None
                ct = head.headers.get("content-type", mime_of(ext))

                if metadata_only:
                    return ExtractedFile(
                        filename=filename,
                        url=candidate,
                        content_type=ct.split(";")[0].strip(),
                        size_bytes=content_len or None,
                        local_path=None,
                    )
            except Exception:
                return None

            progress_cb = (
                (lambda done, total: on_file_progress(filename, done, total))
                if on_file_progress else None
            )
            result = await download_with_retry(
                client, candidate, dest,
                min_size_bytes=min_size_bytes,
                max_size_bytes=max_file_size_bytes,
                max_retries=max_retries,
                on_progress=progress_cb,
            )
            if result is None:
                return None

            hash_verified: bool | None = None
            expected = expected_hashes.get(candidate)
            if expected:
                hash_verified = expected.lower() == result.sha256.lower()
                if not hash_verified:
                    dest.unlink(missing_ok=True)
                    return None

            mime_ok = True
            if verify_mime:
                mime_ok = await asyncio.to_thread(security.verify_mime, ext, dest)

            clamav_clean: bool | None = None
            if scan_with_clamav:
                clamav_clean = await security.clamav_scan(dest)
                if clamav_clean is False:
                    dest.unlink(missing_ok=True)
                    return None

            return ExtractedFile(
                filename=filename,
                url=candidate,
                content_type=result.content_type.split(";")[0].strip(),
                size_bytes=result.bytes_written,
                local_path=str(dest),
                content_hash=result.sha256,
                hash_verified=hash_verified,
                mime_mismatch=not mime_ok,
                clamav_clean=clamav_clean,
            )

        coros = (_fetch_one(c, f, d) for c, f, d in jobs)
        async for result in run_bounded(coros, concurrency):
            if result is not None:
                yield result


