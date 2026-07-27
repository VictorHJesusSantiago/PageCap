"""Tests for the crawl pipeline's shared machinery: the CrawlContext funnel
every extracted file passes through, stage isolation/cancellation, and the
zip/diff helpers. The extractors themselves need a real browser and are out of
scope for the unit suite."""
import asyncio
import zipfile
from pathlib import Path

import pytest

from models import ExtractedFile, ExtractionRequest, JobState, JobStatus
from extractors.crawler import (
    CrawlContext,
    _Stage,
    _run_stage,
    _zip_job_output_sync,
    compute_diff,
    signal_resume,
)


def ctx(tmp_path: Path, **request_kwargs) -> CrawlContext:
    request = ExtractionRequest(url="https://example.com", **request_kwargs)
    job = JobState(job_id="j1", url=request.url, status=JobStatus.running)
    return CrawlContext(request=request, job=job, output_dir=tmp_path)


def a_file(tmp_path: Path, name="a.jpg", **kwargs) -> ExtractedFile:
    path = tmp_path / name
    path.write_bytes(b"x" * 32)
    defaults = dict(
        filename=name, url=f"https://example.com/{name}",
        content_type="image/jpeg", size_bytes=32, local_path=str(path),
    )
    defaults.update(kwargs)
    return ExtractedFile(**defaults)


# ── CrawlContext.add: the single policy funnel ──────────────────────────────

def test_add_accepts_a_file(tmp_path: Path):
    c = ctx(tmp_path)
    c.add(a_file(tmp_path))
    assert [f.filename for f in c.files] == ["a.jpg"]
    assert c.job.files == c.files


def test_add_rejects_a_duplicate_filename(tmp_path: Path):
    c = ctx(tmp_path)
    c.add(a_file(tmp_path))
    c.add(a_file(tmp_path))
    assert len(c.files) == 1


def test_add_drops_and_deletes_a_blocked_domain(tmp_path: Path):
    c = ctx(tmp_path, blocked_domains=["evil.example"])
    c.blocked_domains = {"evil.example"}
    f = a_file(tmp_path, url="https://evil.example/a.jpg")
    c.add(f)
    assert c.files == []
    assert not Path(f.local_path).exists()


def test_add_verifies_expected_hash(tmp_path: Path):
    c = ctx(tmp_path)
    c.expected_hashes = {"https://example.com/a.jpg": "ABCDEF"}
    c.add(a_file(tmp_path, content_hash="abcdef"))
    assert len(c.files) == 1
    assert c.files[0].hash_verified is True


def test_add_deletes_a_file_whose_hash_does_not_match(tmp_path: Path):
    c = ctx(tmp_path)
    c.expected_hashes = {"https://example.com/a.jpg": "expected"}
    f = a_file(tmp_path, content_hash="actual")
    c.add(f)
    assert c.files == []
    assert not Path(f.local_path).exists()


def test_add_dedupes_by_content_hash(tmp_path: Path):
    c = ctx(tmp_path)
    c.add(a_file(tmp_path, name="a.jpg", content_hash="same"))
    second = a_file(tmp_path, name="b.jpg", content_hash="same")
    c.add(second)

    assert [f.filename for f in c.files] == ["a.jpg"]
    assert second.duplicate_of == "a.jpg"
    assert second.local_path is None
    assert not (tmp_path / "b.jpg").exists()


def test_add_keeps_distinct_hashes(tmp_path: Path):
    c = ctx(tmp_path)
    c.add(a_file(tmp_path, name="a.jpg", content_hash="one"))
    c.add(a_file(tmp_path, name="b.jpg", content_hash="two"))
    assert len(c.files) == 2


def test_dedupe_can_be_disabled(tmp_path: Path):
    c = ctx(tmp_path, dedupe_by_hash=False)
    c.add(a_file(tmp_path, name="a.jpg", content_hash="same"))
    c.add(a_file(tmp_path, name="b.jpg", content_hash="same"))
    assert len(c.files) == 2


def test_add_enforces_the_job_size_cap(tmp_path: Path):
    c = ctx(tmp_path, max_job_size_bytes=40)
    c.add(a_file(tmp_path, name="a.jpg"))          # 32 bytes — fits
    over = a_file(tmp_path, name="b.jpg")          # would total 64
    c.add(over)

    assert [f.filename for f in c.files] == ["a.jpg"]
    assert not Path(over.local_path).exists()
    assert "Limite de tamanho" in c.job.message


