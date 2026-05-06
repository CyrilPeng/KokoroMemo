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

CREATE TABLE IF NOT EXISTS conversation_configs (
  conversation_id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
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
  table_template_id TEXT,
  mount_preset_id TEXT,
  memory_write_policy TEXT NOT NULL DEFAULT 'candidate',
  state_update_policy TEXT NOT NULL DEFAULT 'auto',
  injection_policy TEXT NOT NULL DEFAULT 'mixed',
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

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
        await _ensure_columns(db, "retrieval_decisions", _RETRIEVAL_DECISION_COLUMNS)
        await _ensure_default_conversation_config(db)
        await _ensure_builtin_table_templates(db)
        await db.commit()


async def delete_conversation_state_data(db_path: str, conversation_id: str) -> dict[str, int]:
    """删除指定会话关联的状态表格、诊断记录和策略配置。"""
    await init_state_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        row_cursor = await db.execute(
            "SELECT row_id FROM state_table_rows WHERE conversation_id = ?",
            (conversation_id,),
        )
        row_ids = [row[0] for row in await row_cursor.fetchall()]
        table_cells = 0
        if row_ids:
            placeholders = ",".join("?" for _ in row_ids)
            cursor = await db.execute(f"DELETE FROM state_table_cells WHERE row_id IN ({placeholders})", row_ids)
            table_cells = cursor.rowcount
        deletes = []
        for table in [
            "conversation_configs",
            "retrieval_decisions",
            "state_table_events",
            "state_table_debug_runs",
            "state_table_rows",
        ]:
            cursor = await db.execute(f"DELETE FROM {table} WHERE conversation_id = ?", (conversation_id,))
            deletes.append((table, cursor.rowcount))
        await db.commit()
        result = {table: count for table, count in deletes}
        result["state_table_cells"] = table_cells
        return result


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

async def _ensure_default_conversation_config(db: aiosqlite.Connection) -> None:
    profile = get_profile(DEFAULT_CONVERSATION_PROFILE_ID)
    await db.execute(
        """INSERT INTO conversation_default_config
           (id, profile_id, table_template_id, mount_preset_id,
            memory_write_policy, state_update_policy, injection_policy)
           VALUES ('global', ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO NOTHING""",
        (
            profile.profile_id,
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
        table_template_id = payload.get("table_template_id", profile.table_template_id)
        mount_preset_id = payload.get("mount_preset_id", profile.mount_preset_id)
        memory_write_policy = payload.get("memory_write_policy") or profile.memory_write_policy
        state_update_policy = payload.get("state_update_policy") or profile.state_update_policy
        injection_policy = payload.get("injection_policy") or profile.injection_policy
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO conversation_default_config
                   (id, profile_id, table_template_id, mount_preset_id,
                    memory_write_policy, state_update_policy, injection_policy)
                   VALUES ('global', ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    table_template_id = excluded.table_template_id,
                    mount_preset_id = excluded.mount_preset_id,
                    memory_write_policy = excluded.memory_write_policy,
                    state_update_policy = excluded.state_update_policy,
                    injection_policy = excluded.injection_policy,
                    updated_at = datetime('now', 'localtime')""",
                (profile_id, table_template_id, mount_preset_id, memory_write_policy, state_update_policy, injection_policy),
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
        table_template_id = payload.get("table_template_id", profile.table_template_id)
        mount_preset_id = payload.get("mount_preset_id", profile.mount_preset_id)
        memory_write_policy = payload.get("memory_write_policy") or profile.memory_write_policy
        state_update_policy = payload.get("state_update_policy") or profile.state_update_policy
        injection_policy = payload.get("injection_policy") or profile.injection_policy
        created_from_default = 1 if payload.get("created_from_default") else 0
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO conversation_configs
                   (conversation_id, profile_id, table_template_id, mount_preset_id,
                    memory_write_policy, state_update_policy, injection_policy, created_from_default)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(conversation_id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    table_template_id = excluded.table_template_id,
                    mount_preset_id = excluded.mount_preset_id,
                    memory_write_policy = excluded.memory_write_policy,
                    state_update_policy = excluded.state_update_policy,
                    injection_policy = excluded.injection_policy,
                    updated_at = datetime('now', 'localtime')""",
                (
                    conversation_id,
                    profile_id,
                    table_template_id,
                    mount_preset_id,
                    memory_write_policy,
                    state_update_policy,
                    injection_policy,
                    created_from_default,
                ),
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
                table_template_id=default.table_template_id,
                mount_preset_id=default.mount_preset_id,
                memory_write_policy=default.memory_write_policy,
                state_update_policy=default.state_update_policy,
                injection_policy=default.injection_policy,
                created_from_default=True,
            )
        )

    async def update_conversation_character_refs(self, conversation_id: str, character_id: str | None) -> dict[str, int]:
        """更新单个会话状态数据中的角色引用。"""
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            items = await db.execute(
                "UPDATE conversation_state_items SET character_id = ?, updated_at = datetime('now', 'localtime') WHERE conversation_id = ?",
                (character_id, conversation_id),
            )
            await db.commit()
            return {"items": items.rowcount}

    async def merge_character_refs(self, source_character_id: str, target_character_id: str) -> dict[str, int]:
        """将状态板数据中的源角色引用迁移到目标角色。"""
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            items = await db.execute(
                "UPDATE conversation_state_items SET character_id = ?, updated_at = datetime('now', 'localtime') WHERE character_id = ?",
                (target_character_id, source_character_id),
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
        return await self.get_table_template("tpl_roleplay_light_tables")

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

