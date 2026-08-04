from __future__ import annotations

import time
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class ContentType(str, Enum):
    all = "all"
    page_pdf = "page_pdf"
    images = "images"
    videos = "videos"
    audio = "audio"
    documents = "documents"


class AuthMethod(str, Enum):
    none = "none"
    credentials = "credentials"
    cookies = "cookies"
    cookies_browser = "cookies_browser"


class CookiesBrowser(str, Enum):
    chrome = "chrome"
    firefox = "firefox"
    edge = "edge"
    brave = "brave"
    opera = "opera"
    safari = "safari"


class AuthConfig(BaseModel):
    method: AuthMethod = AuthMethod.none
    username: Optional[str] = None
    password: Optional[str] = None
    cookies_raw: Optional[str] = None
    cookies_browser: Optional[CookiesBrowser] = None
    cookies_profile: Optional[str] = None
    manual_captcha: bool = False
    credential_profile: Optional[str] = None
    totp_secret: Optional[str] = None


SECRET_AUTH_FIELDS: set[str] = {"password", "totp_secret", "cookies_raw"}

PUBLIC_EXCLUDE: dict = {"request": {"auth": SECRET_AUTH_FIELDS}}


class ExtractionRequest(BaseModel):
    url: str
    content_types: list[ContentType] = [ContentType.all]
    target_extensions: list[str] = []
    auth: AuthConfig = AuthConfig()
    output_dir: Optional[str] = None
    max_files: int = 500
    quality: str = "best"
    network_wait: int = 12
    screen_record: bool = False
    screen_record_duration: int = 60
    convert_to: Optional[str] = None
    follow_links: bool = False
    max_depth: int = 1
    use_sitemap: bool = False
    max_pages: int = 20
    wait_selector: Optional[str] = None
    click_selector: Optional[str] = None
    click_max_times: int = 0
    min_file_size_bytes: int = 0
    url_pattern: Optional[str] = None
    metadata_only: bool = False
    download_concurrency: int = 6
    download_retries: int = 2
    dedupe_by_hash: bool = True
    convert_rules: dict[str, str] = {}
    zip_output: bool = False
    additional_urls: list[str] = []
    wait_until: str = "networkidle"
    wait_timeout_ms: int = 60000
    headless: Optional[bool] = None
    expected_hashes: dict[str, str] = {}
    download_priority: list[str] = []
    max_file_size_bytes: Optional[int] = None
    max_job_size_bytes: Optional[int] = None
    webhook_url: Optional[str] = None
    blocked_domains: list[str] = []
    scan_with_clamav: bool = False
    verify_mime: bool = True
    export_structured_data_csv: bool = False
    generate_thumbnails: bool = False

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        v = v.strip()
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("URL deve começar com http:// ou https://")
        return v


class ExtractedFile(BaseModel):
    filename: str
    url: str
    content_type: str
    size_bytes: Optional[int] = None
    local_path: Optional[str] = None
    thumbnail: Optional[str] = None
    converted_path: Optional[str] = None
    converted_ext: Optional[str] = None
    content_hash: Optional[str] = None
    duplicate_of: Optional[str] = None
    hash_verified: Optional[bool] = None
    mime_mismatch: bool = False
    clamav_clean: Optional[bool] = None


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    waiting_captcha = "waiting_captcha"
    paused = "paused"
    done = "done"
    error = "error"
    cancelled = "cancelled"


class FileProgress(BaseModel):
    """Byte-level progress of whichever file is downloading right now."""
    filename: str
    bytes_done: int = 0
    bytes_total: Optional[int] = None


class DiffResult(BaseModel):
    compared_to_job_id: str
    added: list[str] = []
    removed: list[str] = []
    changed: list[str] = []
    unchanged_count: int = 0


class JobState(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.queued
    url: str
    progress: int = 0
    total: int = 0
    message: str = ""
    files: list[ExtractedFile] = []
    error: Optional[str] = None
    output_dir: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    zip_path: Optional[str] = None
    current_file: Optional[FileProgress] = None
    diff: Optional[DiffResult] = None
    paywall_warning: Optional[str] = None


class ScheduleConfig(BaseModel):
    schedule_id: str = ""
    name: str
    request: ExtractionRequest
    interval_seconds: float
    enabled: bool = True
    next_run_at: float = Field(default_factory=time.time)
    last_job_id: Optional[str] = None
    created_at: float = Field(default_factory=time.time)


class JobTemplate(BaseModel):
    name: str
    request: ExtractionRequest
    created_at: float = Field(default_factory=time.time)


class CredentialProfile(BaseModel):
    name: str
    domain: str
    username: str
    password: str
    totp_secret: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
