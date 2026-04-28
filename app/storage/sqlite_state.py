"""SQLite storage for conversation hot-state and retrieval gate decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from app.core.ids import generate_id
from app.memory.state_schema import (
    ConversationStateItem,
    StateBoardField,
    StateBoardTab,
    StateBoardTemplate,
)


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
  template_id TEXT,
  tab_id TEXT,
  field_id TEXT,
  field_key TEXT,
  category TEXT NOT NULL,
  item_key TEXT,
  title TEXT,
  content TEXT NOT NULL,
  item_value TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  priority INTEGER NOT NULL DEFAULT 50,
  user_locked INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS state_board_templates (
  template_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  is_builtin INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS state_board_tabs (
  tab_id TEXT PRIMARY KEY,
  template_id TEXT NOT NULL,
  tab_key TEXT NOT NULL,
  label TEXT NOT NULL,
  description TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  FOREIGN KEY(template_id) REFERENCES state_board_templates(template_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_state_tabs_key
ON state_board_tabs(template_id, tab_key);

CREATE TABLE IF NOT EXISTS state_board_fields (
  field_id TEXT PRIMARY KEY,
  template_id TEXT NOT NULL,
  tab_id TEXT NOT NULL,
  field_key TEXT NOT NULL,
  label TEXT NOT NULL,
  field_type TEXT NOT NULL DEFAULT 'multiline',
  description TEXT,
  ai_writable INTEGER NOT NULL DEFAULT 1,
  include_in_prompt INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  default_value TEXT,
  options_json TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  FOREIGN KEY(template_id) REFERENCES state_board_templates(template_id),
  FOREIGN KEY(tab_id) REFERENCES state_board_tabs(tab_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_state_fields_key
ON state_board_fields(template_id, field_key);

CREATE TABLE IF NOT EXISTS conversation_state_boards (
  conversation_id TEXT PRIMARY KEY,
  template_id TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  FOREIGN KEY(template_id) REFERENCES state_board_templates(template_id)
);

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
    "template_id": "TEXT",
    "tab_id": "TEXT",
    "field_id": "TEXT",
    "field_key": "TEXT",
    "item_key": "TEXT",
    "item_value": "TEXT",
    "source_turn_ids_json": "TEXT",
    "source_message_ids_json": "TEXT",
    "linked_card_ids_json": "TEXT",
    "linked_summary_ids_json": "TEXT",
    "created_by": "TEXT NOT NULL DEFAULT 'state_updater'",
    "user_locked": "INTEGER NOT NULL DEFAULT 0",
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
        await _ensure_state_indexes(db)
        await db.execute(
            "UPDATE conversation_state_items SET item_value = content WHERE item_value IS NULL"
        )
        await _ensure_builtin_templates(db)
        await db.commit()


async def _ensure_columns(db: aiosqlite.Connection, table: str, columns: dict[str, str]) -> None:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in await cursor.fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


async def _ensure_state_indexes(db: aiosqlite.Connection) -> None:
    await db.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_state_items_unique_field
           ON conversation_state_items(conversation_id, field_id)
           WHERE status = 'active' AND field_id IS NOT NULL"""
    )


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


