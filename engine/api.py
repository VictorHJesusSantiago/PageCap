"""FastAPI server exposing the extraction engine via REST + WebSocket.

Routing: every endpoint is mounted twice — under `/v1` (canonical) and at the
root (legacy, undocumented, served with `Deprecation`/`Sunset` headers). See
ADR-002 for the retirement schedule of the unversioned paths.

Security: auth is enforced by default. See `auth/tokens.py` and ADR-001.
"""
from __future__ import annotations

import asyncio
import hmac
import re
import shutil
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

import problem_details
from auth.tokens import resolve_api_token
from config import settings
from job_store import ACTIVE_STATUSES, JobStore
from logging_config import configure_logging, get_logger, log_context, set_request_id
from models import (
    PUBLIC_EXCLUDE,
    CredentialProfile,
    ExtractionRequest,
    JobState,
    JobStatus,
    JobTemplate,
    ScheduleConfig,
)
from extractors.crawler import crawl_assets, signal_resume, zip_job_output
from stores import make_stores

configure_logging()
log = get_logger("api")

API_VERSION = "1.0.0"
API_PREFIX = "/v1"

LEGACY_SUNSET = "Wed, 31 Dec 2026 23:59:59 GMT"

DOWNLOADS_DIR = settings.downloads_dir
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = settings.db_path
_store = JobStore(DB_PATH)
_credential_store, _template_store, _schedule_store = make_stores(DB_PATH)

_API_TOKEN = resolve_api_token(settings.api_token, settings.token_file, settings.require_auth)

_RATE_LIMIT_PER_MINUTE = settings.rate_limit_per_minute
_rate_buckets: dict[str, deque] = {}

_UNAUTHENTICATED_PATHS = {"/health", "/health/live", "/health/ready"}

JOB_TTL_SECONDS = settings.job_ttl_seconds
_EVICTION_INTERVAL_SECONDS = settings.eviction_interval_seconds
_SCHEDULER_INTERVAL_SECONDS = settings.scheduler_interval_seconds
_PERSIST_INTERVAL_SECONDS = settings.persist_interval_seconds
_SHUTDOWN_DRAIN_SECONDS = settings.shutdown_drain_seconds

_jobs: dict[str, JobState] = {}
_ws_connections: dict[str, list[WebSocket]] = {}
_ws_lock = asyncio.Lock()

_background_tasks: set[asyncio.Task] = set()
_job_tasks: dict[str, asyncio.Task] = {}

_eviction_task: asyncio.Task | None = None
_scheduler_task: asyncio.Task | None = None
_server_started_at = time.time()
_shutting_down = False

_metrics = {
    "http_requests_total": 0,
    "http_errors_total": 0,
    "jobs_started_total": 0,
    "jobs_completed_total": 0,
    "jobs_failed_total": 0,
    "jobs_cancelled_total": 0,
    "files_extracted_total": 0,
    "bytes_downloaded_total": 0,
}
_request_durations: deque[float] = deque(maxlen=1000)


