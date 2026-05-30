"""State table routes: templates, rows, preview, fill, events, revert, retrieval traces."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Query, Request

from app.api.admin._helpers import _require_admin

router = APIRouter()


# --- Helpers ---


def _state_table_column_to_dict(column) -> dict:
    return {
        "column_id": column.column_id,
        "table_id": column.table_id,
        "column_key": column.column_key,
        "name": column.name,
        "description": column.description,
        "value_type": column.value_type,
        "required": column.required,
        "sort_order": column.sort_order,
        "include_in_prompt": column.include_in_prompt,
        "max_chars": column.max_chars,
        "default_value": column.default_value,
        "options": column.options,
    }


def _state_table_schema_to_dict(table) -> dict:
    return {
        "table_id": table.table_id,
        "template_id": table.template_id,
        "table_key": table.table_key,
        "name": table.name,
        "description": table.description,
        "sort_order": table.sort_order,
        "enabled": table.enabled,
        "required": table.required,
        "as_status": table.as_status,
        "include_in_prompt": table.include_in_prompt,
        "max_prompt_rows": table.max_prompt_rows,
        "prompt_priority": table.prompt_priority,
        "insert_rule": table.insert_rule,
        "update_rule": table.update_rule,
        "delete_rule": table.delete_rule,
        "resolve_rule": table.resolve_rule,
        "note": table.note,
        "columns": [_state_table_column_to_dict(column) for column in table.columns],
    }


def _state_table_template_to_dict(template, include_tables: bool = True) -> dict:
    data = {
        "template_id": template.template_id,
        "name": template.name,
        "description": template.description,
        "scenario_type": template.scenario_type,
        "is_builtin": template.is_builtin,
        "status": template.status,
        "version": template.version,
    }
    if include_tables:
        data["tables"] = [_state_table_schema_to_dict(table) for table in template.tables]
    return data


def _state_table_template_from_dict(data: dict):
    from app.memory.state_schema import StateTableColumn, StateTableSchema, StateTableTemplate

    template_id = data.get("template_id")
    tables = []
    for table_index, raw_table in enumerate(data.get("tables") or []):
        table = StateTableSchema(
            table_id=raw_table.get("table_id"),
            template_id=template_id or raw_table.get("template_id") or "",
            table_key=raw_table.get("table_key") or raw_table.get("name") or f"tab_{table_index + 1}",
            name=raw_table.get("name") or raw_table.get("table_key") or f"Tab {table_index + 1}",
            description=raw_table.get("description", ""),
            sort_order=int(raw_table.get("sort_order", table_index)),
            enabled=bool(raw_table.get("enabled", True)),
            required=bool(raw_table.get("required", False)),
            as_status=bool(raw_table.get("as_status", False)),
            include_in_prompt=bool(raw_table.get("include_in_prompt", True)),
            max_prompt_rows=int(raw_table.get("max_prompt_rows", 4)),
            prompt_priority=int(raw_table.get("prompt_priority", 50)),
            insert_rule=raw_table.get("insert_rule", ""),
            update_rule=raw_table.get("update_rule", ""),
            delete_rule=raw_table.get("delete_rule", ""),
            resolve_rule=raw_table.get("resolve_rule", ""),
            note=raw_table.get("note", ""),
        )
        table.columns = [
            StateTableColumn(
                column_id=raw_column.get("column_id"),
                table_id=table.table_id or "",
                column_key=raw_column.get("column_key") or raw_column.get("name") or f"col_{column_index + 1}",
                name=raw_column.get("name") or raw_column.get("column_key") or f"? {column_index + 1}",
                description=raw_column.get("description", ""),
                value_type=raw_column.get("value_type", "text"),
                required=bool(raw_column.get("required", False)),
                sort_order=int(raw_column.get("sort_order", column_index)),
                include_in_prompt=bool(raw_column.get("include_in_prompt", True)),
                max_chars=int(raw_column.get("max_chars", 240)),
                default_value=raw_column.get("default_value", ""),
                options=raw_column.get("options") or {},
            )
            for column_index, raw_column in enumerate(raw_table.get("columns") or [])
        ]
        tables.append(table)
    return StateTableTemplate(
        template_id=template_id,
        name=data.get("name") or "Custom state board template",
        description=data.get("description", ""),
        scenario_type=data.get("scenario_type", "custom"),
        is_builtin=False,
        status=data.get("status", "active"),
        version=int(data.get("version", 1)),
        tables=tables,
    )


def _state_table_row_to_dict(row) -> dict:
    return {
        "row_id": row.row_id,
        "conversation_id": row.conversation_id,
        "template_id": row.template_id,
        "table_id": row.table_id,
        "table_key": row.table_key,
        "status": row.status,
        "priority": row.priority,
        "confidence": row.confidence,
        "source": row.source,
        "source_turn_id": row.source_turn_id,
        "source_message_ids": row.source_message_ids,
        "metadata": row.metadata,
        "cells": {key: {"cell_id": cell.cell_id, "value": cell.value, "confidence": cell.confidence, "updated_at": cell.updated_at} for key, cell in row.cells.items()},
        "values": {key: cell.value for key, cell in row.cells.items()},
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


# --- Routes ---


@router.get("/admin/state/table-templates")
async def list_state_table_templates(request: Request):
    """List available table-based state board templates."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    templates = await store.list_table_templates()
    return {"items": [_state_table_template_to_dict(template, include_tables=False) for template in templates]}


