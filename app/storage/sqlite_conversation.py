"""Per-conversation SQLite storage for chat logs."""

from __future__ import annotations

import aiosqlite
from pathlib import Path

_CHAT_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS turns (
  turn_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  character_id TEXT,
  request_id TEXT NOT NULL,
  turn_index INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS messages (
  message_id TEXT PRIMARY KEY,
  turn_id TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  role TEXT NOT NULL,
  name TEXT,
  content TEXT,
  raw_json TEXT,
  token_estimate INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  FOREIGN KEY(turn_id) REFERENCES turns(turn_id)
);

CREATE TABLE IF NOT EXISTS raw_requests (
  request_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  body_json TEXT NOT NULL,
  headers_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS raw_responses (
  response_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  body_json TEXT,
  stream_text TEXT,
  finish_reason TEXT,
  error_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS injected_memory_logs (
  injection_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  injected_text TEXT NOT NULL,
  card_ids_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


async def init_chat_db(db_path: str) -> None:
    """Initialize a per-conversation chat.sqlite."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_CHAT_SCHEMA)
        await db.commit()


async def save_raw_request(
    db_path: str, request_id: str, conversation_id: str, body_json: str, headers_json: str | None = None
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO raw_requests (request_id, conversation_id, body_json, headers_json, created_at) VALUES (?, ?, ?, ?, datetime('now', 'localtime'))",
            (request_id, conversation_id, body_json, headers_json),
        )
        await db.commit()


async def save_raw_response(
    db_path: str,
    response_id: str,
    request_id: str,
    conversation_id: str,
    body_json: str | None = None,
    stream_text: str | None = None,
    finish_reason: str | None = None,
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT OR IGNORE INTO raw_responses
               (response_id, request_id, conversation_id, body_json, stream_text, finish_reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))""",
            (response_id, request_id, conversation_id, body_json, stream_text, finish_reason),
        )
        await db.commit()


async def save_injected_memory_log(
    db_path: str,
    injection_id: str,
    request_id: str,
    conversation_id: str,
    injected_text: str,
    card_ids_json: str | None = None,
) -> None:
    """Persist the exact memory block injected into an upstream request."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO injected_memory_logs
               (injection_id, request_id, conversation_id, injected_text, card_ids_json, created_at)
               VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))""",
            (injection_id, request_id, conversation_id, injected_text, card_ids_json),
        )
        await db.commit()


async def save_turn_and_messages(
    db_path: str,
    turn_id: str,
    conversation_id: str,
    user_id: str,
    character_id: str | None,
    request_id: str,
    turn_index: int,
    messages: list[dict],
) -> None:
    """Save a turn and its messages."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO turns (turn_id, conversation_id, user_id, character_id, request_id, turn_index, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))",
            (turn_id, conversation_id, user_id, character_id, request_id, turn_index),
        )
        for msg in messages:
            from app.core.ids import generate_id
            msg_id = generate_id("msg_")
            await db.execute(
                "INSERT OR IGNORE INTO messages (message_id, turn_id, conversation_id, role, name, content, raw_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))",
                (
                    msg_id,
                    turn_id,
                    conversation_id,
                    msg.get("role", ""),
                    msg.get("name"),
                    msg.get("content", ""),
                    None,
                ),
            )
        await db.commit()


async def get_turn_count(db_path: str, conversation_id: str) -> int:
    """Get current turn count for a conversation."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM turns WHERE conversation_id = ?", (conversation_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_all_messages(db_path: str, conversation_id: str) -> list[dict]:
    """Return all messages in a conversation ordered by creation time."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC, message_id ASC",
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]


async def get_recent_messages(db_path: str, conversation_id: str, limit: int = 30) -> list[dict]:
    """Return recent messages in display order for quick conversation preview."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT role, name, content, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at DESC, message_id DESC
            LIMIT ?
            """,
            (conversation_id, limit),
        )
        rows = list(await cursor.fetchall())
        rows.reverse()
        return [
            {
                "role": row["role"],
                "name": row["name"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]


async def update_conversation_character(db_path: str, conversation_id: str, character_id: str | None) -> int:
    """Update saved turn ownership for a conversation."""
    await init_chat_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "UPDATE turns SET character_id = ? WHERE conversation_id = ?",
            (character_id, conversation_id),
        )
        await db.commit()
        return cursor.rowcount
