"""Render table-based conversation state into hot-context text."""

from __future__ import annotations

from app.core.prompts import HOT_CONTEXT_HEADER, get_text
from app.memory.state_schema import StateRenderOptions, StateTableRow, StateTableTemplate


def render_state_tables(
    template: StateTableTemplate | None,
    rows: list[StateTableRow],
    options: StateRenderOptions,
    lang: str = "zh",
) -> str:
    if not template or not template.tables or not rows or options.max_chars <= 0:
        return ""

    rows_by_table: dict[str, list[StateTableRow]] = {}
    for row in rows:
        if row.status != "active" or not any(cell.value.strip() for cell in row.cells.values()):
            continue
        rows_by_table.setdefault(row.table_key, []).append(row)
    if not rows_by_table:
        return ""

    header = get_text(HOT_CONTEXT_HEADER, lang)
    intro = f"当前会话状态板模板：{template.name}。以下表格用于保持角色扮演、剧情与互动连续性："
    lines = [header, intro]
    tables = sorted(
        [table for table in template.tables if table.enabled and table.include_in_prompt],
        key=lambda table: (-table.prompt_priority, table.sort_order, table.name),
    )
    for table in tables:
        table_rows = rows_by_table.get(table.table_key, [])
        if not table_rows:
            continue
        selected = sorted(
            table_rows,
            key=lambda row: (row.priority, row.confidence, row.updated_at or ""),
            reverse=True,
        )[: table.max_prompt_rows]
        section_lines = [f"【{table.name}】"]
        columns = [column for column in sorted(table.columns, key=lambda item: (item.sort_order, item.name)) if column.include_in_prompt]
        for row in selected:
            parts: list[str] = []
            for column in columns:
                cell = row.cells.get(column.column_key)
                value = (cell.value if cell else "").strip()
                if not value:
                    continue
                if column.max_chars > 0 and len(value) > column.max_chars:
                    value = value[: column.max_chars].rstrip() + "…"
                parts.append(f"{column.name}: {value}")
            if parts:
                section_lines.append("- " + "；".join(parts))
        if len(section_lines) <= 1:
            continue
        candidate_lines = lines + section_lines
        candidate_text = "\n".join(candidate_lines)
        if len(candidate_text) > options.max_chars:
            break
        lines = candidate_lines

    if len(lines) <= 2:
        return ""
    return "\n".join(lines)[: options.max_chars]
