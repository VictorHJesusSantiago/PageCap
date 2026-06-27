"""FastAPI server exposing the extraction engine via REST + WebSocket."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from models import ExtractionRequest, JobState, JobStatus
from extractors.crawler import crawl_assets

app = FastAPI(title="PageCap API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store
_jobs: dict[str, JobState] = {}
_ws_connections: dict[str, list[WebSocket]] = {}

DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/extract")
async def start_extraction(request: ExtractionRequest):
    job_id = str(uuid.uuid4())
    if not request.output_dir:
        request.output_dir = str(DOWNLOADS_DIR / job_id)

    job = JobState(job_id=job_id, url=request.url, status=JobStatus.queued)
    _jobs[job_id] = job
    _ws_connections[job_id] = []

    asyncio.create_task(_run_job(request, job))

    return {"job_id": job_id, "status": "queued"}


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


@app.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == JobStatus.running:
        job.status = JobStatus.cancelled
    return {"cancelled": True}


@app.get("/jobs")
async def list_jobs():
    return {"jobs": [j.model_dump() for j in _jobs.values()]}


@app.websocket("/ws/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    if job_id not in _ws_connections:
        _ws_connections[job_id] = []
    _ws_connections[job_id].append(websocket)

    # Send current state immediately
    job = _jobs.get(job_id)
    if job:
        await websocket.send_text(job.model_dump_json())

    try:
        while True:
            await asyncio.sleep(0.5)
            job = _jobs.get(job_id)
            if job and job.status in (JobStatus.done, JobStatus.error, JobStatus.cancelled):
                await websocket.send_text(job.model_dump_json())
                break
    except WebSocketDisconnect:
        pass
    finally:
        if job_id in _ws_connections:
            try:
                _ws_connections[job_id].remove(websocket)
            except ValueError:
                pass


async def _run_job(request: ExtractionRequest, job: JobState):
    job.status = JobStatus.running
    await _broadcast(job)

    def on_progress(j: JobState):
        asyncio.create_task(_broadcast(j))

    try:
        await crawl_assets(request, job, on_progress=on_progress)
    except Exception as e:
        job.status = JobStatus.error
        job.error = str(e)
        job.message = f"Erro: {e}"
    finally:
        await _broadcast(job)


async def _broadcast(job: JobState):
    conns = _ws_connections.get(job.job_id, [])
    dead = []
    for ws in conns:
        try:
            await ws.send_text(job.model_dump_json())
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            conns.remove(ws)
        except ValueError:
            pass
