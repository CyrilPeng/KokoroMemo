"""Centralized SQLite schema migration manager."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from app.storage.sqlite_app import init_app_db
from app.storage.sqlite_cards import init_cards_db
from app.storage.sqlite_state import init_state_db

SCHEMA_VERSION_TABLE = "schema_version"


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class DatabaseMigrationTarget:
    name: str
    db_path: str
    migrations: tuple[Migration, ...]

    @property
    def target_version(self) -> int:
        return max((migration.version for migration in self.migrations), default=0)


APP_MIGRATIONS = (Migration(1, "baseline_app_schema", init_app_db),)
MEMORY_MIGRATIONS = (Migration(1, "baseline_memory_schema", lambda db_path: _init_memory_db(db_path)),)


async def apply_startup_migrations(cfg) -> None:
    """Apply all process-wide database schema migrations once during startup."""
    targets = [
        DatabaseMigrationTarget("app", cfg.storage.sqlite.app_db, APP_MIGRATIONS),
        DatabaseMigrationTarget("memory", cfg.storage.sqlite.memory_db, MEMORY_MIGRATIONS),
    ]
    for target in targets:
        await apply_migrations(target)


async def apply_migrations(target: DatabaseMigrationTarget) -> None:
    Path(target.db_path).parent.mkdir(parents=True, exist_ok=True)
    current_version = await get_schema_version(target.db_path, target.name)
    for migration in sorted(target.migrations, key=lambda item: item.version):
        if migration.version <= current_version:
            continue
        await migration.apply(target.db_path)
        await set_schema_version(target.db_path, target.name, migration.version)


async def get_schema_version(db_path: str, namespace: str) -> int:
    await _ensure_schema_version_table(db_path)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            f"SELECT version FROM {SCHEMA_VERSION_TABLE} WHERE namespace = ?",
            (namespace,),
        )
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def set_schema_version(db_path: str, namespace: str, version: int) -> None:
    await _ensure_schema_version_table(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            f"""INSERT INTO {SCHEMA_VERSION_TABLE} (namespace, version, applied_at)
                VALUES (?, ?, datetime('now', 'localtime'))
                ON CONFLICT(namespace) DO UPDATE SET
                    version = excluded.version,
                    applied_at = excluded.applied_at""",
            (namespace, version),
        )
        await db.commit()


async def _ensure_schema_version_table(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            f"""CREATE TABLE IF NOT EXISTS {SCHEMA_VERSION_TABLE} (
                namespace TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )"""
        )
        await db.commit()


async def _init_memory_db(db_path: str) -> None:
    await init_cards_db(db_path)
    await init_state_db(db_path)
