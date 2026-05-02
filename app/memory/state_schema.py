"""Conversation hot-state schema helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


STATE_CATEGORIES: tuple[str, ...] = (
    "scene",
    "key_person",
    "main_quest",
    "side_quest",
    "promise",
    "open_loop",
    "relationship",
    "boundary",
    "preference",
    "location",
    "item",
    "world_state",
    "recent_summary",
    "mood",
)


STATE_CATEGORY_LABELS: dict[str, str] = {
    "scene": "当前场景",
    "key_person": "关键人物",
    "main_quest": "主线任务",
    "side_quest": "支线任务",
    "promise": "承诺与约定",
    "open_loop": "开放悬念",
    "relationship": "关系状态",
    "boundary": "稳定边界",
    "preference": "偏好",
    "location": "地点",
    "item": "物品",
    "world_state": "世界状态",
    "recent_summary": "近期摘要",
    "mood": "情绪氛围",
}


@dataclass
class ConversationStateItem:
    item_id: str | None
    conversation_id: str
    category: str
    content: str
    template_id: str | None = None
    tab_id: str | None = None
    field_id: str | None = None
    field_key: str | None = None
    user_id: str | None = None
    character_id: str | None = None
    world_id: str | None = None
    item_key: str | None = None
    title: str | None = None
    confidence: float = 0.7
    source: str = "manual"
    status: str = "active"
    priority: int = 0
    user_locked: bool = False
    ttl_turns: int | None = None
    source_turn_id: str | None = None
    source_turn_ids: list[str] = field(default_factory=list)
    source_message_ids: list[str] = field(default_factory=list)
    linked_card_ids: list[str] = field(default_factory=list)
    linked_summary_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None
    last_seen_at: str | None = None
    last_injected_at: str | None = None
    expires_at: str | None = None


@dataclass
class StateUpdate:
    category: str
    content: str
    template_id: str | None = None
    tab_id: str | None = None
    field_id: str | None = None
    field_key: str | None = None
    item_key: str | None = None
    title: str | None = None
    confidence: float = 0.7
    status: str = "active"
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


@dataclass
class StateUpdateResult:
    upserts: list[StateUpdate] = field(default_factory=list)
    resolved_item_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    created: int = 0
    updated: int = 0
    resolved: int = 0
    skipped: int = 0


@dataclass
class StateRenderOptions:
    max_chars: int = 1200
    include_sections: dict[str, bool] = field(default_factory=dict)
    section_order: list[str] = field(default_factory=list)
    max_items_per_section: dict[str, int] = field(default_factory=dict)


@dataclass
class StateBoardField:
    field_id: str | None
    template_id: str
    tab_id: str
    field_key: str
    label: str
    field_type: str = "multiline"
    description: str = ""
    ai_writable: bool = True
    include_in_prompt: bool = True
    sort_order: int = 0
    default_value: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    status: str = "active"


@dataclass
class StateBoardTab:
    tab_id: str | None
    template_id: str
    tab_key: str
    label: str
    description: str = ""
    sort_order: int = 0
    fields: list[StateBoardField] = field(default_factory=list)


@dataclass
class StateBoardTemplate:
    template_id: str | None
    name: str
    description: str = ""
    is_builtin: bool = False
    status: str = "active"
    tabs: list[StateBoardTab] = field(default_factory=list)


@dataclass
class StateTableColumn:
    column_id: str | None
    table_id: str
    column_key: str
    name: str
    description: str = ""
    value_type: str = "text"
    required: bool = False
    sort_order: int = 0
    include_in_prompt: bool = True
    max_chars: int = 240
    default_value: str = ""
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class StateTableSchema:
    table_id: str | None
    template_id: str
    table_key: str
    name: str
    description: str = ""
    sort_order: int = 0
    enabled: bool = True
    required: bool = False
    as_status: bool = False
    include_in_prompt: bool = True
    max_prompt_rows: int = 4
    prompt_priority: int = 50
    insert_rule: str = ""
    update_rule: str = ""
    delete_rule: str = ""
    resolve_rule: str = ""
    note: str = ""
    columns: list[StateTableColumn] = field(default_factory=list)


@dataclass
class StateTableTemplate:
    template_id: str | None
    name: str
    description: str = ""
    scenario_type: str = "roleplay"
    is_builtin: bool = False
    status: str = "active"
    version: int = 1
    tables: list[StateTableSchema] = field(default_factory=list)


@dataclass
class StateTableCell:
    cell_id: str | None
    row_id: str
    column_id: str | None
    column_key: str
    value: str = ""
    confidence: float = 0.7
    updated_at: str | None = None


@dataclass
class StateTableRow:
    row_id: str | None
    conversation_id: str
    template_id: str
    table_id: str
    table_key: str
    status: str = "active"
    priority: int = 50
    confidence: float = 0.7
    source: str = "manual"
    source_turn_id: str | None = None
    source_message_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    cells: dict[str, StateTableCell] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class StateTableOperation:
    op: str
    table_key: str
    values: dict[str, Any] = field(default_factory=dict)
    match: dict[str, Any] = field(default_factory=dict)
    row_id: str | None = None
    confidence: float = 0.7
    reason: str = ""
