"""Conversation management routes: list, config, preview, archive, delete, export/import."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query, Request

from app.api.admin._helpers import _require_admin, _resolve_mount_selection
from app.api.admin.state import _state_table_row_to_dict, _state_table_template_to_dict

router = APIRouter()


@router.get("/admin/conversations/{conversation_id}/config")
async def get_conversation_config_api(conversation_id: str, request: Request):
    """Get conversation policy config with mount summary."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    store = SQLiteStateStore(db_path)
    config = await store.ensure_conversation_config(conversation_id)
    return await _build_conversation_config_response(db_path, store, conversation_id, config)


async def _build_conversation_config_response(db_path: str, store, conversation_id: str, config):
    from app.storage.sqlite_cards import get_conversation_mounts

    mounts = await get_conversation_mounts(db_path, conversation_id)
    mounted_library_ids = [mount["library_id"] for mount in mounts]
    write_library_id = next(
        (mount["library_id"] for mount in mounts if mount.get("is_write_target")),
        mounted_library_ids[0] if mounted_library_ids else "lib_default",
    )
    table_template = await store.get_conversation_table_template(conversation_id)
    table_rows = await store.list_table_rows(
        conversation_id,
        table_template.template_id if table_template else None,
    )
    active_row_count = sum(1 for row in table_rows if row.status == "active")
    data = config.to_dict()
    data.update(
        {
            "mounted_library_ids": mounted_library_ids,
            "write_library_id": write_library_id,
            "mounts": mounts,
            "table_template_id": data.get("table_template_id")
            or (table_template.template_id if table_template else None),
            "table_template_name": table_template.name if table_template else None,
            "template_name": table_template.name if table_template else None,
            "state_row_count": active_row_count,
            "state_item_count": active_row_count,
            "is_new_session": active_row_count == 0 and mounted_library_ids == ["lib_default"],
        }
    )
    return data


