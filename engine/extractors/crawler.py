"""
Main orchestrator: runs all extraction strategies in sequence.

Strategy order (most specific → most general):
  1. Page → PDF           (always, if requested)
  2. yt-dlp               (platform-aware: YouTube, Vimeo, TikTok, 1800+ sites)
  3. Network interception  (any player, HLS/DASH, custom streams)
  4. DOM scan             (direct <audio>/<video> tags, linked files)
  5. Universal scanner    (ALL 150+ registered file types from DOM + network)
  6. Recursive crawl      (link-following / sitemap / extra seed URLs)
  7. Third-party plugins
  8. Screen recording     (last resort: records what renders on screen)
then, outside the browser: conversion, thumbnails, zip, diff, webhook.

Each stage is a `_Stage` — a name plus an async callable taking the shared
`CrawlContext`. The pipeline is data, not control flow, so adding or reordering
a strategy no longer means editing a 400-line function (OCP), and every stage
gets uniform cancellation, pause and error handling for free instead of each
repeating the same try/except/_cancelled() boilerplate.
"""
from __future__ import annotations

import asyncio
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, AsyncGenerator, Callable, Optional
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright

from models import (
    AuthMethod,
    ContentType,
    DiffResult,
    ExtractedFile,
    ExtractionRequest,
    FileProgress,
    JobState,
    JobStatus,
)
from file_types import category_of
from logging_config import get_logger
from auth.credentials import apply_credentials
from auth.cookies import load_cookies
from auth.profiles import resolve_credential_profile
from extractors.page import extract_page_pdf
from extractors.media import extract_media
from extractors.network import extract_via_network
from extractors.generic import extract_generic_media
from extractors.universal import extract_universal
from extractors.screen_record import extract_screen_record
from extractors.structured_data import extract_structured_data
from extractors.links import discover_same_domain_links
from extractors.sitemap import discover_sitemap_urls
from extractors.pdf_blob import extract_pdf_blobs
from paywall import detect_paywall

log = get_logger("crawler")

# Live resume events, keyed by job id. The API mutates `job.status` to pause or
# resume, but only this registry lets it *wake* a waiting crawl immediately
# instead of the crawl noticing on its next poll.
_RESUME_EVENTS: dict[str, asyncio.Event] = {}


def signal_resume(job_id: str) -> None:
    """Wakes a paused crawl. Safe to call for an unknown/finished job."""
    event = _RESUME_EVENTS.get(job_id)
    if event:
        event.set()


# Map ContentType → file_types categories
_CT_TO_CATEGORIES: dict[str, set[str]] = {
    "all":       {"text", "spreadsheet", "presentation", "image", "vector", "audio", "video",
                  "font", "subtitle", "data", "code", "archive", "executable", "certificate",
                  "ml", "3d", "config"},
    "page_pdf":  set(),          # handled separately
    "images":    {"image", "vector"},
    "videos":    {"video"},
    "audio":     {"audio"},
    "documents": {"text", "spreadsheet", "presentation", "data", "subtitle"},
}


