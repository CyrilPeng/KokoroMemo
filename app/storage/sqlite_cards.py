"""SQLite storage for memory cards, inbox, edges, summaries, tags."""

from __future__ import annotations

import json
import aiosqlite
from pathlib import Path

from app.core.ids import generate_id

_CARDS_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS memory_cards (
  card_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  character_id TEXT,
  conversation_id TEXT,
  scope TEXT NOT NULL,
  card_type TEXT NOT NULL,
  title TEXT,
  content TEXT NOT NULL,
  summary TEXT,
  importance REAL NOT NULL DEFAULT 0.5,
  confidence REAL NOT NULL DEFAULT 0.7,
  stability REAL NOT NULL DEFAULT 0.5,
  status TEXT NOT NULL DEFAULT 'pending_review',
  is_pinned INTEGER NOT NULL DEFAULT 0,
  source_turn_ids_json TEXT,
  evidence_text TEXT,
  supersedes_card_id TEXT,
  embedding_model TEXT,
  embedding_dimension INTEGER,
  vector_synced INTEGER NOT NULL DEFAULT 0,
  vector_synced_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  last_accessed_at TEXT,
  access_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_cards_scope
ON memory_cards(user_id, character_id, scope, status);

CREATE INDEX IF NOT EXISTS idx_cards_status
ON memory_cards(status, card_type);

CREATE INDEX IF NOT EXISTS idx_cards_pinned
ON memory_cards(is_pinned, status);

CREATE TABLE IF NOT EXISTS memory_inbox (
  inbox_id TEXT PRIMARY KEY,
  candidate_type TEXT NOT NULL DEFAULT 'card',
  payload_json TEXT NOT NULL,
  user_id TEXT NOT NULL,
  character_id TEXT,
  conversation_id TEXT,
  suggested_action TEXT NOT NULL DEFAULT 'approve',
  risk_level TEXT NOT NULL DEFAULT 'low',
  reason TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  reviewed_at TEXT,
  review_note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_inbox_status
ON memory_inbox(status);

CREATE TABLE IF NOT EXISTS memory_edges (
  edge_id TEXT PRIMARY KEY,
  source_card_id TEXT NOT NULL,
  target_card_id TEXT NOT NULL,
  edge_type TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,
  confidence REAL NOT NULL DEFAULT 0.8,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  FOREIGN KEY(source_card_id) REFERENCES memory_cards(card_id),
  FOREIGN KEY(target_card_id) REFERENCES memory_cards(card_id)
);

CREATE INDEX IF NOT EXISTS idx_edges_source
ON memory_edges(source_card_id, status);

CREATE INDEX IF NOT EXISTS idx_edges_target
ON memory_edges(target_card_id, status);

CREATE TABLE IF NOT EXISTS memory_summaries (
  summary_id TEXT PRIMARY KEY,
  level INTEGER NOT NULL,
  summary_type TEXT NOT NULL,
  title TEXT,
  content TEXT NOT NULL,
  user_id TEXT NOT NULL,
  character_id TEXT,
  conversation_id TEXT,
  importance REAL NOT NULL DEFAULT 0.6,
  confidence REAL NOT NULL DEFAULT 0.7,
  status TEXT NOT NULL DEFAULT 'active',
  source_card_ids_json TEXT,
  embedding_model TEXT,
  vector_synced INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS memory_tags (
  tag_id TEXT PRIMARY KEY,
  tag_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS memory_card_tags (
  card_id TEXT NOT NULL,
  tag_id TEXT NOT NULL,
  PRIMARY KEY(card_id, tag_id),
  FOREIGN KEY(card_id) REFERENCES memory_cards(card_id),
  FOREIGN KEY(tag_id) REFERENCES memory_tags(tag_id)
);

CREATE TABLE IF NOT EXISTS memory_card_events (
  event_id TEXT PRIMARY KEY,
  card_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  FOREIGN KEY(card_id) REFERENCES memory_cards(card_id)
);

CREATE TABLE IF NOT EXISTS memory_card_versions (
  version_id TEXT PRIMARY KEY,
  card_id TEXT NOT NULL,
  version_number INTEGER NOT NULL,
  content TEXT NOT NULL,
  summary TEXT,
  card_type TEXT NOT NULL,
  importance REAL NOT NULL DEFAULT 0.5,
  confidence REAL NOT NULL DEFAULT 0.7,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  FOREIGN KEY(card_id) REFERENCES memory_cards(card_id)
);

CREATE INDEX IF NOT EXISTS idx_card_versions_card
ON memory_card_versions(card_id, version_number);

CREATE TABLE IF NOT EXISTS review_actions (
  action_id TEXT PRIMARY KEY,
  inbox_id TEXT,
  card_id TEXT,
  action TEXT NOT NULL,
  reviewer TEXT,
  note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  payload_json TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  run_after TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


async def init_cards_db(db_path: str) -> None:
    """Initialize the cards database with all tables."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_CARDS_SCHEMA)
        await db.commit()


async def card_exists_with_content(db_path: str, user_id: str, content: str) -> bool:
    """Check if a card with identical content already exists (dedup)."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT 1 FROM memory_cards WHERE user_id = ? AND content = ? AND status != 'deleted' LIMIT 1",
            (user_id, content),
        )
        return (await cursor.fetchone()) is not None


# --- memory_cards CRUD ---

async def insert_card(
    db_path: str,
    card_id: str,
    user_id: str,
    character_id: str | None,
    conversation_id: str | None,
    scope: str,
    card_type: str,
    content: str,
    title: str | None = None,
    summary: str | None = None,
    importance: float = 0.5,
    confidence: float = 0.7,
    status: str = "pending_review",
    is_pinned: int = 0,
    evidence_text: str | None = None,
    supersedes_card_id: str | None = None,
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT OR IGNORE INTO memory_cards
               (card_id, user_id, character_id, conversation_id, scope, card_type,
                title, content, summary, importance, confidence, status, is_pinned,
                evidence_text, supersedes_card_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (card_id, user_id, character_id, conversation_id, scope, card_type,
             title, content, summary, importance, confidence, status, is_pinned,
             evidence_text, supersedes_card_id),
        )
        await db.commit()


async def insert_card_version(
    db_path: str,
    card_id: str,
    content: str,
    card_type: str,
    summary: str | None = None,
    importance: float = 0.5,
    confidence: float = 0.7,
) -> str:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 FROM memory_card_versions WHERE card_id = ?",
            (card_id,),
        )
        version_number = (await cursor.fetchone())[0]
        version_id = generate_id("ver_")
        await db.execute(
            """INSERT INTO memory_card_versions
               (version_id, card_id, version_number, content, summary, card_type, importance, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (version_id, card_id, version_number, content, summary, card_type, importance, confidence),
        )
        await db.commit()
        return version_id


async def insert_review_action(
    db_path: str,
    action: str,
    inbox_id: str | None = None,
    card_id: str | None = None,
    reviewer: str | None = "local_user",
    note: str | None = None,
) -> str:
    action_id = generate_id("review_")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO review_actions
               (action_id, inbox_id, card_id, action, reviewer, note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (action_id, inbox_id, card_id, action, reviewer, note),
        )
        await db.commit()
    return action_id


async def enqueue_job(db_path: str, job_type: str, payload_json: str, last_error: str | None = None) -> str:
    job_id = generate_id("job_")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO jobs (job_id, job_type, status, payload_json, last_error)
               VALUES (?, ?, 'pending', ?, ?)""",
            (job_id, job_type, payload_json, last_error),
        )
        await db.commit()
    return job_id


async def get_pending_jobs(db_path: str, job_type: str | None = None, limit: int = 50) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        if job_type:
            cursor = await db.execute(
                """SELECT * FROM jobs WHERE status IN ('pending', 'failed') AND job_type = ?
                   ORDER BY created_at ASC LIMIT ?""",
                (job_type, limit),
            )
        else:
            cursor = await db.execute(
                """SELECT * FROM jobs WHERE status IN ('pending', 'failed')
                   ORDER BY created_at ASC LIMIT ?""",
                (limit,),
            )
        return [dict(r) for r in await cursor.fetchall()]


async def update_job_status(db_path: str, job_id: str, status: str, last_error: str | None = None) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """UPDATE jobs SET status = ?, last_error = ?,
               attempts = attempts + CASE WHEN ? = 'failed' THEN 1 ELSE 0 END,
               updated_at = datetime('now', 'localtime') WHERE job_id = ?""",
            (status, last_error, status, job_id),
        )
        await db.commit()


async def update_card_status(db_path: str, card_id: str, status: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE memory_cards SET status = ?, updated_at = datetime('now', 'localtime') WHERE card_id = ?",
            (status, card_id),
        )
        await db.commit()


async def mark_card_vector_synced(db_path: str, card_id: str, model: str, dimension: int | None) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """UPDATE memory_cards SET vector_synced = 1, vector_synced_at = datetime('now', 'localtime'),
               embedding_model = ?, embedding_dimension = ? WHERE card_id = ?""",
            (model, dimension, card_id),
        )
        await db.commit()


async def mark_card_vector_unsynced(db_path: str, card_id: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """UPDATE memory_cards SET vector_synced = 0, vector_synced_at = NULL,
               updated_at = datetime('now', 'localtime') WHERE card_id = ?""",
            (card_id,),
        )
        await db.commit()


async def get_cards_by_ids(db_path: str, card_ids: list[str]) -> dict[str, dict]:
    """Get cards by id from SQLite truth source."""
    if not card_ids:
        return {}
    placeholders = ",".join(["?"] * len(card_ids))
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"SELECT * FROM memory_cards WHERE card_id IN ({placeholders})",
            card_ids,
        )
        rows = await cursor.fetchall()
        return {r["card_id"]: dict(r) for r in rows}


async def get_approved_cards(db_path: str, user_id: str | None = None) -> list[dict]:
    """Get all approved cards, optionally filtered by user."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        if user_id:
            cursor = await db.execute(
                "SELECT * FROM memory_cards WHERE status = 'approved' AND user_id = ?", (user_id,)
            )
        else:
            cursor = await db.execute("SELECT * FROM memory_cards WHERE status = 'approved'")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_pinned_cards(db_path: str, user_id: str, character_id: str | None) -> list[dict]:
    """Get pinned/boundary cards for retrieval."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        query = """SELECT * FROM memory_cards
                   WHERE status = 'approved' AND user_id = ?
                   AND (is_pinned = 1 OR card_type = 'boundary')"""
        params: list = [user_id]
        if character_id:
            query += " AND (character_id = ? OR character_id IS NULL)"
            params.append(character_id)
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_recent_important_cards(
    db_path: str, user_id: str, character_id: str | None, days: int = 7, min_importance: float = 0.75, limit: int = 6
) -> list[dict]:
    """Get recently created important approved cards."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        query = """SELECT * FROM memory_cards
                   WHERE status = 'approved' AND user_id = ?
                   AND importance >= ?
                   AND created_at >= datetime('now', 'localtime', ?)"""
        params: list = [user_id, min_importance, f"-{days} days"]
        if character_id:
            query += " AND (character_id = ? OR character_id IS NULL)"
            params.append(character_id)
        query += " ORDER BY importance DESC, created_at DESC LIMIT ?"
        params.append(limit)
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# --- memory_inbox CRUD ---

async def insert_inbox_item(
    db_path: str,
    inbox_id: str,
    candidate_type: str,
    payload_json: str,
    user_id: str,
    character_id: str | None,
    conversation_id: str | None,
    suggested_action: str = "approve",
    risk_level: str = "low",
    reason: str | None = None,
    status: str = "pending",
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO memory_inbox
               (inbox_id, candidate_type, payload_json, user_id, character_id, conversation_id,
                suggested_action, risk_level, reason, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (inbox_id, candidate_type, payload_json, user_id, character_id, conversation_id,
             suggested_action, risk_level, reason, status),
        )
        await db.commit()


async def get_inbox_items(db_path: str, status: str = "pending", limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        count_cursor = await db.execute(
            "SELECT COUNT(*) FROM memory_inbox WHERE status = ?", (status,)
        )
        total = (await count_cursor.fetchone())[0]
        cursor = await db.execute(
            "SELECT * FROM memory_inbox WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (status, limit, offset),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows], total


async def update_inbox_status(db_path: str, inbox_id: str, status: str, review_note: str | None = None) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE memory_inbox SET status = ?, reviewed_at = datetime('now', 'localtime'), review_note = ? WHERE inbox_id = ?",
            (status, review_note, inbox_id),
        )
        await db.commit()


async def get_inbox_item(db_path: str, inbox_id: str) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM memory_inbox WHERE inbox_id = ?", (inbox_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