@router.put("/admin/conversations/{conversation_id}/config")
async def update_conversation_config_api(conversation_id: str, request: Request, data: dict = Body(...)):
    """Update policy config for a conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_cards import set_conversation_mounts
    from app.storage.sqlite_state import SQLiteStateStore

    payload = dict(data)
    payload["conversation_id"] = conversation_id
    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    store = SQLiteStateStore(db_path)
    if payload.get("table_template_id") and not await store.get_table_template(payload["table_template_id"]):
        raise HTTPException(status_code=404, detail="State table template not found")
    library_ids, write_library_id = await _resolve_mount_selection(db_path, payload)
    if library_ids:
        await set_conversation_mounts(
            db_path,
            conversation_id=conversation_id,
            library_ids=library_ids,
            write_library_id=write_library_id,
            user_id=payload.get("user_id"),
            character_id=payload.get("character_id"),
        )
    config = await store.set_conversation_config(payload)
    config_data = await _build_conversation_config_response(db_path, store, conversation_id, config)
    return {"status": "ok", "config": config_data}


@router.post("/admin/conversations/{conversation_id}/config")
async def post_conversation_config_api(conversation_id: str, request: Request, data: dict = Body(...)):
    return await update_conversation_config_api(conversation_id, request, data)


@router.get("/admin/conversations/{conversation_id}/preview")
async def preview_conversation_api(
    conversation_id: str,
    request: Request,
    limit: int = Query(default=30, ge=1, le=100),
):
    """返回最近消息，供快速确认会话归属。"""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import list_conversations
    from app.storage.sqlite_conversation import get_conversation_message_summary, get_recent_messages

    cfg = get_config()
    conversations, _ = await list_conversations(cfg.storage.sqlite.app_db, limit=500, offset=0, status="all")
    conversation = next((item for item in conversations if item.get("conversation_id") == conversation_id), None)
    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")
    chat_db_path = str(Path(cfg.storage.root_dir, "conversations", conversation_id, "chat.sqlite"))
    messages = (
        await get_recent_messages(chat_db_path, conversation_id, limit=limit) if Path(chat_db_path).exists() else []
    )
    summary = (
        await get_conversation_message_summary(chat_db_path, conversation_id) if Path(chat_db_path).exists() else {}
    )
    return {"conversation": {**conversation, **summary}, "messages": messages}


@router.get("/admin/conversations")
async def list_conversations_api(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str = Query(default="active"),
):
    """按最近活跃时间列出会话，并补充摘要与诊断信息。"""
    _require_admin(request)
    from pathlib import Path

    from app.core.state import get_config
    from app.storage.sqlite_app import list_conversations
    from app.storage.sqlite_conversation import get_conversation_message_summary
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    if status not in {"active", "archived", "all"}:
        raise HTTPException(status_code=400, detail="会话状态只能是 active、archived 或 all")
    items, total = await list_conversations(cfg.storage.sqlite.app_db, limit=limit, offset=offset, status=status)
    store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
    for item in items:
        conversation_id = item.get("conversation_id")
        chat_db_path = Path(cfg.storage.root_dir, "conversations", conversation_id, "chat.sqlite")
        summary = (
            await get_conversation_message_summary(str(chat_db_path), conversation_id)
            if chat_db_path.exists()
            else {
                "message_count": 0,
                "turn_count": 0,
                "last_user_message": None,
                "last_assistant_message": None,
            }
        )
        config = await store.get_conversation_config(conversation_id)
        item.update(summary)
        issues = []
        if not (item.get("title") or "").strip():
            issues.append({"key": "untitled", "label": "未命名", "type": "warning"})
        if not item.get("character_id"):
            issues.append({"key": "no_character", "label": "未绑定角色", "type": "error"})
        if summary["message_count"] <= 0:
            issues.append({"key": "no_messages", "label": "无消息", "type": "default"})
        if not config:
            issues.append({"key": "no_config", "label": "未配置策略", "type": "warning"})
        elif not config.table_template_id:
            issues.append({"key": "no_template", "label": "无表格状态模板", "type": "warning"})
        item["diagnostics"] = issues
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.patch("/admin/conversations/{conversation_id}")
async def update_conversation_fields_api(conversation_id: str, request: Request, data: dict = Body(...)):
    """Update user-facing conversation profile fields."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import list_conversations, update_conversation_profile

    cfg = get_config()
    old_item = next(
        (
            item
            for item in (await list_conversations(cfg.storage.sqlite.app_db, limit=500, offset=0, status="all"))[0]
            if item.get("conversation_id") == conversation_id
        ),
        None,
    )
    item = await update_conversation_profile(
        cfg.storage.sqlite.app_db,
        conversation_id,
        title=data.get("title") if "title" in data else None,
        character_id=data.get("character_id") if "character_id" in data else None,
        status=data.get("status") if "status" in data else None,
    )
    if not item:
        return {"status": "error", "message": "会话不存在或没有可更新字段"}
    sync_result = None
    if "character_id" in data and (old_item or {}).get("character_id") != item.get("character_id"):
        from pathlib import Path

        from app.storage.sqlite_cards import update_conversation_character_refs
        from app.storage.sqlite_conversation import update_conversation_character
        from app.storage.sqlite_state import SQLiteStateStore

        chat_db_path = str(Path(cfg.storage.root_dir, "conversations", conversation_id, "chat.sqlite"))
        sync_result = {
            "app": 1,
            "chat_turns": await update_conversation_character(chat_db_path, conversation_id, item.get("character_id")),
            "memory": await update_conversation_character_refs(
                cfg.storage.sqlite.memory_db, conversation_id, item.get("character_id")
            ),
            "state": await SQLiteStateStore(cfg.storage.sqlite.memory_db).update_conversation_character_refs(
                conversation_id, item.get("character_id")
            ),
        }
    return {"status": "ok", "item": item, "sync": sync_result}