BUILTIN_STATE_TEMPLATES = [
    {
        "template_id": "tpl_roleplay_general",
        "name": "通用角色扮演",
        "description": "适合日常 RP、陪伴聊天和角色互动的多标签状态板。",
        "tabs": [
            {
                "tab_key": "interaction",
                "label": "互动状态",
                "description": "记录当前称呼、语气、关系和短期互动目标。",
                "fields": [
                    ("user_addressing", "用户称呼", "当前应如何称呼用户。"),
                    ("character_addressing", "角色对用户称呼", "角色正在使用或被要求使用的称呼。"),
                    ("current_mood", "当前心情状态", "角色或对话的即时情绪氛围。"),
                    ("current_task", "当前任务", "本轮对话正在推进的短期目标。"),
                    ("roleplay_persona", "角色扮演身份", "用户要求角色保持的身份、物种、职业或扮演设定。"),
                    ("speech_habit", "口癖", "角色当前需要保持的口癖或表达习惯。"),
                    ("relationship_state", "关系状态", "用户与角色关系的当前阶段。"),
                ],
            },
            {
                "tab_key": "constraints",
                "label": "偏好边界",
                "description": "记录需要在当前会话持续遵守的偏好与边界。",
                "fields": [
                    ("user_preference", "用户偏好", "用户在当前互动中明确表达的偏好。"),
                    ("stable_boundary", "稳定边界", "不能违反的长期或会话内边界。"),
                    ("unfinished_promise", "未完成承诺", "角色或系统已经承诺但尚未完成的事。"),
                ],
            },
            {
                "tab_key": "scene",
                "label": "场景",
                "description": "当前地点、时间、事件和近期摘要。",
                "fields": [
                    ("current_scene", "当前场景", "当前对话或剧情所在场景。"),
                    ("current_location", "当前地点", "明确的地点或空间。"),
                    ("recent_summary", "近期摘要", "最近几轮对话的简短连续性摘要。"),
                ],
            },
        ],
    },
    {
        "template_id": "tpl_trpg_story",
        "name": "跑团 / 剧情推进",
        "description": "适合跑团、长篇剧情和多角色叙事的状态板。",
        "tabs": [
            {
                "tab_key": "cast",
                "label": "角色",
                "description": "主角、配角、NPC 与阵营关系。",
                "fields": [
                    ("protagonist", "主角", "当前主角及关键状态。"),
                    ("supporting_characters", "配角", "重要配角及当前状态。"),
                    ("npcs", "NPC", "已登场或即将影响剧情的 NPC。"),
                    ("faction_relations", "阵营关系", "组织、阵营、家族等关系变化。"),
                ],
            },
            {
                "tab_key": "quests",
                "label": "任务",
                "description": "主线、支线、线索和未解决伏笔。",
                "fields": [
                    ("main_quest", "当前主线任务", "当前最重要的剧情目标。"),
                    ("side_quests", "支线任务", "可选或并行推进的任务。"),
                    ("open_clues", "未解决线索", "已经出现但尚未解释或解决的线索。"),
                    ("open_loops", "未解决伏笔", "后续需要回收的剧情伏笔。"),
                ],
            },
            {
                "tab_key": "world",
                "label": "世界",
                "description": "地点、物品和世界状态。",
                "fields": [
                    ("current_location", "当前地点", "角色当前所在地点。"),
                    ("important_items", "重要物品", "关键道具、证据或资源。"),
                    ("world_state", "世界状态", "世界规则、局势或环境变化。"),
                    ("recent_summary", "近期摘要", "当前剧情的简短摘要。"),
                ],
            },
        ],
    },
]


async def _ensure_builtin_templates(db: aiosqlite.Connection) -> None:
    for template in BUILTIN_STATE_TEMPLATES:
        await db.execute(
            """INSERT INTO state_board_templates (template_id, name, description, is_builtin, status)
               VALUES (?, ?, ?, 1, 'active')
               ON CONFLICT(template_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                is_builtin = 1,
                status = 'active',
                updated_at = datetime('now', 'localtime')""",
            (template["template_id"], template["name"], template["description"]),
        )
        for tab_index, tab in enumerate(template["tabs"]):
            tab_id = f"{template['template_id']}__{tab['tab_key']}"
            await db.execute(
                """INSERT INTO state_board_tabs (tab_id, template_id, tab_key, label, description, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(tab_id) DO UPDATE SET
                    label = excluded.label,
                    description = excluded.description,
                    sort_order = excluded.sort_order,
                    updated_at = datetime('now', 'localtime')""",
                (tab_id, template["template_id"], tab["tab_key"], tab["label"], tab["description"], tab_index),
            )
            for field_index, (field_key, label, description) in enumerate(tab["fields"]):
                field_id = f"{template['template_id']}__{field_key}"
                await db.execute(
                    """INSERT INTO state_board_fields
                       (field_id, template_id, tab_id, field_key, label, description, sort_order, ai_writable, include_in_prompt, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, 'active')
                       ON CONFLICT(field_id) DO UPDATE SET
                        tab_id = excluded.tab_id,
                        label = excluded.label,
                        description = excluded.description,
                        sort_order = excluded.sort_order,
                        updated_at = datetime('now', 'localtime')""",
                    (field_id, template["template_id"], tab_id, field_key, label, description, field_index),
                )
