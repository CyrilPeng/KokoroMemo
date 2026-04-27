"""SQLite storage for app-level data (conversations registry, users, characters)."""

from __future__ import annotations

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
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS characters (
  character_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  display_name TEXT,
  system_prompt_hash TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
  conversation_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  character_id TEXT,
  client_name TEXT,
  title TEXT,
  path TEXT NOT NULL,
  first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
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
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(conversation_id) DO UPDATE SET
              last_seen_at = datetime('now'),
              character_id = COALESCE(excluded.character_id, conversations.character_id),
              client_name = COALESCE(excluded.client_name, conversations.client_name)
            """,
            (conversation_id, user_id, character_id, client_name, conv_path),
        )
        await db.commit()