@router.delete("/admin/conversations/{conversation_id}")
async def delete_conversation_api(conversation_id: str, request: Request):
    """真正删除会话索引、聊天记录和关联状态/记忆数据。"""
    _require_admin(request)
    import shutil
    from pathlib import Path

    from app.core.state import get_config
    from app.storage.sqlite_app import delete_conversation
    from app.storage.sqlite_cards import delete_conversation_memory_data
    from app.storage.sqlite_conversation import delete_chat_db_records
    from app.storage.sqlite_state import delete_conversation_state_data

    cfg = get_config()
    conversations_dir = Path(cfg.storage.root_dir, "conversations").resolve()
    chat_dir = (conversations_dir / conversation_id).resolve()
    if chat_dir != conversations_dir and conversations_dir not in chat_dir.parents:
        raise HTTPException(status_code=400, detail="会话 ID 对应的目录不在会话存储目录内")
    chat_db_path = str(chat_dir / "chat.sqlite")
    cleanup = {
        "app": await delete_conversation(cfg.storage.sqlite.app_db, conversation_id),
        "chat": await delete_chat_db_records(chat_db_path, conversation_id),
        "memory": await delete_conversation_memory_data(cfg.storage.sqlite.memory_db, conversation_id),
        "state": await delete_conversation_state_data(cfg.storage.sqlite.memory_db, conversation_id),
        "chat_dir_removed": False,
    }
    if chat_dir.exists() and chat_dir.is_dir():
        shutil.rmtree(chat_dir)
        cleanup["chat_dir_removed"] = True
    ok = bool(cleanup["app"] or cleanup["chat_dir_removed"])
    return {"status": "ok" if ok else "error", "message": None if ok else "会话不存在", "cleanup": cleanup}


@router.post("/admin/conversations/{conversation_id}/archive")
async def archive_conversation_api(conversation_id: str, request: Request):
    """归档会话，让它默认不再出现在会话管理和状态板选择中。"""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import update_conversation_profile

    cfg = get_config()
    item = await update_conversation_profile(cfg.storage.sqlite.app_db, conversation_id, status="archived")
    if not item:
        return {"status": "error", "message": "会话不存在"}
    return {"status": "ok", "item": item}


@router.post("/admin/conversations/{conversation_id}/restore")
async def restore_conversation_api(conversation_id: str, request: Request):
    """从归档中恢复会话。"""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import update_conversation_profile

    cfg = get_config()
    item = await update_conversation_profile(cfg.storage.sqlite.app_db, conversation_id, status="active")
    if not item:
        return {"status": "error", "message": "会话不存在"}
    return {"status": "ok", "item": item}


@router.get("/admin/conversations/{conversation_id}/memory-mounts")
async def get_conversation_memory_mounts_api(conversation_id: str):
    """Get mounted long-term memory libraries for a conversation."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_conversation_mounts

    cfg = get_config()
    mounts = await get_conversation_mounts(cfg.storage.sqlite.memory_db, conversation_id)
    return {"items": mounts}


@router.post("/admin/conversations/{conversation_id}/memory-mounts")
async def set_conversation_memory_mounts_api(conversation_id: str, data: dict = Body(...)):
    """Set mounted long-term memory libraries for a conversation."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import set_conversation_mounts

    cfg = get_config()
    library_ids = data.get("library_ids") or []
    await set_conversation_mounts(
        cfg.storage.sqlite.memory_db,
        conversation_id=conversation_id,
        library_ids=library_ids,
        write_library_id=data.get("write_library_id"),
        user_id=data.get("user_id"),
        character_id=data.get("character_id"),
    )
    return {"status": "ok"}


