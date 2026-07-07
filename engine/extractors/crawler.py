"""
Main orchestrator: runs all extraction strategies in sequence.

Strategy order (most specific → most general):
  1. Page → PDF           (always, if requested)
  2. yt-dlp               (platform-aware: YouTube, Vimeo, TikTok, 1800+ sites)
  3. Network interception  (any player, HLS/DASH, custom streams)
  4. DOM scan             (direct <audio>/<video> tags, linked files)
  5. Universal scanner    (ALL 150+ registered file types from DOM + network)
  6. Screen recording     (last resort: records what renders on screen)
  7. Post-download conv.  (convert each file to target format if requested)
"""
from __future__ import annotations

import asyncio
import time
import zipfile
from pathlib import Path
from typing import Awaitable, AsyncGenerator, Callable, Optional
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright

import security
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


async def crawl_assets(
    request: ExtractionRequest,
    job: JobState,
    on_progress: Optional[Callable[[JobState], None]] = None,
    # (url, current_job_id) -> most recent prior *done* JobState for that URL,
    # or None. Used to compute job.diff. Only api.py wires this up (it has the
    # JobStore); the CLI runs without persistence so diffing is simply skipped.
    find_previous_job: Optional[Callable[[str, str], Awaitable[Optional[JobState]]]] = None,
) -> list[ExtractedFile]:
    """
    Main entry point. Runs all applicable extractors and returns all files found.
    Updates job state in place; calls on_progress after each change.
    """
    output_dir = Path(request.output_dir or f"downloads/{job.job_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    job.output_dir = str(output_dir)

    want = {ct.value for ct in request.content_types}
    want_all = ContentType.all.value in want
    want_media = want_all or ContentType.videos.value in want or ContentType.audio.value in want

    # Determine which categories to pass to the universal scanner
    wanted_categories: set[str] = set()
    for ct_val in want:
        wanted_categories |= _CT_TO_CATEGORIES.get(ct_val, set())

    # Explicit extension filter (fine-grained)
    wanted_extensions: set[str] | None = (
        set(request.target_extensions) if request.target_extensions else None
    )

    files: list[ExtractedFile] = []
    seen_filenames: set[str] = set()
    seen_hashes: dict[str, str] = {}  # sha256 -> filename of the file we kept
    blocked_domains = set(request.blocked_domains)
    job_bytes_total = 0
    expected_hashes = {u: h for u, h in request.expected_hashes.items()}

    def _add(f: ExtractedFile):
        nonlocal job_bytes_total
        if f.filename in seen_filenames:
            return

        if blocked_domains and urlparse(f.url).netloc in blocked_domains:
            if f.local_path:
                Path(f.local_path).unlink(missing_ok=True)
            return

        expected = expected_hashes.get(f.url)
        if expected and f.content_hash:
            f.hash_verified = expected.lower() == f.content_hash.lower()
            if not f.hash_verified and f.local_path:
                Path(f.local_path).unlink(missing_ok=True)
                return

        if request.max_job_size_bytes and f.size_bytes:
            if job_bytes_total + f.size_bytes > request.max_job_size_bytes:
                if f.local_path:
                    Path(f.local_path).unlink(missing_ok=True)
                _emit(f"Limite de tamanho do job atingido — {f.filename} descartado", -1)
                return

        if request.dedupe_by_hash and f.content_hash:
            kept_as = seen_hashes.get(f.content_hash)
            if kept_as is not None:
                # Same bytes already saved under a different name/URL — drop
                # this copy instead of wasting disk space on a duplicate.
                if f.local_path:
                    try:
                        Path(f.local_path).unlink(missing_ok=True)
                    except OSError:
                        pass
                f.local_path = None
                f.duplicate_of = kept_as
                return
            seen_hashes[f.content_hash] = f.filename

        if f.local_path:
            job_bytes_total += f.size_bytes or 0

        seen_filenames.add(f.filename)
        files.append(f)
        job.files.append(f)

    def _emit(msg: str, progress: int = -1):
        job.message = msg
        if progress >= 0:
            job.progress = progress
        if on_progress:
            on_progress(job)

    # Per-file byte progress is broadcast at most 4x/second — the underlying
    # download callback fires on every 64KB chunk, which would otherwise flood
    # the WebSocket with dozens of messages/sec on a fast connection.
    _last_progress_emit = [0.0]

    def _emit_file_progress(filename: str, done: int, total: Optional[int]):
        now = time.time()
        if now - _last_progress_emit[0] < 0.25 and (total is None or done < total):
            return
        _last_progress_emit[0] = now
        job.current_file = FileProgress(filename=filename, bytes_done=done, bytes_total=total)
        if on_progress:
            on_progress(job)

    def _cancelled() -> bool:
        return job.status == JobStatus.cancelled

    async def _paused_wait():
        """Cooperative pause: blocks here (still cancellable) while status is
        'paused', polling every second until resumed or cancelled."""
        while job.status == JobStatus.paused:
            await asyncio.sleep(1)

    _emit("Iniciando navegador...", 2)

    if request.headless is not None:
        headless = request.headless
    else:
        headless = not request.auth.manual_captcha

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )

        # ── Authentication ────────────────────────────────────────────────────
        auth = request.auth
        page = await context.new_page()

        if auth.method == AuthMethod.cookies and auth.cookies_raw:
            _emit("Carregando cookies...", 5)
            n = await load_cookies(context, request.url, raw=auth.cookies_raw)
            _emit(f"{n} cookie(s) carregados", 8)

        elif auth.method == AuthMethod.cookies_browser and auth.cookies_browser:
            _emit(f"Importando cookies do {auth.cookies_browser}...", 5)
            n = await load_cookies(
                context, request.url,
                browser_name=auth.cookies_browser,
                profile=auth.cookies_profile,
            )
            _emit(f"{n} cookie(s) importados", 8)

        elif auth.method == AuthMethod.credentials or auth.credential_profile:
            resolved_username, resolved_password = auth.username, auth.password
            resolved_totp = auth.totp_secret
            if auth.credential_profile:
                profile = await resolve_credential_profile(auth.credential_profile)
                if profile:
                    resolved_username = resolved_username or profile.username
                    resolved_password = resolved_password or profile.password
                    resolved_totp = resolved_totp or profile.totp_secret
                else:
                    _emit(f"Perfil de credencial '{auth.credential_profile}' não encontrado", 5)

            if resolved_username and resolved_password:
                _emit("Realizando login...", 5)

                def _on_captcha(msg: str):
                    job.status = JobStatus.waiting_captcha
                    _emit(f"⚠ {msg}", 8)

                try:
                    success = await apply_credentials(
                        page, request.url,
                        resolved_username, resolved_password,
                        manual_captcha=auth.manual_captcha,
                        on_captcha_detected=_on_captcha,
                        totp_secret=resolved_totp,
                    )
                    job.status = JobStatus.running
                    _emit("Login concluído" if success else "Formulário não encontrado; continuando", 10)
                except Exception as e:
                    _emit(f"Erro no login: {e}", 10)

        pw_cookies = await context.cookies()

        if page.url == "about:blank":
            try:
                await page.goto(request.url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass

        paywall_warning = await detect_paywall(page)
        if paywall_warning:
            job.paywall_warning = paywall_warning
            _emit(f"⚠ {paywall_warning}", -1)

        if request.wait_selector:
            try:
                await page.goto(request.url, wait_until="domcontentloaded", timeout=request.wait_timeout_ms)
                await page.wait_for_selector(request.wait_selector, timeout=15000)
            except Exception:
                pass  # best-effort — extractors below still navigate/wait on their own

        # ── 1. Page → PDF ─────────────────────────────────────────────────────
        if want_all or ContentType.page_pdf.value in want:
            _emit("Capturando página como PDF...", 12)
            try:
                async for f in extract_page_pdf(page, request.url, output_dir):
                    _add(f)
                    _emit(f"PDF: {f.filename}", 18)
            except Exception as e:
                _emit(f"PDF falhou: {e}", 18)

            # PDF.js/blob-based viewers render into a blob: URL that a normal
            # HTTP fetch can never see — recover it from inside the page instead.
            try:
                async for f in extract_pdf_blobs(page, request.url, output_dir, already_seen=set(seen_filenames)):
                    _add(f)
                    _emit(f"PDF (viewer): {f.filename}", 19)
            except Exception as e:
                _emit(f"Captura de PDF blob falhou: {e}", 19)

        await _paused_wait()

        # ── 2. yt-dlp (plataformas conhecidas) ───────────────────────────────
        if want_media and not _cancelled():
            _emit("Tentando yt-dlp (YouTube, Vimeo, TikTok, etc.)...", 20)
            try:
                async for f in extract_media(
                    request.url, output_dir, list(want), quality=request.quality,
                ):
                    _add(f)
                    _emit(f"yt-dlp: {f.filename}", 28)
            except Exception as e:
                _emit(f"yt-dlp: {e}", 28)

        await _paused_wait()

        # ── 3. Interceptação de rede ──────────────────────────────────────────
        if want_media and not _cancelled():
            _emit("Interceptando requisições de mídia...", 30)
            try:
                net_page = await context.new_page()
                async for f in extract_via_network(
                    net_page, request.url, output_dir, list(want),
                    cookies=pw_cookies,
                    wait_seconds=request.network_wait,
                    max_files=request.max_files,
                    concurrency=request.download_concurrency,
                    max_retries=request.download_retries,
                    wait_until=request.wait_until,
                    wait_timeout_ms=request.wait_timeout_ms,
                ):
                    _add(f)
                    _emit(f"Rede: {f.filename}", 45)
                await net_page.close()
            except Exception as e:
                _emit(f"Interceptação: {e}", 45)

        await _paused_wait()

        # ── 4. DOM scan (tags diretas) ────────────────────────────────────────
        if want_media and not _cancelled():
            _emit("Escaneando tags de mídia no DOM...", 47)
            try:
                async for f in extract_generic_media(
                    page, request.url, output_dir, list(want), cookies=pw_cookies,
                    concurrency=request.download_concurrency,
                    max_retries=request.download_retries,
                    wait_until=request.wait_until,
                    wait_timeout_ms=request.wait_timeout_ms,
                ):
                    _add(f)
            except Exception as e:
                _emit(f"DOM scan: {e}", 50)

        await _paused_wait()

        # ── 5. Scanner universal (todos os 150+ tipos) ────────────────────────
        if not _cancelled():
            _emit("Scanner universal de arquivos...", 52)
            try:
                uni_page = await context.new_page()
                async for f in extract_universal(
                    uni_page, request.url, output_dir,
                    wanted_categories=wanted_categories if not want_all else None,
                    wanted_extensions=wanted_extensions,
                    cookies=pw_cookies,
                    max_files=max(0, request.max_files - len(files)),
                    already_seen=set(seen_filenames),
                    min_size_bytes=request.min_file_size_bytes,
                    url_pattern=request.url_pattern,
                    metadata_only=request.metadata_only,
                    wait_selector=request.wait_selector,
                    click_selector=request.click_selector,
                    click_max_times=request.click_max_times,
                    concurrency=request.download_concurrency,
                    max_retries=request.download_retries,
                    wait_until=request.wait_until,
                    wait_timeout_ms=request.wait_timeout_ms,
                    blocked_domains=blocked_domains,
                    max_file_size_bytes=request.max_file_size_bytes,
                    expected_hashes=expected_hashes,
                    download_priority=request.download_priority,
                    verify_mime=request.verify_mime,
                    scan_with_clamav=request.scan_with_clamav,
                    on_file_progress=_emit_file_progress,
                ):
                    _add(f)
                    _emit(f"Universal: {f.filename}", 78)

                async for f in extract_structured_data(
                    uni_page, request.url, output_dir, already_seen=set(seen_filenames),
                    export_csv=request.export_structured_data_csv,
                ):
                    _add(f)
                    _emit(f"Metadados: {f.filename}", 80)
                await uni_page.close()
            except Exception as e:
                _emit(f"Scanner universal: {e}", 80)

        # ── 5.5 Crawling recursivo (links + sitemap) + batch de URLs extra ─────
        needs_page_crawl = request.follow_links or request.use_sitemap or request.additional_urls
        if needs_page_crawl and not _cancelled():
            await _paused_wait()
            async for f in _crawl_additional_pages(
                context, request, output_dir, seen_filenames,
                current_file_count=lambda: len(files),
                emit=_emit, cancelled=_cancelled,
                wanted_categories=wanted_categories if not want_all else None,
                wanted_extensions=wanted_extensions,
                blocked_domains=blocked_domains,
            ):
                _add(f)

        # ── 5.6 Plugins de terceiros (PAGECAP_PLUGINS_DIR) ─────────────────────
        from plugins import load_plugins

        for plugin_name, plugin_extract in load_plugins():
            if _cancelled():
                break
            _emit(f"Plugin: {plugin_name}...", -1)
            try:
                plugin_page = await context.new_page()
                async for f in plugin_extract(plugin_page, request.url, output_dir, cookies=pw_cookies):
                    _add(f)
                    _emit(f"Plugin {plugin_name}: {f.filename}", -1)
                await plugin_page.close()
            except Exception as e:
                _emit(f"Plugin {plugin_name} falhou: {e}", -1)

        await _paused_wait()

        # ── 6. Gravação de tela ───────────────────────────────────────────────
        if request.screen_record and want_media and not _cancelled():
            _emit(f"Gravando tela por {request.screen_record_duration}s...", 82)
            try:
                async for f in extract_screen_record(
                    page, context, request.url, output_dir,
                    duration=request.screen_record_duration,
                ):
                    _add(f)
                    _emit(f"Gravação: {f.filename}", 90)
            except Exception as e:
                _emit(f"Gravação de tela: {e}", 90)

        await browser.close()

    # ── 7. Conversão pós-download ─────────────────────────────────────────────
    # `convert_to` is a global "convert everything" shortcut; `convert_rules`
    # (category → target ext, e.g. {"image": ".webp", "video": ".mp4"}) lets a
    # single job apply a different target per file category. A file matching
    # both uses convert_rules (more specific wins).
    if (request.convert_to or request.convert_rules) and files and not _cancelled():
        global_ext = (
            request.convert_to if not request.convert_to or request.convert_to.startswith(".")
            else f".{request.convert_to}"
        )
        rules = {
            cat: (ext if ext.startswith(".") else f".{ext}")
            for cat, ext in request.convert_rules.items()
        }
        _emit("Convertendo arquivos...", 92)
        converted_dir = output_dir / "converted"
        converted_dir.mkdir(exist_ok=True)

        from converter import convert_file, ConversionError

        targets: list[tuple[ExtractedFile, str]] = []
        for f in files:
            if not f.local_path:
                continue
            src_ext = Path(f.local_path).suffix.lower()
            target_ext = rules.get(category_of(src_ext)) or global_ext
            if target_ext and target_ext != src_ext:
                targets.append((f, target_ext))

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
                _emit(msg, 92 + int(6 * done_count / max(1, len(targets))))

        await asyncio.gather(*(_convert_one(f, ext) for f, ext in targets))

    # ── 7.5 Thumbnails ────────────────────────────────────────────────────────
    if request.generate_thumbnails and files and not _cancelled():
        from thumbnails import generate_thumbnail

        _emit("Gerando thumbnails...", 96)
        thumb_sem = asyncio.Semaphore(4)

        async def _thumb_one(f: ExtractedFile) -> None:
            async with thumb_sem:
                if not f.local_path:
                    return
                cat = category_of(Path(f.local_path).suffix.lower())
                if cat not in ("image", "video"):
                    return
                thumb = await generate_thumbnail(Path(f.local_path), cat)
                if thumb:
                    f.thumbnail = thumb

        await asyncio.gather(*(_thumb_one(f) for f in files))

    # ── 8. Zip do resultado ───────────────────────────────────────────────────
    if request.zip_output and files and not _cancelled():
        _emit("Compactando arquivos...", 98)
        try:
            zip_path = await _zip_job_output(output_dir, files)
            job.zip_path = str(zip_path)
            _emit(f"Zip criado: {zip_path.name}", 99)
        except Exception as e:
            _emit(f"Zip falhou: {e}", 99)

    if _cancelled():
        job.message = f"Cancelado. {len(files)} arquivo(s) extraído(s) antes do cancelamento."
    else:
        job.status = JobStatus.done
        job.progress = 100
        job.message = f"Concluído. {len(files)} arquivo(s) extraído(s)."

    # ── 9. Diff contra a execução anterior da mesma URL ────────────────────────
    if find_previous_job and not _cancelled():
        try:
            previous = await find_previous_job(request.url, job.job_id)
            if previous:
                job.diff = _compute_diff(previous, files)
        except Exception:
            pass  # diffing is a convenience, never fatal to the job

    if on_progress:
        on_progress(job)

    # ── 10. Webhook de conclusão ─────────────────────────────────────────────
    if request.webhook_url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(request.webhook_url, content=job.model_dump_json(),
                                   headers={"Content-Type": "application/json"})
        except Exception:
            pass  # best-effort — a broken webhook must never fail the job

    return files


def _compute_diff(previous: JobState, current_files: list[ExtractedFile]) -> DiffResult:
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
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            # Prefer the converted file when one exists, mirroring what a user
            # would want in a single "give me everything" archive.
            path = Path(f.converted_path) if f.converted_path else (
                Path(f.local_path) if f.local_path else None
            )
            if path and path.exists() and path != zip_path:
                zf.write(path, arcname=path.name)
    return zip_path


async def _zip_job_output(output_dir: Path, files: list[ExtractedFile]) -> Path:
    return await asyncio.to_thread(_zip_job_output_sync, output_dir, files)


async def _crawl_additional_pages(
    context,
    request: ExtractionRequest,
    output_dir: Path,
    seen_filenames: set[str],
    current_file_count: Callable[[], int],
    emit: Callable[[str, int], None],
    cancelled: Callable[[], bool],
    wanted_categories: set[str] | None,
    wanted_extensions: set[str] | None,
    blocked_domains: set[str] | None = None,
) -> AsyncGenerator[ExtractedFile, None]:
    """BFS over same-domain pages (seeded by link-following, sitemap.xml,
    and/or an explicit `additional_urls` batch) running the universal
    scanner on each. Bounded by request.max_pages and request.max_files so a
    large site — or a large batch — can't run away with the job."""
    visited: set[str] = {request.url}
    queue: list[tuple[str, int]] = []  # (url, depth)
    blocked_domains = blocked_domains or set()

    # Explicit batch of extra seed pages — always honored regardless of
    # follow_links/use_sitemap, and never expanded further for links (depth
    # is set past max_depth so the follow_links branch below won't chain off them
    # unless the caller also wants that; treat them like first-class start pages).
    for extra_url in request.additional_urls:
        if extra_url not in visited and urlparse(extra_url).netloc not in blocked_domains:
            visited.add(extra_url)
            queue.append((extra_url, 1))

    if request.use_sitemap:
        try:
            for link in await discover_sitemap_urls(request.url, max_urls=request.max_pages):
                if link not in visited and urlparse(link).netloc not in blocked_domains:
                    visited.add(link)
                    queue.append((link, 1))
        except Exception:
            pass

    if request.follow_links and request.max_depth > 0:
        try:
            disc_page = await context.new_page()
            await disc_page.goto(request.url, wait_until="networkidle", timeout=60000)
            for link in await discover_same_domain_links(disc_page, request.url):
                if link not in visited:
                    visited.add(link)
                    queue.append((link, 1))
            await disc_page.close()
        except Exception:
            pass

    pages_visited = 1  # the start URL was already crawled by the caller
    while queue and pages_visited < request.max_pages and current_file_count() < request.max_files:
        if cancelled():
            return
        page_url, depth = queue.pop(0)
        pages_visited += 1

        emit(f"Crawling ({pages_visited}/{request.max_pages}): {page_url}", -1)
        sub_page = None
        try:
            sub_page = await context.new_page()
            async for f in extract_universal(
                sub_page, page_url, output_dir,
                wanted_categories=wanted_categories,
                wanted_extensions=wanted_extensions,
                max_files=max(0, request.max_files - current_file_count()),
                already_seen=set(seen_filenames),
                min_size_bytes=request.min_file_size_bytes,
                url_pattern=request.url_pattern,
                metadata_only=request.metadata_only,
                concurrency=request.download_concurrency,
                max_retries=request.download_retries,
                wait_until=request.wait_until,
                wait_timeout_ms=request.wait_timeout_ms,
                blocked_domains=blocked_domains,
                max_file_size_bytes=request.max_file_size_bytes,
                download_priority=request.download_priority,
                verify_mime=request.verify_mime,
                scan_with_clamav=request.scan_with_clamav,
            ):
                yield f

            if request.follow_links and depth < request.max_depth:
                for link in await discover_same_domain_links(sub_page, page_url):
                    if link not in visited and urlparse(link).netloc not in blocked_domains:
                        visited.add(link)
                        queue.append((link, depth + 1))
        except Exception as e:
            emit(f"Crawling {page_url} falhou: {e}", -1)
        finally:
            if sub_page:
                await sub_page.close()