def _spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return round(ordered[index], 4)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Startup/shutdown. The single context manager guarantees the background
    tasks are cancelled even if startup raised part-way through, and gives
    in-flight jobs a bounded window to finish before the process exits."""
    global _eviction_task, _scheduler_task, _shutting_down
    _shutting_down = False

    for job in await _store.load_all():
        if job.status in ACTIVE_STATUSES:
            job.status = JobStatus.error
            job.error = "Servidor reiniciado durante a execução deste job."
            job.message = job.error
            await _store.save(job)
        _jobs[job.job_id] = job
        _ws_connections.setdefault(job.job_id, [])

    _eviction_task = asyncio.create_task(_eviction_loop())
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    log.info(
        "PageCap API started",
        extra={"extra_fields": {
            "jobs_loaded": len(_jobs),
            "auth_enabled": _API_TOKEN is not None,
        }},
    )

    try:
        yield
    finally:
        _shutting_down = True
        await _drain_jobs()
        for task in (_eviction_task, _scheduler_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        log.info("PageCap API stopped")


async def _drain_jobs() -> None:
    """Graceful shutdown (12-factor IX). Signals every in-flight job to stop
    cooperatively, then waits up to _SHUTDOWN_DRAIN_SECONDS for the tasks to
    unwind so partial output is flushed and Playwright/ffmpeg children are
    closed instead of orphaned."""
    running = [t for t in _job_tasks.values() if not t.done()]
    if not running:
        return

    for job_id in list(_job_tasks):
        job = _jobs.get(job_id)
        if job and job.status in ACTIVE_STATUSES:
            job.status = JobStatus.cancelled
            job.message = "Servidor encerrando — job cancelado."

    log.info("Draining in-flight jobs", extra={"extra_fields": {"count": len(running)}})
    done, pending = await asyncio.wait(running, timeout=_SHUTDOWN_DRAIN_SECONDS)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.wait(pending, timeout=5)
        log.warning(
            "Some jobs did not finish draining and were cancelled",
            extra={"extra_fields": {"count": len(pending)}},
        )


async def _eviction_loop():
    while True:
        try:
            await asyncio.sleep(_EVICTION_INTERVAL_SECONDS)
            await _evict_expired_jobs()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Eviction sweep failed")
            continue


async def _evict_expired_jobs() -> list[str]:
    evicted: list[str] = []
    for job_id in await _store.evictable_job_ids(JOB_TTL_SECONDS):
        job = _jobs.get(job_id)
        if job and job.status in ACTIVE_STATUSES:
            continue
        await _store.delete(job_id)
        _jobs.pop(job_id, None)
        _last_persist.pop(job_id, None)
        async with _ws_lock:
            _ws_connections.pop(job_id, None)
        job_dir = DOWNLOADS_DIR / job_id
        if job_dir.exists() and job_dir.is_dir():
            shutil.rmtree(job_dir, ignore_errors=True)
        evicted.append(job_id)
    return evicted


async def _scheduler_loop():
    """Polls stored ScheduleConfig rows every _SCHEDULER_INTERVAL_SECONDS and
    fires any that are due. This is a simple fixed-interval recurring
    scheduler (interval_seconds), not full cron syntax — sufficient for
    "re-check this page every N minutes/hours" monitoring use cases."""
    while True:
        try:
            await asyncio.sleep(_SCHEDULER_INTERVAL_SECONDS)
            if _shutting_down:
                continue
            now = time.time()
            for schedule in await _schedule_store.list():
                if not schedule.enabled or schedule.next_run_at > now:
                    continue
                try:
                    job_id = await _create_and_run_job(schedule.request)
                    schedule.last_job_id = job_id
                except Exception as e:
                    log.error(
                        "Scheduled job failed to start",
                        extra={"extra_fields": {"schedule": schedule.name, "error": str(e)}},
                    )
                schedule.next_run_at = now + schedule.interval_seconds
                await _schedule_store.save(schedule.name, schedule)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Scheduler tick failed")
            continue


app = FastAPI(
    title="PageCap API",
    version=API_VERSION,
    lifespan=_lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)
problem_details.install(app)


def _normalized_path(path: str) -> str:
    """The route path with the version prefix removed, so policy decisions are
    written once instead of once per mount."""
    return path[len(API_PREFIX):] if path.startswith(API_PREFIX) else path


def _is_authorized(request: Request) -> bool:
    header = request.headers.get("authorization", "")
    query_token = request.query_params.get("token", "")
    return hmac.compare_digest(header, f"Bearer {_API_TOKEN}") or (
        bool(query_token) and hmac.compare_digest(query_token, _API_TOKEN)
    )


def _rate_limited(request: Request) -> bool:
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = _rate_buckets.setdefault(client_ip, deque())
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMIT_PER_MINUTE:
        return True
    bucket.append(now)
    return False


@app.middleware("http")
async def _request_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    set_request_id(request_id)

    path = request.url.path
    normalized = _normalized_path(path)
    exempt = normalized in _UNAUTHENTICATED_PATHS or path in ("/docs", "/openapi.json", "/redoc")

    started = time.perf_counter()
    try:
        if not exempt and _API_TOKEN and not _is_authorized(request):
            response = problem_details.problem(
                401,
                "Invalid or missing API token.",
                instance=path,
                headers={"WWW-Authenticate": "Bearer"},
                request=request,
            )
        elif not exempt and _RATE_LIMIT_PER_MINUTE > 0 and _rate_limited(request):
            response = problem_details.problem(
                429,
                "Rate limit exceeded.",
                instance=path,
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(_RATE_LIMIT_PER_MINUTE),
                    "X-RateLimit-Remaining": "0",
                },
                request=request,
            )
        else:
            response = await call_next(request)
    finally:
        set_request_id(None)

    _request_durations.append(time.perf_counter() - started)
    _metrics["http_requests_total"] += 1
    if response.status_code >= 500:
        _metrics["http_errors_total"] += 1

    response.headers["X-Request-ID"] = request_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Content-Security-Policy", "default-src 'none'; sandbox")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")

    if not path.startswith(API_PREFIX) and normalized not in _UNAUTHENTICATED_PATHS:
        response.headers.setdefault("Deprecation", "true")
        response.headers.setdefault("Sunset", LEGACY_SUNSET)
        response.headers.setdefault("Link", f'<{API_PREFIX}{path}>; rel="successor-version"')
    return response


_ALLOW_NULL_ORIGIN = settings.allow_null_origin
_EXTRA_ORIGINS = list(settings.extra_cors_origins)

if _ALLOW_NULL_ORIGIN and not _API_TOKEN:
    log.warning(
        "PAGECAP_ALLOW_NULL_ORIGIN is set without authentication — any website "
        "can read this API from a sandboxed iframe."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=(["null"] if _ALLOW_NULL_ORIGIN else []) + _EXTRA_ORIGINS,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Deprecation", "Sunset", "Retry-After"],
)


_last_persist: dict[str, tuple[float, JobStatus]] = {}


def _should_persist(job: JobState, now: float) -> bool:
    if job.status not in ACTIVE_STATUSES:
        return True
    last = _last_persist.get(job.job_id)
    return last is None or last[1] != job.status or now - last[0] >= _PERSIST_INTERVAL_SECONDS


router = APIRouter()


@router.get("/health")
async def health():
    active = sum(1 for j in _jobs.values() if j.status in ACTIVE_STATUSES)
    done = sum(1 for j in _jobs.values() if j.status == JobStatus.done)
    errored = sum(1 for j in _jobs.values() if j.status == JobStatus.error)
    finished = [j for j in _jobs.values() if j.status in (JobStatus.done, JobStatus.error, JobStatus.cancelled)]
    finished_count = len(finished)
    avg_duration = (
        sum(j.updated_at - j.created_at for j in finished) / finished_count
        if finished_count else 0.0
    )
    return {
        "status": "ok",
        "version": API_VERSION,
        "uptime_seconds": round(time.time() - _server_started_at, 1),
        "jobs_total": len(_jobs),
        "jobs_active": active,
        "jobs_done": done,
        "jobs_error": errored,
        "error_rate": round(errored / finished_count, 4) if finished_count else 0.0,
        "avg_duration_seconds": round(avg_duration, 2),
        "db_name": DB_PATH.name,
        "job_ttl_seconds": JOB_TTL_SECONDS,
        "auth_required": _API_TOKEN is not None,
    }


@router.get("/health/live")
async def liveness():
    """Liveness probe: the process is up. Never touches the DB, so a database
    problem restarts nothing — that is what readiness is for."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness():
    """Readiness probe: can we actually serve? Verifies the datastore responds
    and that we are not mid-shutdown."""
    if _shutting_down:
        raise HTTPException(status_code=503, detail="Server is shutting down")
    try:
        await _store.evictable_job_ids(float("inf"))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Datastore unavailable: {e}")
    return {"status": "ready"}


