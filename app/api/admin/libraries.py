"""Library and preset routes: CRUD, export, import."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

router = APIRouter()


@router.get("/admin/memory-libraries")
async def list_memory_libraries_api():
    """List long-term memory libraries."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import list_memory_libraries

    cfg = get_config()
    items = await list_memory_libraries(cfg.storage.sqlite.memory_db)
    return {"items": items}


@router.post("/admin/memory-libraries")
async def create_memory_library_api(data: dict = Body(...)):
    """Create a memory library or save selected libraries as a new preset."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import create_memory_library

    cfg = get_config()
    library_id = await create_memory_library(
        cfg.storage.sqlite.memory_db,
        name=data.get("name") or "未命名记忆库",
        description=data.get("description", ""),
        source_library_ids=data.get("source_library_ids") or [],
    )
    return {"status": "ok", "library_id": library_id}


@router.put("/admin/memory-libraries/{library_id}")
async def update_memory_library_api(library_id: str, data: dict = Body(...)):
    """Rename or describe a memory library."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import update_memory_library

    cfg = get_config()
    ok = await update_memory_library(
        cfg.storage.sqlite.memory_db,
        library_id=library_id,
        name=data.get("name") or "未命名记忆库",
        description=data.get("description", ""),
    )
    return {"status": "ok" if ok else "error", "message": None if ok else "记忆库不存在"}


@router.delete("/admin/memory-libraries/{library_id}")
async def delete_memory_library_api(library_id: str):
    """Soft-delete a custom memory library."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import delete_memory_library

    cfg = get_config()
    ok = await delete_memory_library(cfg.storage.sqlite.memory_db, library_id)
    return {"status": "ok" if ok else "error", "message": None if ok else "默认记忆库不能删除或记忆库不存在"}


@router.get("/admin/memory-mount-presets")
async def list_memory_mount_presets_api():
    """List all active memory mount presets."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import list_mount_presets

    cfg = get_config()
    items = await list_mount_presets(cfg.storage.sqlite.memory_db)
    return {"items": items}


@router.post("/admin/memory-mount-presets")
async def create_memory_mount_preset_api(data: dict = Body(...)):
    """Create a new memory mount preset."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import create_mount_preset

    cfg = get_config()
    preset_id = await create_mount_preset(
        cfg.storage.sqlite.memory_db,
        name=data.get("name") or "未命名挂载组合",
        library_ids=data.get("library_ids") or [],
        write_library_id=data.get("write_library_id") or "",
        description=data.get("description", ""),
    )
    return {"status": "ok", "preset_id": preset_id}


@router.put("/admin/memory-mount-presets/{preset_id}")
async def update_memory_mount_preset_api(preset_id: str, data: dict = Body(...)):
    """Update a memory mount preset."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import update_mount_preset

    cfg = get_config()
    ok = await update_mount_preset(
        cfg.storage.sqlite.memory_db,
        preset_id=preset_id,
        name=data.get("name"),
        description=data.get("description"),
        library_ids=data.get("library_ids"),
        write_library_id=data.get("write_library_id"),
    )
    return {"status": "ok" if ok else "error", "message": None if ok else "预设不存在"}


