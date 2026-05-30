"""Character management routes: CRUD, defaults, merge, import/export."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Query, Request

from app.api.admin._helpers import _require_admin, _resolve_mount_selection

router = APIRouter()


@router.get("/admin/characters")
async def list_characters_api(request: Request):
    """List all known characters with their default configurations."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import list_characters

    cfg = get_config()
    items = await list_characters(cfg.storage.sqlite.app_db)
    return {"items": items}


@router.get("/admin/characters/{character_id}")
async def get_character_api(character_id: str, request: Request):
    """Get one character profile and default strategy."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import list_characters

    cfg = get_config()
    for item in await list_characters(cfg.storage.sqlite.app_db):
        if item.get("character_id") == character_id:
            return item
    raise HTTPException(status_code=404, detail="Character not found")


@router.put("/admin/characters/{character_id}")
async def update_character_api(character_id: str, request: Request, data: dict = Body(...)):
    """Update character profile fields."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import update_character_profile

    cfg = get_config()
    await update_character_profile(
        cfg.storage.sqlite.app_db,
        character_id,
        display_name=data.get("display_name"),
        aliases=data.get("aliases") or [],
        notes=data.get("notes"),
        source=data.get("source"),
        user_id=data.get("user_id") or "default",
    )
    return {"status": "ok", "character_id": character_id}


@router.delete("/admin/characters/{character_id}")
async def delete_character_api(
    character_id: str,
    request: Request,
    clear_conversations: bool = Query(default=False),
):
    """删除角色档案；默认保留已有会话、记忆和状态板数据。"""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import delete_character_profile

    cfg = get_config()
    result = await delete_character_profile(
        cfg.storage.sqlite.app_db,
        character_id,
        clear_conversations=clear_conversations,
    )
    if result.get("characters", 0) <= 0:
        return {"status": "error", "message": "角色不存在", "sync": result}
    return {"status": "ok", "sync": result}


@router.post("/admin/characters/{character_id}/merge")
async def merge_character_api(character_id: str, request: Request, data: dict = Body(...)):
    """将一个重复角色合并到当前目标角色。"""
    _require_admin(request)
    from pathlib import Path

    from app.core.state import get_config
    from app.storage.sqlite_app import list_characters, merge_character_profile
    from app.storage.sqlite_cards import merge_character_refs
    from app.storage.sqlite_conversation import merge_character_turn_refs
    from app.storage.sqlite_state import SQLiteStateStore

    source_character_id = (data.get("source_character_id") or "").strip()
    if not source_character_id:
        raise HTTPException(status_code=400, detail="缺少源角色 ID")
    if source_character_id == character_id:
        raise HTTPException(status_code=400, detail="不能合并到同一个角色")
    cfg = get_config()
    known_ids = {item.get("character_id") for item in await list_characters(cfg.storage.sqlite.app_db)}
    if source_character_id not in known_ids or character_id not in known_ids:
        raise HTTPException(status_code=404, detail="角色不存在")

    app_result = await merge_character_profile(cfg.storage.sqlite.app_db, source_character_id, character_id)
    memory_result = await merge_character_refs(cfg.storage.sqlite.memory_db, source_character_id, character_id)
    state_result = await SQLiteStateStore(cfg.storage.sqlite.memory_db).merge_character_refs(source_character_id, character_id)
    turn_count = 0
    for chat_db_path in Path(cfg.storage.root_dir, "conversations").glob("*/chat.sqlite"):
        turn_count += await merge_character_turn_refs(str(chat_db_path), source_character_id, character_id)
    return {
        "status": "ok",
        "source_character_id": source_character_id,
        "target_character_id": character_id,
        "sync": {"app": app_result, "memory": memory_result, "state": state_result, "chat_turns": turn_count},
    }


@router.get("/admin/characters/{character_id}/conversations")
async def list_character_conversations_api(character_id: str, request: Request):
    """List conversations associated with one character, including state config when present."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import list_character_conversations
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
    items = []
    for conv in await list_character_conversations(cfg.storage.sqlite.app_db, character_id):
        config = await store.get_conversation_config(conv["conversation_id"])
        row = dict(conv)
        row["config"] = config.to_dict() if config else None
        items.append(row)
    return {"items": items}


@router.get("/admin/discovered-characters")
async def discover_characters_api(request: Request):
    """Discover characters from conversations and merge default configs."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import discover_characters

    cfg = get_config()
    items = await discover_characters(cfg.storage.sqlite.app_db)
    return {"items": items}


