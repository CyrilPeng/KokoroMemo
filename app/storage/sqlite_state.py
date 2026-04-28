"""SQLite storage for conversation hot-state and retrieval gate decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from app.core.ids import generate_id
from app.memory.state_schema import ConversationStateItem


_STATE_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS conversation_state_items (
  item_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  user_id TEXT,
  character_id TEXT,
  category TEXT NOT NULL,
  title TEXT,
  content TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0.7,
  source TEXT NOT NULL DEFAULT 'manual',
  status TEXT NOT NULL DEFAULT 'active',
  priority INTEGER NOT NULL DEFAULT 0,
  ttl_turns INTEGER,
  source_turn_id TEXT,
  metadata_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  last_seen_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_state_items_conversation
ON conversation_state_items(conversation_id, status, category);

CREATE INDEX IF NOT EXISTS idx_state_items_updated
ON conversation_state_items(conversation_id, updated_at);

CREATE TABLE IF NOT EXISTS conversation_state_events (
  event_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  item_id TEXT,
  event_type TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  FOREIGN KEY(item_id) REFERENCES conversation_state_items(item_id)
);

CREATE INDEX IF NOT EXISTS idx_state_events_conversation
ON conversation_state_events(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS retrieval_decisions (
  decision_id TEXT PRIMARY KEY,
  request_id TEXT,
  conversation_id TEXT NOT NULL,
  user_id TEXT,
  character_id TEXT,
  mode TEXT NOT NULL,
  should_retrieve INTEGER NOT NULL,
  reason TEXT NOT NULL,
  reasons_json TEXT,
  latest_user_text TEXT,
  state_item_count INTEGER NOT NULL DEFAULT 0,
  avg_state_confidence REAL,
  turn_index INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_retrieval_decisions_conversation
ON retrieval_decisions(conversation_id, created_at);
"""


async def init_state_db(db_path: str) -> None:
    """Initialize hot-state tables in memory.sqlite."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.executescript(_STATE_SCHEMA)
        await db.commit()


def _row_to_item(row: aiosqlite.Row) -> ConversationStateItem:
    metadata: dict[str, Any] = {}
    if row["metadata_json"]:
        try:
            metadata = json.loads(row["metadata_json"])
        except json.JSONDecodeError:
            metadata = {}
    return ConversationStateItem(
        item_id=row["item_id"],
        conversation_id=row["conversation_id"],
        user_id=row["user_id"],
        character_id=row["character_id"],
        category=row["category"],
        title=row["title"],
        content=row["content"],
        confidence=float(row["confidence"]),
        source=row["source"],
        status=row["status"],
        priority=int(row["priority"]),
        ttl_turns=row["ttl_turns"],
        source_turn_id=row["source_turn_id"],
        metadata=metadata,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_seen_at=row["last_seen_at"],
    )


class SQLiteStateStore:
    """Small async repository for conversation hot-state."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_schema(self) -> None:
        await init_state_db(self.db_path)

    async def list_active_items(
        self,
        conversation_id: str,
        categories: list[str] | tuple[str, ...] | None = None,
    ) -> list[ConversationStateItem]:
        await self.init_schema()
        params: list[Any] = [conversation_id]
        category_sql = ""
        if categories:
            placeholders = ",".join("?" for _ in categories)
            category_sql = f" AND category IN ({placeholders})"
            params.extend(categories)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""SELECT * FROM conversation_state_items
                    WHERE conversation_id = ? AND status = 'active'{category_sql}
                    ORDER BY priority DESC, updated_at DESC, created_at DESC""",
                params,
            )
            return [_row_to_item(row) for row in await cursor.fetchall()]

    async def upsert_item(self, item: ConversationStateItem) -> str:
        await self.init_schema()
        item_id = item.item_id or generate_id("state_")
        metadata_json = json.dumps(item.metadata or {}, ensure_ascii=False)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO conversation_state_items
                   (item_id, conversation_id, user_id, character_id, category, title, content,
                    confidence, source, status, priority, ttl_turns, source_turn_id, metadata_json,
                    last_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
                   ON CONFLICT(item_id) DO UPDATE SET
                    conversation_id = excluded.conversation_id,
                    user_id = excluded.user_id,
                    character_id = excluded.character_id,
                    category = excluded.category,
                    title = excluded.title,
                    content = excluded.content,
                    confidence = excluded.confidence,
                    source = excluded.source,
                    status = excluded.status,
                    priority = excluded.priority,
                    ttl_turns = excluded.ttl_turns,
                    source_turn_id = excluded.source_turn_id,
                    metadata_json = excluded.metadata_json,
                    updated_at = datetime('now', 'localtime'),
                    last_seen_at = datetime('now', 'localtime')""",
                (
                    item_id,
                    item.conversation_id,
                    item.user_id,
                    item.character_id,
                    item.category,
                    item.title,
                    item.content,
                    item.confidence,
                    item.source,
                    item.status,
                    item.priority,
                    item.ttl_turns,
                    item.source_turn_id,
                    metadata_json,
                ),
            )
            await db.commit()
        return item_id

    async def upsert_many(self, items: list[ConversationStateItem]) -> list[str]:
        item_ids = []
        for item in items:
            item_ids.append(await self.upsert_item(item))
        return item_ids

    async def resolve_item(self, item_id: str, reason: str | None = None) -> None:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE conversation_state_items
                   SET status = 'resolved', updated_at = datetime('now', 'localtime')
                   WHERE item_id = ?""",
                (item_id,),
            )
            cursor = await db.execute(
                "SELECT conversation_id FROM conversation_state_items WHERE item_id = ?",
                (item_id,),
            )
            row = await cursor.fetchone()
            if row:
                await db.execute(
                    """INSERT INTO conversation_state_events
                       (event_id, conversation_id, item_id, event_type, payload_json)
                       VALUES (?, ?, ?, 'resolve', ?)""",
                    (
                        generate_id("state_evt_"),
                        row[0],
                        item_id,
                        json.dumps({"reason": reason}, ensure_ascii=False),
                    ),
                )
            await db.commit()

    async def record_state_event(
        self,
        conversation_id: str,
        event_type: str,
        item_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        await self.init_schema()
        event_id = generate_id("state_evt_")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO conversation_state_events
                   (event_id, conversation_id, item_id, event_type, payload_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (event_id, conversation_id, item_id, event_type, json.dumps(payload or {}, ensure_ascii=False)),
            )
            await db.commit()
        return event_id

    async def record_retrieval_decision(
        self,
        *,
        conversation_id: str,
        mode: str,
        should_retrieve: bool,
        reason: str,
        request_id: str | None = None,
        user_id: str | None = None,
        character_id: str | None = None,
        reasons: list[str] | None = None,
        latest_user_text: str | None = None,
        state_item_count: int = 0,
        avg_state_confidence: float | None = None,
        turn_index: int | None = None,
    ) -> str:
        await self.init_schema()
        decision_id = generate_id("gate_")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO retrieval_decisions
                   (decision_id, request_id, conversation_id, user_id, character_id, mode,
                    should_retrieve, reason, reasons_json, latest_user_text,
                    state_item_count, avg_state_confidence, turn_index)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision_id,
                    request_id,
                    conversation_id,
                    user_id,
                    character_id,
                    mode,
                    1 if should_retrieve else 0,
                    reason,
                    json.dumps(reasons or [], ensure_ascii=False),
                    latest_user_text,
                    state_item_count,
                    avg_state_confidence,
                    turn_index,
                ),
            )
            await db.commit()
        return decision_id