@router.get("/admin/conversations/{conversation_id}/export")
async def export_conversation_state_bundle(conversation_id: str, request: Request):
    """Export a conversation state-board bundle: config, table-template snapshot, mounts, and table rows."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_conversation_mounts
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    store = SQLiteStateStore(db_path)
    mounts = await get_conversation_mounts(db_path, conversation_id)
    mounted_library_ids = [mount["library_id"] for mount in mounts]
    write_library_id = next(
        (mount["library_id"] for mount in mounts if mount.get("is_write_target")),
        mounted_library_ids[0] if mounted_library_ids else "lib_default",
    )
    table_template = await store.get_conversation_table_template(conversation_id)
    table_rows = await store.list_table_rows(
        conversation_id,
        table_template.template_id if table_template else None,
    )
    return {
        "format": "kokoromemo_conversation_state_v2",
        "conversation_id": conversation_id,
        "config": {
            "table_template_id": table_template.template_id if table_template else None,
            "mounted_library_ids": mounted_library_ids,
            "write_library_id": write_library_id,
        },
        "table_template": _state_table_template_to_dict(table_template) if table_template else None,
        "mounts": mounts,
        "table_rows": [_state_table_row_to_dict(row) for row in table_rows],
        "table_row_count": len(table_rows),
    }


@router.post("/admin/conversations/import")
async def import_conversation_state_bundle(request: Request, data: dict = Body(...)):
    """Import a v2 conversation state-board bundle (table-based)."""
    _require_admin(request)
    from app.core.ids import sanitize_id
    from app.core.state import get_config
    from app.memory.state_schema import StateTableRow
    from app.storage.sqlite_cards import set_conversation_mounts
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    source_conversation_id = data.get("conversation_id") or "imported"
    target_conversation_id = sanitize_id(
        data.get("target_conversation_id") or data.get("new_conversation_id") or source_conversation_id
    )
    config = data.get("config") or {}
    raw_rows = data.get("table_rows") or data.get("rows") or []

    store = SQLiteStateStore(db_path)
    exported_template = data.get("template") if isinstance(data.get("template"), dict) else {}
    table_template_id = config.get("table_template_id") or exported_template.get("template_id")
    if table_template_id and not await store.get_table_template(table_template_id):
        table_template_id = None

    if table_template_id:
        existing = await store.ensure_conversation_config(target_conversation_id)
        existing_dict = existing.to_dict()
        existing_dict["table_template_id"] = table_template_id
        existing_dict["conversation_id"] = target_conversation_id
        await store.set_conversation_config(existing_dict)

    library_ids = config.get("mounted_library_ids") or [
        mount.get("library_id") for mount in data.get("mounts", []) if mount.get("library_id")
    ]
    if library_ids:
        await set_conversation_mounts(
            db_path,
            conversation_id=target_conversation_id,
            library_ids=library_ids,
            write_library_id=config.get("write_library_id"),
        )

    imported_rows = 0
    if table_template_id:
        template = await store.get_table_template(table_template_id)
        table_by_key = {table.table_key: table for table in (template.tables if template else [])}
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            table_key = raw.get("table_key")
            table = table_by_key.get(table_key)
            if not table:
                continue
            raw_values = raw.get("values") if isinstance(raw.get("values"), dict) else None
            if raw_values is not None:
                values = {str(key): "" if value is None else str(value) for key, value in raw_values.items()}
            else:
                cells = raw.get("cells") or {}
                values = {key: (cell or {}).get("value", "") for key, cell in cells.items() if isinstance(cell, dict)}
            row = StateTableRow(
                row_id=None,
                conversation_id=target_conversation_id,
                template_id=table_template_id,
                table_id=table.table_id or "",
                table_key=table.table_key,
                status=raw.get("status", "active"),
                priority=int(raw.get("priority", table.prompt_priority)),
                confidence=float(raw.get("confidence", 0.7)),
                source="import",
                metadata={**(raw.get("metadata") or {}), "imported_from": source_conversation_id},
            )
            await store.upsert_table_row(row, values)
            imported_rows += 1

    return {
        "status": "ok",
        "conversation_id": target_conversation_id,
        "table_template_id": table_template_id,
        "imported_rows": imported_rows,
    }