def test_metadata_only_files_do_not_count_against_the_size_cap(tmp_path: Path):
    c = ctx(tmp_path, max_job_size_bytes=40)
    c.add(ExtractedFile(filename="a.jpg", url="https://example.com/a.jpg",
                        content_type="image/jpeg", size_bytes=1000, local_path=None))
    assert c.job_bytes_total == 0
    assert len(c.files) == 1


# ── Derived request state ───────────────────────────────────────────────────

@pytest.mark.parametrize("types,want_media", [
    (["all"], True), (["videos"], True), (["audio"], True),
    (["images"], False), (["page_pdf"], False), (["documents"], False),
])
def test_want_media(tmp_path: Path, types, want_media):
    c = ctx(tmp_path, content_types=types)
    c.want = set(types)
    assert c.want_media is want_media


def test_want_all(tmp_path: Path):
    c = ctx(tmp_path)
    c.want = {"all"}
    assert c.want_all is True
    c.want = {"images"}
    assert c.want_all is False


# ── Stage isolation ─────────────────────────────────────────────────────────

async def test_a_failing_stage_does_not_abort_the_pipeline(tmp_path: Path):
    c = ctx(tmp_path)
    ran: list[str] = []

    async def boom(_c):
        raise RuntimeError("yt-dlp exploded")

    async def ok(_c):
        ran.append("ok")

    await _run_stage(_Stage("boom", boom), c)
    await _run_stage(_Stage("ok", ok), c)

    assert ran == ["ok"]
    assert "yt-dlp exploded" in c.job.message


async def test_cancellation_skips_remaining_stages(tmp_path: Path):
    c = ctx(tmp_path)
    c.job.status = JobStatus.cancelled
    ran: list[str] = []

    async def stage(_c):
        ran.append("ran")

    await _run_stage(_Stage("s", stage), c)
    assert ran == []


async def test_media_only_stages_are_skipped_for_non_media_jobs(tmp_path: Path):
    c = ctx(tmp_path, content_types=["images"])
    c.want = {"images"}
    ran: list[str] = []

    async def stage(_c):
        ran.append("ran")

    await _run_stage(_Stage("s", stage, requires_media=True), c)
    assert ran == []

    await _run_stage(_Stage("s", stage), c)
    assert ran == ["ran"]


async def test_cancelled_error_propagates_and_is_not_swallowed(tmp_path: Path):
    """Stage errors are contained, but task cancellation must reach the caller
    or a shutdown drain would hang."""
    c = ctx(tmp_path)

    async def stage(_c):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await _run_stage(_Stage("s", stage), c)


# ── Pause / resume ──────────────────────────────────────────────────────────

async def test_wait_if_paused_returns_immediately_when_running(tmp_path: Path):
    c = ctx(tmp_path)
    await asyncio.wait_for(c.wait_if_paused(), timeout=0.5)


async def test_wait_if_paused_blocks_then_releases_on_resume(tmp_path: Path):
    c = ctx(tmp_path)
    c.job.status = JobStatus.paused

    async def resume_soon():
        await asyncio.sleep(0.05)
        c.job.status = JobStatus.running
        c.resume_event.set()

    await asyncio.gather(
        asyncio.wait_for(c.wait_if_paused(), timeout=2.0),
        resume_soon(),
    )
    assert c.job.status == JobStatus.running


async def test_wait_if_paused_releases_on_cancel(tmp_path: Path):
    c = ctx(tmp_path)
    c.job.status = JobStatus.paused

    async def cancel_soon():
        await asyncio.sleep(0.05)
        c.job.status = JobStatus.cancelled
        c.resume_event.set()

    await asyncio.gather(
        asyncio.wait_for(c.wait_if_paused(), timeout=2.0),
        cancel_soon(),
    )


def test_signal_resume_is_safe_for_an_unknown_job():
    signal_resume("no-such-job")  # must not raise


# ── Progress throttling ─────────────────────────────────────────────────────

def test_file_progress_is_throttled(tmp_path: Path):
    emitted: list[int] = []
    c = ctx(tmp_path)
    c.on_progress = lambda job: emitted.append(job.current_file.bytes_done)

    c.emit_file_progress("a.bin", 1, 100)
    c.emit_file_progress("a.bin", 2, 100)
    c.emit_file_progress("a.bin", 3, 100)
    assert emitted == [1]  # the rest fall inside the 250ms window


def test_file_progress_always_emits_completion(tmp_path: Path):
    emitted: list[int] = []
    c = ctx(tmp_path)
    c.on_progress = lambda job: emitted.append(job.current_file.bytes_done)

    c.emit_file_progress("a.bin", 1, 100)
    c.emit_file_progress("a.bin", 100, 100)  # done == total bypasses the throttle
    assert emitted == [1, 100]


