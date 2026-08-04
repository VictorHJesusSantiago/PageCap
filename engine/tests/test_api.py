"""API-boundary tests.

Configuration is read at import time (12-factor III: config is immutable at
runtime), so each variant imports the module tree fresh under a temp-directory
cwd. `config` itself must be evicted too — leaving it cached is why an earlier
version of this file saw a stale `settings` and a valid token being rejected.
"""
import importlib
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from models import AuthConfig, AuthMethod, ExtractedFile, ExtractionRequest, JobState, JobStatus

TEST_TOKEN = "test-token-abcdefghijklmnop"

_RELOADABLE = ("api", "config", "auth.tokens", "auth.profiles", "plugins", "logging_config")

_ENV_KEYS = (
    "PAGECAP_API_TOKEN",
    "PAGECAP_REQUIRE_AUTH",
    "PAGECAP_ALLOW_NULL_ORIGIN",
    "PAGECAP_CORS_ORIGINS",
    "PAGECAP_RATE_LIMIT_PER_MINUTE",
    "PAGECAP_SECRET_KEY",
)


def _evict():
    for name in _RELOADABLE:
        sys.modules.pop(name, None)


def _fresh_api(tmp_path: Path, monkeypatch, **env):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PAGECAP_DB_PATH", str(tmp_path / "pagecap.db"))
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _evict()
    return importlib.import_module("api")


@pytest.fixture
def api(tmp_path: Path, monkeypatch):
    module = _fresh_api(tmp_path, monkeypatch, PAGECAP_API_TOKEN=TEST_TOKEN)
    yield module
    _evict()


@contextmanager
def authed(module):
    """A TestClient that carries the bearer token on every request."""
    with TestClient(module.app) as client:
        client.headers.update({"Authorization": f"Bearer {TEST_TOKEN}"})
        yield client


def test_auth_enabled_by_default_with_generated_token(tmp_path: Path, monkeypatch):
    """No PAGECAP_API_TOKEN supplied must not mean "no auth": a token is
    generated, persisted, and enforced."""
    module = _fresh_api(tmp_path, monkeypatch)
    try:
        token_file = tmp_path / ".pagecap_token"
        assert token_file.exists()
        generated = token_file.read_text().strip()
        assert len(generated) >= 32

        with TestClient(module.app) as client:
            assert client.get("/v1/jobs").status_code == 401
            assert client.get(
                "/v1/jobs", headers={"Authorization": f"Bearer {generated}"}
            ).status_code == 200
    finally:
        _evict()


def test_generated_token_is_reused_across_restarts(tmp_path: Path, monkeypatch):
    module = _fresh_api(tmp_path, monkeypatch)
    first = (tmp_path / ".pagecap_token").read_text().strip()
    _evict()
    _fresh_api(tmp_path, monkeypatch)
    try:
        assert (tmp_path / ".pagecap_token").read_text().strip() == first
    finally:
        _evict()


def test_require_auth_can_be_disabled_as_escape_hatch(tmp_path: Path, monkeypatch):
    module = _fresh_api(tmp_path, monkeypatch, PAGECAP_REQUIRE_AUTH="0")
    try:
        with TestClient(module.app) as client:
            assert client.get("/v1/jobs").status_code == 200
        assert not (tmp_path / ".pagecap_token").exists()
    finally:
        _evict()


def test_token_enforced_and_health_exempt(api):
    with TestClient(api.app) as client:
        assert client.get("/v1/jobs").status_code == 401
        assert client.get("/v1/health").status_code == 200
        assert client.get("/v1/health/live").status_code == 200
        assert client.get("/v1/health/ready").status_code == 200
        assert client.get(
            "/v1/jobs", headers={"Authorization": f"Bearer {TEST_TOKEN}"}
        ).status_code == 200
        assert client.get(f"/v1/jobs?token={TEST_TOKEN}").status_code == 200
        assert client.get("/v1/jobs?token=wrong").status_code == 401


def test_401_advertises_bearer_scheme(api):
    with TestClient(api.app) as client:
        res = client.get("/v1/jobs")
        assert res.headers["www-authenticate"] == "Bearer"


def test_v1_and_legacy_paths_both_work(api):
    with authed(api) as client:
        assert client.get("/v1/health").status_code == 200
        assert client.get("/health").status_code == 200


def test_legacy_paths_carry_deprecation_headers(api):
    with authed(api) as client:
        legacy = client.get("/jobs")
        assert legacy.headers["deprecation"] == "true"
        assert "sunset" in legacy.headers
        assert 'rel="successor-version"' in legacy.headers["link"]

        versioned = client.get("/v1/jobs")
        assert "deprecation" not in versioned.headers


