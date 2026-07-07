import pytest
from pydantic import ValidationError

from models import ExtractionRequest, JobStatus


def test_valid_url_accepted():
    req = ExtractionRequest(url="https://example.com/page")
    assert req.url == "https://example.com/page"


def test_url_without_scheme_rejected():
    with pytest.raises(ValidationError):
        ExtractionRequest(url="example.com")


def test_file_url_rejected():
    with pytest.raises(ValidationError):
        ExtractionRequest(url="file:///etc/passwd")


def test_url_is_stripped():
    req = ExtractionRequest(url="  https://example.com  ")
    assert req.url == "https://example.com"


def test_defaults_are_safe():
    req = ExtractionRequest(url="https://example.com")
    assert req.max_files == 500
    assert req.dedupe_by_hash is True
    assert req.verify_mime is True
    assert req.blocked_domains == []
    assert req.headless is None


def test_job_status_has_paused():
    assert JobStatus.paused.value == "paused"


def test_job_status_values_are_strings():
    for status in JobStatus:
        assert isinstance(status.value, str)
