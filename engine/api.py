"""FastAPI server exposing the extraction engine via REST + WebSocket."""
from __future__ import annotations

import asyncio
import os
import shutil
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from job_store import ACTIVE_STATUSES, JobStore
from logging_config import configure_logging, get_logger
from models import (
    CredentialProfile,
    ExtractionRequest,
    JobState,
    JobStatus,
    JobTemplate,
    ScheduleConfig,
)
from extractors.crawler import crawl_assets, _zip_job_output
from stores import make_stores

configure_logging()
log = get_logger("api")

app = FastAPI(title="PageCap API", version="1.0.0")

# ── Optional local-only auth ────────────────────────────────────────────────
# Off by default (the whole point of binding to 127.0.0.1 is that no token is
# normally needed). Set PAGECAP_API_TOKEN to require `Authorization: Bearer
# <token>` on every route except /health — useful if the user tunnels the API
# somewhere less trusted than their own loopback interface.
_API_TOKEN = os.getenv("PAGECAP_API_TOKEN")

# ── Optional rate limiting ──────────────────────────────────────────────────
# Off by default (0). A local single-user tool doesn't need this against
# outside attackers, but it's a cheap guard against a runaway script/loop
# hammering the API from the same machine. Sliding-window per client IP.
_RATE_LIMIT_PER_MINUTE = int(os.getenv("PAGECAP_RATE_LIMIT_PER_MINUTE", "0"))
_rate_buckets: dict[str, deque] = {}


@app.middleware("http")
async def _security_middleware(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)

    if _API_TOKEN:
        header = request.headers.get("authorization", "")
        if header != f"Bearer {_API_TOKEN}":
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API token"})

    if _RATE_LIMIT_PER_MINUTE > 0:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        bucket = _rate_buckets.setdefault(client_ip, deque())
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= _RATE_LIMIT_PER_MINUTE:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        bucket.append(now)

    return await call_next(request)