@router.get("/admin/state/table-templates/{template_id}")
async def get_state_table_template(template_id: str, request: Request):
    """Get a full table-based state board template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    template = await store.get_table_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="State table template not found")
    return _state_table_template_to_dict(template)


@router.post("/admin/state/table-templates")
async def create_state_table_template(request: Request, data: dict = Body(...)):
    """Create a custom table-based state board template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    template = _state_table_template_from_dict(data)
    template.template_id = None
    saved = await store.save_table_template(template)
    return {"status": "ok", "template": _state_table_template_to_dict(saved)}


@router.post("/admin/state/table-templates/{template_id}/clone")
async def clone_state_table_template(template_id: str, request: Request, data: dict = Body(default={})):
    """Clone a state board template into an editable custom template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    try:
        saved = await SQLiteStateStore(get_config().storage.sqlite.memory_db).clone_table_template(template_id, data.get("name"))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok", "template": _state_table_template_to_dict(saved)}


@router.put("/admin/state/table-templates/{template_id}")
async def update_state_table_template(template_id: str, request: Request, data: dict = Body(...)):
    """Replace an editable custom state board template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    payload = dict(data)
    payload["template_id"] = template_id
    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    existing = await store.get_table_template(template_id)
    if existing and existing.is_builtin:
        raise HTTPException(status_code=400, detail="Built-in templates cannot be modified; clone it first")
    saved = await store.save_table_template(_state_table_template_from_dict(payload))
    return {"status": "ok", "template": _state_table_template_to_dict(saved)}


@router.delete("/admin/state/table-templates/{template_id}")
async def delete_state_table_template(template_id: str, request: Request):
    """Delete a custom state board template (soft-delete)."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    try:
        ok = await store.delete_table_template(template_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "ok"}


@router.post("/admin/state/table-templates/{template_id}/tables")
async def add_state_table_template_table(template_id: str, request: Request, data: dict = Body(...)):
    """Add a tab/table to a state board template. Built-ins are cloned automatically."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    try:
        saved = await SQLiteStateStore(get_config().storage.sqlite.memory_db).add_table_to_template(template_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "template": _state_table_template_to_dict(saved)}


@router.patch("/admin/state/table-templates/{template_id}/tables/{table_key}")
async def update_state_table_template_table(template_id: str, table_key: str, request: Request, data: dict = Body(...)):
    """Update a tab/table in a custom state board template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    try:
        saved = await SQLiteStateStore(get_config().storage.sqlite.memory_db).update_table_in_template(template_id, table_key, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "template": _state_table_template_to_dict(saved)}


@router.delete("/admin/state/table-templates/{template_id}/tables/{table_key}")
async def delete_state_table_template_table(template_id: str, table_key: str, request: Request):
    """Delete a tab/table from a custom state board template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    try:
        saved = await SQLiteStateStore(get_config().storage.sqlite.memory_db).delete_table_from_template(template_id, table_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "template": _state_table_template_to_dict(saved)}


@router.post("/admin/state/table-templates/{template_id}/tables/{table_key}/columns")
async def add_state_table_template_column(template_id: str, table_key: str, request: Request, data: dict = Body(...)):
    """Add a column to one state board table. Built-ins are cloned automatically."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    try:
        saved = await SQLiteStateStore(get_config().storage.sqlite.memory_db).add_column_to_table(template_id, table_key, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "template": _state_table_template_to_dict(saved)}


@router.patch("/admin/state/table-templates/{template_id}/tables/{table_key}/columns/{column_key}")
async def update_state_table_template_column(template_id: str, table_key: str, column_key: str, request: Request, data: dict = Body(...)):
    """Update a column in a custom state board template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    try:
        saved = await SQLiteStateStore(get_config().storage.sqlite.memory_db).update_column_in_table(template_id, table_key, column_key, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "template": _state_table_template_to_dict(saved)}


