"""Render conversation hot-state into a compact system prompt block."""

from __future__ import annotations

from collections import defaultdict

from app.memory.state_schema import (
    STATE_CATEGORY_LABELS,
    STATE_CATEGORIES,
    ConversationStateItem,
    StateRenderOptions,
)


HOT_CONTEXT_HEADER = "【KokoroMemo 会话状态板】"


def render_state_board(items: list[ConversationStateItem], options: StateRenderOptions) -> str:
    """Render active state items grouped by category within a character budget."""
    if not items or options.max_chars <= 0:
        return ""

    include_sections = options.include_sections or {category: True for category in STATE_CATEGORIES}
    section_order = options.section_order or list(STATE_CATEGORIES)
    max_items_per_section = options.max_items_per_section or {}

    grouped: dict[str, list[ConversationStateItem]] = defaultdict(list)
    for item in items:
        if item.status != "active" or not item.content.strip():
            continue
        if not include_sections.get(item.category, True):
            continue
        grouped[item.category].append(item)

    if not grouped:
        return ""

    lines = [HOT_CONTEXT_HEADER, "以下是当前会话的热状态，仅用于保持当前剧情与互动连续性："]
    for category in section_order:
        category_items = grouped.get(category, [])
        if not category_items:
            continue
        limit = max_items_per_section.get(category, 5)
        selected = sorted(
            category_items,
            key=lambda item: (item.priority, item.confidence, item.updated_at or ""),
            reverse=True,
        )[:limit]
        label = STATE_CATEGORY_LABELS.get(category, category)
        section_lines = [f"【{label}】"]
        for item in selected:
            prefix = f"{item.title}：" if item.title else ""
            section_lines.append(f"- {prefix}{item.content}")
        candidate_lines = lines + section_lines
        candidate_text = "\n".join(candidate_lines)
        if len(candidate_text) > options.max_chars:
            break
        lines = candidate_lines

    if len(lines) <= 2:
        return ""
    return "\n".join(lines)[: options.max_chars]
