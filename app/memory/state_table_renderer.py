"""Render table-based conversation state into hot-context text."""

from __future__ import annotations

from app.core.prompts import HOT_CONTEXT_HEADER, get_text
from app.memory.state_schema import StateRenderOptions, StateTableRow, StateTableTemplate


def _truncate(value: str, max_chars: int) -> str:
    value = value.strip()
    if max_chars > 0 and len(value) > max_chars:
        return value[:max_chars].rstrip() + "\u2026"
    return value


def _format_cell(column_name: str, value: str) -> str:
    if "\n" in value or len(value) > 80:
        indented = "\n".join(f"    {line}" for line in value.splitlines() if line.strip())
        return f"  - **{column_name}**:\n{indented}"
    return f"  - **{column_name}**: {value}"


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
    if lang.startswith("zh"):
        intro = f"\u5f53\u524d\u4f1a\u8bdd\u72b6\u6001\u677f\u6a21\u677f\uff1a{template.name}\u3002\u4ee5\u4e0b\u4e3a\u9700\u8981\u4f18\u5148\u4fdd\u6301\u4e00\u81f4\u7684\u70ed\u72b6\u6001\uff1a"
    else:
        intro = f"Current session state board template: {template.name}. Keep the following hot state consistent:"
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
        section_lines = ["", f"## {table.name}"]
        if table.description:
            section_lines.append(f"> {table.description.strip()}")
        columns = [
            column
            for column in sorted(table.columns, key=lambda item: (item.sort_order, item.name))
            if column.include_in_prompt
        ]
        for index, row in enumerate(selected, 1):
            row_lines: list[str] = []
            for column in columns:
                cell = row.cells.get(column.column_key)
                value = _truncate(cell.value if cell else "", column.max_chars)
                if value:
                    row_lines.append(_format_cell(column.name, value))
            if row_lines:
                section_lines.append(f"- Row {index} (priority {row.priority}, confidence {row.confidence:.2f})")
                section_lines.extend(row_lines)
        if len(section_lines) <= (3 if table.description else 2):
            continue
        candidate_lines = lines + section_lines
        candidate_text = "\n".join(candidate_lines)
        if len(candidate_text) > options.max_chars:
            break
        lines = candidate_lines

    if len(lines) <= 2:
        return ""
    return "\n".join(lines)[: options.max_chars].rstrip()