# ── Zip ─────────────────────────────────────────────────────────────────────

def test_zip_prefers_the_converted_file(tmp_path: Path):
    src = tmp_path / "a.png"
    src.write_bytes(b"png")
    conv = tmp_path / "a.webp"
    conv.write_bytes(b"webp")

    f = ExtractedFile(filename="a.png", url="u", content_type="image/png",
                      local_path=str(src), converted_path=str(conv))
    zip_path = _zip_job_output_sync(tmp_path, [f])
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == ["a.webp"]


def test_zip_deduplicates_colliding_basenames(tmp_path: Path):
    """Two files from different directories can share a basename; writing both
    under the same arcname produced an archive most tools half-extract."""
    (tmp_path / "sub").mkdir()
    one, two = tmp_path / "a.txt", tmp_path / "sub" / "a.txt"
    one.write_text("first")
    two.write_text("second")

    files = [
        ExtractedFile(filename="a.txt", url="u1", content_type="text/plain", local_path=str(one)),
        ExtractedFile(filename="a_2.txt", url="u2", content_type="text/plain", local_path=str(two)),
    ]
    zip_path = _zip_job_output_sync(tmp_path, files)
    with zipfile.ZipFile(zip_path) as zf:
        assert sorted(zf.namelist()) == ["a.txt", "a_1.txt"]


def test_zip_skips_missing_and_metadata_only_files(tmp_path: Path):
    present = tmp_path / "a.txt"
    present.write_text("x")
    files = [
        ExtractedFile(filename="a.txt", url="u", content_type="text/plain", local_path=str(present)),
        ExtractedFile(filename="gone.txt", url="u", content_type="text/plain",
                      local_path=str(tmp_path / "gone.txt")),
        ExtractedFile(filename="meta.txt", url="u", content_type="text/plain", local_path=None),
    ]
    zip_path = _zip_job_output_sync(tmp_path, files)
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == ["a.txt"]


def test_zip_never_contains_itself(tmp_path: Path):
    zip_path = tmp_path / "download.zip"
    zip_path.write_bytes(b"stale")
    f = ExtractedFile(filename="download.zip", url="u",
                      content_type="application/zip", local_path=str(zip_path))
    result = _zip_job_output_sync(tmp_path, [f])
    with zipfile.ZipFile(result) as zf:
        assert zf.namelist() == []


# ── Diff ────────────────────────────────────────────────────────────────────

def test_diff_reports_added_removed_changed_and_unchanged():
    previous = JobState(job_id="prev", url="https://example.com", status=JobStatus.done)
    previous.files = [
        ExtractedFile(filename="same.jpg", url="u1", content_type="image/jpeg", content_hash="h1"),
        ExtractedFile(filename="changed.jpg", url="u2", content_type="image/jpeg", content_hash="old"),
        ExtractedFile(filename="gone.jpg", url="u3", content_type="image/jpeg", content_hash="h3"),
    ]
    current = [
        ExtractedFile(filename="same.jpg", url="u1", content_type="image/jpeg", content_hash="h1"),
        ExtractedFile(filename="changed.jpg", url="u2", content_type="image/jpeg", content_hash="new"),
        ExtractedFile(filename="fresh.jpg", url="u4", content_type="image/jpeg", content_hash="h4"),
    ]

    diff = compute_diff(previous, current)
    assert diff.compared_to_job_id == "prev"
    assert diff.added == ["fresh.jpg"]
    assert diff.removed == ["gone.jpg"]
    assert diff.changed == ["changed.jpg"]
    assert diff.unchanged_count == 1


def test_diff_ignores_files_without_a_hash():
    previous = JobState(job_id="prev", url="u", status=JobStatus.done)
    previous.files = [ExtractedFile(filename="a.jpg", url="u", content_type="image/jpeg")]
    current = [ExtractedFile(filename="a.jpg", url="u", content_type="image/jpeg")]

    diff = compute_diff(previous, current)
    assert diff.changed == []
    assert diff.unchanged_count == 1


def test_diff_against_an_empty_previous_run():
    previous = JobState(job_id="prev", url="u", status=JobStatus.done)
    current = [ExtractedFile(filename="a.jpg", url="u", content_type="image/jpeg")]
    diff = compute_diff(previous, current)
    assert diff.added == ["a.jpg"]
    assert diff.removed == []
    assert diff.unchanged_count == 0