@router.get("/admin/characters/{character_id}/defaults")
async def get_character_defaults_api(character_id: str, request: Request):
    """Get default config for a character."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import get_character_defaults

    cfg = get_config()
    defaults = await get_character_defaults(cfg.storage.sqlite.app_db, character_id)
    if not defaults:
        return {
            "character_id": character_id,
            "template_id": None,
            "library_ids": None,
            "write_library_id": None,
            "retrieval_profile_id": "balanced",
            "auto_apply": True,
        }
    return defaults


@router.post("/admin/characters/{character_id}/defaults")
async def set_character_defaults_api(character_id: str, request: Request, data: dict = Body(...)):
    """Set default template and library config for a character."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import set_character_defaults

    cfg = get_config()
    library_ids, write_library_id = await _resolve_mount_selection(cfg.storage.sqlite.memory_db, data)
    await set_character_defaults(
        cfg.storage.sqlite.app_db,
        character_id,
        profile_id=data.get("profile_id"),
        template_id=data.get("template_id"),
        table_template_id=data.get("table_template_id"),
        mount_preset_id=data.get("mount_preset_id"),
        memory_write_policy=data.get("memory_write_policy"),
        state_update_policy=data.get("state_update_policy"),
        injection_policy=data.get("injection_policy"),
        retrieval_profile_id=data.get("retrieval_profile_id"),
        library_ids=library_ids or data.get("library_ids"),
        write_library_id=write_library_id or data.get("write_library_id"),
        auto_apply=data.get("auto_apply", True),
    )
    return {"status": "ok", "character_id": character_id}


@router.put("/admin/characters/{character_id}/defaults")
async def put_character_defaults_api(character_id: str, request: Request, data: dict = Body(...)):
    return await set_character_defaults_api(character_id, request, data)


@router.post("/admin/characters/{character_id}/apply-defaults")
async def apply_character_defaults_api(character_id: str, request: Request, data: dict = Body(default_factory=dict)):
    """Apply character default mounts and conversation config to existing conversations."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import get_character_defaults, list_character_conversations
    from app.storage.sqlite_cards import set_conversation_mounts
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    defaults = await get_character_defaults(cfg.storage.sqlite.app_db, character_id)
    if not defaults:
        raise HTTPException(status_code=404, detail="Character defaults not found")

    selected = set(data.get("conversation_ids") or [])
    conversations = await list_character_conversations(cfg.storage.sqlite.app_db, character_id)
    if selected:
        conversations = [item for item in conversations if item["conversation_id"] in selected]

    apply_policy = data.get("apply_policy", True)
    apply_mounts = data.get("apply_mounts", True)
    overwrite_existing = data.get("overwrite_existing", True)
    store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
    updated = 0
    library_ids, write_library_id = await _resolve_mount_selection(cfg.storage.sqlite.memory_db, defaults)
    for conv in conversations:
        conversation_id = conv["conversation_id"]
        if apply_mounts and library_ids:
            await set_conversation_mounts(
                cfg.storage.sqlite.memory_db,
                conversation_id,
                library_ids,
                write_library_id or library_ids[0],
            )
        if apply_policy:
            existing = await store.get_conversation_config(conversation_id)
            if overwrite_existing or not existing:
                await store.set_conversation_config({
                    "conversation_id": conversation_id,
                    "profile_id": defaults.get("profile_id"),
                    "template_id": defaults.get("template_id"),
                    "table_template_id": defaults.get("table_template_id"),
                    "mount_preset_id": defaults.get("mount_preset_id"),
                    "memory_write_policy": defaults.get("memory_write_policy"),
                    "state_update_policy": defaults.get("state_update_policy"),
                    "injection_policy": defaults.get("injection_policy"),
                    "retrieval_profile_id": defaults.get("retrieval_profile_id") or "balanced",
                    "created_from_default": True,
                })
        updated += 1
    return {"status": "ok", "updated": updated}


@router.get("/admin/characters/{character_id}/export")
async def export_character_config_api(character_id: str, request: Request):
    """Export one character profile and default strategy."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import get_character_defaults, list_characters

    cfg = get_config()
    character = None
    for item in await list_characters(cfg.storage.sqlite.app_db):
        if item.get("character_id") == character_id:
            character = item
            break
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return {
        "version": 1,
        "character": character,
        "defaults": await get_character_defaults(cfg.storage.sqlite.app_db, character_id),
    }


@router.post("/admin/characters/import")
async def import_character_config_api(request: Request, data: dict = Body(...)):
    """Import one character profile and default strategy."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import set_character_defaults, update_character_profile

    cfg = get_config()
    character = data.get("character") or {}
    defaults = data.get("defaults") or {}
    character_id = data.get("target_character_id") or character.get("character_id") or defaults.get("character_id")
    if not character_id:
        raise HTTPException(status_code=400, detail="character_id is required")
    await update_character_profile(
        cfg.storage.sqlite.app_db,
        character_id,
        display_name=character.get("display_name"),
        aliases=character.get("aliases") or [],
        notes=character.get("notes"),
        source=character.get("source"),
        user_id=character.get("user_id") or "default",
    )
    await set_character_defaults(
        cfg.storage.sqlite.app_db,
        character_id,
        profile_id=defaults.get("profile_id"),
        template_id=defaults.get("template_id"),
        table_template_id=defaults.get("table_template_id"),
        mount_preset_id=defaults.get("mount_preset_id"),
        memory_write_policy=defaults.get("memory_write_policy"),
        state_update_policy=defaults.get("state_update_policy"),
        injection_policy=defaults.get("injection_policy"),
        retrieval_profile_id=defaults.get("retrieval_profile_id"),
        library_ids=defaults.get("library_ids"),
        write_library_id=defaults.get("write_library_id"),
        auto_apply=defaults.get("auto_apply", True),
    )
    return {"status": "ok", "character_id": character_id}
