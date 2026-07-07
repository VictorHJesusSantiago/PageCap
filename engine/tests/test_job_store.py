import time
from pathlib import Path

import pytest

from job_store import JobStore
from models import JobState, JobStatus


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "test.db")


async def test_save_and_load(store: JobStore):
    job = JobState(job_id="abc", url="https://example.com", status=JobStatus.running)
    await store.save(job)
    jobs = await store.load_all()
    assert len(jobs) == 1
    assert jobs[0].job_id == "abc"
    assert jobs[0].status == JobStatus.running


async def test_save_overwrites_existing(store: JobStore):
    job = JobState(job_id="abc", url="https://example.com", status=JobStatus.running)
    await store.save(job)
    job.status = JobStatus.done
    await store.save(job)
    jobs = await store.load_all()
    assert len(jobs) == 1
    assert jobs[0].status == JobStatus.done


async def test_delete(store: JobStore):
    job = JobState(job_id="abc", url="https://example.com")
    await store.save(job)
    await store.delete("abc")
    assert await store.load_all() == []


async def test_evictable_respects_ttl(store: JobStore):
    job = JobState(job_id="abc", url="https://example.com", status=JobStatus.done)
    await store.save(job)

    # Not expired yet with a generous TTL.
    assert await store.evictable_job_ids(ttl_seconds=3600) == []

    # Any TTL in the past means it's evictable.
    assert await store.evictable_job_ids(ttl_seconds=-1) == ["abc"]


async def test_evictable_excludes_active_status(store: JobStore):
    job = JobState(job_id="abc", url="https://example.com", status=JobStatus.running)
    await store.save(job)
    assert await store.evictable_job_ids(ttl_seconds=-1) == []


async def test_evictable_excludes_paused_status(store: JobStore):
    # Regression: a paused job must never be swept up by TTL eviction just
    # because it's sitting idle — pausing is a user action, not abandonment.
    job = JobState(job_id="abc", url="https://example.com", status=JobStatus.paused)
    await store.save(job)
    assert await store.evictable_job_ids(ttl_seconds=-1) == []
