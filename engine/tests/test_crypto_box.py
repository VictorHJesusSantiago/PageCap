import base64
from pathlib import Path

import pytest

from crypto_box import SecretBox, default_box


@pytest.fixture
def box(tmp_path: Path) -> SecretBox:
    return SecretBox(tmp_path / ".pagecap_key")


def test_roundtrip_recovers_plaintext(box: SecretBox):
    assert box.decrypt(box.encrypt("s3cr3t")) == "s3cr3t"


def test_ciphertext_does_not_contain_plaintext(box: SecretBox):
    assert "s3cr3t" not in (box.encrypt("s3cr3t") or "")


def test_ciphertext_is_tagged(box: SecretBox):
    assert (box.encrypt("hunter2") or "").startswith("enc:v1:")


def test_same_plaintext_encrypts_differently(box: SecretBox):
    """A fresh nonce per call — identical passwords must not produce identical
    rows, or the DB leaks which accounts share a password."""
    assert box.encrypt("same") != box.encrypt("same")


def test_none_and_empty_pass_through(box: SecretBox):
    assert box.encrypt(None) is None
    assert box.encrypt("") == ""
    assert box.decrypt(None) is None


def test_already_encrypted_is_not_double_encrypted(box: SecretBox):
    once = box.encrypt("abc")
    assert box.encrypt(once) == once


def test_legacy_plaintext_decrypts_to_itself(box: SecretBox):
    """Rows written before encryption existed have no prefix and must keep
    working rather than being read as corrupt."""
    assert box.decrypt("legacy-plaintext-password") == "legacy-plaintext-password"


def test_wrong_key_fails_closed(tmp_path: Path):
    ciphertext = SecretBox(tmp_path / "a.key").encrypt("topsecret")
    assert SecretBox(tmp_path / "b.key").decrypt(ciphertext) is None


def test_tampered_ciphertext_fails_closed(box: SecretBox):
    ciphertext = box.encrypt("topsecret") or ""
    body = bytearray(base64.urlsafe_b64decode(ciphertext[len("enc:v1:"):]))
    body[-1] ^= 0xFF  # flip a bit in the GCM tag
    tampered = "enc:v1:" + base64.urlsafe_b64encode(bytes(body)).decode()
    assert box.decrypt(tampered) is None


def test_env_key_is_used_when_set(tmp_path: Path, monkeypatch):
    key = base64.urlsafe_b64encode(b"k" * 32).decode()
    monkeypatch.setenv("PAGECAP_SECRET_KEY", key)
    a, b = SecretBox(tmp_path / "x.key"), SecretBox(tmp_path / "y.key")
    # Different key files, same env key → interchangeable.
    assert b.decrypt(a.encrypt("shared")) == "shared"
    assert not (tmp_path / "x.key").exists()  # no key file written


def test_env_key_wrong_length_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PAGECAP_SECRET_KEY", base64.urlsafe_b64encode(b"short").decode())
    with pytest.raises(ValueError):
        SecretBox(tmp_path / "z.key").encrypt("x")


def test_key_file_is_created_next_to_db(tmp_path: Path):
    db = tmp_path / "sub" / "pagecap.db"
    db.parent.mkdir()
    default_box(db).encrypt("x")
    assert (tmp_path / "sub" / ".pagecap_key").exists()
