"""Render conversation hot-state into a compact system prompt block."""

from __future__ import annotations

from collections import defaultdict

from app.core.prompts import (
    HOT_CONTEXT_HEADER,
    HOT_CONTEXT_INTRO,
    HOT_CONTEXT_TEMPLATE_INTRO,
    get_text,
)
from app.memory.state_schema import (
    STATE_CATEGORY_LABELS,
    STATE_CATEGORIES,
    ConversationStateItem,
    StateBoardTemplate,
    StateRenderOptions,
)


def render_state_board(
    items: list[ConversationStateItem],
    options: StateRenderOptions,
    template: StateBoardTemplate | None = None,
    lang: str = "zh",
) -> str:
    """Render active state items grouped by category within a character budget."""
    if not items or options.max_chars <= 0:
        return ""

    if template and template.tabs:
        rendered = _render_template_board(items, options, template, lang)
        if rendered:
            return rendered

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

    header = get_text(HOT_CONTEXT_HEADER, lang)
    intro = get_text(HOT_CONTEXT_INTRO, lang)
    lines = [header, intro]
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


def _render_template_board(
    items: list[ConversationStateItem],
    options: StateRenderOptions,
    template: StateBoardTemplate,
    lang: str = "zh",
) -> str:
    by_field = {item.field_id: item for item in items if item.status == "active" and item.field_id and item.content.strip()}
    if not by_field:
        return ""

    header = get_text(HOT_CONTEXT_HEADER, lang)
    intro = get_text(HOT_CONTEXT_TEMPLATE_INTRO, lang, name=template.name)
    lines = [header, intro]
    for tab in sorted(template.tabs, key=lambda item: (item.sort_order, item.label)):
        section_lines: list[str] = []
        for field in sorted(tab.fields, key=lambda item: (item.sort_order, item.label)):
            if not field.include_in_prompt:
                continue
            item = by_field.get(field.field_id)
            if not item:
                continue
            section_lines.append(f"- {field.label}：{item.content}")
        if not section_lines:
            continue
        candidate_lines = lines + [f"【{tab.label}】"] + section_lines
        candidate_text = "\n".join(candidate_lines)
        if len(candidate_text) > options.max_chars:
            break
        lines = candidate_lines

    if len(lines) <= 2:
        return ""
    return "\n".join(lines)[: options.max_chars]
