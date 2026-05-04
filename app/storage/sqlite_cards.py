"""SQLite storage for memory cards, inbox, edges, summaries, tags."""

from __future__ import annotations

import json
import aiosqlite
from pathlib import Path

from app.core.ids import generate_id

DEFAULT_MEMORY_LIBRARY_ID = "lib_default"

_CARDS_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS memory_cards (
  card_id TEXT PRIMARY KEY,
  library_id TEXT NOT NULL DEFAULT 'lib_default',
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
  library_id TEXT NOT NULL DEFAULT 'lib_default',
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
  library_id TEXT NOT NULL DEFAULT 'lib_default',
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

CREATE TABLE IF NOT EXISTS memory_libraries (
  library_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  is_builtin INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS conversation_memory_mounts (
  mount_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  library_id TEXT NOT NULL,
  user_id TEXT,
  character_id TEXT,
  is_write_target INTEGER NOT NULL DEFAULT 0,
  sort_order INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  FOREIGN KEY(library_id) REFERENCES memory_libraries(library_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_mount_unique
ON conversation_memory_mounts(conversation_id, library_id)
WHERE status = 'active';

CREATE TABLE IF NOT EXISTS memory_mount_presets (
  preset_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  library_ids_json TEXT NOT NULL,
  write_library_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


_MEMORY_CARD_COLUMNS = {
    "library_id": "TEXT NOT NULL DEFAULT 'lib_default'",
}

_MEMORY_INBOX_COLUMNS = {
    "library_id": "TEXT NOT NULL DEFAULT 'lib_default'",
}

_MEMORY_SUMMARY_COLUMNS = {
    "library_id": "TEXT NOT NULL DEFAULT 'lib_default'",
}


async def init_cards_db(db_path: str) -> None:
    """Initialize the cards database with all tables."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_CARDS_SCHEMA)
        await _ensure_columns(db, "memory_cards", _MEMORY_CARD_COLUMNS)
        await _ensure_columns(db, "memory_inbox", _MEMORY_INBOX_COLUMNS)
        await _ensure_columns(db, "memory_summaries", _MEMORY_SUMMARY_COLUMNS)
        await _ensure_library_indexes(db)
        await _ensure_default_library(db)
        await db.commit()


async def _ensure_columns(db: aiosqlite.Connection, table: str, columns: dict[str, str]) -> None:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in await cursor.fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


async def _ensure_library_indexes(db: aiosqlite.Connection) -> None:
    await db.execute(
        """CREATE INDEX IF NOT EXISTS idx_cards_library_scope
           ON memory_cards(library_id, user_id, character_id, scope, status)"""
    )
    await db.execute(
        """CREATE INDEX IF NOT EXISTS idx_cards_library
           ON memory_cards(library_id, status, updated_at)"""
    )


async def _ensure_default_library(db: aiosqlite.Connection) -> None:
    await db.execute(
        """INSERT INTO memory_libraries (library_id, name, description, status, is_builtin)
           VALUES (?, '默认记忆库', '未指定预设时使用的默认长期记忆库。', 'active', 1)
           ON CONFLICT(library_id) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            status = 'active',
            is_builtin = 1,
            updated_at = datetime('now', 'localtime')""",
        (DEFAULT_MEMORY_LIBRARY_ID,),
    )
    await db.execute("UPDATE memory_cards SET library_id = ? WHERE library_id IS NULL OR library_id = ''", (DEFAULT_MEMORY_LIBRARY_ID,))
    await db.execute("UPDATE memory_inbox SET library_id = ? WHERE library_id IS NULL OR library_id = ''", (DEFAULT_MEMORY_LIBRARY_ID,))


async def card_exists_with_content(db_path: str, user_id: str, content: str) -> bool:
    """Check if a card with identical content already exists (dedup)."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT 1 FROM memory_cards WHERE user_id = ? AND content = ? AND status != 'deleted' LIMIT 1",
            (user_id, content),
        )
        return (await cursor.fetchone()) is not None


# --- 记忆库与挂载 ---

async def list_memory_libraries(db_path: str, include_deleted: bool = False) -> list[dict]:
    await init_cards_db(db_path)
    where = "" if include_deleted else "WHERE l.status = 'active'"
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"""SELECT l.*, COUNT(c.card_id) AS card_count
                FROM memory_libraries l
                LEFT JOIN memory_cards c ON c.library_id = l.library_id AND c.status != 'deleted'
                {where}
                GROUP BY l.library_id
                ORDER BY l.is_builtin DESC, l.updated_at DESC"""
        )
        return [dict(row) for row in await cursor.fetchall()]


async def create_memory_library(
    db_path: str,
    name: str,
    description: str = "",
    library_id: str | None = None,
    source_library_ids: list[str] | None = None,
) -> str:
    await init_cards_db(db_path)
    library_id = library_id or generate_id("lib_")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO memory_libraries (library_id, name, description, status, is_builtin)
               VALUES (?, ?, ?, 'active', 0)
               ON CONFLICT(library_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                status = 'active',
                updated_at = datetime('now', 'localtime')""",
            (library_id, name, description),
        )
        for source_library_id in source_library_ids or []:
            await db.execute(
                """INSERT OR IGNORE INTO memory_cards
                   (card_id, library_id, user_id, character_id, conversation_id, scope, card_type,
                    title, content, summary, importance, confidence, stability, status, is_pinned,
                    source_turn_ids_json, evidence_text, supersedes_card_id, embedding_model,
                    embedding_dimension, vector_synced, vector_synced_at, created_at, updated_at,
                    last_accessed_at, access_count)
                   SELECT 'card_' || lower(hex(randomblob(12))), ?, user_id, character_id, conversation_id,
                    scope, card_type, title, content, summary, importance, confidence, stability, status,
                    is_pinned, source_turn_ids_json, evidence_text, supersedes_card_id, NULL, NULL, 0, NULL,
                    datetime('now', 'localtime'), datetime('now', 'localtime'), NULL, access_count
                   FROM memory_cards
                   WHERE library_id = ? AND status != 'deleted'""",
                (library_id, source_library_id),
            )
        await db.commit()
    return library_id


async def update_memory_library(db_path: str, library_id: str, name: str, description: str = "") -> bool:
    await init_cards_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """UPDATE memory_libraries
               SET name = ?, description = ?, updated_at = datetime('now', 'localtime')
               WHERE library_id = ?""",
            (name, description, library_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_memory_library(db_path: str, library_id: str) -> bool:
    if library_id == DEFAULT_MEMORY_LIBRARY_ID:
        return False
    await init_cards_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """UPDATE memory_libraries
               SET status = 'deleted', updated_at = datetime('now', 'localtime')
               WHERE library_id = ? AND is_builtin = 0""",
            (library_id,),
        )
        await db.execute(
            "UPDATE conversation_memory_mounts SET status = 'deleted', updated_at = datetime('now', 'localtime') WHERE library_id = ?",
            (library_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_conversation_mounts(db_path: str, conversation_id: str) -> list[dict]:
    await init_cards_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT m.*, l.name, l.description, l.is_builtin
               FROM conversation_memory_mounts m
               JOIN memory_libraries l ON l.library_id = m.library_id
               WHERE m.conversation_id = ? AND m.status = 'active' AND l.status = 'active'
               ORDER BY m.is_write_target DESC, m.sort_order ASC, m.created_at ASC""",
            (conversation_id,),
        )
        rows = [dict(row) for row in await cursor.fetchall()]
    if not rows:
        await set_conversation_mounts(db_path, conversation_id, [DEFAULT_MEMORY_LIBRARY_ID])
        return await get_conversation_mounts(db_path, conversation_id)
    return rows


async def get_mounted_library_ids(db_path: str, conversation_id: str) -> list[str]:
    mounts = await get_conversation_mounts(db_path, conversation_id)
    return [mount["library_id"] for mount in mounts]


async def get_write_library_id(db_path: str, conversation_id: str) -> str:
    mounts = await get_conversation_mounts(db_path, conversation_id)
    for mount in mounts:
        if mount.get("is_write_target"):
            return mount["library_id"]
    return mounts[0]["library_id"] if mounts else DEFAULT_MEMORY_LIBRARY_ID


async def set_conversation_mounts(
    db_path: str,
    conversation_id: str,
    library_ids: list[str],
    write_library_id: str | None = None,
    user_id: str | None = None,
    character_id: str | None = None,
) -> None:
    await init_cards_db(db_path)
    library_ids = [library_id for library_id in dict.fromkeys(library_ids) if library_id]
    if not library_ids:
        library_ids = [DEFAULT_MEMORY_LIBRARY_ID]
    write_library_id = write_library_id if write_library_id in library_ids else library_ids[0]
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE conversation_memory_mounts SET status = 'deleted', updated_at = datetime('now', 'localtime') WHERE conversation_id = ?",
            (conversation_id,),
        )
        for index, library_id in enumerate(library_ids):
            await db.execute(
                """INSERT INTO conversation_memory_mounts
                   (mount_id, conversation_id, library_id, user_id, character_id, is_write_target, sort_order, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                   ON CONFLICT(conversation_id, library_id) WHERE status = 'active' DO UPDATE SET
                    is_write_target = excluded.is_write_target,
                    sort_order = excluded.sort_order,
                    status = 'active',
                    updated_at = datetime('now', 'localtime')""",
                (
                    generate_id("mount_"), conversation_id, library_id, user_id, character_id,
                    1 if library_id == write_library_id else 0, index,
                ),
            )
        await db.commit()


# --- 记忆卡片 CRUD ---

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
    library_id: str | None = None,
) -> None:
    library_id = library_id or DEFAULT_MEMORY_LIBRARY_ID
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT OR IGNORE INTO memory_cards
               (card_id, library_id, user_id, character_id, conversation_id, scope, card_type,
                title, content, summary, importance, confidence, status, is_pinned,
                evidence_text, supersedes_card_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (card_id, library_id, user_id, character_id, conversation_id, scope, card_type,
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


async def get_pinned_cards(
    db_path: str,
    user_id: str,
    character_id: str | None,
    library_ids: list[str] | None = None,
) -> list[dict]:
    """Get pinned/boundary cards for retrieval."""
    library_ids = library_ids or [DEFAULT_MEMORY_LIBRARY_ID]
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" for _ in library_ids)
        query = """SELECT * FROM memory_cards
                   WHERE status = 'approved' AND user_id = ?
                   AND (is_pinned = 1 OR card_type = 'boundary')"""
        query += f" AND library_id IN ({placeholders})"
        params: list = [user_id, *library_ids]
        if character_id:
            query += " AND (character_id = ? OR character_id IS NULL)"
            params.append(character_id)
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_recent_important_cards(
    db_path: str,
    user_id: str,
    character_id: str | None,
    days: int = 7,
    min_importance: float = 0.75,
    limit: int = 6,
    library_ids: list[str] | None = None,
) -> list[dict]:
    """Get recently created important approved cards."""
    library_ids = library_ids or [DEFAULT_MEMORY_LIBRARY_ID]
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" for _ in library_ids)
        query = """SELECT * FROM memory_cards
                   WHERE status = 'approved' AND user_id = ?
                   AND importance >= ?
                   AND created_at >= datetime('now', 'localtime', ?)"""
        query += f" AND library_id IN ({placeholders})"
        params: list = [user_id, min_importance, f"-{days} days", *library_ids]
        if character_id:
            query += " AND (character_id = ? OR character_id IS NULL)"
            params.append(character_id)
        query += " ORDER BY importance DESC, created_at DESC LIMIT ?"
        params.append(limit)
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# --- 待审核条目 CRUD ---

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
    library_id: str | None = None,
) -> None:
    library_id = library_id or DEFAULT_MEMORY_LIBRARY_ID
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO memory_inbox
               (inbox_id, library_id, candidate_type, payload_json, user_id, character_id, conversation_id,
                suggested_action, risk_level, reason, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (inbox_id, library_id, candidate_type, payload_json, user_id, character_id, conversation_id,
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


async def transition_inbox_status(
    db_path: str,
    inbox_id: str,
    from_status: str,
    to_status: str,
    review_note: str | None = None,
) -> bool:
    """Atomically move an inbox item between statuses if it is still in from_status."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """UPDATE memory_inbox
               SET status = ?, reviewed_at = datetime('now', 'localtime'), review_note = ?
               WHERE inbox_id = ? AND status = ?""",
            (to_status, review_note, inbox_id, from_status),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_inbox_item(db_path: str, inbox_id: str) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM memory_inbox WHERE inbox_id = ?", (inbox_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


# --- 复制挂载 ---

async def copy_conversation_mounts(db_path: str, source_conversation_id: str, target_conversation_id: str) -> int:
    """Copy memory mount configuration from one conversation to another. Returns count copied."""
    await init_cards_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM conversation_memory_mounts
               WHERE conversation_id = ? AND status = 'active'
               ORDER BY sort_order ASC""",
            (source_conversation_id,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return 0
        # 清理目标的现有挂载
        await db.execute(
            "UPDATE conversation_memory_mounts SET status = 'deleted', updated_at = datetime('now', 'localtime') WHERE conversation_id = ?",
            (target_conversation_id,),
        )
        for row in rows:
            await db.execute(
                """INSERT INTO conversation_memory_mounts
                   (mount_id, conversation_id, library_id, user_id, character_id, is_write_target, sort_order, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                   ON CONFLICT(conversation_id, library_id) WHERE status = 'active' DO UPDATE SET
                    is_write_target = excluded.is_write_target,
                    sort_order = excluded.sort_order,
                    status = 'active',
                    updated_at = datetime('now', 'localtime')""",
                (
                    generate_id("mount_"), target_conversation_id, row["library_id"],
                    row["user_id"], row["character_id"], row["is_write_target"], row["sort_order"],
                ),
            )
        await db.commit()
    return len(rows)


async def update_conversation_character_refs(db_path: str, conversation_id: str, character_id: str | None) -> dict[str, int]:
    """Update character references tied to one conversation in memory-related tables."""
    await init_cards_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        mounts = await db.execute(
            "UPDATE conversation_memory_mounts SET character_id = ?, updated_at = datetime('now', 'localtime') WHERE conversation_id = ?",
            (character_id, conversation_id),
        )
        cards = await db.execute(
            "UPDATE memory_cards SET character_id = ?, updated_at = datetime('now', 'localtime') WHERE conversation_id = ?",
            (character_id, conversation_id),
        )
        inbox = await db.execute(
            "UPDATE memory_inbox SET character_id = ?, updated_at = datetime('now', 'localtime') WHERE conversation_id = ?",
            (character_id, conversation_id),
        )
        await db.commit()
        return {"mounts": mounts.rowcount, "cards": cards.rowcount, "inbox": inbox.rowcount}


# --- 记忆挂载预设 ---

async def list_mount_presets(db_path: str, include_deleted: bool = False) -> list[dict]:
    await init_cards_db(db_path)
    where = "" if include_deleted else "WHERE status = 'active'"
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"SELECT * FROM memory_mount_presets {where} ORDER BY updated_at DESC"
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_mount_preset(db_path: str, preset_id: str) -> dict | None:
    await init_cards_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM memory_mount_presets WHERE preset_id = ?", (preset_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_mount_preset(
    db_path: str,
    name: str,
    library_ids: list[str],
    write_library_id: str,
    description: str = "",
    preset_id: str | None = None,
) -> str:
    await init_cards_db(db_path)
    preset_id = preset_id or generate_id("preset_")
    library_ids_json = json.dumps(library_ids, ensure_ascii=False)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO memory_mount_presets
               (preset_id, name, description, library_ids_json, write_library_id, status)
               VALUES (?, ?, ?, ?, ?, 'active')
               ON CONFLICT(preset_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                library_ids_json = excluded.library_ids_json,
                write_library_id = excluded.write_library_id,
                status = 'active',
                updated_at = datetime('now', 'localtime')""",
            (preset_id, name, description, library_ids_json, write_library_id),
        )
        await db.commit()
    return preset_id


async def update_mount_preset(
    db_path: str,
    preset_id: str,
    name: str | None = None,
    description: str | None = None,
    library_ids: list[str] | None = None,
    write_library_id: str | None = None,
) -> bool:
    await init_cards_db(db_path)
    fields: list[str] = []
    params: list = []
    if name is not None:
        fields.append("name = ?")
        params.append(name)
    if description is not None:
        fields.append("description = ?")
        params.append(description)
    if library_ids is not None:
        fields.append("library_ids_json = ?")
        params.append(json.dumps(library_ids, ensure_ascii=False))
    if write_library_id is not None:
        fields.append("write_library_id = ?")
        params.append(write_library_id)
    if not fields:
        return False
    fields.append("updated_at = datetime('now', 'localtime')")
    params.append(preset_id)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            f"UPDATE memory_mount_presets SET {', '.join(fields)} WHERE preset_id = ?",
            params,
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_mount_preset(db_path: str, preset_id: str) -> bool:
    await init_cards_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """UPDATE memory_mount_presets
               SET status = 'deleted', updated_at = datetime('now', 'localtime')
               WHERE preset_id = ?""",
            (preset_id,),
        )
        await db.commit()
        return cursor.rowcount > 0
