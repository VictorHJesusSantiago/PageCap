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
    # If True, open browser visibly so user can solve CAPTCHA/2FA manually
    manual_captcha: bool = False
    # Name of a saved CredentialProfile (see auth/profiles.py) to resolve
    # username/password/TOTP from instead of (or as default for) the fields above.
    credential_profile: Optional[str] = None
    # Base32 TOTP secret — when set, PageCap computes the current 6-digit code
    # itself and fills the detected OTP field automatically (no manual_captcha
    # pause needed for TOTP-only 2FA).
    totp_secret: Optional[str] = None


class ExtractionRequest(BaseModel):
    url: str
    content_types: list[ContentType] = [ContentType.all]
    # Specific file extensions to target (overrides content_types for fine-grained control)
    # e.g. [".pdf", ".mp3", ".xlsx"] — empty = use content_types
    target_extensions: list[str] = []
    auth: AuthConfig = AuthConfig()
    output_dir: Optional[str] = None
    max_files: int = 500
    quality: str = "best"
    # Network interception: wait N seconds for async media requests to fire
    network_wait: int = 12
    # Screen recording fallback: record N seconds of what plays on screen
    screen_record: bool = False
    screen_record_duration: int = 60
    # Conversion: after download, convert each file to this extension
    # e.g. ".mp3" to convert all audio; ".pdf" to convert all docs; "" = no conversion
    convert_to: Optional[str] = None
    # Recursive crawling: follow same-domain <a href> links up to max_depth
    # hops from the start URL (0 = only the start page, the default).
    follow_links: bool = False
    max_depth: int = 1
    # Read /sitemap.xml (and /robots.txt Sitemap: entries) to seed extra
    # same-domain pages to crawl, in addition to (or instead of) link-following.
    use_sitemap: bool = False
    # Hard cap on total pages visited during a crawl (start page + follow_links + sitemap).
    max_pages: int = 20
    # Wait for a CSS selector to appear before scanning (dynamic/SPA content).
    wait_selector: Optional[str] = None
    # Click a "load more"/"next page" button up to N times before scanning,
    # waiting network_wait/4 seconds (min 1s) between clicks.
    click_selector: Optional[str] = None
    click_max_times: int = 0
    # Fine-grained filters applied by the universal scanner before download.
    min_file_size_bytes: int = 0
    url_pattern: Optional[str] = None  # regex; candidate URL must match
    # List assets found without downloading them (files[].local_path stays null).
    metadata_only: bool = False
    # Download tuning: how many files download concurrently, and how many
    # times a failed download is retried (exponential backoff) before giving up.
    download_concurrency: int = 6
    download_retries: int = 2
    # Skip saving a file whose content (sha256) matches one already kept in
    # this job, even if the filename/URL differs.
    dedupe_by_hash: bool = True
    # Per-category conversion template, e.g. {"image": ".webp", "video": ".mp4"}.
    # Applied in addition to (and after) the single `convert_to` field, which
    # remains a simpler "convert everything" shortcut.
    convert_rules: dict[str, str] = {}
    # Zip every downloaded file into <output_dir>.zip once the job finishes.
    zip_output: bool = False
    # Extra seed URLs crawled in the same job as the primary `url`, sharing
    # output_dir/max_files/max_pages budgets — a "batch of pages in one job".
    additional_urls: list[str] = []
    # Playwright navigation wait strategy + timeout, previously hardcoded.
    wait_until: str = "networkidle"  # "load" | "domcontentloaded" | "networkidle" | "commit"
    wait_timeout_ms: int = 60000
    # Independent headless override. None = old behavior (headless unless
    # manual_captcha); True/False force the browser visibility explicitly.
    headless: Optional[bool] = None
    # sha256 hashes the caller already knows are correct for specific URLs
    # (url -> expected hex digest); a mismatch drops the file and records why.
    expected_hashes: dict[str, str] = {}
    # Download priority: categories listed here are downloaded before any
    # others (still bounded by download_concurrency), e.g. ["image","document"].
    download_priority: list[str] = []
    # Hard byte caps. max_file_size_bytes rejects any single file over the
    # limit (checked via Content-Length HEAD before download); max_job_size_bytes
    # stops starting new downloads once the job's total bytes-on-disk would exceed it.
    max_file_size_bytes: Optional[int] = None
    max_job_size_bytes: Optional[int] = None
    # POST the final JobState JSON to this URL when the job finishes (best-effort).
    webhook_url: Optional[str] = None
    # Domains (exact host match) that must never be requested — checked before
    # every navigation and every candidate download URL.
    blocked_domains: list[str] = []
    # Verify downloaded bytes against the OS's installed ClamAV (clamscan/clamdscan)
    # before keeping them; infected files are deleted. No-op if ClamAV isn't installed.
    scan_with_clamav: bool = False
    # Cross-check declared Content-Type/extension against the file's actual
    # magic-byte signature; mismatches are flagged (file.mime_mismatch=True)
    # rather than silently trusted.
    verify_mime: bool = True
    # Also write structured_data.csv (flattened JSON-LD/OG/Twitter/meta) next
    # to the structured_data.json that's always produced when any is found.
    export_structured_data_csv: bool = False
    # Generate a small local thumbnail (data: URI) for downloaded images/videos.
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
    content_hash: Optional[str] = None  # sha256, used for content-based dedup
    duplicate_of: Optional[str] = None  # filename of the file this duplicated, if dropped
    hash_verified: Optional[bool] = None  # True/False if expected_hashes had an entry for this URL
    mime_mismatch: bool = False  # True if magic-byte sniff disagreed with declared content-type
    clamav_clean: Optional[bool] = None  # True/False if scan_with_clamav was on and ClamAV ran


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    waiting_captcha = "waiting_captcha"   # paused for manual CAPTCHA
    paused = "paused"                     # user-requested pause (resumable)
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
    added: list[str] = []      # filenames present now but not in the previous run
    removed: list[str] = []    # filenames present in the previous run but not now
    changed: list[str] = []    # same URL, different content_hash
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
    interval_seconds: float  # simple recurring interval (not full cron syntax)
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