@router.get("/admin/conversations/{conversation_id}/state/tables")
async def get_conversation_state_tables(conversation_id: str, request: Request):
    """Return the table-based state board for a conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    template = await store.get_conversation_table_template(conversation_id)
    if not template:
        raise HTTPException(status_code=404, detail="State table template not found")
    rows = await store.list_table_rows(conversation_id, template.template_id)
    recent_events = await store.list_table_events(conversation_id, limit=30)
    return {
        "conversation_id": conversation_id,
        "template": _state_table_template_to_dict(template),
        "rows": [_state_table_row_to_dict(row) for row in rows],
        "recent_events": recent_events,
        "source": "table",
    }


@router.post("/admin/conversations/{conversation_id}/state/tables/{table_key}/rows")
async def upsert_conversation_state_table_row(conversation_id: str, table_key: str, request: Request, data: dict = Body(...)):
    """Create or update one row in a table-based state board."""
    _require_admin(request)
    from app.core.state import get_config
    from app.memory.state_schema import StateTableRow
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    template = await store.get_conversation_table_template(conversation_id)
    if not template:
        raise HTTPException(status_code=404, detail="State table template not found")
    table = next((item for item in template.tables if item.table_key == table_key), None)
    if not table:
        raise HTTPException(status_code=404, detail="State table not found")
    values = data.get("values") if isinstance(data.get("values"), dict) else {}
    row = StateTableRow(
        row_id=data.get("row_id"),
        conversation_id=conversation_id,
        template_id=template.template_id or "",
        table_id=table.table_id or "",
        table_key=table.table_key,
        status=data.get("status", "active"),
        priority=int(data.get("priority", table.prompt_priority)),
        confidence=float(data.get("confidence", 0.9)),
        source="manual",
        metadata=data.get("metadata", {}),
    )
    row_id = await store.upsert_table_row(row, values)
    await store.record_table_event(
        conversation_id,
        "manual_upsert_row",
        table_key=table.table_key,
        row_id=row_id,
        after=values,
        reason=data.get("reason", "GUI manual edit"),
    )
    return {"status": "ok", "row_id": row_id}


@router.delete("/admin/state/table-rows/{row_id}")
async def delete_conversation_state_table_row(row_id: str, request: Request):
    """Resolve one row in a table-based state board."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    ok = await SQLiteStateStore(get_config().storage.sqlite.memory_db).update_table_row_status(row_id, "resolved", "GUI delete")
    return {"status": "ok" if ok else "error", "message": None if ok else "State table row not found"}


@router.post("/admin/state/table-rows/batch")
async def batch_update_state_table_rows(request: Request, data: dict = Body(...)):
    """Batch operations on state table rows (delete, set_priority, set_status)."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    action = data.get("action")
    row_ids = data.get("row_ids", [])
    if not action or not row_ids:
        raise HTTPException(status_code=400, detail="action and row_ids required")
    if action not in {"delete", "set_priority", "set_status"}:
        raise HTTPException(status_code=400, detail="Invalid action")
    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    affected = await store.batch_update_rows(row_ids, action, data.get("value"))
    return {"status": "ok", "affected": affected}


@router.patch("/admin/state/table-rows/{row_id}/cells/{column_key}")
async def patch_state_table_cell(row_id: str, column_key: str, request: Request, data: dict = Body(...)):
    """Update a single cell value in a state table row."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    value = data.get("value", "")
    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    cell = await store.update_single_cell(row_id, column_key, str(value))
    if not cell:
        raise HTTPException(status_code=404, detail="Row not found")
    return {"status": "ok", "cell": cell}


@router.get("/admin/state/table-rows/{row_id}/cells/{column_key}/history")
async def get_cell_history(
    row_id: str,
    column_key: str,
    request: Request,
    limit: int = Query(default=20, le=100),
):
    """Get value change history for a specific cell."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    history = await store.get_cell_history(row_id, column_key, limit=limit)
    return {"items": history}


@router.get("/admin/conversations/{conversation_id}/retrieval-decisions")
async def get_retrieval_decisions(
    conversation_id: str,
    request: Request,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List Retrieval Gate decisions for debugging."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    decisions, total = await store.list_retrieval_decisions(conversation_id, limit=limit, offset=offset)
    return {"items": decisions, "total": total, "limit": limit, "offset": offset}


@router.get("/admin/conversations/{conversation_id}/retrieval-traces")
async def get_retrieval_traces(
    conversation_id: str,
    request: Request,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List memory retrieval and injection traces for a conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    traces, total = await store.list_retrieval_traces(conversation_id, limit=limit, offset=offset)
    return {"items": traces, "total": total, "limit": limit, "offset": offset}


@router.get("/admin/retrieval-traces/{trace_id}")
async def get_retrieval_trace(trace_id: str, request: Request):
    """Get one retrieval trace with its candidate rows."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    trace = await store.get_retrieval_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Retrieval trace not found")
    return trace


