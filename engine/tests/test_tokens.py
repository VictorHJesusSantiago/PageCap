import stat
import sys
from pathlib import Path

from auth.tokens import read_local_token, resolve_api_token


def test_configured_token_wins(tmp_path: Path):
    token_file = tmp_path / ".pagecap_token"
    assert resolve_api_token("explicit", token_file, True) == "explicit"
    assert not token_file.exists()  # nothing generated when one was supplied


def test_generates_and_persists_when_none_supplied(tmp_path: Path):
    token_file = tmp_path / ".pagecap_token"
    token = resolve_api_token(None, token_file, True)
    assert token and len(token) >= 32
    assert token_file.read_text().strip() == token


def test_reuses_a_persisted_token(tmp_path: Path):
    token_file = tmp_path / ".pagecap_token"
    first = resolve_api_token(None, token_file, True)
    second = resolve_api_token(None, token_file, True)
    assert first == second


def test_generated_tokens_are_unique_per_file(tmp_path: Path):
    a = resolve_api_token(None, tmp_path / "a", True)
    b = resolve_api_token(None, tmp_path / "b", True)
    assert a != b


def test_require_auth_false_returns_none(tmp_path: Path):
    token_file = tmp_path / ".pagecap_token"
    assert resolve_api_token(None, token_file, False) is None
    assert not token_file.exists()


def test_configured_token_still_enforced_even_with_require_auth_false(tmp_path: Path):
    """An explicit token is an explicit intent to authenticate; the opt-out flag
    only governs the *generated* fallback."""
    assert resolve_api_token("explicit", tmp_path / "t", False) == "explicit"


def test_token_file_is_owner_only(tmp_path: Path):
    token_file = tmp_path / ".pagecap_token"
    resolve_api_token(None, token_file, True)
    if sys.platform != "win32":
        mode = stat.S_IMODE(token_file.stat().st_mode)
        assert mode == stat.S_IRUSR | stat.S_IWUSR


def test_parent_directory_is_created(tmp_path: Path):
    token_file = tmp_path / "nested" / "dir" / ".pagecap_token"
    assert resolve_api_token(None, token_file, True)
    assert token_file.exists()


def test_blank_token_file_is_treated_as_absent(tmp_path: Path):
    token_file = tmp_path / ".pagecap_token"
    token_file.write_text("   \n")
    token = resolve_api_token(None, token_file, True)
    assert token and token.strip() == token
    assert token_file.read_text().strip() == token


def test_read_local_token(tmp_path: Path):
    token_file = tmp_path / ".pagecap_token"
    assert read_local_token(token_file) is None
    resolve_api_token(None, token_file, True)
    assert read_local_token(token_file) == token_file.read_text().strip()
