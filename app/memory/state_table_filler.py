"""Operation-based filler for table state boards."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.memory.state_filler import StateFillerConfigView
from app.memory.state_schema import StateTableOperation, StateTableRow, StateTableSchema, StateTableTemplate
from app.proxy.llm_providers import create_llm_provider
from app.storage.sqlite_state import SQLiteStateStore


@dataclass
class AppliedTableOperation:
    op: str
    table_key: str
    row_id: str | None = None
    confidence: float = 0.7
    reason: str = ""


@dataclass
class StateTableFillResult:
    operations: list[AppliedTableOperation] = field(default_factory=list)
    applied: int = 0
    skipped: int = 0
    notes: list[str] = field(default_factory=list)


async def fill_conversation_state_tables(
    *,
    db_path: str,
    conversation_id: str,
    user_message: str,
    assistant_message: str,
    config: StateFillerConfigView,
    lang: str = "zh",
    turn_id: str | None = None,
) -> StateTableFillResult:
    result = StateTableFillResult()
    if not config.base_url or not config.model or not assistant_message:
        result.notes.append("state_table_filler_not_configured")
        return result

    store = SQLiteStateStore(db_path)
    template = await store.get_conversation_table_template(conversation_id)
    if not template:
        result.notes.append("state_table_template_not_found")
        return result

    current_rows = await store.list_table_rows(conversation_id, template.template_id)
    prompt = _build_table_prompt(config.prompt, template, current_rows, lang=lang)
    user_content = (
        "请根据本轮用户与助手对话，仅输出 JSON。\n"
        f"用户消息：{user_message}\n\n助手回复：{assistant_message}"
    )

    provider = create_llm_provider(config.provider, config.base_url, config.api_key, config.timeout_seconds)
    try:
        text = await provider.chat(
            model=config.model,
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_content}],
            temperature=config.temperature,
        )
    except Exception as exc:
        result.notes.append(f"llm_error:{exc}")
        return result

    payload = _parse_json(text)
    operations = _parse_operations(payload)
    if not operations:
        result.notes.append("no_operations")
        return result

    tables_by_key = {table.table_key: table for table in template.tables if table.enabled}
    rows_by_table: dict[str, list[StateTableRow]] = {}
    for row in current_rows:
        rows_by_table.setdefault(row.table_key, []).append(row)

    for operation in operations:
        table = tables_by_key.get(operation.table_key)
        if not table or operation.confidence < config.min_confidence:
            result.skipped += 1
            continue
        row = _match_row(rows_by_table.get(table.table_key, []), operation)
        normalized_values = _normalize_values(table, operation.values)
        if operation.op in {"insert_row", "upsert_row"} and not row:
            row = StateTableRow(
                row_id=None,
                conversation_id=conversation_id,
                template_id=template.template_id or "",
                table_id=table.table_id or "",
                table_key=table.table_key,
                priority=table.prompt_priority,
                confidence=operation.confidence,
                source="state_table_filler",
                source_turn_id=turn_id,
                metadata={"reason": operation.reason},
            )
            row_id = await store.upsert_table_row(row, normalized_values)
            await store.record_table_event(
                conversation_id,
                "insert_row",
                table_key=table.table_key,
                row_id=row_id,
                operation=operation.__dict__,
                after=normalized_values,
                reason=operation.reason,
                turn_id=turn_id,
                model_output=text,
            )
        elif operation.op in {"update_row", "upsert_row"} and row:
            before = {key: cell.value for key, cell in row.cells.items()}
            values = {**before, **normalized_values}
            row.confidence = operation.confidence
            row.source = "state_table_filler"
            row.source_turn_id = turn_id
            row.metadata = {**row.metadata, "reason": operation.reason}
            row_id = await store.upsert_table_row(row, values)
            await store.record_table_event(
                conversation_id,
                "update_row",
                table_key=table.table_key,
                row_id=row_id,
                operation=operation.__dict__,
                before=before,
                after=values,
                reason=operation.reason,
                turn_id=turn_id,
                model_output=text,
            )
        elif operation.op in {"delete_row", "resolve_row"} and row and row.row_id:
            row_id = row.row_id
            await store.update_table_row_status(row_id, "resolved", operation.reason)
            await store.record_table_event(
                conversation_id,
                operation.op,
                table_key=table.table_key,
                row_id=row_id,
                operation=operation.__dict__,
                reason=operation.reason,
                turn_id=turn_id,
                model_output=text,
            )
        else:
            result.skipped += 1
            continue
        result.applied += 1
        result.operations.append(AppliedTableOperation(operation.op, operation.table_key, row_id, operation.confidence, operation.reason))

    return result


def _build_table_prompt(custom_prompt: str, template: StateTableTemplate, rows: list[StateTableRow], lang: str = "zh") -> str:
    if custom_prompt.strip():
        base = custom_prompt.strip()
    else:
        base = (
            "你是 KokoroMemo 的会话状态板维护器。你的任务是把本轮对话转化为表格行级操作，"
            "只记录对后续角色扮演/剧情连续性有帮助的信息。不要记录流水账，不要臆造未出现的信息。"
        )
    lines = [
        base,
        "输出必须是严格 JSON，不要使用 Markdown。格式：",
        '{"operations":[{"op":"insert_row|update_row|upsert_row|resolve_row|delete_row","table_key":"...","match":{},"values":{},"confidence":0.8,"reason":"..."}]}',
        "可用表格：",
    ]
    for table in sorted(template.tables, key=lambda item: (item.sort_order, item.name)):
        columns = ", ".join(f"{column.column_key}({column.name})" for column in table.columns)
        lines.append(f"- {table.table_key}: {table.name}; {table.description}; columns: {columns}")
    if rows:
        lines.append("当前已有行（匹配时优先 update/upsert）：")
        for row in rows[:80]:
            values = {key: cell.value for key, cell in row.cells.items() if cell.value.strip()}
            lines.append(f"- row_id={row.row_id}; table_key={row.table_key}; values={json.dumps(values, ensure_ascii=False)}")
    return "\n".join(lines)


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"operations": []}
    return payload if isinstance(payload, dict) else {"operations": []}


def _parse_operations(payload: dict[str, Any]) -> list[StateTableOperation]:
    operations: list[StateTableOperation] = []
    for raw in payload.get("operations") or []:
        if not isinstance(raw, dict):
            continue
        op = str(raw.get("op") or "").strip()
        table_key = str(raw.get("table_key") or "").strip()
        if op not in {"insert_row", "update_row", "upsert_row", "resolve_row", "delete_row"} or not table_key:
            continue
        operations.append(StateTableOperation(
            op=op,
            table_key=table_key,
            values=raw.get("values") if isinstance(raw.get("values"), dict) else {},
            match=raw.get("match") if isinstance(raw.get("match"), dict) else {},
            row_id=str(raw.get("row_id") or "").strip() or None,
            confidence=_safe_float(raw.get("confidence"), 0.7),
            reason=str(raw.get("reason") or ""),
        ))
    return operations


def _match_row(rows: list[StateTableRow], operation: StateTableOperation) -> StateTableRow | None:
    if operation.row_id:
        for row in rows:
            if row.row_id == operation.row_id:
                return row
    match = {str(key): str(value).strip() for key, value in operation.match.items() if str(value).strip()}
    if not match:
        return None
    for row in rows:
        values = {key: cell.value.strip() for key, cell in row.cells.items()}
        if all(values.get(key) == value for key, value in match.items()):
            return row
    for row in rows:
        values = {key: cell.value.strip() for key, cell in row.cells.items()}
        if any(values.get(key) == value for key, value in match.items()):
            return row
    return None


def _normalize_values(table: StateTableSchema, values: dict[str, Any]) -> dict[str, str]:
    allowed = {column.column_key: column for column in table.columns}
    result: dict[str, str] = {}
    for key, value in values.items():
        column = allowed.get(str(key))
        if not column:
            continue
        text = "" if value is None else str(value).strip()
        if column.max_chars > 0:
            text = text[: column.max_chars]
        if text:
            result[column.column_key] = text
    return result


def _safe_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