@router.get("/metrics")
async def metrics():
    """RED metrics (Rate, Errors, Duration) as JSON. Latency is reported as
    percentiles, never as an average — an average hides exactly the tail that
    users notice."""
    durations = list(_request_durations)
    return {
        "counters": dict(_metrics),
        "http_request_duration_seconds": {
            "count": len(durations),
            "p50": _percentile(durations, 50),
            "p95": _percentile(durations, 95),
            "p99": _percentile(durations, 99),
            "p999": _percentile(durations, 99.9),
        },
        "gauges": {
            "jobs_in_memory": len(_jobs),
            "jobs_active": sum(1 for j in _jobs.values() if j.status in ACTIVE_STATUSES),
            "websocket_connections": sum(len(v) for v in _ws_connections.values()),
            "background_tasks": len(_background_tasks),
        },
    }


async def _create_and_run_job(request: ExtractionRequest) -> str:
    if _shutting_down:
        raise HTTPException(status_code=503, detail="Server is shutting down")

    job_id = str(uuid.uuid4())
    if not request.output_dir:
        request.output_dir = str(DOWNLOADS_DIR / job_id)

    job = JobState(job_id=job_id, url=request.url, status=JobStatus.queued)
    _jobs[job_id] = job
    async with _ws_lock:
        _ws_connections[job_id] = []
    await _store.save(job)
    _metrics["jobs_started_total"] += 1

    task = _spawn(_run_job(request, job))
    _job_tasks[job_id] = task
    task.add_done_callback(lambda _t, jid=job_id: _job_tasks.pop(jid, None))
    return job_id