def test_openapi_documents_only_the_versioned_surface(api):
    with authed(api) as client:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/v1/jobs" in paths
        assert "/jobs" not in paths


def test_404_is_problem_json(api):
    with authed(api) as client:
        res = client.get("/v1/jobs/does-not-exist")
        assert res.status_code == 404
        assert res.headers["content-type"] == "application/problem+json"
        body = res.json()
        assert body["status"] == 404
        assert body["title"] == "Not Found"
        assert body["type"].endswith("/not-found")
        assert body["instance"] == "/v1/jobs/does-not-exist"
        assert body["traceId"] == res.headers["x-request-id"]


def test_validation_error_lists_offending_fields(api):
    with authed(api) as client:
        res = client.post("/v1/extract", json={"url": "not-a-url"})
        assert res.status_code == 422
        assert res.headers["content-type"] == "application/problem+json"
        body = res.json()
        assert body["type"].endswith("/validation-error")
        assert any("url" in e["field"] for e in body["errors"])


def test_401_is_problem_json_with_trace_id(api):
    with TestClient(api.app) as client:
        res = client.get("/v1/jobs")
        assert res.headers["content-type"] == "application/problem+json"
        assert res.json()["traceId"] == res.headers["x-request-id"]


def test_request_id_is_propagated_when_supplied(api):
    with authed(api) as client:
        res = client.get("/v1/health", headers={"X-Request-ID": "caller-supplied-id"})
        assert res.headers["x-request-id"] == "caller-supplied-id"


def test_conflict_on_pausing_a_non_running_job(api):
    job = JobState(job_id="j", url="https://example.com", status=JobStatus.done)
    api._jobs["j"] = job
    with authed(api) as client:
        res = client.post("/v1/jobs/j/pause")
        assert res.status_code == 409
        assert res.json()["type"].endswith("/conflict")


def _request_with_secrets() -> ExtractionRequest:
    return ExtractionRequest(
        url="https://example.com",
        auth=AuthConfig(
            method=AuthMethod.credentials,
            username="alice",
            password="TOP-SECRET-PW",
            totp_secret="JBSWY3DPEHPK3PXP",
            cookies_raw="session=abc123",
        ),
    )


def test_template_list_and_get_never_return_secrets(api):
    with authed(api) as client:
        payload = {"name": "t", "request": _request_with_secrets().model_dump(mode="json")}
        assert client.post("/v1/templates", json=payload).status_code == 200

        for body in (client.get("/v1/templates").text, client.get("/v1/templates/t").text):
            assert "TOP-SECRET-PW" not in body
            assert "JBSWY3DPEHPK3PXP" not in body
            assert "session=abc123" not in body
            assert "alice" in body


def test_schedule_list_never_returns_secrets(api):
    with authed(api) as client:
        payload = {
            "name": "s",
            "request": _request_with_secrets().model_dump(mode="json"),
            "interval_seconds": 3600,
        }
        assert client.post("/v1/schedules", json=payload).status_code == 200

        body = client.get("/v1/schedules").text
        assert "TOP-SECRET-PW" not in body
        assert "JBSWY3DPEHPK3PXP" not in body


def test_credential_list_never_returns_secrets(api):
    with authed(api) as client:
        client.post("/v1/credentials", json={
            "name": "c", "domain": "example.com",
            "username": "alice", "password": "TOP-SECRET-PW",
            "totp_secret": "JBSWY3DPEHPK3PXP",
        })
        body = client.get("/v1/credentials").text
        assert "TOP-SECRET-PW" not in body
        assert "JBSWY3DPEHPK3PXP" not in body


def test_health_does_not_leak_absolute_db_path(api):
    with authed(api) as client:
        body = client.get("/v1/health").json()
        assert "db_path" not in body
        assert body["db_name"] == "pagecap.db"
        assert body["auth_required"] is True


def _extracted(filename: str, content_type: str, path: Path) -> ExtractedFile:
    return ExtractedFile(filename=filename, url="https://example.com/x",
                         content_type=content_type, local_path=str(path))


def _job_with_file(api, filename: str, content_type: str, body: bytes, job_id: str = "job-1"):
    job_dir = Path("downloads") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    target = job_dir / filename
    target.write_bytes(body)

    job = JobState(job_id=job_id, url="https://example.com", status=JobStatus.done,
                   output_dir=str(job_dir))
    job.files.append(_extracted(filename, content_type, target))
    api._jobs[job_id] = job
    return job


