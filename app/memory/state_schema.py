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
    user_id: str | None = None
    character_id: str | None = None
    world_id: str | None = None
    item_key: str | None = None
    title: str | None = None
    confidence: float = 0.7
    source: str = "manual"
    status: str = "active"
    priority: int = 0
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