@dataclass
class CrawlContext:
    """Everything a stage needs, and the only thing stages mutate.

    Collecting this into one object is what let the stages become independent:
    previously each was a closure over ~15 locals of `crawl_assets`, which is
    why they could not be moved, reordered or tested in isolation.
    """
    request: ExtractionRequest
    job: JobState
    output_dir: Path
    on_progress: Optional[Callable[[JobState], None]] = None

    # Browser handles, populated once the Playwright context is up.
    browser_context: object = None
    page: object = None
    pw_cookies: list[dict] = field(default_factory=list)

    # Accumulated results
    files: list[ExtractedFile] = field(default_factory=list)
    seen_filenames: set[str] = field(default_factory=set)
    seen_hashes: dict[str, str] = field(default_factory=dict)
    job_bytes_total: int = 0

    # Derived request state
    want: set[str] = field(default_factory=set)
    wanted_categories: set[str] = field(default_factory=set)
    wanted_extensions: Optional[set[str]] = None
    blocked_domains: set[str] = field(default_factory=set)
    expected_hashes: dict[str, str] = field(default_factory=dict)

    # Pause is an Event, not a polled flag: a resumed job continues on the next
    # loop tick instead of up to a second later, and a cancelled job stops
    # waiting immediately.
    resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    _last_progress_emit: float = 0.0

    @property
    def want_all(self) -> bool:
        return ContentType.all.value in self.want

    @property
    def want_media(self) -> bool:
        return (
            self.want_all
            or ContentType.videos.value in self.want
            or ContentType.audio.value in self.want
        )

    def cancelled(self) -> bool:
        return self.job.status == JobStatus.cancelled

    def emit(self, msg: str, progress: int = -1) -> None:
        self.job.message = msg
        if progress >= 0:
            self.job.progress = progress
        if self.on_progress:
            self.on_progress(self.job)

    def emit_file_progress(self, filename: str, done: int, total: Optional[int]) -> None:
        """Per-file byte progress is broadcast at most 4x/second — the
        underlying download callback fires on every 64KB chunk, which would
        otherwise flood the WebSocket with dozens of messages/sec."""
        now = time.time()
        if now - self._last_progress_emit < 0.25 and (total is None or done < total):
            return
        self._last_progress_emit = now
        self.job.current_file = FileProgress(filename=filename, bytes_done=done, bytes_total=total)
        if self.on_progress:
            self.on_progress(self.job)

    async def wait_if_paused(self) -> None:
        """Cooperative pause: blocks while status is 'paused' and returns as
        soon as the job is resumed or cancelled."""
        while self.job.status == JobStatus.paused:
            self.resume_event.clear()
            try:
                await asyncio.wait_for(self.resume_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue  # re-check status; the API mutates it out-of-band

    def add(self, f: ExtractedFile) -> None:
        """The single funnel every extracted file passes through: dedupe by
        name, domain blocklist, expected-hash verification, job size cap and
        content dedupe. Keeping it in one place is why those policies cannot
        drift between extractors."""
        if f.filename in self.seen_filenames:
            return

        if self.blocked_domains and urlparse(f.url).netloc in self.blocked_domains:
            self._discard(f)
            return

        expected = self.expected_hashes.get(f.url)
        if expected and f.content_hash:
            f.hash_verified = expected.lower() == f.content_hash.lower()
            if not f.hash_verified:
                self._discard(f)
                return

        # max_job_size_bytes is a budget for bytes *on disk*, so it only applies
        # to files that were actually downloaded. A metadata_only run populates
        # size_bytes from a HEAD request while local_path stays None — charging
        # those against the budget silently truncated the listing the user asked
        # for, even though nothing was written.
        if self.request.max_job_size_bytes and f.size_bytes and f.local_path:
            if self.job_bytes_total + f.size_bytes > self.request.max_job_size_bytes:
                self._discard(f)
                self.emit(f"Limite de tamanho do job atingido — {f.filename} descartado", -1)
                return

        if self.request.dedupe_by_hash and f.content_hash:
            kept_as = self.seen_hashes.get(f.content_hash)
            if kept_as is not None:
                # Same bytes already saved under a different name/URL — drop
                # this copy instead of wasting disk space on a duplicate.
                self._discard(f)
                f.local_path = None
                f.duplicate_of = kept_as
                return
            self.seen_hashes[f.content_hash] = f.filename

        if f.local_path:
            self.job_bytes_total += f.size_bytes or 0

        self.seen_filenames.add(f.filename)
        self.files.append(f)
        self.job.files.append(f)

    @staticmethod
    def _discard(f: ExtractedFile) -> None:
        if f.local_path:
            try:
                Path(f.local_path).unlink(missing_ok=True)
            except OSError:
                pass


StageFn = Callable[[CrawlContext], Awaitable[None]]


@dataclass(frozen=True)
class _Stage:
    name: str
    run: StageFn
    # Stages that only make sense for audio/video skip themselves entirely when
    # the caller asked for something else.
    requires_media: bool = False


# ── Individual stages ───────────────────────────────────────────────────────

async def _stage_page_pdf(ctx: CrawlContext) -> None:
    if not (ctx.want_all or ContentType.page_pdf.value in ctx.want):
        return
    ctx.emit("Capturando página como PDF...", 12)
    async for f in extract_page_pdf(ctx.page, ctx.request.url, ctx.output_dir):
        ctx.add(f)
        ctx.emit(f"PDF: {f.filename}", 18)

    # PDF.js/blob-based viewers render into a blob: URL that a normal HTTP
    # fetch can never see — recover it from inside the page instead.
    async for f in extract_pdf_blobs(
        ctx.page, ctx.request.url, ctx.output_dir, already_seen=set(ctx.seen_filenames)
    ):
        ctx.add(f)
        ctx.emit(f"PDF (viewer): {f.filename}", 19)


async def _stage_ytdlp(ctx: CrawlContext) -> None:
    ctx.emit("Tentando yt-dlp (YouTube, Vimeo, TikTok, etc.)...", 20)
    async for f in extract_media(
        ctx.request.url, ctx.output_dir, list(ctx.want),
        quality=ctx.request.quality,
        max_downloads=max(1, ctx.request.max_files - len(ctx.files)),
    ):
        ctx.add(f)
        ctx.emit(f"yt-dlp: {f.filename}", 28)


async def _stage_network(ctx: CrawlContext) -> None:
    ctx.emit("Interceptando requisições de mídia...", 30)
    net_page = await ctx.browser_context.new_page()
    try:
        async for f in extract_via_network(
            net_page, ctx.request.url, ctx.output_dir, list(ctx.want),
            cookies=ctx.pw_cookies,
            wait_seconds=ctx.request.network_wait,
            max_files=ctx.request.max_files,
            concurrency=ctx.request.download_concurrency,
            max_retries=ctx.request.download_retries,
            wait_until=ctx.request.wait_until,
            wait_timeout_ms=ctx.request.wait_timeout_ms,
        ):
            ctx.add(f)
            ctx.emit(f"Rede: {f.filename}", 45)
    finally:
        await net_page.close()


async def _stage_dom_media(ctx: CrawlContext) -> None:
    ctx.emit("Escaneando tags de mídia no DOM...", 47)
    async for f in extract_generic_media(
        ctx.page, ctx.request.url, ctx.output_dir, list(ctx.want),
        cookies=ctx.pw_cookies,
        concurrency=ctx.request.download_concurrency,
        max_retries=ctx.request.download_retries,
        wait_until=ctx.request.wait_until,
        wait_timeout_ms=ctx.request.wait_timeout_ms,
    ):
        ctx.add(f)


async def _stage_universal(ctx: CrawlContext) -> None:
    ctx.emit("Scanner universal de arquivos...", 52)
    uni_page = await ctx.browser_context.new_page()
    try:
        async for f in extract_universal(
            uni_page, ctx.request.url, ctx.output_dir,
            wanted_categories=None if ctx.want_all else ctx.wanted_categories,
            wanted_extensions=ctx.wanted_extensions,
            cookies=ctx.pw_cookies,
            max_files=max(0, ctx.request.max_files - len(ctx.files)),
            already_seen=set(ctx.seen_filenames),
            min_size_bytes=ctx.request.min_file_size_bytes,
            url_pattern=ctx.request.url_pattern,
            metadata_only=ctx.request.metadata_only,
            wait_selector=ctx.request.wait_selector,
            click_selector=ctx.request.click_selector,
            click_max_times=ctx.request.click_max_times,
            concurrency=ctx.request.download_concurrency,
            max_retries=ctx.request.download_retries,
            wait_until=ctx.request.wait_until,
            wait_timeout_ms=ctx.request.wait_timeout_ms,
            blocked_domains=ctx.blocked_domains,
            max_file_size_bytes=ctx.request.max_file_size_bytes,
            expected_hashes=ctx.expected_hashes,
            download_priority=ctx.request.download_priority,
            verify_mime=ctx.request.verify_mime,
            scan_with_clamav=ctx.request.scan_with_clamav,
            on_file_progress=ctx.emit_file_progress,
        ):
            ctx.add(f)
            ctx.emit(f"Universal: {f.filename}", 78)

        async for f in extract_structured_data(
            uni_page, ctx.request.url, ctx.output_dir,
            already_seen=set(ctx.seen_filenames),
            export_csv=ctx.request.export_structured_data_csv,
        ):
            ctx.add(f)
            ctx.emit(f"Metadados: {f.filename}", 80)
    finally:
        await uni_page.close()


async def _stage_recursive_crawl(ctx: CrawlContext) -> None:
    request = ctx.request
    if not (request.follow_links or request.use_sitemap or request.additional_urls):
        return
    async for f in _crawl_additional_pages(ctx):
        ctx.add(f)


async def _stage_plugins(ctx: CrawlContext) -> None:
    from plugins import load_plugins

    for plugin_name, plugin_extract in load_plugins():
        if ctx.cancelled():
            return
        ctx.emit(f"Plugin: {plugin_name}...", -1)
        plugin_page = await ctx.browser_context.new_page()
        try:
            async for f in plugin_extract(
                plugin_page, ctx.request.url, ctx.output_dir, cookies=ctx.pw_cookies
            ):
                ctx.add(f)
                ctx.emit(f"Plugin {plugin_name}: {f.filename}", -1)
        except Exception as e:
            # A misbehaving third-party plugin must never fail the job.
            ctx.emit(f"Plugin {plugin_name} falhou: {e}", -1)
            log.warning(
                "Plugin failed",
                extra={"extra_fields": {"plugin": plugin_name, "error": str(e)}},
            )
        finally:
            await plugin_page.close()


async def _stage_screen_record(ctx: CrawlContext) -> None:
    if not ctx.request.screen_record:
        return
    ctx.emit(f"Gravando tela por {ctx.request.screen_record_duration}s...", 82)
    async for f in extract_screen_record(
        ctx.page, ctx.browser_context, ctx.request.url, ctx.output_dir,
        duration=ctx.request.screen_record_duration,
    ):
        ctx.add(f)
        ctx.emit(f"Gravação: {f.filename}", 90)


# The pipeline. Order matters (most specific strategy first); everything else
# about a stage is declared, not coded.
_BROWSER_STAGES: tuple[_Stage, ...] = (
    _Stage("page_pdf", _stage_page_pdf),
    _Stage("ytdlp", _stage_ytdlp, requires_media=True),
    _Stage("network", _stage_network, requires_media=True),
    _Stage("dom_media", _stage_dom_media, requires_media=True),
    _Stage("universal", _stage_universal),
    _Stage("recursive_crawl", _stage_recursive_crawl),
    _Stage("plugins", _stage_plugins),
    _Stage("screen_record", _stage_screen_record, requires_media=True),
)


async def _run_stage(stage: _Stage, ctx: CrawlContext) -> None:
    """Uniform cancellation, pause and error isolation for every stage.

    Errors are contained per stage, matching the per-file resilience the
    extractors already provide: a broken yt-dlp run must not cost the user the
    universal scan that would have succeeded.
    """
    if ctx.cancelled():
        return
    if stage.requires_media and not ctx.want_media:
        return

    await ctx.wait_if_paused()
    if ctx.cancelled():
        return

    started = time.perf_counter()
    try:
        await stage.run(ctx)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        ctx.emit(f"{stage.name}: {e}", -1)
        log.warning(
            "Stage failed",
            extra={"extra_fields": {"stage": stage.name, "error": str(e)}},
        )
    else:
        log.debug(
            "Stage finished",
            extra={"extra_fields": {
                "stage": stage.name,
                "elapsed_seconds": round(time.perf_counter() - started, 2),
                "files_so_far": len(ctx.files),
            }},
        )


# ── Post-processing (no browser needed) ─────────────────────────────────────

async def _post_convert(ctx: CrawlContext) -> None:
    """`convert_to` is a global "convert everything" shortcut; `convert_rules`
    (category → target ext) lets a single job apply a different target per file
    category. A file matching both uses convert_rules (more specific wins)."""
    request = ctx.request
    if not (request.convert_to or request.convert_rules) or not ctx.files:
        return

    global_ext = (
        request.convert_to if not request.convert_to or request.convert_to.startswith(".")
        else f".{request.convert_to}"
    )
    rules = {
        cat: (ext if ext.startswith(".") else f".{ext}")
        for cat, ext in request.convert_rules.items()
    }
    ctx.emit("Convertendo arquivos...", 92)
    converted_dir = ctx.output_dir / "converted"
    converted_dir.mkdir(exist_ok=True)

    from converter import convert_file, ConversionError

    targets: list[tuple[ExtractedFile, str]] = []
    for f in ctx.files:
        if not f.local_path:
            continue
        src_ext = Path(f.local_path).suffix.lower()
        target_ext = rules.get(category_of(src_ext)) or global_ext
        if target_ext and target_ext != src_ext:
            targets.append((f, target_ext))

    if not targets:
        return

    sem = asyncio.Semaphore(4)
    done_count = 0

    async def _convert_one(f: ExtractedFile, target_ext: str) -> None:
        nonlocal done_count
        async with sem:
            src = Path(f.local_path)
            try:
                dest = await convert_file(src, target_ext, converted_dir)
                f.converted_path = str(dest)
                f.converted_ext = target_ext
                msg = f"Convertido: {dest.name}"
            except ConversionError as e:
                msg = f"Conversão ignorada ({src.name}): {e}"
            done_count += 1
            ctx.emit(msg, 92 + int(6 * done_count / len(targets)))

    await asyncio.gather(*(_convert_one(f, ext) for f, ext in targets))


async def _post_thumbnails(ctx: CrawlContext) -> None:
    if not ctx.request.generate_thumbnails or not ctx.files:
        return
    from thumbnails import generate_thumbnail

    ctx.emit("Gerando thumbnails...", 96)
    sem = asyncio.Semaphore(4)

    async def _thumb_one(f: ExtractedFile) -> None:
        async with sem:
            if not f.local_path:
                return
            cat = category_of(Path(f.local_path).suffix.lower())
            if cat not in ("image", "video"):
                return
            thumb = await generate_thumbnail(Path(f.local_path), cat)
            if thumb:
                f.thumbnail = thumb

    await asyncio.gather(*(_thumb_one(f) for f in ctx.files))


async def _post_zip(ctx: CrawlContext) -> None:
    if not ctx.request.zip_output or not ctx.files:
        return
    ctx.emit("Compactando arquivos...", 98)
    zip_path = await zip_job_output(ctx.output_dir, ctx.files)
    ctx.job.zip_path = str(zip_path)
    ctx.emit(f"Zip criado: {zip_path.name}", 99)


_POST_STAGES: tuple[_Stage, ...] = (
    _Stage("convert", _post_convert),
    _Stage("thumbnails", _post_thumbnails),
    _Stage("zip", _post_zip),
)


# ── Entry point ─────────────────────────────────────────────────────────────

async def crawl_assets(
    request: ExtractionRequest,
    job: JobState,
    on_progress: Optional[Callable[[JobState], None]] = None,
    # (url, current_job_id) -> most recent prior *done* JobState for that URL,
    # or None. Used to compute job.diff. Only api.py wires this up (it has the
    # JobStore); the CLI runs without persistence so diffing is simply skipped.
    find_previous_job: Optional[Callable[[str, str], Awaitable[Optional[JobState]]]] = None,
) -> list[ExtractedFile]:
    """Main entry point. Runs all applicable extractors and returns all files
    found. Updates job state in place; calls on_progress after each change."""
    output_dir = Path(request.output_dir or f"downloads/{job.job_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    job.output_dir = str(output_dir)

    ctx = CrawlContext(
        request=request,
        job=job,
        output_dir=output_dir,
        on_progress=on_progress,
        want={ct.value for ct in request.content_types},
        wanted_extensions=set(request.target_extensions) if request.target_extensions else None,
        blocked_domains=set(request.blocked_domains),
        expected_hashes=dict(request.expected_hashes),
    )
    for ct_val in ctx.want:
        ctx.wanted_categories |= _CT_TO_CATEGORIES.get(ct_val, set())

    _RESUME_EVENTS[job.job_id] = ctx.resume_event
    try:
        return await _run_pipeline(ctx, find_previous_job)
    finally:
        _RESUME_EVENTS.pop(job.job_id, None)


async def _run_pipeline(
    ctx: CrawlContext,
    find_previous_job: Optional[Callable[[str, str], Awaitable[Optional[JobState]]]],
) -> list[ExtractedFile]:
    request, job, on_progress = ctx.request, ctx.job, ctx.on_progress

    ctx.emit("Iniciando navegador...", 2)
    headless = request.headless if request.headless is not None else not request.auth.manual_captcha

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            ctx.browser_context = context
            ctx.page = await context.new_page()

            await _authenticate(ctx)
            ctx.pw_cookies = await context.cookies()
            await _prepare_page(ctx)

            for stage in _BROWSER_STAGES:
                await _run_stage(stage, ctx)
        finally:
            # Always close the browser, including on cancellation — otherwise a
            # cancelled job leaves an orphaned Chromium process behind.
            await browser.close()

    for stage in _POST_STAGES:
        await _run_stage(stage, ctx)

    if ctx.cancelled():
        job.message = f"Cancelado. {len(ctx.files)} arquivo(s) extraído(s) antes do cancelamento."
    else:
        job.status = JobStatus.done
        job.progress = 100
        job.message = f"Concluído. {len(ctx.files)} arquivo(s) extraído(s)."

    await _post_diff(ctx, find_previous_job)

    if on_progress:
        on_progress(job)

    await _post_webhook(ctx)
    return ctx.files


async def _authenticate(ctx: CrawlContext) -> None:
    auth = ctx.request.auth
    page = ctx.page

    if auth.method == AuthMethod.cookies and auth.cookies_raw:
        ctx.emit("Carregando cookies...", 5)
        n = await load_cookies(ctx.browser_context, ctx.request.url, raw=auth.cookies_raw)
        ctx.emit(f"{n} cookie(s) carregados", 8)
        return

    if auth.method == AuthMethod.cookies_browser and auth.cookies_browser:
        ctx.emit(f"Importando cookies do {auth.cookies_browser}...", 5)
        n = await load_cookies(
            ctx.browser_context, ctx.request.url,
            browser_name=auth.cookies_browser,
            profile=auth.cookies_profile,
        )
        ctx.emit(f"{n} cookie(s) importados", 8)
        return

    if auth.method != AuthMethod.credentials and not auth.credential_profile:
        return

    username, password, totp = auth.username, auth.password, auth.totp_secret
    if auth.credential_profile:
        profile = await resolve_credential_profile(auth.credential_profile)
        if profile:
            username = username or profile.username
            password = password or profile.password
            totp = totp or profile.totp_secret
        else:
            ctx.emit(f"Perfil de credencial '{auth.credential_profile}' não encontrado", 5)

    if not (username and password):
        return

    ctx.emit("Realizando login...", 5)

    def _on_captcha(msg: str):
        ctx.job.status = JobStatus.waiting_captcha
        ctx.emit(f"⚠ {msg}", 8)

    try:
        success = await apply_credentials(
            page, ctx.request.url, username, password,
            manual_captcha=auth.manual_captcha,
            on_captcha_detected=_on_captcha,
            totp_secret=totp,
        )
        ctx.job.status = JobStatus.running
        ctx.emit("Login concluído" if success else "Formulário não encontrado; continuando", 10)
    except Exception as e:
        # Never log the credentials themselves, only that the attempt failed.
        log.warning("Login attempt failed", extra={"extra_fields": {"error": str(e)}})
        ctx.emit(f"Erro no login: {e}", 10)


async def _prepare_page(ctx: CrawlContext) -> None:
    page = ctx.page
    if page.url == "about:blank":
        try:
            await page.goto(ctx.request.url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass

    paywall_warning = await detect_paywall(page)
    if paywall_warning:
        ctx.job.paywall_warning = paywall_warning
        ctx.emit(f"⚠ {paywall_warning}", -1)

    if ctx.request.wait_selector:
        try:
            await page.goto(
                ctx.request.url, wait_until="domcontentloaded",
                timeout=ctx.request.wait_timeout_ms,
            )
            await page.wait_for_selector(ctx.request.wait_selector, timeout=15000)
        except Exception:
            pass  # best-effort — extractors below still navigate/wait on their own


async def _post_diff(
    ctx: CrawlContext,
    find_previous_job: Optional[Callable[[str, str], Awaitable[Optional[JobState]]]],
) -> None:
    if not find_previous_job or ctx.cancelled():
        return
    try:
        previous = await find_previous_job(ctx.request.url, ctx.job.job_id)
        if previous:
            ctx.job.diff = compute_diff(previous, ctx.files)
    except Exception:
        pass  # diffing is a convenience, never fatal to the job


async def _post_webhook(ctx: CrawlContext) -> None:
    url = ctx.request.webhook_url
    if not url:
        return
    if urlparse(url).scheme not in ("http", "https"):
        log.warning("Webhook URL rejected: unsupported scheme")
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                url,
                content=ctx.job.model_dump_json(),
                headers={"Content-Type": "application/json"},
            )
    except Exception as e:
        # Best-effort — a broken webhook must never fail the job.
        log.warning("Webhook delivery failed", extra={"extra_fields": {"error": str(e)}})


def compute_diff(previous: JobState, current_files: list[ExtractedFile]) -> DiffResult:
    prev_by_filename = {f.filename: f for f in previous.files}
    cur_by_filename = {f.filename: f for f in current_files}

    added = [name for name in cur_by_filename if name not in prev_by_filename]
    removed = [name for name in prev_by_filename if name not in cur_by_filename]
    changed = [
        name for name in cur_by_filename.keys() & prev_by_filename.keys()
        if cur_by_filename[name].content_hash
        and prev_by_filename[name].content_hash
        and cur_by_filename[name].content_hash != prev_by_filename[name].content_hash
    ]
    unchanged = len(cur_by_filename.keys() & prev_by_filename.keys()) - len(changed)

    return DiffResult(
        compared_to_job_id=previous.job_id,
        added=added,
        removed=removed,
        changed=changed,
        unchanged_count=max(0, unchanged),
    )


def _zip_job_output_sync(output_dir: Path, files: list[ExtractedFile]) -> Path:
    zip_path = output_dir / "download.zip"
    written: set[str] = set()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            # Prefer the converted file when one exists, mirroring what a user
            # would want in a single "give me everything" archive.
            path = Path(f.converted_path) if f.converted_path else (
                Path(f.local_path) if f.local_path else None
            )
            if not path or not path.exists() or path == zip_path:
                continue
            # Two files from different subdirectories can share a basename;
            # writing both under the same arcname silently produced a zip with
            # duplicate entries where most tools only extract the last one.
            arcname = path.name
            if arcname in written:
                stem, suffix = Path(arcname).stem, Path(arcname).suffix
                i = 1
                while f"{stem}_{i}{suffix}" in written:
                    i += 1
                arcname = f"{stem}_{i}{suffix}"
            written.add(arcname)
            zf.write(path, arcname=arcname)
    return zip_path


async def zip_job_output(output_dir: Path, files: list[ExtractedFile]) -> Path:
    return await asyncio.to_thread(_zip_job_output_sync, output_dir, files)


async def _crawl_additional_pages(ctx: CrawlContext) -> AsyncGenerator[ExtractedFile, None]:
    """BFS over same-domain pages (seeded by link-following, sitemap.xml,
    and/or an explicit `additional_urls` batch) running the universal
    scanner on each. Bounded by request.max_pages and request.max_files so a
    large site — or a large batch — can't run away with the job."""
    request = ctx.request
    context = ctx.browser_context
    visited: set[str] = {request.url}
    queue: list[tuple[str, int]] = []  # (url, depth)

    def _enqueue(url: str, depth: int) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return
        if url in visited or parsed.netloc in ctx.blocked_domains:
            return
        visited.add(url)
        queue.append((url, depth))

    # Explicit batch of extra seed pages — always honored regardless of
    # follow_links/use_sitemap, and never expanded further for links (depth is
    # set past max_depth so the follow_links branch below won't chain off them
    # unless the caller also wants that; treat them like first-class start pages).
    for extra_url in request.additional_urls:
        _enqueue(extra_url, 1)

    if request.use_sitemap:
        try:
            for link in await discover_sitemap_urls(request.url, max_urls=request.max_pages):
                _enqueue(link, 1)
        except Exception as e:
            log.warning("Sitemap discovery failed", extra={"extra_fields": {"error": str(e)}})

    if request.follow_links and request.max_depth > 0:
        disc_page = await context.new_page()
        try:
            await disc_page.goto(request.url, wait_until="networkidle", timeout=60000)
            for link in await discover_same_domain_links(disc_page, request.url):
                _enqueue(link, 1)
        except Exception as e:
            log.warning("Link discovery failed", extra={"extra_fields": {"error": str(e)}})
        finally:
            await disc_page.close()

    pages_visited = 1  # the start URL was already crawled by the caller
    while queue and pages_visited < request.max_pages and len(ctx.files) < request.max_files:
        if ctx.cancelled():
            return
        await ctx.wait_if_paused()

        page_url, depth = queue.pop(0)
        pages_visited += 1
        ctx.emit(f"Crawling ({pages_visited}/{request.max_pages}): {page_url}", -1)

        sub_page = await context.new_page()
        try:
            async for f in extract_universal(
                sub_page, page_url, ctx.output_dir,
                wanted_categories=None if ctx.want_all else ctx.wanted_categories,
                wanted_extensions=ctx.wanted_extensions,
                max_files=max(0, request.max_files - len(ctx.files)),
                already_seen=set(ctx.seen_filenames),
                min_size_bytes=request.min_file_size_bytes,
                url_pattern=request.url_pattern,
                metadata_only=request.metadata_only,
                concurrency=request.download_concurrency,
                max_retries=request.download_retries,
                wait_until=request.wait_until,
                wait_timeout_ms=request.wait_timeout_ms,
                blocked_domains=ctx.blocked_domains,
                max_file_size_bytes=request.max_file_size_bytes,
                download_priority=request.download_priority,
                verify_mime=request.verify_mime,
                scan_with_clamav=request.scan_with_clamav,
            ):
                yield f

            if request.follow_links and depth < request.max_depth:
                for link in await discover_same_domain_links(sub_page, page_url):
                    _enqueue(link, depth + 1)
        except Exception as e:
            ctx.emit(f"Crawling {page_url} falhou: {e}", -1)
        finally:
            await sub_page.close()