# The engine binds to 127.0.0.1, but any website the user browses could still
# POST to the local API unless we restrict CORS. We only trust localhost dev
# origins and the packaged Electron renderer (file:// → Origin "null").
# Extra origins can be added via PAGECAP_CORS_ORIGINS (comma-separated).
_EXTRA_ORIGINS = [
    o for o in (o.strip() for o in os.getenv("PAGECAP_CORS_ORIGINS", "").split(","))
    if o and o != "*"  # never allow a bare wildcard — it would open CORS to any origin
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["null", *_EXTRA_ORIGINS],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

# In-memory cache of JobState, rehydrated from and mirrored into JobStore
# (SQLite) so job history survives a server restart. _ws_connections and its
# lock guard against concurrent mutation from _broadcast (readers) and the
# websocket connect/disconnect handlers (writers) racing on the same list.
_jobs: dict[str, JobState] = {}
_ws_connections: dict[str, list[WebSocket]] = {}
_ws_lock = asyncio.Lock()

DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

DB_PATH = Path(os.getenv("PAGECAP_DB_PATH", "pagecap.db"))
_store = JobStore(DB_PATH)
_credential_store, _template_store, _schedule_store = make_stores(DB_PATH)

# Jobs that finished (done/error/cancelled) longer than this get evicted —
# both their DB row and their downloads/<job_id>/ folder — by the background
# sweep below. Jobs that are still queued/running/waiting_captcha are never
# evicted regardless of age.
JOB_TTL_SECONDS = float(os.getenv("PAGECAP_JOB_TTL_SECONDS", str(3 * 24 * 3600)))
_EVICTION_INTERVAL_SECONDS = float(os.getenv("PAGECAP_EVICTION_INTERVAL_SECONDS", "3600"))

_eviction_task: asyncio.Task | None = None
_scheduler_task: asyncio.Task | None = None
_server_started_at = time.time()
_SCHEDULER_INTERVAL_SECONDS = float(os.getenv("PAGECAP_SCHEDULER_INTERVAL_SECONDS", "30"))


@app.on_event("startup")
async def _on_startup():
    global _eviction_task, _scheduler_task
    for job in await _store.load_all():
        _jobs[job.job_id] = job
        _ws_connections.setdefault(job.job_id, [])
    _eviction_task = asyncio.create_task(_eviction_loop())
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    log.info("PageCap API started", extra={"extra_fields": {"jobs_loaded": len(_jobs)}})


@app.on_event("shutdown")
async def _on_shutdown():
    for task in (_eviction_task, _scheduler_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    log.info("PageCap API stopped")


async def _eviction_loop():
    while True:
        try:
            await asyncio.sleep(_EVICTION_INTERVAL_SECONDS)
            await _evict_expired_jobs()
        except asyncio.CancelledError:
            raise
        except Exception:
            # A sweep failure must not kill the background loop.
            continue


async def _evict_expired_jobs() -> list[str]:
    evicted: list[str] = []
    for job_id in await _store.evictable_job_ids(JOB_TTL_SECONDS):
        job = _jobs.get(job_id)
        if job and job.status in ACTIVE_STATUSES:
            continue  # stale read from DB — never evict an in-flight job
        await _store.delete(job_id)
        _jobs.pop(job_id, None)
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
            now = time.time()
            for schedule in await _schedule_store.list():
                if not schedule.enabled or schedule.next_run_at > now:
                    continue
                try:
                    job_id = await _create_and_run_job(schedule.request)
                    schedule.last_job_id = job_id
                except Exception as e:
                    log.error("Scheduled job failed to start", extra={"extra_fields": {"schedule": schedule.name, "error": str(e)}})
                schedule.next_run_at = now + schedule.interval_seconds
                await _schedule_store.save(schedule.name, schedule)
        except asyncio.CancelledError:
            raise
        except Exception:
            continue


@app.get("/health")
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
        "version": "1.0.0",
        "uptime_seconds": round(time.time() - _server_started_at, 1),
        "jobs_total": len(_jobs),
        "jobs_active": active,
        "jobs_done": done,
        "jobs_error": errored,
        "error_rate": round(errored / finished_count, 4) if finished_count else 0.0,
        "avg_duration_seconds": round(avg_duration, 2),
        "db_path": str(DB_PATH.resolve()),
        "job_ttl_seconds": JOB_TTL_SECONDS,
    }


async def _create_and_run_job(request: ExtractionRequest) -> str:
    job_id = str(uuid.uuid4())
    if not request.output_dir:
        request.output_dir = str(DOWNLOADS_DIR / job_id)

    job = JobState(job_id=job_id, url=request.url, status=JobStatus.queued)
    _jobs[job_id] = job
    async with _ws_lock:
        _ws_connections[job_id] = []
    await _store.save(job)

    asyncio.create_task(_run_job(request, job))
    return job_id


@app.post("/extract")
async def start_extraction(request: ExtractionRequest):
    job_id = await _create_and_run_job(request)
    return JSONResponse(status_code=202, content={"job_id": job_id, "status": "queued"})


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/jobs/{job_id}/files")
async def list_files(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"files": job.files}


@app.get("/jobs/{job_id}/download/{filename}")
async def download_file(job_id: str, filename: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    for f in job.files:
        if f.filename == filename and f.local_path:
            path = Path(f.local_path)
            if path.exists():
                return FileResponse(
                    path=str(path),
                    filename=filename,
                    media_type=f.content_type,
                )
    raise HTTPException(status_code=404, detail="File not found")


@app.get("/jobs/{job_id}/preview/{filename}")
async def preview_file(job_id: str, filename: str):
    """Same file as /download, but without a Content-Disposition: attachment
    header, so <img>/<video>/<audio> tags can render it inline instead of the
    browser always prompting to save it."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    for f in job.files:
        if f.filename == filename and f.local_path:
            path = Path(f.local_path)
            if path.exists():
                return FileResponse(path=str(path), media_type=f.content_type)
    raise HTTPException(status_code=404, detail="File not found")


@app.get("/jobs/{job_id}/download-all")
async def download_all(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in (JobStatus.done, JobStatus.error, JobStatus.cancelled):
        raise HTTPException(status_code=409, detail="Job still running")
    if not job.files:
        raise HTTPException(status_code=404, detail="No files to zip")

    zip_path = Path(job.zip_path) if job.zip_path else None
    if not zip_path or not zip_path.exists():
        zip_path = await _zip_job_output(Path(job.output_dir or DOWNLOADS_DIR / job_id), job.files)
        job.zip_path = str(zip_path)
        await _store.save(job)

    return FileResponse(path=str(zip_path), filename=f"{job_id}.zip", media_type="application/zip")


@app.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in (JobStatus.queued, JobStatus.running, JobStatus.waiting_captcha, JobStatus.paused):
        job.status = JobStatus.cancelled
        await _store.save(job)
    return {"cancelled": True}


@app.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.running:
        raise HTTPException(status_code=409, detail=f"Cannot pause a job in status '{job.status}'")
    job.status = JobStatus.paused
    job.message = "Pausado pelo usuário."
    await _broadcast(job)
    return {"paused": True}


@app.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.paused:
        raise HTTPException(status_code=409, detail=f"Job is not paused (status '{job.status}')")
    job.status = JobStatus.running
    job.message = "Retomado."
    await _broadcast(job)
    return {"resumed": True}


@app.get("/jobs")
async def list_jobs():
    jobs = sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)
    return {"jobs": [j.model_dump() for j in jobs]}


# ── Credential profiles ─────────────────────────────────────────────────────

@app.post("/credentials")
async def save_credential_profile(profile: CredentialProfile):
    await _credential_store.save(profile.name, profile)
    return {"saved": profile.name}


@app.get("/credentials")
async def list_credential_profiles():
    profiles = await _credential_store.list()
    # Never return the plaintext password over the API — only the caller who
    # already knows it (via POST) should have it; everyone else gets metadata.
    return {"profiles": [p.model_dump(exclude={"password", "totp_secret"}) for p in profiles]}


@app.delete("/credentials/{name}")
async def delete_credential_profile(name: str):
    await _credential_store.delete(name)
    return {"deleted": name}


# ── Job templates (reusable ExtractionRequest presets) ─────────────────────

@app.post("/templates")
async def save_template(template: JobTemplate):
    await _template_store.save(template.name, template)
    return {"saved": template.name}


@app.get("/templates")
async def list_templates():
    return {"templates": [t.model_dump() for t in await _template_store.list()]}


@app.get("/templates/{name}")
async def get_template(name: str):
    template = await _template_store.get(name)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@app.delete("/templates/{name}")
async def delete_template(name: str):
    await _template_store.delete(name)
    return {"deleted": name}


# ── Recurring schedules ──────────────────────────────────────────────────────

@app.post("/schedules")
async def save_schedule(schedule: ScheduleConfig):
    if not schedule.schedule_id:
        schedule.schedule_id = str(uuid.uuid4())
    await _schedule_store.save(schedule.name, schedule)
    return {"saved": schedule.name}


@app.get("/schedules")
async def list_schedules():
    return {"schedules": [s.model_dump() for s in await _schedule_store.list()]}


@app.delete("/schedules/{name}")
async def delete_schedule(name: str):
    await _schedule_store.delete(name)
    return {"deleted": name}


@app.websocket("/ws/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    async with _ws_lock:
        _ws_connections.setdefault(job_id, []).append(websocket)

    # Send current state immediately so the client doesn't miss events that
    # fired before the WebSocket was opened.
    job = _jobs.get(job_id)
    if job:
        await websocket.send_text(job.model_dump_json())

    # All subsequent updates are pushed by _broadcast — we just keep the
    # connection alive until the client disconnects.
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
    if job.status == JobStatus.cancelled:
        await _broadcast(job)
        return
    job.status = JobStatus.running
    await _broadcast(job)
    log.info("Job started", extra={"extra_fields": {"job_id": job.job_id, "url": job.url}})

    def on_progress(j: JobState):
        asyncio.create_task(_broadcast(j))

    try:
        await crawl_assets(request, job, on_progress=on_progress, find_previous_job=_find_previous_job)
    except Exception as e:
        job.status = JobStatus.error
        job.error = str(e)
        job.message = f"Erro: {e}"
        log.error("Job failed", extra={"extra_fields": {"job_id": job.job_id, "error": str(e)}})
    finally:
        log.info("Job finished", extra={"extra_fields": {"job_id": job.job_id, "status": job.status.value, "files": len(job.files)}})
        await _broadcast(job)


async def _broadcast(job: JobState):
    job.updated_at = time.time()
    await _store.save(job)

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