@router.delete("/admin/memory-mount-presets/{preset_id}")
async def delete_memory_mount_preset_api(preset_id: str):
    """Delete a memory mount preset."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import delete_mount_preset

    cfg = get_config()
    ok = await delete_mount_preset(cfg.storage.sqlite.memory_db, preset_id)
    return {"status": "ok" if ok else "error", "message": None if ok else "预设不存在"}


@router.get("/admin/memory-libraries/{library_id}/export")
async def export_memory_library(library_id: str):
    """Export a memory library with all its cards as JSON."""
    import aiosqlite

    from app.core.state import get_config
    from app.storage.sqlite_cards import init_cards_db

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    await init_cards_db(db_path)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        lib_cursor = await db.execute(
            "SELECT * FROM memory_libraries WHERE library_id = ?", (library_id,)
        )
        lib_row = await lib_cursor.fetchone()
        if not lib_row:
            raise HTTPException(status_code=404, detail="记忆库不存在")

        cards_cursor = await db.execute(
            """SELECT * FROM memory_cards WHERE library_id = ? AND status != 'deleted'
               ORDER BY created_at ASC""",
            (library_id,),
        )
        cards = [dict(r) for r in await cards_cursor.fetchall()]

    lib = dict(lib_row)
    return {
        "format": "kokoromemo_library_v1",
        "library": {
            "library_id": lib["library_id"],
            "name": lib["name"],
            "description": lib["description"],
            "is_builtin": lib["is_builtin"],
        },
        "cards": cards,
    }


@router.post("/admin/memory-libraries/import")
async def import_memory_library(data: dict = Body(...)):
    """Import a memory library from exported JSON."""
    from app.core.ids import generate_id
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.storage.sqlite_cards import create_memory_library, insert_card, insert_card_version
    from app.storage.vector_sync import enqueue_card_vector_sync, sync_card_vector

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    library_data = data.get("library", {})
    new_library_id = await create_memory_library(
        db_path,
        name=library_data.get("name") or "导入的记忆库",
        description=library_data.get("description", ""),
    )

    imported = 0
    for card in data.get("cards", []):
        card_id = generate_id("card_")
        await insert_card(
            db_path,
            card_id=card_id,
            library_id=new_library_id,
            user_id=card.get("user_id", "default_user"),
            character_id=card.get("character_id"),
            conversation_id=card.get("conversation_id"),
            scope=card.get("scope", "global"),
            card_type=card.get("card_type", "preference"),
            content=card.get("content", ""),
            title=card.get("title"),
            summary=card.get("summary"),
            importance=float(card.get("importance", 0.5)),
            confidence=float(card.get("confidence", 0.7)),
            status=card.get("status", "approved"),
            is_pinned=int(card.get("is_pinned", 0)),
            evidence_text=card.get("evidence_text"),
        )
        await insert_card_version(
            db_path,
            card_id=card_id,
            content=card.get("content", ""),
            card_type=card.get("card_type", "preference"),
            summary=card.get("summary"),
            importance=float(card.get("importance", 0.5)),
            confidence=float(card.get("confidence", 0.7)),
        )
        if card.get("status", "approved") == "approved":
            ep = get_embedding_provider(cfg)
            store = get_lancedb_store(cfg)
            if ep and store:
                try:
                    await sync_card_vector(db_path, card_id, ep, store)
                except Exception as exc:
                    await enqueue_card_vector_sync(db_path, card_id, str(exc))
        imported += 1

    return {"status": "ok", "library_id": new_library_id, "imported_cards": imported}


@router.get("/admin/memory-mount-presets/{preset_id}/export")
async def export_mount_preset(preset_id: str):
    """Export a memory mount preset as JSON."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_mount_preset

    cfg = get_config()
    preset = await get_mount_preset(cfg.storage.sqlite.memory_db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")

    return {
        "format": "kokoromemo_mount_preset_v1",
        "preset": {
            "name": preset["name"],
            "description": preset["description"],
            "library_ids_json": preset["library_ids_json"],
            "write_library_id": preset["write_library_id"],
        },
    }


@router.post("/admin/memory-mount-presets/import")
async def import_mount_preset(data: dict = Body(...)):
    """Import a memory mount preset from exported JSON."""
    import json as json_mod

    from app.core.state import get_config
    from app.storage.sqlite_cards import create_mount_preset

    preset_data = data.get("preset", data)
    library_ids = json_mod.loads(preset_data.get("library_ids_json", "[]"))

    cfg = get_config()
    preset_id = await create_mount_preset(
        cfg.storage.sqlite.memory_db,
        name=preset_data.get("name") or "导入的挂载组合",
        library_ids=library_ids,
        write_library_id=preset_data.get("write_library_id") or (library_ids[0] if library_ids else "lib_default"),
        description=preset_data.get("description", ""),
    )
    return {"status": "ok", "preset_id": preset_id}
