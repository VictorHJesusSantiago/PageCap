from pathlib import Path

import pytest

from models import CredentialProfile, ExtractionRequest, JobTemplate, ScheduleConfig
from stores import make_stores


@pytest.fixture
def db_stores(tmp_path: Path):
    return make_stores(tmp_path / "stores.db")


async def test_credential_profile_roundtrip(db_stores):
    credentials, _templates, _schedules = db_stores
    profile = CredentialProfile(name="mysite", domain="example.com", username="alice", password="s3cr3t")
    await credentials.save(profile.name, profile)

    fetched = await credentials.get("mysite")
    assert fetched is not None
    assert fetched.username == "alice"
    assert fetched.password == "s3cr3t"


async def test_credential_profile_list_and_delete(db_stores):
    credentials, _templates, _schedules = db_stores
    await credentials.save("a", CredentialProfile(name="a", domain="a.com", username="u", password="p"))
    await credentials.save("b", CredentialProfile(name="b", domain="b.com", username="u", password="p"))

    profiles = await credentials.list()
    assert {p.name for p in profiles} == {"a", "b"}

    await credentials.delete("a")
    profiles = await credentials.list()
    assert {p.name for p in profiles} == {"b"}


async def test_job_template_roundtrip(db_stores):
    _credentials, templates, _schedules = db_stores
    req = ExtractionRequest(url="https://example.com", max_files=50)
    tpl = JobTemplate(name="quick-images", request=req)
    await templates.save(tpl.name, tpl)

    fetched = await templates.get("quick-images")
    assert fetched is not None
    assert fetched.request.url == "https://example.com"
    assert fetched.request.max_files == 50


async def test_schedule_roundtrip(db_stores):
    _credentials, _templates, schedules = db_stores
    req = ExtractionRequest(url="https://example.com")
    sched = ScheduleConfig(name="daily", request=req, interval_seconds=3600)
    await schedules.save(sched.name, sched)

    fetched = await schedules.get("daily")
    assert fetched is not None
    assert fetched.interval_seconds == 3600
    assert fetched.enabled is True


async def test_get_missing_returns_none(db_stores):
    credentials, _templates, _schedules = db_stores
    assert await credentials.get("does-not-exist") is None
