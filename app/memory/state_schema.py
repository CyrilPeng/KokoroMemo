"""Conversation hot-state schema helpers (table-based v2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StateRenderOptions:
    max_chars: int = 1200


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
