"""SQLite-backed stores for credential profiles, job templates, and schedules.

Mirrors the JSON-blob-per-row pattern of job_store.JobStore: each row is a
single Pydantic model serialized to JSON, which keeps these small stores
simple and avoids a second schema migration path.
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class _JsonRowStore(Generic[T]):
    """A generic `name -> JSON blob` table, used by all three stores below."""

    def __init__(self, db_path: Path, table: str, model_cls: type[T]):
        self.db_path = db_path
        self.table = table
        self.model_cls = model_cls
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_sync()

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
        import time
        conn = self._connect()
        try:
            conn.execute(
                f"INSERT INTO {self.table} (name, data_json, updated_at) VALUES (?, ?, ?) "
                f"ON CONFLICT(name) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at",
                (name, obj.model_dump_json(), time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    def _get_sync(self, name: str) -> Optional[T]:
        conn = self._connect()
        try:
            row = conn.execute(f"SELECT data_json FROM {self.table} WHERE name = ?", (name,)).fetchone()
            return self.model_cls.model_validate_json(row[0]) if row else None
        finally:
            conn.close()

    def _list_sync(self) -> list[T]:
        conn = self._connect()
        try:
            rows = conn.execute(f"SELECT data_json FROM {self.table} ORDER BY updated_at DESC").fetchall()
            return [self.model_cls.model_validate_json(r[0]) for r in rows]
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
    """Returns (credential_store, template_store, schedule_store) sharing one db file."""
    from models import CredentialProfile, JobTemplate, ScheduleConfig

    credentials = _JsonRowStore(db_path, "credential_profiles", CredentialProfile)
    templates = _JsonRowStore(db_path, "job_templates", JobTemplate)
    schedules = _JsonRowStore(db_path, "schedules", ScheduleConfig)
    return credentials, templates, schedules