def test_preview_forces_html_to_attachment(api):
    """An HTML file scraped from a hostile site must not be rendered inline on
    the API's own origin — that would be same-origin script execution against
    every other endpoint."""
    _job_with_file(api, "evil.html", "text/html", b"<script>alert(1)</script>")
    with authed(api) as client:
        res = client.get("/v1/jobs/job-1/preview/evil.html")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("application/octet-stream")
        assert "attachment" in res.headers.get("content-disposition", "")
        assert res.headers["x-content-type-options"] == "nosniff"


def test_preview_forces_svg_to_attachment(api):
    _job_with_file(api, "evil.svg", "image/svg+xml", b"<svg onload='alert(1)'/>")
    with authed(api) as client:
        res = client.get("/v1/jobs/job-1/preview/evil.svg")
        assert res.headers["content-type"].startswith("application/octet-stream")


def test_preview_allows_real_image_inline(api):
    _job_with_file(api, "ok.png", "image/png", b"\x89PNG\r\n\x1a\n")
    with authed(api) as client:
        res = client.get("/v1/jobs/job-1/preview/ok.png")
        assert res.headers["content-type"].startswith("image/png")
        assert "attachment" not in res.headers.get("content-disposition", "")


def test_download_rejects_path_outside_job_dir(api, tmp_path: Path):
    outside = tmp_path / "secret.txt"
    outside.write_text("classified")

    job_dir = Path("downloads") / "job-2"
    job_dir.mkdir(parents=True, exist_ok=True)
    job = JobState(job_id="job-2", url="https://example.com", status=JobStatus.done,
                   output_dir=str(job_dir))
    job.files.append(_extracted("secret.txt", "text/plain", outside))
    api._jobs["job-2"] = job

    with authed(api) as client:
        assert client.get("/v1/jobs/job-2/download/secret.txt").status_code == 404


def test_unknown_job_is_404(api):
    with authed(api) as client:
        assert client.get("/v1/jobs/nope/download/x.png").status_code == 404


def test_security_headers_present_on_every_response(api):
    with authed(api) as client:
        res = client.get("/v1/health")
        assert res.headers["x-content-type-options"] == "nosniff"
        assert res.headers["x-frame-options"] == "DENY"
        assert res.headers["referrer-policy"] == "no-referrer"
        assert "default-src 'none'" in res.headers["content-security-policy"]


def test_jobs_are_keyset_paginated(api):
    for i in range(5):
        api._jobs[f"j{i}"] = JobState(
            job_id=f"j{i}", url="https://example.com", status=JobStatus.done,
            created_at=1000.0 + i,
        )
    with authed(api) as client:
        first = client.get("/v1/jobs?limit=2").json()
        assert len(first["jobs"]) == 2
        assert first["total"] == 5
        assert first["next_cursor"] is not None
        assert first["jobs"][0]["job_id"] == "j4"

        second = client.get(f"/v1/jobs?limit=2&cursor={first['next_cursor']}").json()
        assert [j["job_id"] for j in second["jobs"]] == ["j2", "j1"]

        last = client.get(f"/v1/jobs?limit=2&cursor={second['next_cursor']}").json()
        assert [j["job_id"] for j in last["jobs"]] == ["j0"]
        assert last["next_cursor"] is None


def test_jobs_rejects_out_of_range_limit(api):
    with authed(api) as client:
        assert client.get("/v1/jobs?limit=0").status_code == 422
        assert client.get("/v1/jobs?limit=99999").status_code == 422


def test_jobs_rejects_non_numeric_cursor(api):
    with authed(api) as client:
        assert client.get("/v1/jobs?cursor=abc").status_code == 422


def test_extract_returns_202_with_location(api, monkeypatch):
    async def _noop(request, job, on_progress=None, find_previous_job=None):
        job.status = JobStatus.done
        return []

    monkeypatch.setattr(api, "crawl_assets", _noop)
    with authed(api) as client:
        res = client.post("/v1/extract", json={"url": "https://example.com"})
        assert res.status_code == 202
        job_id = res.json()["job_id"]
        assert res.headers["location"] == f"/v1/jobs/{job_id}"


def test_download_all_conflicts_while_running(api):
    job = JobState(job_id="run", url="https://example.com", status=JobStatus.running)
    job.files.append(_extracted("a.png", "image/png", Path("downloads/run/a.png")))
    api._jobs["run"] = job
    with authed(api) as client:
        assert client.get("/v1/jobs/run/download-all").status_code == 409


def test_metrics_exposes_red_counters_and_percentiles(api):
    with authed(api) as client:
        client.get("/v1/health")
        body = client.get("/v1/metrics").json()
        assert body["counters"]["http_requests_total"] >= 1
        for key in ("p50", "p95", "p99", "p999"):
            assert key in body["http_request_duration_seconds"]
        assert "jobs_active" in body["gauges"]


