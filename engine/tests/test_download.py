import asyncio
from pathlib import Path

import httpx
import pytest

from download import download_with_retry, run_bounded, sort_by_priority


class _FakeStream:
    def __init__(self, status_code: int, body: bytes, headers: dict | None = None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.request = httpx.Request("GET", "http://test/x")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def aiter_bytes(self, chunk_size=65536):
        yield self._body


class _FakeClient:
    """Minimal stand-in for httpx.AsyncClient.stream() used by download_with_retry."""

    def __init__(self, responses):
        self._responses = list(responses)  # list of _FakeStream, consumed in order

    def stream(self, method, url, headers=None):
        return self._responses.pop(0)


async def test_download_with_retry_success(tmp_path: Path):
    client = _FakeClient([_FakeStream(200, b"hello world", {"content-type": "text/plain"})])
    dest = tmp_path / "out.txt"
    result = await download_with_retry(client, "http://test/x", dest, max_retries=0)
    assert result is not None
    assert result.bytes_written == len(b"hello world")
    assert dest.read_bytes() == b"hello world"
    assert len(result.sha256) == 64  # hex sha256


async def test_download_with_retry_below_min_size_fails(tmp_path: Path):
    client = _FakeClient([_FakeStream(200, b"hi")])
    dest = tmp_path / "out.txt"
    result = await download_with_retry(client, "http://test/x", dest, min_size_bytes=100, max_retries=0)
    assert result is None
    assert not dest.exists()


async def test_download_with_retry_http_error_retries_then_fails(tmp_path: Path):
    client = _FakeClient([_FakeStream(500, b""), _FakeStream(500, b"")])
    dest = tmp_path / "out.txt"
    result = await download_with_retry(client, "http://test/x", dest, max_retries=1, backoff_base=0.01)
    assert result is None
    assert not dest.exists()


async def test_download_with_retry_succeeds_after_one_failure(tmp_path: Path):
    client = _FakeClient([_FakeStream(500, b""), _FakeStream(200, b"ok")])
    dest = tmp_path / "out.txt"
    result = await download_with_retry(client, "http://test/x", dest, max_retries=1, backoff_base=0.01)
    assert result is not None
    assert dest.read_bytes() == b"ok"


async def test_run_bounded_respects_concurrency_limit():
    in_flight = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def task(i):
        nonlocal in_flight, max_in_flight
        async with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.02)
        async with lock:
            in_flight -= 1
        return i

    results = []
    async for r in run_bounded((task(i) for i in range(10)), concurrency=3):
        results.append(r)

    assert sorted(results) == list(range(10))
    assert max_in_flight <= 3


def test_sort_by_priority_orders_matching_first():
    items = [("a", "archive"), ("b", "image"), ("c", "video"), ("d", "image")]
    result = sort_by_priority(items, key=lambda it: it[1], priority=["video", "image"])
    assert [it[0] for it in result] == ["c", "b", "d", "a"]


def test_sort_by_priority_empty_priority_is_noop():
    items = [1, 2, 3]
    assert sort_by_priority(items, key=lambda x: str(x), priority=[]) == items