@router.post("/extract", status_code=202)
async def start_extraction(request: ExtractionRequest):
    job_id = await _create_and_run_job(request)
    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "status": "queued"},
        headers={"Location": f"{API_PREFIX}/jobs/{job_id}"},
    )


def _require_job(job_id: str) -> JobState:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    return _require_job(job_id)


@router.get("/jobs/{job_id}/files")
async def list_files(job_id: str):
    return {"files": _require_job(job_id).files}


_INLINE_SAFE_PREFIXES = ("image/", "audio/", "video/")
_INLINE_UNSAFE_EXACT = {"image/svg+xml"}


def _resolve_job_file(job: JobState, filename: str) -> tuple[Path, str]:
    """Locates `filename` among a job's extracted files and returns
    (path, content_type). Raises 404 for anything not recorded on the job, not
    on disk, or resolving outside the job's own output directory."""
    root = Path(job.output_dir or DOWNLOADS_DIR / job.job_id).resolve()
    for f in job.files:
        if f.filename != filename or not f.local_path:
            continue
        path = Path(f.local_path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            break
        return path, f.content_type
    raise HTTPException(status_code=404, detail="File not found")


@router.get("/jobs/{job_id}/download/{filename}")
async def download_file(job_id: str, filename: str):
    path, content_type = _resolve_job_file(_require_job(job_id), filename)
    return FileResponse(path=str(path), filename=filename, media_type=content_type)


@router.get("/jobs/{job_id}/preview/{filename}")
async def preview_file(job_id: str, filename: str):
    """Same file as /download, but without a Content-Disposition: attachment
    header, so <img>/<video>/<audio> tags can render it inline instead of the
    browser always prompting to save it."""
    path, content_type = _resolve_job_file(_require_job(job_id), filename)

    base = content_type.split(";")[0].strip().lower()
    inline_safe = base.startswith(_INLINE_SAFE_PREFIXES) and base not in _INLINE_UNSAFE_EXACT
    if not inline_safe:
        return FileResponse(
            path=str(path), filename=filename, media_type="application/octet-stream"
        )
    return FileResponse(path=str(path), media_type=base)


@router.get("/jobs/{job_id}/download-all")
async def download_all(job_id: str):
    job = _require_job(job_id)
    if job.status in ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="Job still running")
    if not job.files:
        raise HTTPException(status_code=404, detail="No files to zip")

    zip_path = Path(job.zip_path) if job.zip_path else None
    if not zip_path or not zip_path.exists():
        zip_path = await zip_job_output(Path(job.output_dir or DOWNLOADS_DIR / job_id), job.files)
        job.zip_path = str(zip_path)
        await _store.save(job)

    return FileResponse(path=str(zip_path), filename=f"{job_id}.zip", media_type="application/zip")


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancels a running job. This is deliberately not a resource delete — the
    job row survives so its history and partial output stay inspectable; TTL
    eviction is what removes it."""
    job = _require_job(job_id)
    if job.status in ACTIVE_STATUSES:
        job.status = JobStatus.cancelled
        _metrics["jobs_cancelled_total"] += 1
        signal_resume(job_id)
        await _store.save(job)
    return {"cancelled": True, "status": job.status.value}


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str):
    job = _require_job(job_id)
    if job.status != JobStatus.running:
        raise HTTPException(status_code=409, detail=f"Cannot pause a job in status '{job.status.value}'")
    job.status = JobStatus.paused
    job.message = "Pausado pelo usuário."
    await _broadcast(job)
    return {"paused": True}


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str):
    job = _require_job(job_id)
    if job.status != JobStatus.paused:
        raise HTTPException(status_code=409, detail=f"Job is not paused (status '{job.status.value}')")
    job.status = JobStatus.running
    job.message = "Retomado."
    signal_resume(job_id)
    await _broadcast(job)
    return {"resumed": True}


_MAX_PAGE_SIZE = 200


@router.get("/jobs")
async def list_jobs(limit: int = 50, cursor: Optional[str] = None):
    """Newest-first, cursor-paginated. The cursor is the `created_at` of the
    last item seen — keyset pagination, so the page stays stable and O(1) even
    as new jobs arrive, which OFFSET does not."""
    if limit < 1 or limit > _MAX_PAGE_SIZE:
        raise HTTPException(status_code=422, detail=f"limit must be between 1 and {_MAX_PAGE_SIZE}")

    ordered = sorted(_jobs.values(), key=lambda j: (j.created_at, j.job_id), reverse=True)
    if cursor:
        try:
            cursor_value = float(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="cursor must be a numeric created_at value")
        ordered = [j for j in ordered if j.created_at < cursor_value]

    page = ordered[:limit]
    next_cursor = str(page[-1].created_at) if len(ordered) > limit and page else None
    return {
        "jobs": [j.model_dump() for j in page],
        "next_cursor": next_cursor,
        "total": len(_jobs),
    }


@router.post("/credentials")
async def save_credential_profile(profile: CredentialProfile):
    await _credential_store.save(profile.name, profile)
    return {"saved": profile.name}


@router.get("/credentials")
async def list_credential_profiles():
    profiles = await _credential_store.list()
    return {"profiles": [p.model_dump(exclude={"password", "totp_secret"}) for p in profiles]}


@router.delete("/credentials/{name}")
async def delete_credential_profile(name: str):
    await _credential_store.delete(name)
    return {"deleted": name}


@router.post("/templates")
async def save_template(template: JobTemplate):
    await _template_store.save(template.name, template)
    return {"saved": template.name}


@router.get("/templates")
async def list_templates():
    return {"templates": [t.model_dump(exclude=PUBLIC_EXCLUDE) for t in await _template_store.list()]}


@router.get("/templates/{name}")
async def get_template(name: str):
    template = await _template_store.get(name)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template.model_dump(exclude=PUBLIC_EXCLUDE)


@router.delete("/templates/{name}")
async def delete_template(name: str):
    await _template_store.delete(name)
    return {"deleted": name}


@router.post("/schedules")
async def save_schedule(schedule: ScheduleConfig):
    if not schedule.schedule_id:
        schedule.schedule_id = str(uuid.uuid4())
    await _schedule_store.save(schedule.name, schedule)
    return {"saved": schedule.name}


@router.get("/schedules")
async def list_schedules():
    return {"schedules": [s.model_dump(exclude=PUBLIC_EXCLUDE) for s in await _schedule_store.list()]}


@router.delete("/schedules/{name}")
async def delete_schedule(name: str):
    await _schedule_store.delete(name)
    return {"deleted": name}


app.include_router(router, prefix=API_PREFIX)
app.include_router(router, include_in_schema=False)


_ALLOWED_WS_ORIGIN_RE = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")


def _websocket_allowed(websocket: WebSocket) -> bool:
    """WebSockets get neither the HTTP middleware (Starlette only runs it for
    the http scope) nor CORS (browsers do not preflight ws://). Both checks
    therefore have to be repeated here, or /ws is an unauthenticated,
    any-origin read of live job state including every extracted filename."""
    if _API_TOKEN:
        token = websocket.query_params.get("token", "")
        return bool(token) and hmac.compare_digest(token, _API_TOKEN)

    origin = websocket.headers.get("origin")
    if origin is None:
        return True
    if origin == "null":
        return _ALLOW_NULL_ORIGIN
    return bool(_ALLOWED_WS_ORIGIN_RE.match(origin)) or origin in _EXTRA_ORIGINS


async def _websocket_progress(websocket: WebSocket, job_id: str):
    if not _websocket_allowed(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    async with _ws_lock:
        _ws_connections.setdefault(job_id, []).append(websocket)

    job = _jobs.get(job_id)
    if job:
        await websocket.send_text(job.model_dump_json())

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        async with _ws_lock:
            conns = _ws_connections.get(job_id)
            if conns is not None:
                try:
                    conns.remove(websocket)
                except ValueError:
                    pass


app.websocket(f"{API_PREFIX}/ws/{{job_id}}")(_websocket_progress)
app.websocket("/ws/{job_id}")(_websocket_progress)


async def _find_previous_job(url: str, current_job_id: str) -> Optional[JobState]:
    """Most recent *other* done job that crawled this exact URL — used to
    compute JobState.diff (added/removed/changed files since last run)."""
    candidates = [
        j for j in _jobs.values()
        if j.url == url and j.job_id != current_job_id and j.status == JobStatus.done
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda j: j.created_at)


async def _run_job(request: ExtractionRequest, job: JobState):
    with log_context(job_id=job.job_id):
        if job.status == JobStatus.cancelled:
            await _broadcast(job)
            return
        job.status = JobStatus.running
        await _broadcast(job)
        log.info("Job started", extra={"extra_fields": {"url": job.url}})

        def on_progress(j: JobState):
            _spawn(_broadcast(j))

        try:
            await crawl_assets(request, job, on_progress=on_progress, find_previous_job=_find_previous_job)
        except asyncio.CancelledError:
            job.status = JobStatus.cancelled
            job.message = "Cancelado."
            await _broadcast(job)
            raise
        except Exception as e:
            job.status = JobStatus.error
            job.error = str(e)
            job.message = f"Erro: {e}"
            log.exception("Job failed", extra={"extra_fields": {"error": str(e)}})
        finally:
            if job.status == JobStatus.done:
                _metrics["jobs_completed_total"] += 1
            elif job.status == JobStatus.error:
                _metrics["jobs_failed_total"] += 1
            _metrics["files_extracted_total"] += len(job.files)
            _metrics["bytes_downloaded_total"] += sum(f.size_bytes or 0 for f in job.files)
            log.info(
                "Job finished",
                extra={"extra_fields": {"status": job.status.value, "files": len(job.files)}},
            )
            await _broadcast(job)


async def _broadcast(job: JobState):
    job.updated_at = time.time()
    if _should_persist(job, job.updated_at):
        _last_persist[job.job_id] = (job.updated_at, job.status)
        await _store.save(job)
    if job.status not in ACTIVE_STATUSES:
        _last_persist.pop(job.job_id, None)

    async with _ws_lock:
        conns = list(_ws_connections.get(job.job_id, []))
    dead = []
    payload = job.model_dump_json()
    for ws in conns:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    if dead:
        async with _ws_lock:
            live = _ws_connections.get(job.job_id)
            if live is not None:
                for ws in dead:
                    if ws in live:
                        live.remove(ws)
