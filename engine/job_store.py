"""SQLite-backed persistence for JobState.

Jobs previously lived only in an in-memory dict (`api._jobs`), so restarting the
server silently dropped every job and its progress history. This module gives
jobs a durable home: each job is stored as a single JSON blob (JobState already
serializes cleanly via Pydantic) alongside a couple of indexed columns used for
TTL eviction queries.

All access goes through `asyncio.to_thread` because `sqlite3` is synchronous;
a short-lived connection is opened per call, which is fine at PageCap's scale
(single local user, low write frequency) and avoids cross-thread connection
sharing issues.
"""
from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

from models import JobState, JobStatus

ACTIVE_STATUSES = (JobStatus.queued, JobStatus.running, JobStatus.waiting_captcha, JobStatus.paused)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    state_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_updated_at ON jobs(updated_at);
"""


class JobStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_sync()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_sync(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _save_sync(self, job: JobState) -> None:
        now = time.time()
        conn = self._connect()
        try:
            existing = conn.execute(
                "SELECT created_at FROM jobs WHERE job_id = ?", (job.job_id,)
            ).fetchone()
            created_at = existing[0] if existing else now
            conn.execute(
                """
                INSERT INTO jobs (job_id, status, created_at, updated_at, state_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    state_json = excluded.state_json
                """,
                (job.job_id, job.status.value, created_at, now, job.model_dump_json()),
            )
            conn.commit()
        finally:
            conn.close()

    def _load_all_sync(self) -> list[JobState]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT state_json FROM jobs").fetchall()
            return [JobState.model_validate_json(row[0]) for row in rows]
        finally:
            conn.close()

    def _delete_sync(self, job_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            conn.commit()
        finally:
            conn.close()

    def _evictable_sync(self, cutoff: float) -> list[str]:
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(ACTIVE_STATUSES))
            rows = conn.execute(
                f"""
                SELECT job_id FROM jobs
                WHERE updated_at < ? AND status NOT IN ({placeholders})
                """,
                (cutoff, *[s.value for s in ACTIVE_STATUSES]),
            ).fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()

    async def save(self, job: JobState) -> None:
        await asyncio.to_thread(self._save_sync, job)

    async def load_all(self) -> list[JobState]:
        return await asyncio.to_thread(self._load_all_sync)

    async def delete(self, job_id: str) -> None:
        await asyncio.to_thread(self._delete_sync, job_id)

    async def evictable_job_ids(self, ttl_seconds: float) -> list[str]:
        cutoff = time.time() - ttl_seconds
        return await asyncio.to_thread(self._evictable_sync, cutoff)
