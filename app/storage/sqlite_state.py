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
  user_id TEXT,
  character_id TEXT,
  conversation_id TEXT NOT NULL,
  world_id TEXT,
  category TEXT NOT NULL,
  item_key TEXT,
  title TEXT,
  content TEXT NOT NULL,
  item_value TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  priority INTEGER NOT NULL DEFAULT 50,
  confidence REAL NOT NULL DEFAULT 0.8,
  source TEXT NOT NULL DEFAULT 'manual',
  source_turn_id TEXT,
  source_turn_ids_json TEXT,
  source_message_ids_json TEXT,
  linked_card_ids_json TEXT,
  linked_summary_ids_json TEXT,
  ttl_turns INTEGER,
  metadata_json TEXT,
  created_by TEXT NOT NULL DEFAULT 'state_updater',
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  last_seen_at TEXT,
  last_injected_at TEXT,
  expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_state_items_conversation
ON conversation_state_items(user_id, character_id, conversation_id, world_id, status);

CREATE INDEX IF NOT EXISTS idx_state_items_category
ON conversation_state_items(conversation_id, category, status, priority);

CREATE INDEX IF NOT EXISTS idx_state_items_updated
ON conversation_state_items(conversation_id, updated_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_state_items_unique_key
ON conversation_state_items(conversation_id, category, item_key)
WHERE status = 'active' AND item_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS conversation_state_events (
  event_id TEXT PRIMARY KEY,
  item_id TEXT,
  conversation_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT,
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
  world_id TEXT,
  mode TEXT NOT NULL DEFAULT 'auto',
  should_retrieve INTEGER NOT NULL,
  reason TEXT,
  reasons_json TEXT,
  skipped_routes_json TEXT,
  triggered_routes_json TEXT,
  latest_user_text TEXT,
  state_confidence REAL,
  state_item_count INTEGER NOT NULL DEFAULT 0,
  avg_state_confidence REAL,
  turn_index INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_retrieval_decisions_conversation
ON retrieval_decisions(conversation_id, created_at);
"""


_STATE_ITEM_COLUMNS = {
    "world_id": "TEXT",
    "item_key": "TEXT",
    "item_value": "TEXT",
    "source_turn_ids_json": "TEXT",
    "source_message_ids_json": "TEXT",
    "linked_card_ids_json": "TEXT",
    "linked_summary_ids_json": "TEXT",
    "created_by": "TEXT NOT NULL DEFAULT 'state_updater'",
    "last_injected_at": "TEXT",
    "expires_at": "TEXT",
}

_STATE_EVENT_COLUMNS = {
    "old_value": "TEXT",
    "new_value": "TEXT",
}

_RETRIEVAL_DECISION_COLUMNS = {
    "world_id": "TEXT",
    "skipped_routes_json": "TEXT",
    "triggered_routes_json": "TEXT",
    "state_confidence": "REAL",
}


async def init_state_db(db_path: str) -> None:
    """Initialize hot-state tables in memory.sqlite."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.executescript(_STATE_SCHEMA)
        await _ensure_columns(db, "conversation_state_items", _STATE_ITEM_COLUMNS)
        await _ensure_columns(db, "conversation_state_events", _STATE_EVENT_COLUMNS)
        await _ensure_columns(db, "retrieval_decisions", _RETRIEVAL_DECISION_COLUMNS)
        await db.execute(
            "UPDATE conversation_state_items SET item_value = content WHERE item_value IS NULL"
        )
        await db.commit()


async def _ensure_columns(db: aiosqlite.Connection, table: str, columns: dict[str, str]) -> None:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in await cursor.fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _row_to_item(row: aiosqlite.Row) -> ConversationStateItem:
    return ConversationStateItem(
        item_id=row["item_id"],
        conversation_id=row["conversation_id"],
        user_id=row["user_id"],
        character_id=row["character_id"],
        world_id=row["world_id"],
        category=row["category"],
        item_key=row["item_key"],
        title=row["title"],
        content=row["item_value"] or row["content"],
        confidence=float(row["confidence"]),
        source=row["source"],
        status=row["status"],
        priority=int(row["priority"]),
        ttl_turns=row["ttl_turns"],
        source_turn_id=row["source_turn_id"],
        source_turn_ids=_json_loads(row["source_turn_ids_json"], []),
        source_message_ids=_json_loads(row["source_message_ids_json"], []),
        linked_card_ids=_json_loads(row["linked_card_ids_json"], []),
        linked_summary_ids=_json_loads(row["linked_summary_ids_json"], []),
        metadata=_json_loads(row["metadata_json"], {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_seen_at=row["last_seen_at"],
        last_injected_at=row["last_injected_at"],
        expires_at=row["expires_at"],
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
                    WHERE conversation_id = ?
                      AND status = 'active'
                      AND (expires_at IS NULL OR expires_at > datetime('now', 'localtime')){category_sql}
                    ORDER BY priority DESC, updated_at DESC, created_at DESC""",
                params,
            )
            return [_row_to_item(row) for row in await cursor.fetchall()]

    async def list_items(
        self,
        conversation_id: str,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[ConversationStateItem], int]:
        await self.init_schema()
        where = ["conversation_id = ?"]
        params: list[Any] = [conversation_id]
        if status:
            where.append("status = ?")
            params.append(status)
        where_sql = " AND ".join(where)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            count_cursor = await db.execute(
                f"SELECT COUNT(*) FROM conversation_state_items WHERE {where_sql}", params
            )
            total = (await count_cursor.fetchone())[0]
            cursor = await db.execute(
                f"""SELECT * FROM conversation_state_items WHERE {where_sql}
                    ORDER BY status ASC, priority DESC, updated_at DESC LIMIT ? OFFSET ?""",
                params + [limit, offset],
            )
            return [_row_to_item(row) for row in await cursor.fetchall()], total

    async def upsert_item(self, item: ConversationStateItem) -> str:
        await self.init_schema()
        item_id = item.item_id or generate_id("state_")
        item_key = item.item_key or _derive_item_key(item)
        payload = _item_payload(item)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT item_id, content FROM conversation_state_items
                   WHERE conversation_id = ? AND category = ? AND item_key = ? AND status = 'active'""",
                (item.conversation_id, item.category, item_key),
            )
            existing = await cursor.fetchone()
            if existing:
                item_id = existing[0]
                old_value = existing[1]
                event_type = "updated"
            else:
                old_value = None
                event_type = "created"

            await db.execute(
                """INSERT INTO conversation_state_items
                   (item_id, user_id, character_id, conversation_id, world_id, category, item_key,
                    title, content, item_value, status, priority, confidence, source, source_turn_id,
                    source_turn_ids_json, source_message_ids_json, linked_card_ids_json,
                    linked_summary_ids_json, ttl_turns, metadata_json, last_seen_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?)
                   ON CONFLICT(item_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    character_id = excluded.character_id,
                    conversation_id = excluded.conversation_id,
                    world_id = excluded.world_id,
                    category = excluded.category,
                    item_key = excluded.item_key,
                    title = excluded.title,
                    content = excluded.content,
                    item_value = excluded.item_value,
                    status = excluded.status,
                    priority = excluded.priority,
                    confidence = excluded.confidence,
                    source = excluded.source,
                    source_turn_id = excluded.source_turn_id,
                    source_turn_ids_json = excluded.source_turn_ids_json,
                    source_message_ids_json = excluded.source_message_ids_json,
                    linked_card_ids_json = excluded.linked_card_ids_json,
                    linked_summary_ids_json = excluded.linked_summary_ids_json,
                    ttl_turns = excluded.ttl_turns,
                    metadata_json = excluded.metadata_json,
                    updated_at = datetime('now', 'localtime'),
                    last_seen_at = datetime('now', 'localtime'),
                    expires_at = excluded.expires_at""",
                (
                    item_id,
                    item.user_id,
                    item.character_id,
                    item.conversation_id,
                    item.world_id,
                    item.category,
                    item_key,
                    item.title,
                    item.content,
                    item.content,
                    item.status,
                    item.priority,
                    item.confidence,
                    item.source,
                    item.source_turn_id,
                    payload["source_turn_ids_json"],
                    payload["source_message_ids_json"],
                    payload["linked_card_ids_json"],
                    payload["linked_summary_ids_json"],
                    item.ttl_turns,
                    payload["metadata_json"],
                    item.expires_at,
                ),
            )
            await db.execute(
                """INSERT INTO conversation_state_events
                   (event_id, conversation_id, item_id, event_type, old_value, new_value, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    generate_id("state_evt_"),
                    item.conversation_id,
                    item_id,
                    event_type,
                    old_value,
                    item.content,
                    json.dumps({"item_key": item_key, "source": item.source}, ensure_ascii=False),
                ),
            )
            await db.commit()
        return item_id

    async def upsert_many(self, items: list[ConversationStateItem]) -> list[str]:
        item_ids = []
        for item in items:
            item_ids.append(await self.upsert_item(item))
        return item_ids

    async def update_item(self, item_id: str, updates: dict[str, Any]) -> bool:
        await self.init_schema()
        allowed = {
            "category", "item_key", "title", "content", "item_value", "status", "priority",
            "confidence", "source", "metadata_json", "expires_at", "linked_card_ids_json",
            "linked_summary_ids_json",
        }
        filtered = {key: value for key, value in updates.items() if key in allowed}
        if "content" in filtered and "item_value" not in filtered:
            filtered["item_value"] = filtered["content"]
        if not filtered:
            return False
        set_sql = ", ".join(f"{key} = ?" for key in filtered)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT conversation_id, content FROM conversation_state_items WHERE item_id = ?", (item_id,))
            row = await cursor.fetchone()
            if not row:
                return False
            await db.execute(
                f"UPDATE conversation_state_items SET {set_sql}, updated_at = datetime('now', 'localtime') WHERE item_id = ?",
                list(filtered.values()) + [item_id],
            )
            await db.execute(
                """INSERT INTO conversation_state_events
                   (event_id, conversation_id, item_id, event_type, old_value, new_value, payload_json)
                   VALUES (?, ?, ?, 'manual_edit', ?, ?, ?)""",
                (
                    generate_id("state_evt_"), row[0], item_id, row[1],
                    filtered.get("content") or filtered.get("item_value"),
                    json.dumps(filtered, ensure_ascii=False),
                ),
            )
            await db.commit()
        return True

    async def resolve_item(self, item_id: str, reason: str | None = None) -> None:
        await self.set_item_status(item_id, "resolved", reason=reason)

    async def delete_item(self, item_id: str, reason: str | None = None) -> None:
        await self.set_item_status(item_id, "deleted", reason=reason)

    async def set_item_status(self, item_id: str, status: str, reason: str | None = None) -> None:
        await self.init_schema()
        event_type = "resolved" if status == "resolved" else status
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT conversation_id, content FROM conversation_state_items WHERE item_id = ?",
                (item_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return
            await db.execute(
                """UPDATE conversation_state_items
                   SET status = ?, updated_at = datetime('now', 'localtime')
                   WHERE item_id = ?""",
                (status, item_id),
            )
            await db.execute(
                """INSERT INTO conversation_state_events
                   (event_id, conversation_id, item_id, event_type, old_value, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    generate_id("state_evt_"), row[0], item_id, event_type, row[1],
                    json.dumps({"reason": reason}, ensure_ascii=False),
                ),
            )
            await db.commit()

    async def mark_items_injected(self, item_ids: list[str]) -> None:
        if not item_ids:
            return
        await self.init_schema()
        placeholders = ",".join("?" for _ in item_ids)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE conversation_state_items SET last_injected_at = datetime('now', 'localtime') WHERE item_id IN ({placeholders})",
                item_ids,
            )
            await db.commit()

    async def record_state_event(
        self,
        conversation_id: str,
        event_type: str,
        item_id: str | None = None,
        payload: dict[str, Any] | None = None,
        old_value: str | None = None,
        new_value: str | None = None,
    ) -> str:
        await self.init_schema()
        event_id = generate_id("state_evt_")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO conversation_state_events
                   (event_id, conversation_id, item_id, event_type, old_value, new_value, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id, conversation_id, item_id, event_type, old_value, new_value,
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )
            await db.commit()
        return event_id

    async def list_state_events(
        self,
        conversation_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            count_cursor = await db.execute(
                "SELECT COUNT(*) FROM conversation_state_events WHERE conversation_id = ?",
                (conversation_id,),
            )
            total = (await count_cursor.fetchone())[0]
            cursor = await db.execute(
                """SELECT * FROM conversation_state_events WHERE conversation_id = ?
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (conversation_id, limit, offset),
            )
            return [dict(row) for row in await cursor.fetchall()], total

    async def list_retrieval_decisions(
        self,
        conversation_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            count_cursor = await db.execute(
                "SELECT COUNT(*) FROM retrieval_decisions WHERE conversation_id = ?",
                (conversation_id,),
            )
            total = (await count_cursor.fetchone())[0]
            cursor = await db.execute(
                """SELECT * FROM retrieval_decisions WHERE conversation_id = ?
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (conversation_id, limit, offset),
            )
            return [dict(row) for row in await cursor.fetchall()], total

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
        world_id: str | None = None,
        reasons: list[str] | None = None,
        skipped_routes: list[str] | None = None,
        triggered_routes: list[str] | None = None,
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
                   (decision_id, request_id, conversation_id, user_id, character_id, world_id, mode,
                    should_retrieve, reason, reasons_json, skipped_routes_json, triggered_routes_json,
                    latest_user_text, state_confidence, state_item_count, avg_state_confidence, turn_index)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision_id, request_id, conversation_id, user_id, character_id, world_id, mode,
                    1 if should_retrieve else 0, reason,
                    json.dumps(reasons or [], ensure_ascii=False),
                    json.dumps(skipped_routes or [], ensure_ascii=False),
                    json.dumps(triggered_routes or reasons or [], ensure_ascii=False),
                    latest_user_text, avg_state_confidence, state_item_count, avg_state_confidence,
                    turn_index,
                ),
            )
            await db.commit()
        return decision_id


def _derive_item_key(item: ConversationStateItem) -> str:
    base = item.title or item.content[:40]
    normalized = "_".join(base.strip().split())
    return normalized[:80] or generate_id("key_")


def _item_payload(item: ConversationStateItem) -> dict[str, str]:
    return {
        "source_turn_ids_json": json.dumps(item.source_turn_ids or [], ensure_ascii=False),
        "source_message_ids_json": json.dumps(item.source_message_ids or [], ensure_ascii=False),
        "linked_card_ids_json": json.dumps(item.linked_card_ids or [], ensure_ascii=False),
        "linked_summary_ids_json": json.dumps(item.linked_summary_ids or [], ensure_ascii=False),
        "metadata_json": json.dumps(item.metadata or {}, ensure_ascii=False),
    }
