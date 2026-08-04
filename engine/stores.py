"""SQLite-backed stores for credential profiles, job templates, and schedules.

Mirrors the JSON-blob-per-row pattern of job_store.JobStore: each row is a
single Pydantic model serialized to JSON, which keeps these small stores
simple and avoids a second schema migration path.

Secret fields (site passwords, TOTP secrets, raw cookie headers) are encrypted
before they reach the JSON blob and decrypted on read — see crypto_box.py. The
in-memory model is always plaintext; only the row on disk is ciphertext.
"""
from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

from crypto_box import SecretBox, default_box

T = TypeVar("T", bound=BaseModel)

_SECRET_PATHS: dict[str, tuple[str, ...]] = {
    "credential_profiles": ("password", "totp_secret"),
    "job_templates": ("request.auth.password", "request.auth.totp_secret", "request.auth.cookies_raw"),
    "schedules": ("request.auth.password", "request.auth.totp_secret", "request.auth.cookies_raw"),
}


def _walk(payload: dict, dotted: str, transform) -> None:
    """Applies `transform` in place to the leaf at `dotted` inside `payload`,
    doing nothing if any segment along the way is missing or not a dict."""
    node: Any = payload
    *parents, leaf = dotted.split(".")
    for part in parents:
        node = node.get(part) if isinstance(node, dict) else None
        if node is None:
            return
    if isinstance(node, dict) and node.get(leaf) is not None:
        node[leaf] = transform(node[leaf])


class _JsonRowStore(Generic[T]):
    """A generic `name -> JSON blob` table, used by all three stores below."""

    def __init__(self, db_path: Path, table: str, model_cls: type[T], box: Optional[SecretBox] = None):
        self.db_path = db_path
        self.table = table
        self.model_cls = model_cls
        self.box = box or default_box(db_path)
        self.secret_paths = _SECRET_PATHS.get(table, ())
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_sync()

    def _to_row(self, obj: T) -> str:
        if not self.secret_paths:
            return obj.model_dump_json()
        payload = obj.model_dump()
        for dotted in self.secret_paths:
            _walk(payload, dotted, self.box.encrypt)
        return self.model_cls.model_validate(payload).model_dump_json()

    def _from_row(self, data_json: str) -> T:
        if not self.secret_paths:
            return self.model_cls.model_validate_json(data_json)
        import json

        payload = json.loads(data_json)
        for dotted in self.secret_paths:
            _walk(payload, dotted, self.box.decrypt)
        return self.model_cls.model_validate(payload)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_sync(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table} "
                f"(name TEXT PRIMARY KEY, data_json TEXT NOT NULL, updated_at REAL NOT NULL)"
            )
            conn.commit()
        finally:
            conn.close()

    def _save_sync(self, name: str, obj: T) -> None:
        conn = self._connect()
        try:
            conn.execute(
                f"INSERT INTO {self.table} (name, data_json, updated_at) VALUES (?, ?, ?) "
                f"ON CONFLICT(name) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at",
                (name, self._to_row(obj), time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    def _get_sync(self, name: str) -> Optional[T]:
        conn = self._connect()
        try:
            row = conn.execute(f"SELECT data_json FROM {self.table} WHERE name = ?", (name,)).fetchone()
            return self._from_row(row[0]) if row else None
        finally:
            conn.close()

    def _list_sync(self) -> list[T]:
        conn = self._connect()
        try:
            rows = conn.execute(f"SELECT data_json FROM {self.table} ORDER BY updated_at DESC").fetchall()
            return [self._from_row(r[0]) for r in rows]
        finally:
            conn.close()

    def _delete_sync(self, name: str) -> None:
        conn = self._connect()
        try:
            conn.execute(f"DELETE FROM {self.table} WHERE name = ?", (name,))
            conn.commit()
        finally:
            conn.close()

    async def save(self, name: str, obj: T) -> None:
        await asyncio.to_thread(self._save_sync, name, obj)

    async def get(self, name: str) -> Optional[T]:
        return await asyncio.to_thread(self._get_sync, name)

    async def list(self) -> list[T]:
        return await asyncio.to_thread(self._list_sync)

    async def delete(self, name: str) -> None:
        await asyncio.to_thread(self._delete_sync, name)


def make_stores(db_path: Path):
    """Returns (credential_store, template_store, schedule_store) sharing one
    db file and one encryption key."""
    from models import CredentialProfile, JobTemplate, ScheduleConfig

    box = default_box(db_path)
    credentials = _JsonRowStore(db_path, "credential_profiles", CredentialProfile, box)
    templates = _JsonRowStore(db_path, "job_templates", JobTemplate, box)
    schedules = _JsonRowStore(db_path, "schedules", ScheduleConfig, box)
    return credentials, templates, schedules
