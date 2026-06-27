from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel


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


class ExtractionRequest(BaseModel):
    url: str
    content_types: list[ContentType] = [ContentType.all]
    # Specific file extensions to target (overrides content_types for fine-grained control)
    # e.g. [".pdf", ".mp3", ".xlsx"] — empty = use content_types
    target_extensions: list[str] = []
    auth: AuthConfig = AuthConfig()
    output_dir: Optional[str] = None
    max_depth: int = 1
    max_files: int = 500
    follow_links: bool = False
    quality: str = "best"
    # Network interception: wait N seconds for async media requests to fire
    network_wait: int = 12
    # Screen recording fallback: record N seconds of what plays on screen
    screen_record: bool = False
    screen_record_duration: int = 60
    # Conversion: after download, convert each file to this extension
    # e.g. ".mp3" to convert all audio; ".pdf" to convert all docs; "" = no conversion
    convert_to: Optional[str] = None


class ExtractedFile(BaseModel):
    filename: str
    url: str
    content_type: str
    size_bytes: Optional[int] = None
    local_path: Optional[str] = None
    thumbnail: Optional[str] = None
    converted_path: Optional[str] = None
    converted_ext: Optional[str] = None


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    waiting_captcha = "waiting_captcha"   # paused for manual CAPTCHA
    done = "done"
    error = "error"
    cancelled = "cancelled"


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