@router.get("/admin/conversations/{conversation_id}/state/preview")
async def preview_state_board(conversation_id: str, request: Request):
    """Return the rendered state board text as it would be injected into the LLM prompt."""
    _require_admin(request)
    from app.core.state import get_config
    from app.memory.state_schema import StateRenderOptions
    from app.memory.state_table_renderer import render_state_tables, summarize_state_tables
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
    table_template = await store.get_conversation_table_template(conversation_id)
    table_rows = await store.list_table_rows(conversation_id, table_template.template_id if table_template else None)
    hot = cfg.memory.hot_context
    options = StateRenderOptions(max_chars=hot.max_chars)
    text = render_state_tables(table_template, table_rows, options, lang=cfg.language)
    summary = summarize_state_tables(table_template, table_rows, options, lang=cfg.language)
    return {
        "preview": text,
        "char_count": len(text),
        "max_chars": hot.max_chars,
        "item_count": len(table_rows),
        "summary": summary,
    }


@router.post("/admin/conversations/{conversation_id}/state/fill")
async def fill_conversation_state_once(conversation_id: str, request: Request, data: dict = Body(...)):
    """Manually run the model-driven state board filler."""
    _require_admin(request)
    from app.core.state import get_config
    from app.memory.state_filler import StateFillerConfigView
    from app.memory.state_table_filler import _parse_operations, fill_conversation_state_tables

    cfg = get_config()
    filler_config = StateFillerConfigView(
        provider=data.get("provider") or cfg.memory.state_updater.provider,
        base_url=data.get("base_url") or cfg.memory.state_updater.base_url or cfg.memory.judge.base_url or cfg.llm.base_url,
        api_key=data.get("api_key") or cfg.memory.state_updater.get_api_key() or cfg.memory.judge.get_api_key() or cfg.llm.get_api_key(),
        model=data.get("model") or cfg.memory.state_updater.model or cfg.memory.judge.model or cfg.llm.model,
        timeout_seconds=int(data.get("timeout_seconds") or cfg.memory.state_updater.timeout_seconds),
        temperature=float(data.get("temperature") if data.get("temperature") is not None else cfg.memory.state_updater.temperature),
        min_confidence=float(data.get("min_confidence") if data.get("min_confidence") is not None else cfg.memory.state_updater.min_confidence),
        prompt=data.get("prompt") or cfg.memory.state_updater.prompt,
    )
    operations = None
    if isinstance(data.get("operations"), list):
        raw_operations = []
        for item in data.get("operations"):
            if not isinstance(item, dict):
                continue
            raw = dict(item)
            if "values" not in raw and isinstance(raw.get("after"), dict):
                raw["values"] = raw.get("after")
            raw_operations.append(raw)
        operations = _parse_operations({"operations": raw_operations})
    table_result = await fill_conversation_state_tables(
        db_path=cfg.storage.sqlite.memory_db,
        conversation_id=conversation_id,
        user_message=data.get("user_message", ""),
        assistant_message=data.get("assistant_message", ""),
        config=filler_config,
        lang=cfg.language,
        dry_run=bool(data.get("preview")),
        preset_operations=operations,
    )
    return {
        "status": "ok",
        "mode": "table",
        "applied": table_result.applied,
        "skipped": table_result.skipped,
        "operations": [
            {k: v for k, v in op.__dict__.items() if v is not None}
            for op in table_result.operations
        ],
        "notes": table_result.notes,
        "preview": bool(data.get("preview")),
    }


@router.get("/admin/conversations/{conversation_id}/state/events")
async def list_conversation_state_events(
    conversation_id: str,
    request: Request,
    turn_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    """List state table change events for a conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    events = await store.list_table_events(conversation_id, turn_id=turn_id, limit=limit)
    return {"items": events}


@router.post("/admin/conversations/{conversation_id}/state/revert")
async def revert_conversation_state_events(conversation_id: str, request: Request, data: dict = Body(...)):
    """Revert state table events (undo operations)."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    event_ids = data.get("event_ids", [])
    if not event_ids:
        raise HTTPException(status_code=400, detail="event_ids required")
    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    reverted = await store.revert_table_events(conversation_id, event_ids)
    return {"status": "ok", "reverted": reverted}