def test_readiness_fails_while_shutting_down(api):
    with authed(api) as client:
        api._shutting_down = True
        try:
            assert client.get("/v1/health/ready").status_code == 503
        finally:
            api._shutting_down = False


def test_jobs_left_running_after_a_crash_are_marked_errored(tmp_path: Path, monkeypatch):
    """A "running" row means the process that was driving it died. Leaving the
    status as running makes the UI wait forever."""
    from job_store import JobStore

    db = tmp_path / "pagecap.db"
    store = JobStore(db)
    import asyncio as _asyncio
    _asyncio.run(store.save(JobState(job_id="zombie", url="https://x.com", status=JobStatus.running)))

    module = _fresh_api(tmp_path, monkeypatch, PAGECAP_API_TOKEN=TEST_TOKEN)
    try:
        with authed(module) as client:
            body = client.get("/v1/jobs/zombie").json()
            assert body["status"] == "error"
            assert "reinici" in body["error"].lower()
    finally:
        _evict()


def test_null_origin_rejected_by_default(api):
    with authed(api) as client:
        res = client.get("/v1/jobs", headers={"Origin": "null"})
        assert "access-control-allow-origin" not in res.headers


def test_null_origin_allowed_when_opted_in(tmp_path: Path, monkeypatch):
    module = _fresh_api(
        tmp_path, monkeypatch,
        PAGECAP_ALLOW_NULL_ORIGIN="1", PAGECAP_API_TOKEN=TEST_TOKEN,
    )
    try:
        with authed(module) as client:
            res = client.get("/v1/jobs", headers={"Origin": "null"})
            assert res.headers.get("access-control-allow-origin") == "null"
    finally:
        _evict()


def test_localhost_origin_always_allowed(api):
    with authed(api) as client:
        res = client.get("/v1/jobs", headers={"Origin": "http://localhost:5173"})
        assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_foreign_origin_gets_no_cors_grant(api):
    with authed(api) as client:
        res = client.get("/v1/jobs", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in res.headers


def test_rate_limit_returns_429_with_retry_after(tmp_path: Path, monkeypatch):
    module = _fresh_api(
        tmp_path, monkeypatch,
        PAGECAP_RATE_LIMIT_PER_MINUTE="2", PAGECAP_API_TOKEN=TEST_TOKEN,
    )
    try:
        with authed(module) as client:
            assert client.get("/v1/jobs").status_code == 200
            assert client.get("/v1/jobs").status_code == 200
            res = client.get("/v1/jobs")
            assert res.status_code == 429
            assert res.headers["retry-after"] == "60"
            assert res.headers["x-ratelimit-limit"] == "2"
            assert res.json()["type"].endswith("/rate-limit-exceeded")
    finally:
        _evict()


def test_websocket_requires_token_when_configured(api):
    from starlette.websockets import WebSocketDisconnect

    with TestClient(api.app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/v1/ws/job-x") as ws:
                ws.receive_text()


def test_websocket_accepts_valid_token(api):
    api._jobs["job-x"] = JobState(job_id="job-x", url="https://example.com")
    with TestClient(api.app) as client:
        with client.websocket_connect(f"/v1/ws/job-x?token={TEST_TOKEN}") as ws:
            assert ws.receive_json()["job_id"] == "job-x"


def test_websocket_rejects_foreign_origin_when_unauthenticated(tmp_path: Path, monkeypatch):
    """WebSockets bypass both the HTTP middleware and CORS, so the origin
    check has to be repeated on the socket handler itself."""
    from starlette.websockets import WebSocketDisconnect

    module = _fresh_api(tmp_path, monkeypatch, PAGECAP_REQUIRE_AUTH="0")
    try:
        with TestClient(module.app) as client:
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/v1/ws/job-x", headers={"Origin": "https://evil.example"}
                ) as ws:
                    ws.receive_text()
    finally:
        _evict()


def test_websocket_allows_localhost_origin_when_unauthenticated(tmp_path: Path, monkeypatch):
    module = _fresh_api(tmp_path, monkeypatch, PAGECAP_REQUIRE_AUTH="0")
    try:
        module._jobs["job-y"] = JobState(job_id="job-y", url="https://example.com")
        with TestClient(module.app) as client:
            with client.websocket_connect(
                "/v1/ws/job-y", headers={"Origin": "http://localhost:5173"}
            ) as ws:
                assert ws.receive_json()["job_id"] == "job-y"
    finally:
        _evict()


def test_legacy_websocket_path_still_works(api):
    api._jobs["job-z"] = JobState(job_id="job-z", url="https://example.com")
    with TestClient(api.app) as client:
        with client.websocket_connect(f"/ws/job-z?token={TEST_TOKEN}") as ws:
            assert ws.receive_json()["job_id"] == "job-z"
