"""SQLite storage for structured memories."""

from __future__ import annotations

import aiosqlite
from pathlib import Path

_MEMORY_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS memories (
  memory_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  character_id TEXT,
  conversation_id TEXT,
  scope TEXT NOT NULL,
  memory_type TEXT NOT NULL,
  content TEXT NOT NULL,
  summary TEXT,
  tags_json TEXT,
  importance REAL NOT NULL DEFAULT 0.5,
  confidence REAL NOT NULL DEFAULT 0.7,
  status TEXT NOT NULL DEFAULT 'active',
  source_turn_ids_json TEXT,
  source_message_ids_json TEXT,
  embedding_provider TEXT,
  embedding_model TEXT,
  embedding_dimension INTEGER,
  vector_index_name TEXT,
  vector_synced INTEGER NOT NULL DEFAULT 0,
  vector_synced_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  last_accessed_at TEXT,
  access_count INTEGER NOT NULL DEFAULT 0,
  expires_at TEXT,
  supersedes_memory_id TEXT,
  conflict_group_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_memories_scope
ON memories(user_id, character_id, conversation_id, scope, status);

CREATE INDEX IF NOT EXISTS idx_memories_embedding
ON memories(embedding_model, embedding_dimension, vector_synced);

CREATE TABLE IF NOT EXISTS memory_events (
  event_id TEXT PRIMARY KEY,
  memory_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  FOREIGN KEY(memory_id) REFERENCES memories(memory_id)
);

CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  payload_json TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  run_after TEXT
);
"""


async def init_memory_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_MEMORY_SCHEMA)
        await db.commit()


async def insert_memory(
    db_path: str,
    memory_id: str,
    user_id: str,
    character_id: str | None,
    conversation_id: str | None,
    scope: str,
    memory_type: str,
    content: str,
    summary: str | None = None,
    tags_json: str | None = None,
    importance: float = 0.5,
    confidence: float = 0.7,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
    embedding_dimension: int | None = None,
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT OR IGNORE INTO memories
               (memory_id, user_id, character_id, conversation_id, scope, memory_type,
                content, summary, tags_json, importance, confidence,
                embedding_provider, embedding_model, embedding_dimension, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))""",
            (memory_id, user_id, character_id, conversation_id, scope, memory_type,
             content, summary, tags_json, importance, confidence,
             embedding_provider, embedding_model, embedding_dimension),
        )
        await db.commit()


async def mark_vector_synced(db_path: str, memory_id: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE memories SET vector_synced = 1, vector_synced_at = datetime('now', 'localtime') WHERE memory_id = ?",
            (memory_id,),
        )
        await db.commit()


async def get_active_memories(db_path: str) -> list[dict]:
    """Get all active memories for rebuild."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM memories WHERE status = 'active'"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def update_memory_access(db_path: str, memory_id: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE memories SET last_accessed_at = datetime('now', 'localtime'), access_count = access_count + 1 WHERE memory_id = ?",
            (memory_id,),
        )
        await db.commit()
