"""SQLite storage for conversation hot-state and retrieval gate decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from app.core.ids import generate_id
from app.memory.conversation_policy import (
    ConversationConfig,
    DEFAULT_CONVERSATION_PROFILE_ID,
    get_profile,
)
from app.memory.state_schema import (
    ConversationStateItem,
    StateBoardField,
    StateBoardTab,
    StateBoardTemplate,
    StateTableCell,
    StateTableColumn,
    StateTableRow,
    StateTableSchema,
    StateTableTemplate,
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

CREATE TABLE IF NOT EXISTS conversation_configs (
  conversation_id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  template_id TEXT,
  table_template_id TEXT,
  mount_preset_id TEXT,
  memory_write_policy TEXT NOT NULL DEFAULT 'candidate',
  state_update_policy TEXT NOT NULL DEFAULT 'auto',
  injection_policy TEXT NOT NULL DEFAULT 'mixed',
  created_from_default INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS conversation_default_config (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  template_id TEXT,
  table_template_id TEXT,
  mount_preset_id TEXT,
  memory_write_policy TEXT NOT NULL DEFAULT 'candidate',
  state_update_policy TEXT NOT NULL DEFAULT 'auto',
  injection_policy TEXT NOT NULL DEFAULT 'mixed',
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
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

CREATE TABLE IF NOT EXISTS state_table_templates (
  template_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  scenario_type TEXT NOT NULL DEFAULT 'roleplay',
  is_builtin INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS state_table_schemas (
  table_id TEXT PRIMARY KEY,
  template_id TEXT NOT NULL,
  table_key TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1,
  required INTEGER NOT NULL DEFAULT 0,
  as_status INTEGER NOT NULL DEFAULT 0,
  include_in_prompt INTEGER NOT NULL DEFAULT 1,
  max_prompt_rows INTEGER NOT NULL DEFAULT 4,
  prompt_priority INTEGER NOT NULL DEFAULT 50,
  insert_rule TEXT,
  update_rule TEXT,
  delete_rule TEXT,
  resolve_rule TEXT,
  note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  FOREIGN KEY(template_id) REFERENCES state_table_templates(template_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_state_table_schemas_key
ON state_table_schemas(template_id, table_key);

CREATE TABLE IF NOT EXISTS state_table_columns (
  column_id TEXT PRIMARY KEY,
  table_id TEXT NOT NULL,
  column_key TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  value_type TEXT NOT NULL DEFAULT 'text',
  required INTEGER NOT NULL DEFAULT 0,
  sort_order INTEGER NOT NULL DEFAULT 0,
  include_in_prompt INTEGER NOT NULL DEFAULT 1,
  max_chars INTEGER NOT NULL DEFAULT 240,
  default_value TEXT,
  options_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  FOREIGN KEY(table_id) REFERENCES state_table_schemas(table_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_state_table_columns_key
ON state_table_columns(table_id, column_key);

CREATE TABLE IF NOT EXISTS state_table_rows (
  row_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  template_id TEXT NOT NULL,
  table_id TEXT NOT NULL,
  table_key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  priority INTEGER NOT NULL DEFAULT 50,
  confidence REAL NOT NULL DEFAULT 0.7,
  source TEXT NOT NULL DEFAULT 'manual',
  source_turn_id TEXT,
  source_message_ids_json TEXT,
  metadata_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  FOREIGN KEY(template_id) REFERENCES state_table_templates(template_id),
  FOREIGN KEY(table_id) REFERENCES state_table_schemas(table_id)
);

CREATE INDEX IF NOT EXISTS idx_state_table_rows_conversation
ON state_table_rows(conversation_id, template_id, table_key, status, priority);

CREATE TABLE IF NOT EXISTS state_table_cells (
  cell_id TEXT PRIMARY KEY,
  row_id TEXT NOT NULL,
  column_id TEXT,
  column_key TEXT NOT NULL,
  value TEXT,
  confidence REAL NOT NULL DEFAULT 0.7,
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  FOREIGN KEY(row_id) REFERENCES state_table_rows(row_id),
  FOREIGN KEY(column_id) REFERENCES state_table_columns(column_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_state_table_cells_key
ON state_table_cells(row_id, column_key);

CREATE TABLE IF NOT EXISTS state_table_events (
  event_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  request_id TEXT,
  turn_id TEXT,
  event_type TEXT NOT NULL,
  table_key TEXT,
  row_id TEXT,
  before_json TEXT,
  after_json TEXT,
  operation_json TEXT,
  model_output TEXT,
  reason TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_state_table_events_conversation
ON state_table_events(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS state_table_debug_runs (
  run_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  turn_id TEXT,
  mode TEXT NOT NULL DEFAULT 'manual',
  input_messages_json TEXT,
  prompt_json TEXT,
  raw_model_output TEXT,
  parsed_operations_json TEXT,
  applied_result_json TEXT,
  status TEXT NOT NULL DEFAULT 'ok',
  error TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
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
        await _ensure_default_conversation_config(db)
        await db.execute(
            "UPDATE conversation_state_items SET item_value = content WHERE item_value IS NULL"
        )
        await _ensure_builtin_templates(db)
        await _ensure_builtin_table_templates(db)
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
                    ("user_addressing", "称呼用户为", "角色称呼用户时应使用的称呼；不是角色自己的名字。"),
                    ("character_addressing", "用户称呼角色为", "用户称呼角色时使用的称呼；不是角色称呼用户的方式。"),
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


BUILTIN_STATE_TABLE_TEMPLATES = [
    {
        "template_id": "tpl_rimtalk_roleplay_tables",
        "name": "RimTalk 角色扮演表格版",
        "description": "面向连续角色扮演的结构化状态板，强调当前场景、角色状态、关系、规则、承诺、事件和物品。",
        "scenario_type": "roleplay",
        "tables": [
            {
                "table_key": "current_scene",
                "name": "当前场景",
                "description": "只记录正在发生的地点、时间、局面和下一步，不写长期设定。",
                "as_status": True,
                "max_prompt_rows": 2,
                "prompt_priority": 100,
                "columns": [
                    ("scene", "场景", "当前发生的具体场景或地点", True, 220),
                    ("time", "时间", "剧情内时间或阶段", False, 80),
                    ("focus", "焦点", "本轮互动最需要延续的行动或冲突", True, 220),
                    ("next_step", "下一步", "已经明确但尚未完成的下一步", False, 180),
                ],
            },
            {
                "table_key": "character_state",
                "name": "角色状态",
                "description": "记录角色当前身份、情绪、身体状态、口癖和短期目标。",
                "max_prompt_rows": 6,
                "prompt_priority": 90,
                "columns": [
                    ("character", "角色", "角色名或称呼", True, 80),
                    ("identity", "身份", "本会话中需要保持的角色身份", False, 160),
                    ("mood", "情绪", "当前情绪或态度", False, 120),
                    ("state", "状态", "身体/能力/处境等即时状态", False, 180),
                    ("goal", "短期目标", "角色当前想做的事", False, 180),
                    ("speech", "口癖/语气", "需要延续的表达习惯", False, 160),
                ],
            },
            {
                "table_key": "relationship_state",
                "name": "关系状态",
                "description": "记录用户与角色、角色之间的关系阶段和最近变化。",
                "max_prompt_rows": 6,
                "prompt_priority": 80,
                "columns": [
                    ("subject", "主体", "关系的一方", True, 80),
                    ("object", "对象", "关系的另一方", True, 80),
                    ("relationship", "关系", "关系阶段或称谓", True, 160),
                    ("attitude", "态度", "当前好感、信任、警惕等", False, 160),
                    ("recent_change", "最近变化", "最近一轮或事件造成的变化", False, 200),
                ],
            },
            {
                "table_key": "roleplay_rules",
                "name": "扮演规则",
                "description": "记录用户明确要求保持的扮演规则、边界、称呼和偏好。",
                "max_prompt_rows": 8,
                "prompt_priority": 95,
                "columns": [
                    ("rule", "规则", "必须遵守的扮演规则或边界", True, 240),
                    ("scope", "范围", "适用角色、场景或全局", False, 120),
                    ("source", "来源", "用户明确要求/剧情约定/系统推断", False, 120),
                ],
            },
            {
                "table_key": "promises_tasks",
                "name": "承诺与任务",
                "description": "记录尚未完成的承诺、命令、约定和短期任务。",
                "max_prompt_rows": 8,
                "prompt_priority": 75,
                "columns": [
                    ("task", "事项", "未完成事项", True, 220),
                    ("owner", "负责人", "谁承诺或需要执行", False, 80),
                    ("status", "状态", "待办/进行中/完成/取消", False, 80),
                    ("due", "时机", "触发条件或截止时机", False, 120),
                ],
            },
            {
                "table_key": "important_events",
                "name": "重要事件",
                "description": "记录影响后续对话的关键事件，不记录流水账。",
                "max_prompt_rows": 6,
                "prompt_priority": 65,
                "columns": [
                    ("event", "事件", "关键事件摘要", True, 240),
                    ("impact", "影响", "对关系、剧情或状态造成的影响", False, 220),
                    ("time", "时间", "发生时间或阶段", False, 100),
                ],
            },
            {
                "table_key": "important_items",
                "name": "重要物品",
                "description": "记录剧情中需要记住的物品、证据、资源和归属。",
                "max_prompt_rows": 6,
                "prompt_priority": 55,
                "columns": [
                    ("item", "物品", "物品或资源名称", True, 120),
                    ("owner", "持有者", "当前持有者或归属", False, 100),
                    ("state", "状态", "数量、损坏、位置等", False, 160),
                    ("meaning", "意义", "为什么重要", False, 180),
                ],
            },
        ],
    },
    {
        "template_id": "tpl_rimtalk_colony_tables",
        "name": "RimTalk 殖民地状态表",
        "description": "面向 RimWorld / RimTalk 的殖民地模拟状态板，只记录当前可变状态，默认不写入长期记忆。",
        "scenario_type": "rimtalk_colony",
        "tables": [
            {
                "table_key": "colony_overview",
                "name": "殖民地概况",
                "description": "殖民地当前阶段、地点、目标和整体风险。",
                "as_status": True,
                "max_prompt_rows": 3,
                "prompt_priority": 100,
                "columns": [
                    ("name", "殖民地", "殖民地名称或识别信息", True, 100),
                    ("stage", "阶段", "开局/扩张/危机/恢复等", False, 100),
                    ("focus", "当前重点", "当前最重要的发展方向", True, 220),
                    ("risk", "主要风险", "威胁、短缺或隐患", False, 220),
                ],
            },
            {
                "table_key": "pawn_state",
                "name": "小人状态",
                "description": "殖民者的职业、健康、心情、任务和短期处境。",
                "max_prompt_rows": 10,
                "prompt_priority": 95,
                "columns": [
                    ("pawn", "小人", "小人姓名", True, 80),
                    ("role", "职责", "主要工作或定位", False, 120),
                    ("health", "健康", "伤病、成瘾、精神状态等", False, 180),
                    ("mood", "心情", "心情、压力或社交状态", False, 160),
                    ("task", "当前任务", "正在做或下一步应做的事", False, 180),
                ],
            },
            {
                "table_key": "pawn_relationships",
                "name": "小人关系",
                "description": "小人之间的关系、冲突、恋爱、亲属和社交变化。",
                "max_prompt_rows": 8,
                "prompt_priority": 80,
                "columns": [
                    ("subject", "主体", "关系主体", True, 80),
                    ("object", "对象", "关系对象", True, 80),
                    ("relationship", "关系", "朋友/恋人/敌对/亲属等", True, 160),
                    ("change", "最近变化", "最近事件带来的关系变化", False, 200),
                ],
            },
            {
                "table_key": "resources",
                "name": "资源库存",
                "description": "关键资源的数量、短缺和用途，不记录无关流水账。",
                "max_prompt_rows": 8,
                "prompt_priority": 75,
                "columns": [
                    ("resource", "资源", "资源名称", True, 100),
                    ("amount", "数量/状态", "数量、充足/短缺等", True, 120),
                    ("trend", "趋势", "增加/消耗/紧缺", False, 100),
                    ("note", "备注", "用途或风险", False, 180),
                ],
            },
            {
                "table_key": "buildings",
                "name": "建筑与设施",
                "description": "基地建筑、设施状态、规划和损坏情况。",
                "max_prompt_rows": 8,
                "prompt_priority": 70,
                "columns": [
                    ("building", "设施", "建筑或区域", True, 120),
                    ("status", "状态", "已建/规划/损坏/缺材料", True, 140),
                    ("purpose", "用途", "功能或服务对象", False, 160),
                    ("next_step", "下一步", "维修、扩建、拆除等", False, 180),
                ],
            },
            {
                "table_key": "threats_events",
                "name": "威胁与事件",
                "description": "袭击、疾病、天气、贸易、任务等会影响后续的事件。",
                "max_prompt_rows": 8,
                "prompt_priority": 85,
                "columns": [
                    ("event", "事件", "事件或威胁", True, 220),
                    ("status", "状态", "进行中/已解决/潜在", True, 100),
                    ("impact", "影响", "对殖民地或小人的影响", False, 220),
                    ("response", "应对", "已采取或计划采取的措施", False, 220),
                ],
            },
            {
                "table_key": "factions",
                "name": "阵营关系",
                "description": "附近派系、商队、敌对势力和声望变化。",
                "max_prompt_rows": 6,
                "prompt_priority": 60,
                "columns": [
                    ("faction", "阵营", "派系或组织", True, 120),
                    ("relation", "关系", "友好/中立/敌对/未知", True, 120),
                    ("recent", "最近互动", "交易、袭击、任务等", False, 200),
                ],
            },
        ],
    },
    {
        "template_id": "tpl_ttrpg_story_tables",
        "name": "跑团剧情状态表",
        "description": "面向跑团和长线剧情的状态板，记录队伍、场景、线索、NPC、地点和剧情旗标。",
        "scenario_type": "ttrpg_story",
        "tables": [
            {
                "table_key": "party",
                "name": "队伍成员",
                "description": "玩家角色、随从和当前状态。",
                "max_prompt_rows": 8,
                "prompt_priority": 95,
                "columns": [
                    ("member", "成员", "角色名", True, 100),
                    ("role", "定位", "职业、职责或战斗定位", False, 140),
                    ("status", "状态", "生命、资源、异常、心理状态", False, 200),
                    ("goal", "当前目标", "此角色正在推进的目标", False, 180),
                ],
            },
            {
                "table_key": "current_scene",
                "name": "当前场景",
                "description": "当前地点、局势、冲突和下一步行动。",
                "as_status": True,
                "max_prompt_rows": 3,
                "prompt_priority": 100,
                "columns": [
                    ("location", "地点", "当前地点", True, 160),
                    ("situation", "局势", "正在发生什么", True, 240),
                    ("stakes", "风险/赌注", "失败或成功的影响", False, 200),
                    ("next_step", "下一步", "已明确的下一步", False, 180),
                ],
            },
            {
                "table_key": "quests_clues",
                "name": "任务与线索",
                "description": "主线、支线、线索和未解谜题。",
                "max_prompt_rows": 10,
                "prompt_priority": 90,
                "columns": [
                    ("item", "事项", "任务、线索或谜题", True, 220),
                    ("status", "状态", "未解/进行中/完成/失败", True, 100),
                    ("owner", "相关方", "相关角色或阵营", False, 140),
                    ("note", "备注", "条件、证据或限制", False, 240),
                ],
            },
            {
                "table_key": "npcs",
                "name": "重要 NPC",
                "description": "重要 NPC 的身份、动机、态度和最新变化。",
                "max_prompt_rows": 10,
                "prompt_priority": 80,
                "columns": [
                    ("npc", "NPC", "姓名或称呼", True, 100),
                    ("identity", "身份", "公开或已知身份", False, 160),
                    ("motive", "动机", "目标或诉求", False, 180),
                    ("attitude", "态度", "对队伍的态度", False, 140),
                    ("recent", "最近变化", "最近互动或状态变化", False, 200),
                ],
            },
            {
                "table_key": "locations_factions",
                "name": "地点与阵营",
                "description": "地点状态、阵营关系和势力变化。",
                "max_prompt_rows": 8,
                "prompt_priority": 70,
                "columns": [
                    ("name", "名称", "地点或阵营", True, 140),
                    ("type", "类型", "地点/阵营/组织", False, 80),
                    ("state", "状态", "当前状态或关系", True, 200),
                    ("hook", "关联钩子", "相关任务、线索或危险", False, 220),
                ],
            },
            {
                "table_key": "story_flags",
                "name": "剧情旗标",
                "description": "影响后续判定和叙事分支的关键事实。",
                "max_prompt_rows": 10,
                "prompt_priority": 85,
                "columns": [
                    ("flag", "旗标", "关键剧情事实", True, 220),
                    ("value", "状态", "开启/关闭/阶段/数值", True, 100),
                    ("impact", "影响", "对后续剧情的影响", False, 240),
                ],
            },
        ],
    },
    {
        "template_id": "tpl_roleplay_light_tables",
        "name": "轻量角色扮演表格版",
        "description": "适合日常陪伴和轻量 RP，只保留当前互动、规则、关系和近期摘要。",
        "scenario_type": "roleplay_light",
        "tables": [
            {
                "table_key": "current_interaction",
                "name": "当前互动",
                "description": "当前聊天场景和短期目标。",
                "as_status": True,
                "max_prompt_rows": 3,
                "prompt_priority": 100,
                "columns": [
                    ("topic", "话题", "当前正在聊什么", True, 180),
                    ("mood", "氛围", "当前情绪氛围", False, 120),
                    ("next_step", "下一步", "接下来应延续的动作", False, 180),
                ],
            },
            {
                "table_key": "roleplay_rules",
                "name": "互动规则",
                "description": "称呼、口癖、边界和偏好。",
                "max_prompt_rows": 6,
                "prompt_priority": 90,
                "columns": [
                    ("rule", "规则", "需要持续遵守的规则", True, 240),
                    ("scope", "范围", "适用范围", False, 120),
                ],
            },
            {
                "table_key": "relationship_state",
                "name": "关系状态",
                "description": "用户和角色的关系阶段。",
                "max_prompt_rows": 4,
                "prompt_priority": 80,
                "columns": [
                    ("subject", "主体", "关系主体", True, 80),
                    ("object", "对象", "关系对象", True, 80),
                    ("relationship", "关系", "当前关系", True, 160),
                    ("recent_change", "最近变化", "最近变化", False, 180),
                ],
            },
            {
                "table_key": "recent_summary",
                "name": "近期摘要",
                "description": "短期剧情摘要。",
                "max_prompt_rows": 3,
                "prompt_priority": 60,
                "columns": [
                    ("summary", "摘要", "最近几轮需要延续的信息", True, 260),
                    ("impact", "影响", "对下一轮的影响", False, 180),
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


async def _ensure_builtin_table_templates(db: aiosqlite.Connection) -> None:
    for template in BUILTIN_STATE_TABLE_TEMPLATES:
        await db.execute(
            """INSERT INTO state_table_templates
               (template_id, name, description, scenario_type, is_builtin, status, version)
               VALUES (?, ?, ?, ?, 1, 'active', 1)
               ON CONFLICT(template_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                scenario_type = excluded.scenario_type,
                is_builtin = 1,
                status = 'active',
                updated_at = datetime('now', 'localtime')""",
            (
                template["template_id"],
                template["name"],
                template["description"],
                template.get("scenario_type", "roleplay"),
            ),
        )
        for table_index, table in enumerate(template["tables"]):
            table_id = f"{template['template_id']}__{table['table_key']}"
            await db.execute(
                """INSERT INTO state_table_schemas
                   (table_id, template_id, table_key, name, description, sort_order,
                    enabled, required, as_status, include_in_prompt, max_prompt_rows,
                    prompt_priority, insert_rule, update_rule, delete_rule, resolve_rule, note)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(table_id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    sort_order = excluded.sort_order,
                    enabled = excluded.enabled,
                    required = excluded.required,
                    as_status = excluded.as_status,
                    include_in_prompt = excluded.include_in_prompt,
                    max_prompt_rows = excluded.max_prompt_rows,
                    prompt_priority = excluded.prompt_priority,
                    insert_rule = excluded.insert_rule,
                    update_rule = excluded.update_rule,
                    delete_rule = excluded.delete_rule,
                    resolve_rule = excluded.resolve_rule,
                    note = excluded.note,
                    updated_at = datetime('now', 'localtime')""",
                (
                    table_id,
                    template["template_id"],
                    table["table_key"],
                    table["name"],
                    table.get("description", ""),
                    table_index,
                    int(bool(table.get("required", False))),
                    int(bool(table.get("as_status", False))),
                    int(table.get("max_prompt_rows", 4)),
                    int(table.get("prompt_priority", 50)),
                    table.get("insert_rule", ""),
                    table.get("update_rule", ""),
                    table.get("delete_rule", ""),
                    table.get("resolve_rule", ""),
                    table.get("note", ""),
                ),
            )
            for column_index, column in enumerate(table["columns"]):
                column_key, name, description, required, max_chars = column
                column_id = f"{table_id}__{column_key}"
                await db.execute(
                    """INSERT INTO state_table_columns
                       (column_id, table_id, column_key, name, description, value_type,
                        required, sort_order, include_in_prompt, max_chars, default_value, options_json)
                       VALUES (?, ?, ?, ?, ?, 'text', ?, ?, 1, ?, '', '{}')
                       ON CONFLICT(column_id) DO UPDATE SET
                        name = excluded.name,
                        description = excluded.description,
                        required = excluded.required,
                        sort_order = excluded.sort_order,
                        include_in_prompt = excluded.include_in_prompt,
                        max_chars = excluded.max_chars,
                        updated_at = datetime('now', 'localtime')""",
                    (column_id, table_id, column_key, name, description, int(bool(required)), column_index, int(max_chars)),
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


async def _ensure_default_conversation_config(db: aiosqlite.Connection) -> None:
    profile = get_profile(DEFAULT_CONVERSATION_PROFILE_ID)
    await db.execute(
        """INSERT INTO conversation_default_config
           (id, profile_id, template_id, table_template_id, mount_preset_id,
            memory_write_policy, state_update_policy, injection_policy)
           VALUES ('global', ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO NOTHING""",
        (
            profile.profile_id,
            profile.template_id,
            profile.table_template_id,
            profile.mount_preset_id,
            profile.memory_write_policy,
            profile.state_update_policy,
            profile.injection_policy,
        ),
    )


def _row_to_table_column(row: aiosqlite.Row) -> StateTableColumn:
    return StateTableColumn(
        column_id=row["column_id"],
        table_id=row["table_id"],
        column_key=row["column_key"],
        name=row["name"],
        description=row["description"] or "",
        value_type=row["value_type"],
        required=bool(row["required"]),
        sort_order=int(row["sort_order"]),
        include_in_prompt=bool(row["include_in_prompt"]),
        max_chars=int(row["max_chars"]),
        default_value=row["default_value"] or "",
        options=_json_loads(row["options_json"], {}),
    )


def _row_to_table_schema(row: aiosqlite.Row) -> StateTableSchema:
    return StateTableSchema(
        table_id=row["table_id"],
        template_id=row["template_id"],
        table_key=row["table_key"],
        name=row["name"],
        description=row["description"] or "",
        sort_order=int(row["sort_order"]),
        enabled=bool(row["enabled"]),
        required=bool(row["required"]),
        as_status=bool(row["as_status"]),
        include_in_prompt=bool(row["include_in_prompt"]),
        max_prompt_rows=int(row["max_prompt_rows"]),
        prompt_priority=int(row["prompt_priority"]),
        insert_rule=row["insert_rule"] or "",
        update_rule=row["update_rule"] or "",
        delete_rule=row["delete_rule"] or "",
        resolve_rule=row["resolve_rule"] or "",
        note=row["note"] or "",
    )


def _row_to_table_template(row: aiosqlite.Row) -> StateTableTemplate:
    return StateTableTemplate(
        template_id=row["template_id"],
        name=row["name"],
        description=row["description"] or "",
        scenario_type=row["scenario_type"] or "roleplay",
        is_builtin=bool(row["is_builtin"]),
        status=row["status"],
        version=int(row["version"]),
    )


def _row_to_conversation_config(row: aiosqlite.Row) -> ConversationConfig:
    return ConversationConfig(
        conversation_id=row["conversation_id"],
        profile_id=row["profile_id"],
        template_id=row["template_id"],
        table_template_id=row["table_template_id"],
        mount_preset_id=row["mount_preset_id"],
        memory_write_policy=row["memory_write_policy"],
        state_update_policy=row["state_update_policy"],
        injection_policy=row["injection_policy"],
        created_from_default=bool(row["created_from_default"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_table_cell(row: aiosqlite.Row) -> StateTableCell:
    return StateTableCell(
        cell_id=row["cell_id"],
        row_id=row["row_id"],
        column_id=row["column_id"],
        column_key=row["column_key"],
        value=row["value"] or "",
        confidence=float(row["confidence"]),
        updated_at=row["updated_at"],
    )


def _row_to_table_row(row: aiosqlite.Row) -> StateTableRow:
    return StateTableRow(
        row_id=row["row_id"],
        conversation_id=row["conversation_id"],
        template_id=row["template_id"],
        table_id=row["table_id"],
        table_key=row["table_key"],
        status=row["status"],
        priority=int(row["priority"]),
        confidence=float(row["confidence"]),
        source=row["source"],
        source_turn_id=row["source_turn_id"],
        source_message_ids=_json_loads(row["source_message_ids_json"], []),
        metadata=_json_loads(row["metadata_json"], {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SQLiteStateStore:
    """Small async repository for conversation hot-state."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_schema(self) -> None:
        await init_state_db(self.db_path)

    async def get_default_conversation_config(self) -> ConversationConfig:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM conversation_default_config WHERE id = 'global'")
            row = await cursor.fetchone()
        if row:
            return ConversationConfig(
                conversation_id="__default__",
                profile_id=row["profile_id"],
                template_id=row["template_id"],
                table_template_id=row["table_template_id"],
                mount_preset_id=row["mount_preset_id"],
                memory_write_policy=row["memory_write_policy"],
                state_update_policy=row["state_update_policy"],
                injection_policy=row["injection_policy"],
                created_from_default=True,
                updated_at=row["updated_at"],
            )
        profile = get_profile(DEFAULT_CONVERSATION_PROFILE_ID)
        return ConversationConfig(
            conversation_id="__default__",
            profile_id=profile.profile_id,
            template_id=profile.template_id,
            table_template_id=profile.table_template_id,
            mount_preset_id=profile.mount_preset_id,
            memory_write_policy=profile.memory_write_policy,
            state_update_policy=profile.state_update_policy,
            injection_policy=profile.injection_policy,
            created_from_default=True,
        )

    async def set_default_conversation_config(self, data: ConversationConfig | dict[str, Any]) -> ConversationConfig:
        await self.init_schema()
        if isinstance(data, ConversationConfig):
            payload = data.to_dict()
        else:
            payload = dict(data)
        profile = get_profile(payload.get("profile_id"))
        profile_id = payload.get("profile_id") or profile.profile_id
        template_id = payload.get("template_id", profile.template_id)
        table_template_id = payload.get("table_template_id", profile.table_template_id)
        mount_preset_id = payload.get("mount_preset_id", profile.mount_preset_id)
        memory_write_policy = payload.get("memory_write_policy") or profile.memory_write_policy
        state_update_policy = payload.get("state_update_policy") or profile.state_update_policy
        injection_policy = payload.get("injection_policy") or profile.injection_policy
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO conversation_default_config
                   (id, profile_id, template_id, table_template_id, mount_preset_id,
                    memory_write_policy, state_update_policy, injection_policy)
                   VALUES ('global', ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    template_id = excluded.template_id,
                    table_template_id = excluded.table_template_id,
                    mount_preset_id = excluded.mount_preset_id,
                    memory_write_policy = excluded.memory_write_policy,
                    state_update_policy = excluded.state_update_policy,
                    injection_policy = excluded.injection_policy,
                    updated_at = datetime('now', 'localtime')""",
                (profile_id, template_id, table_template_id, mount_preset_id, memory_write_policy, state_update_policy, injection_policy),
            )
            await db.commit()
        return await self.get_default_conversation_config()

    async def get_conversation_config(self, conversation_id: str) -> ConversationConfig | None:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM conversation_configs WHERE conversation_id = ?", (conversation_id,))
            row = await cursor.fetchone()
        return _row_to_conversation_config(row) if row else None

    async def set_conversation_config(self, config: ConversationConfig | dict[str, Any]) -> ConversationConfig:
        await self.init_schema()
        payload = config.to_dict() if isinstance(config, ConversationConfig) else dict(config)
        conversation_id = payload.get("conversation_id")
        if not conversation_id:
            raise ValueError("conversation_id is required")
        profile = get_profile(payload.get("profile_id"))
        profile_id = payload.get("profile_id") or profile.profile_id
        template_id = payload.get("template_id", profile.template_id)
        table_template_id = payload.get("table_template_id", profile.table_template_id)
        mount_preset_id = payload.get("mount_preset_id", profile.mount_preset_id)
        memory_write_policy = payload.get("memory_write_policy") or profile.memory_write_policy
        state_update_policy = payload.get("state_update_policy") or profile.state_update_policy
        injection_policy = payload.get("injection_policy") or profile.injection_policy
        created_from_default = 1 if payload.get("created_from_default") else 0
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO conversation_configs
                   (conversation_id, profile_id, template_id, table_template_id, mount_preset_id,
                    memory_write_policy, state_update_policy, injection_policy, created_from_default)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(conversation_id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    template_id = excluded.template_id,
                    table_template_id = excluded.table_template_id,
                    mount_preset_id = excluded.mount_preset_id,
                    memory_write_policy = excluded.memory_write_policy,
                    state_update_policy = excluded.state_update_policy,
                    injection_policy = excluded.injection_policy,
                    updated_at = datetime('now', 'localtime')""",
                (
                    conversation_id,
                    profile_id,
                    template_id,
                    table_template_id,
                    mount_preset_id,
                    memory_write_policy,
                    state_update_policy,
                    injection_policy,
                    created_from_default,
                ),
            )
            if template_id:
                await db.execute(
                    """INSERT INTO conversation_state_boards (conversation_id, template_id)
                       VALUES (?, ?)
                       ON CONFLICT(conversation_id) DO UPDATE SET
                        template_id = excluded.template_id,
                        updated_at = datetime('now', 'localtime')""",
                    (conversation_id, template_id),
                )
            await db.commit()
        saved = await self.get_conversation_config(conversation_id)
        if not saved:
            raise RuntimeError("failed to save conversation config")
        return saved

    async def ensure_conversation_config(self, conversation_id: str) -> ConversationConfig:
        existing = await self.get_conversation_config(conversation_id)
        if existing:
            return existing
        default = await self.get_default_conversation_config()
        return await self.set_conversation_config(
            ConversationConfig(
                conversation_id=conversation_id,
                profile_id=default.profile_id,
                template_id=default.template_id,
                table_template_id=default.table_template_id,
                mount_preset_id=default.mount_preset_id,
                memory_write_policy=default.memory_write_policy,
                state_update_policy=default.state_update_policy,
                injection_policy=default.injection_policy,
                created_from_default=True,
            )
        )

    async def update_conversation_character_refs(self, conversation_id: str, character_id: str | None) -> dict[str, int]:
        """Update character references for state data belonging to one conversation."""
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            items = await db.execute(
                "UPDATE conversation_state_items SET character_id = ?, updated_at = datetime('now', 'localtime') WHERE conversation_id = ?",
                (character_id, conversation_id),
            )
            await db.commit()
            return {"items": items.rowcount}

    async def list_table_templates(self, include_inactive: bool = False) -> list[StateTableTemplate]:
        await self.init_schema()
        where = "" if include_inactive else "WHERE status = 'active'"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM state_table_templates {where} ORDER BY is_builtin DESC, name ASC"
            )
            return [_row_to_table_template(row) for row in await cursor.fetchall()]

    async def get_table_template(self, template_id: str) -> StateTableTemplate | None:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM state_table_templates WHERE template_id = ?", (template_id,))
            template_row = await cursor.fetchone()
            if not template_row:
                return None
            template = _row_to_table_template(template_row)
            table_cursor = await db.execute(
                """SELECT * FROM state_table_schemas
                   WHERE template_id = ? ORDER BY sort_order ASC, name ASC""",
                (template_id,),
            )
            tables = [_row_to_table_schema(row) for row in await table_cursor.fetchall()]
            for table in tables:
                column_cursor = await db.execute(
                    """SELECT * FROM state_table_columns
                       WHERE table_id = ? ORDER BY sort_order ASC, name ASC""",
                    (table.table_id,),
                )
                table.columns = [_row_to_table_column(row) for row in await column_cursor.fetchall()]
            template.tables = tables
            return template

    async def get_default_table_template(self) -> StateTableTemplate | None:
        return await self.get_table_template("tpl_rimtalk_roleplay_tables")

    async def get_conversation_table_template(self, conversation_id: str) -> StateTableTemplate | None:
        config = await self.ensure_conversation_config(conversation_id)
        if config.table_template_id:
            template = await self.get_table_template(config.table_template_id)
            if template:
                return template
        return await self.get_default_table_template()

    async def list_table_rows(
        self,
        conversation_id: str,
        template_id: str | None = None,
        table_key: str | None = None,
        status: str | None = "active",
        limit: int = 500,
    ) -> list[StateTableRow]:
        await self.init_schema()
        where = ["conversation_id = ?"]
        params: list[Any] = [conversation_id]
        if template_id:
            where.append("template_id = ?")
            params.append(template_id)
        if table_key:
            where.append("table_key = ?")
            params.append(table_key)
        if status:
            where.append("status = ?")
            params.append(status)
        where_sql = " AND ".join(where)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""SELECT * FROM state_table_rows WHERE {where_sql}
                    ORDER BY priority DESC, updated_at DESC, created_at DESC LIMIT ?""",
                params + [limit],
            )
            rows = [_row_to_table_row(row) for row in await cursor.fetchall()]
            if not rows:
                return []
            row_ids = [row.row_id for row in rows if row.row_id]
            placeholders = ",".join("?" for _ in row_ids)
            cell_cursor = await db.execute(
                f"SELECT * FROM state_table_cells WHERE row_id IN ({placeholders}) ORDER BY updated_at ASC",
                row_ids,
            )
            cells_by_row: dict[str, dict[str, StateTableCell]] = {}
            for cell_row in await cell_cursor.fetchall():
                cell = _row_to_table_cell(cell_row)
                cells_by_row.setdefault(cell.row_id, {})[cell.column_key] = cell
            for row in rows:
                row.cells = cells_by_row.get(row.row_id or "", {})
            return rows

    async def upsert_table_row(self, row: StateTableRow, values: dict[str, Any] | None = None) -> str:
        await self.init_schema()
        row_id = row.row_id or generate_id("state_row_")
        values = values or {key: cell.value for key, cell in row.cells.items()}
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO state_table_rows
                   (row_id, conversation_id, template_id, table_id, table_key, status, priority,
                    confidence, source, source_turn_id, source_message_ids_json, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(row_id) DO UPDATE SET
                    conversation_id = excluded.conversation_id,
                    template_id = excluded.template_id,
                    table_id = excluded.table_id,
                    table_key = excluded.table_key,
                    status = excluded.status,
                    priority = excluded.priority,
                    confidence = excluded.confidence,
                    source = excluded.source,
                    source_turn_id = excluded.source_turn_id,
                    source_message_ids_json = excluded.source_message_ids_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = datetime('now', 'localtime')""",
                (
                    row_id,
                    row.conversation_id,
                    row.template_id,
                    row.table_id,
                    row.table_key,
                    row.status,
                    row.priority,
                    row.confidence,
                    row.source,
                    row.source_turn_id,
                    json.dumps(row.source_message_ids, ensure_ascii=False),
                    json.dumps(row.metadata, ensure_ascii=False),
                ),
            )
            column_ids: dict[str, str | None] = {}
            cursor = await db.execute("SELECT column_key, column_id FROM state_table_columns WHERE table_id = ?", (row.table_id,))
            for column_key, column_id in await cursor.fetchall():
                column_ids[column_key] = column_id
            for column_key, value in values.items():
                cell_id = row.cells.get(column_key).cell_id if column_key in row.cells else generate_id("state_cell_")
                cell_value = "" if value is None else str(value)
                await db.execute(
                    """INSERT INTO state_table_cells (cell_id, row_id, column_id, column_key, value, confidence)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(row_id, column_key) DO UPDATE SET
                        column_id = excluded.column_id,
                        value = excluded.value,
                        confidence = excluded.confidence,
                        updated_at = datetime('now', 'localtime')""",
                    (cell_id, row_id, column_ids.get(column_key), column_key, cell_value, row.confidence),
                )
            await db.commit()
        return row_id

    async def update_table_row_status(self, row_id: str, status: str, reason: str | None = None) -> bool:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT conversation_id, table_key FROM state_table_rows WHERE row_id = ?", (row_id,))
            existing = await cursor.fetchone()
            if not existing:
                return False
            await db.execute(
                "UPDATE state_table_rows SET status = ?, updated_at = datetime('now', 'localtime') WHERE row_id = ?",
                (status, row_id),
            )
            await db.execute(
                """INSERT INTO state_table_events
                   (event_id, conversation_id, event_type, table_key, row_id, reason)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (generate_id("state_evt_"), existing[0], status, existing[1], row_id, reason or ""),
            )
            await db.commit()
            return True

    async def record_table_event(
        self,
        conversation_id: str,
        event_type: str,
        table_key: str | None = None,
        row_id: str | None = None,
        operation: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        reason: str | None = None,
        request_id: str | None = None,
        turn_id: str | None = None,
        model_output: str | None = None,
    ) -> str:
        await self.init_schema()
        event_id = generate_id("state_evt_")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO state_table_events
                   (event_id, conversation_id, request_id, turn_id, event_type, table_key, row_id,
                    before_json, after_json, operation_json, model_output, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    conversation_id,
                    request_id,
                    turn_id,
                    event_type,
                    table_key,
                    row_id,
                    json.dumps(before or {}, ensure_ascii=False),
                    json.dumps(after or {}, ensure_ascii=False),
                    json.dumps(operation or {}, ensure_ascii=False),
                    model_output,
                    reason or "",
                ),
            )
            await db.commit()
        return event_id

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
        config = await self.get_conversation_config(conversation_id)
        if config:
            config.template_id = template_id
            await self.set_conversation_config(config)

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
            # 清理孤立分页（模板载荷中已移除的分页）
            keep_tab_ids = {tab.tab_id for tab in template.tabs if tab.tab_id}
            existing_cursor = await db.execute(
                "SELECT tab_id FROM state_board_tabs WHERE template_id = ?", (template_id,)
            )
            existing_tab_ids = {row[0] for row in await existing_cursor.fetchall()}
            orphan_tab_ids = existing_tab_ids - keep_tab_ids
            for orphan_id in orphan_tab_ids:
                await db.execute(
                    "UPDATE conversation_state_items SET tab_id = NULL, field_id = NULL WHERE tab_id = ? AND status = 'active'",
                    (orphan_id,),
                )
                await db.execute(
                    "UPDATE state_board_fields SET status = 'deleted', updated_at = datetime('now','localtime') WHERE tab_id = ?",
                    (orphan_id,),
                )
                await db.execute("DELETE FROM state_board_tabs WHERE tab_id = ?", (orphan_id,))
            await db.commit()
        return template_id

    async def clone_template(self, source_template_id: str) -> str | None:
        """Clone a template with all its tabs and fields. Returns the new template_id."""
        source = await self.get_template(source_template_id)
        if not source:
            return None
        new_id = generate_id("tpl_copy_")
        cloned_tabs: list[StateBoardTab] = []
        for tab in source.tabs:
            cloned_fields: list[StateBoardField] = []
            for field in tab.fields:
                cloned_fields.append(StateBoardField(
                    field_id=None, template_id=new_id, tab_id="",
                    field_key=field.field_key, label=field.label, field_type=field.field_type,
                    description=field.description, ai_writable=field.ai_writable,
                    include_in_prompt=field.include_in_prompt, sort_order=field.sort_order,
                    default_value=field.default_value, options=field.options, status=field.status,
                ))
            cloned_tabs.append(StateBoardTab(
                tab_id=None, template_id=new_id, tab_key=tab.tab_key,
                label=tab.label, description=tab.description, sort_order=tab.sort_order,
                fields=cloned_fields,
            ))
        new_template = StateBoardTemplate(
            template_id=new_id, name=f"{source.name} (副本)", description=source.description,
            is_builtin=False, status="active", tabs=cloned_tabs,
        )
        await self.save_template(new_template)
        return new_id

    async def count_items_for_tab(self, tab_id: str) -> int:
        """Return the number of active state items linked to a tab."""
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM conversation_state_items WHERE tab_id = ? AND status = 'active'",
                (tab_id,),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

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

    async def hard_delete_item(self, item_id: str) -> None:
        """Permanently remove an item and its events from the database."""
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM conversation_state_events WHERE item_id = ?", (item_id,))
            await db.execute("DELETE FROM conversation_state_items WHERE item_id = ?", (item_id,))
            await db.commit()

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

    async def expire_old_items(self, conversation_id: str) -> int:
        """Proactively expire items whose expires_at has passed. Returns count expired."""
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """UPDATE conversation_state_items
                   SET status = 'expired', updated_at = datetime('now', 'localtime')
                   WHERE conversation_id = ? AND status = 'active'
                     AND expires_at IS NOT NULL AND expires_at < datetime('now', 'localtime')""",
                (conversation_id,),
            )
            expired = cursor.rowcount
            if expired > 0:
                await db.execute(
                    """INSERT INTO conversation_state_events
                       (event_id, conversation_id, item_id, event_type, payload_json)
                       VALUES (?, ?, NULL, 'batch_expire', ?)""",
                    (
                        generate_id("state_evt_"),
                        conversation_id,
                        json.dumps({"expired_count": expired}, ensure_ascii=False),
                    ),
                )
            await db.commit()
        return expired

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

            # 复制模板绑定
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