def _row_to_item(row: aiosqlite.Row) -> ConversationStateItem:
    return ConversationStateItem(
        item_id=row["item_id"],
        conversation_id=row["conversation_id"],
        template_id=row["template_id"],
        tab_id=row["tab_id"],
        field_id=row["field_id"],
        field_key=row["field_key"],
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
        user_locked=bool(row["user_locked"]),
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


def _row_to_field(row: aiosqlite.Row) -> StateBoardField:
    return StateBoardField(
        field_id=row["field_id"],
        template_id=row["template_id"],
        tab_id=row["tab_id"],
        field_key=row["field_key"],
        label=row["label"],
        field_type=row["field_type"],
        description=row["description"] or "",
        ai_writable=bool(row["ai_writable"]),
        include_in_prompt=bool(row["include_in_prompt"]),
        sort_order=int(row["sort_order"]),
        default_value=row["default_value"] or "",
        options=_json_loads(row["options_json"], {}),
        status=row["status"],
    )


def _row_to_tab(row: aiosqlite.Row) -> StateBoardTab:
    return StateBoardTab(
        tab_id=row["tab_id"],
        template_id=row["template_id"],
        tab_key=row["tab_key"],
        label=row["label"],
        description=row["description"] or "",
        sort_order=int(row["sort_order"]),
    )


def _row_to_template(row: aiosqlite.Row) -> StateBoardTemplate:
    return StateBoardTemplate(
        template_id=row["template_id"],
        name=row["name"],
        description=row["description"] or "",
        is_builtin=bool(row["is_builtin"]),
        status=row["status"],
    )


class SQLiteStateStore:
    """Small async repository for conversation hot-state."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_schema(self) -> None:
        await init_state_db(self.db_path)

    async def list_templates(self, include_inactive: bool = False) -> list[StateBoardTemplate]:
        await self.init_schema()
        where = "" if include_inactive else "WHERE status = 'active'"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM state_board_templates {where} ORDER BY is_builtin DESC, name ASC"
            )
            return [_row_to_template(row) for row in await cursor.fetchall()]

    async def get_template(self, template_id: str) -> StateBoardTemplate | None:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM state_board_templates WHERE template_id = ?", (template_id,))
            template_row = await cursor.fetchone()
            if not template_row:
                return None
            template = _row_to_template(template_row)
            tabs_cursor = await db.execute(
                "SELECT * FROM state_board_tabs WHERE template_id = ? ORDER BY sort_order ASC, label ASC",
                (template_id,),
            )
            tabs = [_row_to_tab(row) for row in await tabs_cursor.fetchall()]
            fields_cursor = await db.execute(
                "SELECT * FROM state_board_fields WHERE template_id = ? AND status = 'active' ORDER BY sort_order ASC, label ASC",
                (template_id,),
            )
            fields_by_tab: dict[str, list[StateBoardField]] = {}
            for row in await fields_cursor.fetchall():
                field = _row_to_field(row)
                fields_by_tab.setdefault(field.tab_id, []).append(field)
            for tab in tabs:
                tab.fields = fields_by_tab.get(tab.tab_id or "", [])
            template.tabs = tabs
            return template

    async def get_conversation_template(self, conversation_id: str) -> StateBoardTemplate | None:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT template_id FROM conversation_state_boards WHERE conversation_id = ?",
                (conversation_id,),
            )
            row = await cursor.fetchone()
        template_id = row[0] if row else "tpl_roleplay_general"
        return await self.get_template(template_id)

    async def set_conversation_template(self, conversation_id: str, template_id: str) -> None:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO conversation_state_boards (conversation_id, template_id)
                   VALUES (?, ?)
                   ON CONFLICT(conversation_id) DO UPDATE SET
                    template_id = excluded.template_id,
                    updated_at = datetime('now', 'localtime')""",
                (conversation_id, template_id),
            )
            await db.commit()

    async def save_template(self, template: StateBoardTemplate) -> str:
        await self.init_schema()
        template_id = template.template_id or generate_id("tpl_")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO state_board_templates (template_id, name, description, is_builtin, status)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(template_id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    status = excluded.status,
                    updated_at = datetime('now', 'localtime')""",
                (template_id, template.name, template.description, 1 if template.is_builtin else 0, template.status),
            )
            for tab_index, tab in enumerate(template.tabs):
                tab_id = tab.tab_id or generate_id("tab_")
                tab.tab_id = tab_id
                await db.execute(
                    """INSERT INTO state_board_tabs (tab_id, template_id, tab_key, label, description, sort_order)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(tab_id) DO UPDATE SET
                        tab_key = excluded.tab_key,
                        label = excluded.label,
                        description = excluded.description,
                        sort_order = excluded.sort_order,
                        updated_at = datetime('now', 'localtime')""",
                    (tab_id, template_id, tab.tab_key, tab.label, tab.description, tab.sort_order or tab_index),
                )
                for field_index, field in enumerate(tab.fields):
                    field_id = field.field_id or generate_id("field_")
                    field.field_id = field_id
                    await db.execute(
                        """INSERT INTO state_board_fields
                           (field_id, template_id, tab_id, field_key, label, field_type, description,
                            ai_writable, include_in_prompt, sort_order, default_value, options_json, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(field_id) DO UPDATE SET
                            tab_id = excluded.tab_id,
                            field_key = excluded.field_key,
                            label = excluded.label,
                            field_type = excluded.field_type,
                            description = excluded.description,
                            ai_writable = excluded.ai_writable,
                            include_in_prompt = excluded.include_in_prompt,
                            sort_order = excluded.sort_order,
                            default_value = excluded.default_value,
                            options_json = excluded.options_json,
                            status = excluded.status,
                            updated_at = datetime('now', 'localtime')""",
                        (
                            field_id, template_id, tab_id, field.field_key, field.label, field.field_type,
                            field.description, 1 if field.ai_writable else 0,
                            1 if field.include_in_prompt else 0, field.sort_order or field_index,
                            field.default_value, json.dumps(field.options or {}, ensure_ascii=False), field.status,
                        ),
                    )
            await db.commit()
        return template_id

    async def update_template_status(self, template_id: str, status: str) -> bool:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """UPDATE state_board_templates
                   SET status = ?, updated_at = datetime('now', 'localtime')
                   WHERE template_id = ? AND is_builtin = 0""",
                (status, template_id),
            )
            await db.commit()
            return cursor.rowcount > 0

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
            if item.field_id:
                cursor = await db.execute(
                    """SELECT item_id, content FROM conversation_state_items
                       WHERE conversation_id = ? AND field_id = ? AND status = 'active'""",
                    (item.conversation_id, item.field_id),
                )
            else:
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
                   (item_id, user_id, character_id, conversation_id, world_id, template_id, tab_id,
                    field_id, field_key, category, item_key, title, content, item_value, status,
                    priority, user_locked, confidence, source, source_turn_id,
                    source_turn_ids_json, source_message_ids_json, linked_card_ids_json,
                    linked_summary_ids_json, ttl_turns, metadata_json, last_seen_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?)
                   ON CONFLICT(item_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    character_id = excluded.character_id,
                    conversation_id = excluded.conversation_id,
                    world_id = excluded.world_id,
                    template_id = excluded.template_id,
                    tab_id = excluded.tab_id,
                    field_id = excluded.field_id,
                    field_key = excluded.field_key,
                    category = excluded.category,
                    item_key = excluded.item_key,
                    title = excluded.title,
                    content = excluded.content,
                    item_value = excluded.item_value,
                    status = excluded.status,
                    priority = excluded.priority,
                    user_locked = excluded.user_locked,
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
                    item.template_id,
                    item.tab_id,
                    item.field_id,
                    item.field_key,
                    item.category,
                    item_key,
                    item.title,
                    item.content,
                    item.content,
                    item.status,
                    item.priority,
                    1 if item.user_locked else 0,
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
            "template_id", "tab_id", "field_id", "field_key", "category", "item_key",
            "title", "content", "item_value", "status", "priority", "user_locked",
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

    async def clear_conversation_state_items(self, conversation_id: str) -> int:
        """Soft-delete all active state items for a conversation. Returns count of items cleared."""
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """UPDATE conversation_state_items
                   SET status = 'cleared', updated_at = datetime('now', 'localtime')
                   WHERE conversation_id = ? AND status = 'active'""",
                (conversation_id,),
            )
            cleared = cursor.rowcount
            if cleared > 0:
                await db.execute(
                    """INSERT INTO conversation_state_events
                       (event_id, conversation_id, item_id, event_type, payload_json)
                       VALUES (?, ?, NULL, 'batch_clear', ?)""",
                    (
                        generate_id("state_evt_"),
                        conversation_id,
                        json.dumps({"cleared_count": cleared}, ensure_ascii=False),
                    ),
                )
            await db.commit()
        return cleared

    async def copy_state_items(self, source_conversation_id: str, target_conversation_id: str) -> int:
        """Copy all active state items from one conversation to another. Returns count copied."""
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT * FROM conversation_state_items
                   WHERE conversation_id = ? AND status = 'active'""",
                (source_conversation_id,),
            )
            rows = await cursor.fetchall()
            if not rows:
                return 0
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM conversation_state_items
                   WHERE conversation_id = ? AND status = 'active'""",
                (source_conversation_id,),
            )
            rows = await cursor.fetchall()
            count = 0
            for row in rows:
                new_item_id = generate_id("state_")
                await db.execute(
                    """INSERT INTO conversation_state_items
                       (item_id, user_id, character_id, conversation_id, world_id, template_id, tab_id,
                        field_id, field_key, category, item_key, title, content, item_value, status,
                        priority, user_locked, confidence, source, source_turn_id,
                        source_turn_ids_json, source_message_ids_json, linked_card_ids_json,
                        linked_summary_ids_json, ttl_turns, metadata_json, created_by,
                        last_seen_at, expires_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?)""",
                    (
                        new_item_id,
                        row["user_id"],
                        row["character_id"],
                        target_conversation_id,
                        row["world_id"],
                        row["template_id"],
                        row["tab_id"],
                        row["field_id"],
                        row["field_key"],
                        row["category"],
                        row["item_key"],
                        row["title"],
                        row["content"],
                        row["item_value"] or row["content"],
                        "active",
                        row["priority"],
                        row["user_locked"],
                        row["confidence"],
                        "copied",
                        row["source_turn_id"],
                        row["source_turn_ids_json"],
                        row["source_message_ids_json"],
                        row["linked_card_ids_json"],
                        row["linked_summary_ids_json"],
                        row["ttl_turns"],
                        row["metadata_json"],
                        row["created_by"],
                        row["expires_at"],
                    ),
                )
                count += 1

            # Copy the template binding
            template_cursor = await db.execute(
                "SELECT template_id FROM conversation_state_boards WHERE conversation_id = ?",
                (source_conversation_id,),
            )
            template_row = await template_cursor.fetchone()
            if template_row:
                await db.execute(
                    """INSERT INTO conversation_state_boards (conversation_id, template_id)
                       VALUES (?, ?)
                       ON CONFLICT(conversation_id) DO UPDATE SET
                        template_id = excluded.template_id,
                        updated_at = datetime('now', 'localtime')""",
                    (target_conversation_id, template_row[0]),
                )

            await db.execute(
                """INSERT INTO conversation_state_events
                   (event_id, conversation_id, item_id, event_type, payload_json)
                   VALUES (?, ?, NULL, 'batch_copy', ?)""",
                (
                    generate_id("state_evt_"),
                    target_conversation_id,
                    json.dumps({"source": source_conversation_id, "copied_count": count}, ensure_ascii=False),
                ),
            )
            await db.commit()
        return count

    async def reset_to_template_empty(self, conversation_id: str) -> int:
        """Clear all state items but keep the template binding. Returns count cleared."""
        return await self.clear_conversation_state_items(conversation_id)

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
