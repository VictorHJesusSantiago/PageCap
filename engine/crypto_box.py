"""Encryption-at-rest for the few fields PageCap has to keep in cleartext-capable
form: site passwords, TOTP secrets and raw cookie headers.

Why this exists: `stores.py` writes each Pydantic model as one JSON blob, so a
saved CredentialProfile put the user's password for a third-party site into
`pagecap.db` in plaintext. That file sits in the working directory, gets copied
by backups and sync clients, and (before this audit) was even bundled into the
Electron installer. A local-only threat model still assumes the *disk* is a
lower trust tier than the running process.

Design:
  - AES-256-GCM (AEAD: confidentiality + integrity) via `cryptography`, with a
    fresh 12-byte nonce per encryption. Never reuse a nonce with the same key.
  - The key comes from PAGECAP_SECRET_KEY (base64, 32 bytes) if set, otherwise
    a key file next to the DB, created 0600 on first use.
  - Ciphertext is tagged with a version prefix so plaintext rows written by
    older builds keep decrypting to themselves (transparent lazy migration:
    they re-encrypt the next time they are saved).
  - If `cryptography` is unavailable the module degrades to a no-op and logs
    loudly, rather than making credential storage unusable on a partial install.
"""
from __future__ import annotations

import base64
import os
import secrets
import stat
from pathlib import Path
from typing import Optional

from logging_config import get_logger

log = get_logger("crypto")

_PREFIX = "enc:v1:"
_NONCE_BYTES = 12
_KEY_BYTES = 32

try:  # pragma: no cover - exercised by whichever branch the environment has
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    _AVAILABLE = True
except ImportError:  # pragma: no cover
    AESGCM = None  # type: ignore[assignment]
    _AVAILABLE = False


class SecretBox:
    """Encrypts/decrypts short strings with one key. `decrypt` is total: any
    value that is not our own ciphertext is returned unchanged, which is what
    makes the migration from previously-plaintext rows seamless."""

    def __init__(self, key_path: Path):
        self._key_path = key_path
        self._key: Optional[bytes] = None

    # ── key management ──────────────────────────────────────────────────────
    def _load_key(self) -> Optional[bytes]:
        if self._key is not None:
            return self._key

        env_key = os.getenv("PAGECAP_SECRET_KEY")
        if env_key:
            try:
                key = base64.urlsafe_b64decode(env_key)
            except Exception:
                raise ValueError("PAGECAP_SECRET_KEY is not valid base64")
            if len(key) != _KEY_BYTES:
                raise ValueError(f"PAGECAP_SECRET_KEY must decode to {_KEY_BYTES} bytes")
            self._key = key
            return key

        if self._key_path.exists():
            key = base64.urlsafe_b64decode(self._key_path.read_bytes())
        else:
            key = secrets.token_bytes(_KEY_BYTES)
            self._key_path.parent.mkdir(parents=True, exist_ok=True)
            self._key_path.write_bytes(base64.urlsafe_b64encode(key))
            try:
                # Owner read/write only. No-op semantics on Windows, where the
                # inherited directory ACL is what actually governs access.
                self._key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
        self._key = key
        return key

    # ── API ─────────────────────────────────────────────────────────────────
    def encrypt(self, plaintext: Optional[str]) -> Optional[str]:
        if plaintext is None or plaintext == "" or plaintext.startswith(_PREFIX):
            return plaintext
        if not _AVAILABLE:
            log.warning(
                "cryptography is not installed — storing a secret in plaintext. "
                "Run: pip install 'cryptography>=43.0.0'"
            )
            return plaintext
        key = self._load_key()
        nonce = secrets.token_bytes(_NONCE_BYTES)
        blob = nonce + AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
        return _PREFIX + base64.urlsafe_b64encode(blob).decode("ascii")

    def decrypt(self, value: Optional[str]) -> Optional[str]:
        if value is None or not value.startswith(_PREFIX):
            return value  # legacy plaintext row, or nothing to do
        if not _AVAILABLE:
            log.error("Encrypted secret found but cryptography is not installed")
            return None
        try:
            blob = base64.urlsafe_b64decode(value[len(_PREFIX):])
            key = self._load_key()
            return AESGCM(key).decrypt(blob[:_NONCE_BYTES], blob[_NONCE_BYTES:], None).decode("utf-8")
        except Exception:
            # Wrong key or tampered ciphertext. Fail closed: the caller sees a
            # missing credential rather than a corrupted one it might submit.
            log.error("Failed to decrypt a stored secret (wrong key or tampered data)")
            return None


def default_box(db_path: Path) -> SecretBox:
    """The SecretBox guarding `db_path`, keyed by a sibling `.pagecap_key`.

    Takes the path explicitly rather than reading `config.settings` so tests
    (and any future multi-database use) can point it at a temp directory
    without mutating global configuration.
    """
    return SecretBox(db_path.parent / ".pagecap_key")
