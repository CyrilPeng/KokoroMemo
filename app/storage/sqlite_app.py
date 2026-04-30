"""SQLite storage for app-level data (conversations registry, users, characters)."""

from __future__ import annotations

import json

import aiosqlite
from pathlib import Path

_APP_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  display_name TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS characters (
  character_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  display_name TEXT,
  system_prompt_hash TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS character_defaults (
  character_id TEXT PRIMARY KEY,
  template_id TEXT,
  library_ids_json TEXT NOT NULL DEFAULT '["lib_default"]',
  write_library_id TEXT,
  auto_apply INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS conversations (
  conversation_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  character_id TEXT,
  client_name TEXT,
  title TEXT,
  path TEXT NOT NULL,
  first_seen_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  last_seen_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  status TEXT NOT NULL DEFAULT 'active'
);
"""


async def init_app_db(db_path: str) -> None:
    """Initialize app.sqlite with schema."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_APP_SCHEMA)
        await db.commit()


async def upsert_conversation(
    db_path: str,
    conversation_id: str,
    user_id: str,
    character_id: str | None,
    client_name: str | None,
    conv_path: str,
) -> None:
    """Register or update a conversation in app.sqlite."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO conversations (conversation_id, user_id, character_id, client_name, path, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
            ON CONFLICT(conversation_id) DO UPDATE SET
              last_seen_at = datetime('now', 'localtime'),
              character_id = COALESCE(excluded.character_id, conversations.character_id),
              client_name = COALESCE(excluded.client_name, conversations.client_name)
            """,
            (conversation_id, user_id, character_id, client_name, conv_path),
        )
        await db.commit()


async def get_character_defaults(db_path: str, character_id: str) -> dict | None:
    """Get default template and library config for a character."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM character_defaults WHERE character_id = ?",
            (character_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "character_id": row["character_id"],
            "template_id": row["template_id"],
            "library_ids": json.loads(row["library_ids_json"]),
            "write_library_id": row["write_library_id"],
            "auto_apply": bool(row["auto_apply"]),
        }


async def set_character_defaults(
    db_path: str,
    character_id: str,
    template_id: str | None = None,
    library_ids: list[str] | None = None,
    write_library_id: str | None = None,
    auto_apply: bool = True,
) -> None:
    """Save default template and library config for a character."""
    library_ids_json = json.dumps(library_ids or ["lib_default"])
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO character_defaults (character_id, template_id, library_ids_json, write_library_id, auto_apply)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(character_id) DO UPDATE SET
              template_id = excluded.template_id,
              library_ids_json = excluded.library_ids_json,
              write_library_id = excluded.write_library_id,
              auto_apply = excluded.auto_apply,
              updated_at = datetime('now', 'localtime')
            """,
            (character_id, template_id, library_ids_json, write_library_id, int(auto_apply)),
        )
        await db.commit()


async def list_characters(db_path: str) -> list[dict]:
    """List all known characters."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT c.*, cd.template_id, cd.library_ids_json, cd.write_library_id, cd.auto_apply "
            "FROM characters c LEFT JOIN character_defaults cd ON c.character_id = cd.character_id "
            "ORDER BY c.updated_at DESC"
        )
        rows = await cursor.fetchall()
        return [
            {
                "character_id": row["character_id"],
                "user_id": row["user_id"],
                "display_name": row["display_name"],
                "system_prompt_hash": row["system_prompt_hash"],
                "template_id": row["template_id"],
                "library_ids": json.loads(row["library_ids_json"]) if row["library_ids_json"] else None,
                "write_library_id": row["write_library_id"],
                "auto_apply": bool(row["auto_apply"]) if row["auto_apply"] is not None else None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]


async def list_conversations(db_path: str, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    """List recent conversations ordered by last_seen_at descending."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT COUNT(*) FROM conversations")
        total = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "SELECT conversation_id, user_id, character_id, client_name, last_seen_at, first_seen_at "
            "FROM conversations ORDER BY last_seen_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        items = [
            {
                "conversation_id": row["conversation_id"],
                "user_id": row["user_id"],
                "character_id": row["character_id"],
                "client_name": row["client_name"],
                "last_seen_at": row["last_seen_at"],
                "first_seen_at": row["first_seen_at"],
            }
            for row in rows
        ]
        return items, total
