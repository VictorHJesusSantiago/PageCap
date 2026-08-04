import sqlite3
from pathlib import Path

import pytest

from models import AuthConfig, AuthMethod, CredentialProfile, ExtractionRequest, JobTemplate, ScheduleConfig
from stores import make_stores


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "stores.db"


@pytest.fixture
def db_stores(db_path: Path):
    return make_stores(db_path)


def _raw_rows(db_path: Path, table: str) -> str:
    """The bytes actually on disk, bypassing the store's decryption."""
    conn = sqlite3.connect(db_path)
    try:
        return "".join(r[0] for r in conn.execute(f"SELECT data_json FROM {table}"))
    finally:
        conn.close()


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


async def test_credential_secrets_are_encrypted_on_disk(db_stores, db_path):
    credentials, _templates, _schedules = db_stores
    await credentials.save(
        "mysite",
        CredentialProfile(
            name="mysite", domain="example.com", username="alice",
            password="pl41nt3xt", totp_secret="JBSWY3DPEHPK3PXP",
        ),
    )

    raw = _raw_rows(db_path, "credential_profiles")
    assert "pl41nt3xt" not in raw
    assert "JBSWY3DPEHPK3PXP" not in raw
    assert "alice" in raw
    assert raw.count("enc:v1:") == 2


async def test_template_auth_secrets_are_encrypted_on_disk(db_stores, db_path):
    _credentials, templates, _schedules = db_stores
    req = ExtractionRequest(
        url="https://example.com",
        auth=AuthConfig(
            method=AuthMethod.credentials, username="bob",
            password="tpl-secret", cookies_raw="session=abc123",
        ),
    )
    await templates.save("t", JobTemplate(name="t", request=req))

    raw = _raw_rows(db_path, "job_templates")
    assert "tpl-secret" not in raw
    assert "session=abc123" not in raw

    fetched = await templates.get("t")
    assert fetched is not None
    assert fetched.request.auth.password == "tpl-secret"
    assert fetched.request.auth.cookies_raw == "session=abc123"


async def test_schedule_auth_secrets_are_encrypted_on_disk(db_stores, db_path):
    _credentials, _templates, schedules = db_stores
    req = ExtractionRequest(
        url="https://example.com",
        auth=AuthConfig(method=AuthMethod.credentials, username="bob", password="sched-secret"),
    )
    await schedules.save("s", ScheduleConfig(name="s", request=req, interval_seconds=60))

    assert "sched-secret" not in _raw_rows(db_path, "schedules")
    fetched = await schedules.get("s")
    assert fetched is not None and fetched.request.auth.password == "sched-secret"


async def test_legacy_plaintext_row_still_reads(db_stores, db_path):
    """Databases written before encryption existed must keep working."""
    credentials, _templates, _schedules = db_stores
    legacy = CredentialProfile(name="old", domain="x.com", username="u", password="legacy-pw")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO credential_profiles (name, data_json, updated_at) VALUES (?, ?, ?)",
            ("old", legacy.model_dump_json(), 0.0),
        )
        conn.commit()
    finally:
        conn.close()

    fetched = await credentials.get("old")
    assert fetched is not None and fetched.password == "legacy-pw"


async def test_resaving_migrates_legacy_row_to_ciphertext(db_stores, db_path):
    credentials, _templates, _schedules = db_stores
    fetched = CredentialProfile(name="m", domain="x.com", username="u", password="migrate-me")
    await credentials.save("m", fetched)
    await credentials.save("m", await credentials.get("m"))

    raw = _raw_rows(db_path, "credential_profiles")
    assert "migrate-me" not in raw
    assert (await credentials.get("m")).password == "migrate-me"
