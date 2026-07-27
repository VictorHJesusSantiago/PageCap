import importlib
import sys
from pathlib import Path

import pytest


def _fresh_config(monkeypatch, **env):
    for key in list(env) + [
        "PAGECAP_DB_PATH", "PAGECAP_REQUIRE_AUTH", "PAGECAP_ALLOW_NULL_ORIGIN",
        "PAGECAP_CORS_ORIGINS", "PAGECAP_RATE_LIMIT_PER_MINUTE", "PAGECAP_API_TOKEN",
        "PAGECAP_JOB_TTL_SECONDS", "PAGECAP_PLUGINS_DIR", "PAGECAP_DOWNLOADS_DIR",
    ]:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop("config", None)
    return importlib.import_module("config").settings


def test_defaults(monkeypatch):
    s = _fresh_config(monkeypatch)
    assert s.db_path == Path("pagecap.db")
    assert s.downloads_dir == Path("downloads")
    assert s.require_auth is True  # auth is on unless explicitly disabled
    assert s.allow_null_origin is False
    assert s.rate_limit_per_minute == 0
    assert s.job_ttl_seconds == 3 * 24 * 3600
    assert s.plugins_dir is None


@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("true", True), ("TRUE", True), ("yes", True), ("on", True),
    ("0", False), ("false", False), ("no", False), ("", False), ("garbage", False),
])
def test_flag_parsing(monkeypatch, raw, expected):
    assert _fresh_config(monkeypatch, PAGECAP_ALLOW_NULL_ORIGIN=raw).allow_null_origin is expected


def test_require_auth_defaults_true_but_can_be_turned_off(monkeypatch):
    assert _fresh_config(monkeypatch, PAGECAP_REQUIRE_AUTH="0").require_auth is False
    assert _fresh_config(monkeypatch).require_auth is True


def test_wildcard_cors_origin_is_always_dropped(monkeypatch):
    s = _fresh_config(monkeypatch, PAGECAP_CORS_ORIGINS="*,https://ok.example, ,https://two.example")
    assert s.extra_cors_origins == ("https://ok.example", "https://two.example")


def test_malformed_numbers_fall_back_to_defaults(monkeypatch):
    """A typo in a numeric env var must not crash the server at import."""
    s = _fresh_config(monkeypatch, PAGECAP_JOB_TTL_SECONDS="not-a-number",
                      PAGECAP_RATE_LIMIT_PER_MINUTE="abc")
    assert s.job_ttl_seconds == 3 * 24 * 3600
    assert s.rate_limit_per_minute == 0


def test_token_and_key_files_sit_next_to_the_database(monkeypatch, tmp_path: Path):
    s = _fresh_config(monkeypatch, PAGECAP_DB_PATH=str(tmp_path / "sub" / "db.sqlite"))
    assert s.token_file == tmp_path / "sub" / ".pagecap_token"
    assert s.key_file == tmp_path / "sub" / ".pagecap_key"


def test_settings_are_immutable(monkeypatch):
    """Frozen so nothing can mutate configuration at runtime, which is what
    makes "config is read once at import" a real guarantee."""
    import dataclasses

    s = _fresh_config(monkeypatch)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.require_auth = False  # type: ignore[misc]


def test_empty_api_token_is_treated_as_unset(monkeypatch):
    assert _fresh_config(monkeypatch, PAGECAP_API_TOKEN="").api_token is None
