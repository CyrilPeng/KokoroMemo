"""Health check and admin routes."""

from __future__ import annotations

from pathlib import Path

import httpx
import yaml
from fastapi import APIRouter, Query, Body, Request, HTTPException

router = APIRouter()


def _require_admin(request: Request) -> None:
    """Require Bearer token only when ADMIN_TOKEN/admin_token is configured."""
    from app.core.state import get_config

    token = get_config().server.get_admin_token()
    if not token:
        return
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/health")
async def health():
    from app.core.state import get_config

    cfg = get_config()
    return {
        "status": "ok",
        "server": "ok",
        "embedding": {
            "enabled": cfg.embedding.enabled,
            "model": cfg.embedding.model,
            "dimension": cfg.embedding.dimension,
        },
        "rerank": {
            "enabled": cfg.rerank.enabled,
            "model": cfg.rerank.model if cfg.rerank.enabled else None,
        },
        "llm": {"model": cfg.llm.model},
        "server_port": cfg.server.port,
    }


@router.get("/admin/stats")
async def get_stats(request: Request):
    """Return memory system statistics for the dashboard."""
    _require_admin(request)
    import aiosqlite
    from app.core.state import get_config

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    result: dict = {}

    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT status, COUNT(*) FROM memory_cards GROUP BY status")
            result["cards_by_status"] = dict(await cursor.fetchall())

            cursor = await db.execute(
                "SELECT card_type, COUNT(*) FROM memory_cards WHERE status='approved' GROUP BY card_type"
            )
            result["cards_by_type"] = dict(await cursor.fetchall())

            cursor = await db.execute("SELECT COUNT(*) FROM memory_inbox WHERE status='pending'")
            row = await cursor.fetchone()
            result["inbox_pending"] = row[0] if row else 0

            cursor = await db.execute(
                "SELECT vector_synced, COUNT(*) FROM memory_cards WHERE status='approved' GROUP BY vector_synced"
            )
            result["sync_status"] = dict(await cursor.fetchall())

            cursor = await db.execute(
                "SELECT date(created_at) as day, COUNT(*) FROM memory_cards "
                "WHERE status='approved' AND created_at >= datetime('now', '-7 days') "
                "GROUP BY day ORDER BY day"
            )
            result["daily_growth"] = [{"date": r[0], "count": r[1]} for r in await cursor.fetchall()]

            cursor = await db.execute(
                "SELECT should_retrieve, COUNT(*) FROM retrieval_decisions "
                "WHERE created_at >= datetime('now', '-24 hours') GROUP BY should_retrieve"
            )
            result["gate_stats_24h"] = dict(await cursor.fetchall())
    except Exception:
        result.setdefault("cards_by_status", {})
        result.setdefault("inbox_pending", 0)

    return result


async def _fetch_models_from_remote(base_url: str, api_key: str, provider: str | None = None):
    """Fetch available models from a remote models endpoint."""
    if not api_key:
        return {"status": "error", "message": "未提供 API Key", "models": []}

    base_url = base_url.rstrip("/")
    is_gemini = provider == "gemini" or "googleapis.com" in base_url or "generativelanguage" in base_url
    is_anthropic = provider == "anthropic" or "anthropic.com" in base_url

    if is_gemini:
        url = base_url + "/models?key=" + api_key
        headers = {}
    elif is_anthropic:
        url = base_url + "/models"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    else:
        url = base_url + "/models"
        headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                body = resp.text[:200]
                return {"status": "error", "message": f"远端返回 HTTP {resp.status_code}: {body}", "models": []}
            data = resp.json()

            models = []
            if is_gemini:
                for item in data.get("models", []):
                    if isinstance(item, dict) and "name" in item:
                        name = item["name"]
                        if name.startswith("models/"):
                            name = name[7:]
                        models.append(name)
            else:
                items = data.get("data", []) if isinstance(data, dict) else []
                for item in items:
                    if isinstance(item, dict) and "id" in item:
                        models.append(item["id"])
                    elif isinstance(item, str):
                        models.append(item)

            return {"status": "ok", "models": sorted(models)}
    except httpx.TimeoutException:
        return {"status": "error", "message": "请求超时，请检查 Base URL", "models": []}
    except Exception as e:
        return {"status": "error", "message": str(e), "models": []}


@router.post("/admin/fetch-models")
async def fetch_models(data: dict = Body(...)):
    """Fetch remote models without putting API keys in URLs."""
    return await _fetch_models_from_remote(data.get("base_url", ""), data.get("api_key", ""), data.get("provider"))


@router.get("/admin/fetch-models")
async def fetch_models_legacy(
    base_url: str = Query(...),
    api_key: str = Query(default=""),
):
    """Legacy compatibility endpoint. Prefer POST /admin/fetch-models."""
    return await _fetch_models_from_remote(base_url, api_key)


@router.get("/admin/config")
async def get_current_config():
    """Return current configuration (safe fields only)."""
    from app.core.services import resolve_lancedb_path
    from app.core.state import get_config

    cfg = get_config()
    llm_key = cfg.llm.get_api_key()
    embedding_key = cfg.embedding.get_api_key()
    rerank_key = cfg.rerank.get_api_key()
    return {
        "server": {"host": cfg.server.host, "port": cfg.server.port, "webui_port": cfg.server.webui_port, "timezone": cfg.server.timezone},
        "storage": {"root_dir": cfg.storage.root_dir},
        "vector_index": {"path": resolve_lancedb_path(cfg), "table": cfg.storage.lancedb.table},
        "embedding": {
            "enabled": cfg.embedding.enabled,
            "provider": cfg.embedding.provider,
            "base_url": cfg.embedding.base_url,
            "api_key": cfg.embedding.api_key,
            "api_key_set": bool(embedding_key),
            "model": cfg.embedding.model,
            "dimension": cfg.embedding.dimension,
        },
        "rerank": {
            "enabled": cfg.rerank.enabled,
            "provider": cfg.rerank.provider,
            "base_url": cfg.rerank.base_url,
            "api_key": cfg.rerank.api_key,
            "api_key_set": bool(rerank_key),
            "model": cfg.rerank.model,
            "max_documents_per_request": cfg.rerank.max_documents_per_request,
        },
        "memory": {
            "enabled": cfg.memory.enabled,
            "final_top_k": cfg.memory.final_top_k,
            "max_injected_chars": cfg.memory.max_injected_chars,
            "judge": {
                "enabled": cfg.memory.judge.enabled,
                "provider": cfg.memory.judge.provider,
                "base_url": cfg.memory.judge.base_url,
                "api_key": cfg.memory.judge.api_key,
                "api_key_set": bool(cfg.memory.judge.get_api_key()),
                "model": cfg.memory.judge.model,
                "timeout_seconds": cfg.memory.judge.timeout_seconds,
                "temperature": cfg.memory.judge.temperature,
                "mode": cfg.memory.judge.mode,
                "user_rules": cfg.memory.judge.user_rules,
                "prompt": cfg.memory.judge.prompt,
            },
            "state_updater": {
                "enabled": cfg.memory.state_updater.enabled,
                "mode": cfg.memory.state_updater.mode,
                "update_after_each_turn": cfg.memory.state_updater.update_after_each_turn,
                "update_every_n_turns": cfg.memory.state_updater.update_every_n_turns,
                "min_confidence": cfg.memory.state_updater.min_confidence,
                "max_state_items_per_conversation": cfg.memory.state_updater.max_state_items_per_conversation,
                "provider": cfg.memory.state_updater.provider,
                "base_url": cfg.memory.state_updater.base_url,
                "api_key": cfg.memory.state_updater.api_key,
                "api_key_set": bool(cfg.memory.state_updater.get_api_key()),
                "model": cfg.memory.state_updater.model,
                "timeout_seconds": cfg.memory.state_updater.timeout_seconds,
                "temperature": cfg.memory.state_updater.temperature,
                "prompt": cfg.memory.state_updater.prompt,
            },
        },
        "llm": {
            "forward_mode": cfg.llm.forward_mode,
            "provider": cfg.llm.provider,
            "base_url": cfg.llm.base_url,
            "api_key": cfg.llm.api_key,
            "api_key_set": bool(llm_key),
            "model": cfg.llm.model,
        },
    }


@router.post("/admin/config")
async def save_config(data: dict = Body(...)):
    """Save configuration to config.yaml and reload."""
    from app.core.config import load_config, _merge_dataclass
    from app.core.services import reset_services
    from app.core.state import get_config, set_config

    cfg = get_config()

    # Find config file path
    config_path = Path("config.yaml")
    if not config_path.exists():
        config_path = Path("config.example.yaml")

    # Read existing YAML
    existing = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}

    # Detect if restart-requiring fields changed
    old_root_dir = cfg.storage.root_dir
    old_port = cfg.server.port

    # Merge incoming data into existing config
    if "server" in data:
        existing.setdefault("server", {}).update(data["server"])
    if "llm" in data:
        existing.setdefault("llm", {}).update(data["llm"])
    if "embedding" in data:
        existing.setdefault("embedding", {}).update(data["embedding"])
    if "rerank" in data:
        existing.setdefault("rerank", {}).update(data["rerank"])
    if "memory" in data:
        existing.setdefault("memory", {}).update(data["memory"])
    if "storage" in data:
        existing.setdefault("storage", {}).update(data["storage"])

    # Write to config.yaml
    out_path = Path("config.yaml")
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(existing, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # Reload config in memory
    new_cfg = load_config(str(out_path))
    set_config(new_cfg)
    from app.core.time_util import set_configured_timezone
    set_configured_timezone(new_cfg.server.timezone or None)
    reset_services()

    # Check if restart is needed
    needs_restart = (
        new_cfg.storage.root_dir != old_root_dir
        or new_cfg.server.port != old_port
    )

    if needs_restart:
        import asyncio
        import os
        import sys
        import logging

        logger = logging.getLogger("kokoromemo")
        logger.info("配置变更需要重启服务（存储目录或端口已更改）")

        async def _delayed_restart():
            await asyncio.sleep(1)  # Give response time to reach client
            logger.info("正在重启服务...")
            os.execv(sys.executable, [sys.executable] + sys.argv)

        asyncio.get_event_loop().create_task(_delayed_restart())
        return {"status": "ok", "message": "配置已保存，服务正在重启..."}

    return {"status": "ok", "message": "配置已保存并生效"}


@router.get("/admin/memories")
async def list_memories(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    library_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    character_id: str | None = Query(default=None),
    status: str = Query(default="approved"),
):
    """List memory cards."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import init_cards_db
    import aiosqlite

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    await init_cards_db(db_path)

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            where_clauses = ["status = ?"]
            params: list = [status]

            if scope:
                where_clauses.append("scope = ?")
                params.append(scope)
            if library_id:
                where_clauses.append("library_id = ?")
                params.append(library_id)
            if character_id:
                where_clauses.append("character_id = ?")
                params.append(character_id)

            where_sql = " AND ".join(where_clauses)

            count_cursor = await db.execute(
                f"SELECT COUNT(*) FROM memory_cards WHERE {where_sql}",
                params,
            )
            count_row = await count_cursor.fetchone()
            total = count_row[0] if count_row else 0

            params.extend([limit, offset])
            cursor = await db.execute(
                f"SELECT * FROM memory_cards WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params,
            )
            rows = await cursor.fetchall()

            memories = []
            for r in rows:
                memories.append({
                    "memory_id": r["card_id"],
                    "card_id": r["card_id"],
                    "library_id": r["library_id"],
                    "user_id": r["user_id"],
                    "character_id": r["character_id"],
                    "conversation_id": r["conversation_id"],
                    "scope": r["scope"],
                    "memory_type": r["card_type"],
                    "content": r["content"],
                    "summary": r["summary"],
                    "importance": r["importance"],
                    "confidence": r["confidence"],
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "access_count": r["access_count"],
                })

            return {"memories": memories, "total": total, "limit": limit, "offset": offset}
    except Exception:
        return {"memories": [], "total": 0, "limit": limit, "offset": offset}


@router.get("/admin/characters")
async def list_characters_api(request: Request):
    """List all known characters with their default configurations."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import list_characters

    cfg = get_config()
    items = await list_characters(cfg.storage.sqlite.app_db)
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
        return {"character_id": character_id, "template_id": None, "library_ids": None, "write_library_id": None, "auto_apply": True}
    return defaults


@router.post("/admin/characters/{character_id}/defaults")
async def set_character_defaults_api(character_id: str, request: Request, data: dict = Body(...)):
    """Set default template and library config for a character."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import set_character_defaults

    cfg = get_config()
    await set_character_defaults(
        cfg.storage.sqlite.app_db,
        character_id,
        template_id=data.get("template_id"),
        library_ids=data.get("library_ids"),
        write_library_id=data.get("write_library_id"),
        auto_apply=data.get("auto_apply", True),
    )
    return {"status": "ok", "character_id": character_id}


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


@router.get("/admin/conversations")
async def list_conversations_api(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List recent conversations ordered by last activity."""
    from app.core.state import get_config
    from app.storage.sqlite_app import list_conversations

    cfg = get_config()
    items, total = await list_conversations(cfg.storage.sqlite.app_db, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.delete("/admin/conversations/{conversation_id}")
async def delete_conversation_api(conversation_id: str):
    """Delete a conversation record."""
    from app.core.state import get_config
    from app.storage.sqlite_app import delete_conversation

    cfg = get_config()
    ok = await delete_conversation(cfg.storage.sqlite.app_db, conversation_id)
    return {"status": "ok" if ok else "error", "message": None if ok else "会话不存在"}


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


@router.post("/admin/memories")
async def create_memory_card(data: dict = Body(...)):
    """Manually create an approved memory card."""
    from app.core.ids import generate_id
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.storage.sqlite_cards import insert_card, insert_card_version
    from app.storage.vector_sync import enqueue_card_vector_sync, sync_card_vector

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    card_id = generate_id("card_")
    await insert_card(
        db_path,
        card_id=card_id,
        library_id=data.get("library_id"),
        user_id=data.get("user_id") or "default_user",
        character_id=data.get("character_id"),
        conversation_id=data.get("conversation_id"),
        scope=data.get("scope", "global"),
        card_type=data.get("card_type", "preference"),
        title=data.get("title"),
        content=data.get("content", ""),
        summary=data.get("summary"),
        importance=float(data.get("importance", 0.5)),
        confidence=float(data.get("confidence", 0.7)),
        status=data.get("status", "approved"),
        is_pinned=1 if data.get("is_pinned") else 0,
        evidence_text=data.get("evidence_text"),
    )
    await insert_card_version(
        db_path,
        card_id=card_id,
        content=data.get("content", ""),
        card_type=data.get("card_type", "preference"),
        summary=data.get("summary"),
        importance=float(data.get("importance", 0.5)),
        confidence=float(data.get("confidence", 0.7)),
    )
    if data.get("status", "approved") == "approved":
        ep = get_embedding_provider(cfg)
        store = get_lancedb_store(cfg)
        if ep and store:
            try:
                await sync_card_vector(db_path, card_id, ep, store)
            except Exception as exc:
                await enqueue_card_vector_sync(db_path, card_id, str(exc))
    return {"status": "ok", "card_id": card_id}


@router.put("/admin/memories/{card_id}")
async def update_memory_card(card_id: str, data: dict = Body(...)):
    """Edit a memory card's content, type, or importance."""
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.storage.sqlite_cards import insert_card_version, mark_card_vector_unsynced
    from app.storage.vector_sync import enqueue_card_vector_sync, sync_card_vector
    import aiosqlite

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    allowed_fields = {"library_id", "content", "card_type", "scope", "importance", "confidence", "title", "summary", "is_pinned"}
    updates = {k: v for k, v in data.items() if k in allowed_fields}
    if not updates:
        return {"status": "error", "message": "无可更新字段"}

    set_clauses = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [card_id]

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            f"UPDATE memory_cards SET {set_clauses}, updated_at = datetime('now', 'localtime') WHERE card_id = ?",
            values,
        )
        await db.commit()

        cursor = await db.execute("SELECT * FROM memory_cards WHERE card_id = ?", (card_id,))
        row = await cursor.fetchone()

    if row and row["status"] == "approved":
        await insert_card_version(
            db_path,
            card_id=row["card_id"],
            content=row["content"],
            card_type=row["card_type"],
            summary=row["summary"],
            importance=row["importance"],
            confidence=row["confidence"],
        )
        ep = get_embedding_provider(cfg)
        store = get_lancedb_store(cfg)
        if ep and store:
            try:
                await sync_card_vector(db_path, card_id, ep, store)
            except Exception as exc:
                await mark_card_vector_unsynced(db_path, card_id)
                await enqueue_card_vector_sync(db_path, card_id, str(exc))

    return {"status": "ok", "card_id": card_id}


@router.delete("/admin/memories/{card_id}")
async def delete_memory_card(card_id: str):
    """Soft-delete a memory card."""
    from app.core.services import get_lancedb_store
    from app.core.state import get_config
    import aiosqlite

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE memory_cards SET status = 'deleted', updated_at = datetime('now', 'localtime') WHERE card_id = ?",
            (card_id,),
        )
        await db.commit()

    store = get_lancedb_store(cfg)
    if store:
        try:
            store.delete(f"memory_id = '{card_id}'")
        except Exception:
            pass

    return {"status": "ok"}


@router.post("/admin/memories/{card_id}/deprecate")
async def deprecate_memory_card(card_id: str, note: str = Body(default="")):
    """Mark a memory card as deprecated so it is no longer recalled by default."""
    from app.core.services import get_lancedb_store
    from app.core.state import get_config
    from app.storage.sqlite_cards import insert_review_action
    import aiosqlite

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE memory_cards SET status = 'deprecated', updated_at = datetime('now', 'localtime') WHERE card_id = ?",
            (card_id,),
        )
        await db.commit()

    await insert_review_action(db_path, action="deprecate", card_id=card_id, note=note)

    store = get_lancedb_store(cfg)
    if store:
        try:
            store.delete(f"memory_id = '{card_id}'")
        except Exception:
            pass

    return {"status": "ok", "card_id": card_id}


@router.post("/admin/rebuild-vector-index")
async def rebuild_index():
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.storage.rebuild_v2 import rebuild_vector_index_v2

    cfg = get_config()
    ep = get_embedding_provider(cfg)
    store = get_lancedb_store(cfg)
    if not ep or not store:
        return {"status": "error", "message": "Embedding or LanceDB not configured"}

    result = await rebuild_vector_index_v2(
        cfg.storage.sqlite.memory_db, store, ep, batch_size=cfg.embedding.batch_size,
    )
    return result


@router.get("/admin/index-migration-status")
async def get_index_migration_status_api(request: Request):
    """Check the status of an ongoing or completed index migration."""
    _require_admin(request)
    from app.core.services import get_index_migration_status

    status = get_index_migration_status()
    if not status:
        return {"status": "idle", "message": "No migration in progress"}
    return status


# --- Inbox API ---

@router.get("/admin/inbox")
async def list_inbox(
    status: str = Query(default="pending"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List memory inbox items."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_inbox_items

    cfg = get_config()
    items, total = await get_inbox_items(cfg.storage.sqlite.memory_db, status=status, limit=limit, offset=offset)
    return {"items": items, "total": total, "status": status}


@router.post("/admin/inbox/{inbox_id}/approve")
async def approve_inbox_item(inbox_id: str):
    """Approve an inbox item → create approved card + vector sync."""
    import json as json_mod
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.core.ids import generate_id
    from app.storage.sqlite_cards import (
        get_inbox_item, update_inbox_status, insert_card, insert_card_version,
        insert_review_action, get_write_library_id,
    )
    from app.storage.vector_sync import enqueue_card_vector_sync, sync_card_vector

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    item = await get_inbox_item(db_path, inbox_id)
    if not item:
        return {"status": "error", "message": "Inbox item not found"}
    if item["status"] != "pending":
        return {"status": "error", "message": f"Item already {item['status']}"}

    payload = json_mod.loads(item["payload_json"])

    # Create approved card
    card_id = generate_id("card_")
    library_id = payload.get("library_id") or await get_write_library_id(db_path, payload.get("conversation_id") or "default")
    await insert_card(
        db_path,
        card_id=card_id,
        library_id=library_id,
        user_id=payload.get("user_id", ""),
        character_id=payload.get("character_id"),
        conversation_id=payload.get("conversation_id"),
        scope=payload.get("scope", "global"),
        card_type=payload.get("card_type", "preference"),
        content=payload.get("content", ""),
        importance=payload.get("importance", 0.5),
        confidence=payload.get("confidence", 0.7),
        status="approved",
        evidence_text=payload.get("evidence_text"),
    )
    await insert_card_version(
        db_path,
        card_id=card_id,
        content=payload.get("content", ""),
        card_type=payload.get("card_type", "preference"),
        summary=payload.get("summary"),
        importance=payload.get("importance", 0.5),
        confidence=payload.get("confidence", 0.7),
    )

    # Vector sync
    warning = None
    ep = get_embedding_provider(cfg)
    store = get_lancedb_store(cfg)
    if ep and store:
        try:
            await sync_card_vector(db_path, card_id, ep, store)
        except Exception as e:
            warning = f"Vector sync failed: {e}"
            await enqueue_card_vector_sync(db_path, card_id, str(e))

    # Mark inbox item as approved
    await update_inbox_status(db_path, inbox_id, "approved")
    await insert_review_action(db_path, action="approve", inbox_id=inbox_id, card_id=card_id)
    result = {"status": "ok", "card_id": card_id}
    if warning:
        result["warning"] = warning
    return result


@router.post("/admin/jobs/retry-vector-sync")
async def retry_vector_sync_jobs(limit: int = Query(default=50, le=200)):
    """Retry failed/pending card vector sync jobs."""
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.storage.vector_sync import retry_card_vector_sync_jobs

    cfg = get_config()
    ep = get_embedding_provider(cfg)
    store = get_lancedb_store(cfg)
    if not ep or not store:
        return {"status": "error", "message": "Embedding or LanceDB not configured"}
    return await retry_card_vector_sync_jobs(cfg.storage.sqlite.memory_db, ep, store, limit=limit)


# --- Conversation State API ---

def _state_item_to_dict(item) -> dict:
    return {
        "item_id": item.item_id,
        "template_id": item.template_id,
        "tab_id": item.tab_id,
        "field_id": item.field_id,
        "field_key": item.field_key,
        "user_id": item.user_id,
        "character_id": item.character_id,
        "world_id": item.world_id,
        "conversation_id": item.conversation_id,
        "category": item.category,
        "item_key": item.item_key,
        "item_value": item.content,
        "content": item.content,
        "title": item.title,
        "status": item.status,
        "priority": item.priority,
        "user_locked": item.user_locked,
        "confidence": item.confidence,
        "source": item.source,
        "source_turn_ids": item.source_turn_ids,
        "source_message_ids": item.source_message_ids,
        "linked_card_ids": item.linked_card_ids,
        "linked_summary_ids": item.linked_summary_ids,
        "metadata": item.metadata,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "last_injected_at": item.last_injected_at,
        "expires_at": item.expires_at,
    }


def _field_to_dict(field) -> dict:
    return {
        "field_id": field.field_id,
        "template_id": field.template_id,
        "tab_id": field.tab_id,
        "field_key": field.field_key,
        "label": field.label,
        "field_type": field.field_type,
        "description": field.description,
        "ai_writable": field.ai_writable,
        "include_in_prompt": field.include_in_prompt,
        "sort_order": field.sort_order,
        "default_value": field.default_value,
        "options": field.options,
        "status": field.status,
    }


def _tab_to_dict(tab) -> dict:
    return {
        "tab_id": tab.tab_id,
        "template_id": tab.template_id,
        "tab_key": tab.tab_key,
        "label": tab.label,
        "description": tab.description,
        "sort_order": tab.sort_order,
        "fields": [_field_to_dict(field) for field in tab.fields],
    }


def _template_to_dict(template, include_tabs: bool = True) -> dict:
    data = {
        "template_id": template.template_id,
        "name": template.name,
        "description": template.description,
        "is_builtin": template.is_builtin,
        "status": template.status,
    }
    if include_tabs:
        data["tabs"] = [_tab_to_dict(tab) for tab in template.tabs]
    return data


def _template_from_payload(data: dict):
    from app.memory.state_schema import StateBoardField, StateBoardTab, StateBoardTemplate

    template = StateBoardTemplate(
        template_id=data.get("template_id"),
        name=data.get("name", "未命名模板"),
        description=data.get("description", ""),
        is_builtin=bool(data.get("is_builtin", False)),
        status=data.get("status", "active"),
    )
    for tab_data in data.get("tabs", []):
        tab = StateBoardTab(
            tab_id=tab_data.get("tab_id"),
            template_id=template.template_id or "",
            tab_key=tab_data.get("tab_key") or tab_data.get("label") or "tab",
            label=tab_data.get("label") or tab_data.get("tab_key") or "标签页",
            description=tab_data.get("description", ""),
            sort_order=int(tab_data.get("sort_order", 0)),
        )
        for field_data in tab_data.get("fields", []):
            tab.fields.append(StateBoardField(
                field_id=field_data.get("field_id"),
                template_id=template.template_id or "",
                tab_id=tab.tab_id or "",
                field_key=field_data.get("field_key") or field_data.get("label") or "field",
                label=field_data.get("label") or field_data.get("field_key") or "字段",
                field_type=field_data.get("field_type", "multiline"),
                description=field_data.get("description", ""),
                ai_writable=bool(field_data.get("ai_writable", True)),
                include_in_prompt=bool(field_data.get("include_in_prompt", True)),
                sort_order=int(field_data.get("sort_order", 0)),
                default_value=field_data.get("default_value", ""),
                options=field_data.get("options", {}),
                status=field_data.get("status", "active"),
            ))
        template.tabs.append(tab)
    return template


@router.get("/admin/state/templates")
async def list_state_templates(request: Request):
    """List available state board templates."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    templates = await store.list_templates()
    return {"items": [_template_to_dict(template, include_tabs=False) for template in templates]}


@router.get("/admin/state/templates/{template_id}")
async def get_state_template(template_id: str, request: Request):
    """Get a full state board template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    template = await SQLiteStateStore(get_config().storage.sqlite.memory_db).get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return _template_to_dict(template)


@router.post("/admin/state/templates")
async def create_state_template(request: Request, data: dict = Body(...)):
    """Create or update a custom state board template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    template_id = await SQLiteStateStore(get_config().storage.sqlite.memory_db).save_template(_template_from_payload(data))
    return {"status": "ok", "template_id": template_id}


@router.delete("/admin/state/templates/{template_id}")
async def delete_state_template(template_id: str, request: Request):
    """Soft-delete a custom state board template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    ok = await SQLiteStateStore(get_config().storage.sqlite.memory_db).update_template_status(template_id, "deleted")
    return {"status": "ok" if ok else "error", "message": None if ok else "内置模板不能删除或模板不存在"}


@router.get("/admin/conversations/{conversation_id}/state/template")
async def get_conversation_state_template(conversation_id: str, request: Request):
    """Get the template selected for a conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    template = await SQLiteStateStore(get_config().storage.sqlite.memory_db).get_conversation_template(conversation_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return _template_to_dict(template)


@router.post("/admin/conversations/{conversation_id}/state/template")
async def set_conversation_state_template(conversation_id: str, request: Request, data: dict = Body(...)):
    """Select a state board template for a conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    template_id = data.get("template_id")
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id is required")
    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    if not await store.get_template(template_id):
        raise HTTPException(status_code=404, detail="Template not found")
    await store.set_conversation_template(conversation_id, template_id)
    return {"status": "ok", "template_id": template_id}


@router.get("/admin/conversations/{conversation_id}/state")
async def get_conversation_state(
    conversation_id: str,
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=200, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List hot-state items for a conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
    items, total = await store.list_items(conversation_id, status=status, limit=limit, offset=offset)
    return {"items": [_state_item_to_dict(item) for item in items], "total": total, "limit": limit, "offset": offset}


@router.get("/admin/conversations/{conversation_id}/state/events")
async def get_conversation_state_events(
    conversation_id: str,
    request: Request,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List hot-state change events."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    events, total = await store.list_state_events(conversation_id, limit=limit, offset=offset)
    return {"items": events, "total": total, "limit": limit, "offset": offset}


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


@router.post("/admin/conversations/{conversation_id}/state")
async def create_conversation_state_item(conversation_id: str, request: Request, data: dict = Body(...)):
    """Manually create or upsert a hot-state item."""
    _require_admin(request)
    from app.core.state import get_config
    from app.memory.state_schema import ConversationStateItem
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    item_id = await store.upsert_item(ConversationStateItem(
        item_id=data.get("item_id"),
        template_id=data.get("template_id"),
        tab_id=data.get("tab_id"),
        field_id=data.get("field_id"),
        field_key=data.get("field_key"),
        user_id=data.get("user_id"),
        character_id=data.get("character_id"),
        world_id=data.get("world_id"),
        conversation_id=conversation_id,
        category=data.get("category", "scene"),
        item_key=data.get("item_key"),
        title=data.get("title"),
        content=data.get("item_value") or data.get("content", ""),
        status=data.get("status", "active"),
        priority=int(data.get("priority", 50)),
        user_locked=bool(data.get("user_locked", False)),
        confidence=float(data.get("confidence", 0.8)),
        source="manual",
        linked_card_ids=data.get("linked_card_ids", []),
        linked_summary_ids=data.get("linked_summary_ids", []),
        metadata=data.get("metadata", {}),
        expires_at=data.get("expires_at"),
    ))
    return {"status": "ok", "item_id": item_id}


@router.patch("/admin/state/{item_id}")
async def update_conversation_state_item(item_id: str, request: Request, data: dict = Body(...)):
    """Edit a hot-state item."""
    _require_admin(request)
    import json as json_mod
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    updates = dict(data)
    if "linked_card_ids" in updates:
        updates["linked_card_ids_json"] = json_mod.dumps(updates.pop("linked_card_ids"), ensure_ascii=False)
    if "linked_summary_ids" in updates:
        updates["linked_summary_ids_json"] = json_mod.dumps(updates.pop("linked_summary_ids"), ensure_ascii=False)
    if "metadata" in updates:
        updates["metadata_json"] = json_mod.dumps(updates.pop("metadata"), ensure_ascii=False)
    if "user_locked" in updates:
        updates["user_locked"] = 1 if updates["user_locked"] else 0
    if "item_value" in updates and "content" not in updates:
        updates["content"] = updates["item_value"]
    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    ok = await store.update_item(item_id, updates)
    return {"status": "ok" if ok else "error", "message": None if ok else "State item not found or no fields updated"}


@router.post("/admin/state/{item_id}/resolve")
async def resolve_conversation_state_item(item_id: str, request: Request, data: dict = Body(default={})):
    """Mark a hot-state item as resolved."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    await SQLiteStateStore(get_config().storage.sqlite.memory_db).resolve_item(item_id, data.get("reason"))
    return {"status": "ok"}


@router.delete("/admin/state/{item_id}")
async def delete_conversation_state_item(item_id: str, request: Request):
    """Soft-delete a hot-state item."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    await SQLiteStateStore(get_config().storage.sqlite.memory_db).delete_item(item_id, "manual_delete")
    return {"status": "ok"}


@router.get("/admin/conversations/{conversation_id}/state/preview")
async def preview_state_board(conversation_id: str, request: Request):
    """Return the rendered state board text as it would be injected into the LLM prompt."""
    _require_admin(request)
    from app.core.state import get_config
    from app.memory.state_renderer import render_state_board
    from app.memory.state_schema import StateRenderOptions
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
    items = await store.list_active_items(conversation_id)
    template = await store.get_conversation_template(conversation_id)
    hot = cfg.memory.hot_context
    text = render_state_board(
        items,
        StateRenderOptions(
            max_chars=hot.max_chars,
            include_sections=hot.include_sections,
            section_order=hot.section_order,
            max_items_per_section=hot.max_items_per_section,
        ),
        template,
        lang=cfg.language,
    )
    return {
        "preview": text,
        "char_count": len(text),
        "max_chars": hot.max_chars,
        "item_count": len(items),
    }


@router.post("/admin/conversations/{conversation_id}/state/rebuild")
async def rebuild_conversation_state(conversation_id: str, request: Request, data: dict = Body(default={})):
    """Rebuild hot-state by projecting approved boundary/preference cards."""
    _require_admin(request)
    from app.core.state import get_config
    from app.memory.state_projector import project_cards_to_state

    cfg = get_config()
    result = await project_cards_to_state(
        cfg.storage.sqlite.memory_db,
        conversation_id=conversation_id,
        user_id=data.get("user_id"),
        character_id=data.get("character_id"),
    )
    return {"status": "ok", **result}


@router.post("/admin/conversations/{conversation_id}/state/fill")
async def fill_conversation_state_once(conversation_id: str, request: Request, data: dict = Body(...)):
    """Manually run the model-driven state board filler."""
    _require_admin(request)
    from app.core.state import get_config
    from app.memory.state_filler import StateFillerConfigView, fill_conversation_state

    cfg = get_config()
    result = await fill_conversation_state(
        db_path=cfg.storage.sqlite.memory_db,
        conversation_id=conversation_id,
        user_id=data.get("user_id"),
        character_id=data.get("character_id"),
        user_message=data.get("user_message", ""),
        assistant_message=data.get("assistant_message", ""),
        config=StateFillerConfigView(
            provider=data.get("provider") or cfg.memory.state_updater.provider,
            base_url=data.get("base_url") or cfg.memory.state_updater.base_url or cfg.memory.judge.base_url or cfg.llm.base_url,
            api_key=data.get("api_key") or cfg.memory.state_updater.get_api_key() or cfg.memory.judge.get_api_key() or cfg.llm.get_api_key(),
            model=data.get("model") or cfg.memory.state_updater.model or cfg.memory.judge.model or cfg.llm.model,
            timeout_seconds=int(data.get("timeout_seconds") or cfg.memory.state_updater.timeout_seconds),
            temperature=float(data.get("temperature") if data.get("temperature") is not None else cfg.memory.state_updater.temperature),
            min_confidence=float(data.get("min_confidence") if data.get("min_confidence") is not None else cfg.memory.state_updater.min_confidence),
            prompt=data.get("prompt") or cfg.memory.state_updater.prompt,
        ),
    )
    return {
        "status": "ok",
        "applied": result.applied,
        "skipped": result.skipped,
        "updates": [update.__dict__ for update in result.updates],
        "notes": result.notes,
    }


@router.post("/admin/inbox/{inbox_id}/reject")
async def reject_inbox_item(inbox_id: str, note: str = Body(default="")):
    """Reject an inbox item."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_inbox_item, update_inbox_status, insert_review_action

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    item = await get_inbox_item(db_path, inbox_id)
    if not item:
        return {"status": "error", "message": "Inbox item not found"}
    if item["status"] != "pending":
        return {"status": "error", "message": f"Item already {item['status']}"}

    await update_inbox_status(db_path, inbox_id, "rejected", review_note=note)
    await insert_review_action(db_path, action="reject", inbox_id=inbox_id, note=note)
    return {"status": "ok"}


# --- Conversation Config Summary API ---

@router.get("/admin/conversations/{conversation_id}/config")
async def get_conversation_config(conversation_id: str, request: Request):
    """Get aggregated session configuration: template, mounts, state item count, write target."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_conversation_mounts
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    mounts = await get_conversation_mounts(db_path, conversation_id)
    mounted_library_ids = [m["library_id"] for m in mounts]
    write_library_id = next((m["library_id"] for m in mounts if m.get("is_write_target")), mounted_library_ids[0] if mounted_library_ids else "lib_default")

    store = SQLiteStateStore(db_path)
    template = await store.get_conversation_template(conversation_id)
    items, item_count = await store.list_items(conversation_id, status="active", limit=1)

    return {
        "conversation_id": conversation_id,
        "mounted_library_ids": mounted_library_ids,
        "write_library_id": write_library_id,
        "mounts": mounts,
        "template_id": template.template_id if template else None,
        "template_name": template.name if template else None,
        "state_item_count": item_count,
        "is_new_session": item_count == 0 and mounted_library_ids == ["lib_default"],
    }


@router.post("/admin/conversations/{conversation_id}/config")
async def save_conversation_config(conversation_id: str, request: Request, data: dict = Body(...)):
    """Save all session configuration at once: mounts, write target, template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_cards import set_conversation_mounts
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    library_ids = data.get("library_ids") or data.get("mounted_library_ids") or []
    write_library_id = data.get("write_library_id")
    template_id = data.get("template_id")

    if library_ids:
        await set_conversation_mounts(
            db_path,
            conversation_id=conversation_id,
            library_ids=library_ids,
            write_library_id=write_library_id,
            user_id=data.get("user_id"),
            character_id=data.get("character_id"),
        )

    if template_id:
        store = SQLiteStateStore(db_path)
        if await store.get_template(template_id):
            await store.set_conversation_template(conversation_id, template_id)

    return {"status": "ok"}


# --- State Board Clear API ---

@router.post("/admin/conversations/{conversation_id}/state/clear")
async def clear_conversation_state(conversation_id: str, request: Request):
    """Soft-delete all active state items for a conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    cleared = await store.clear_conversation_state_items(conversation_id)
    return {"status": "ok", "cleared": cleared}


@router.post("/admin/conversations/{conversation_id}/state/copy")
async def copy_conversation_state(conversation_id: str, request: Request, data: dict = Body(...)):
    """Copy state items and optionally mounts to a target conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_cards import copy_conversation_mounts
    from app.storage.sqlite_state import SQLiteStateStore

    target_id = data.get("target_conversation_id")
    if not target_id:
        raise HTTPException(status_code=400, detail="target_conversation_id is required")
    if target_id == conversation_id:
        raise HTTPException(status_code=400, detail="target_conversation_id must differ from source")

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    store = SQLiteStateStore(db_path)
    copied_items = await store.copy_state_items(conversation_id, target_id)

    copied_mounts = 0
    if data.get("copy_mounts", True):
        copied_mounts = await copy_conversation_mounts(db_path, conversation_id, target_id)

    return {"status": "ok", "copied_items": copied_items, "copied_mounts": copied_mounts}


@router.post("/admin/conversations/{conversation_id}/state/reset")
async def reset_conversation_state(conversation_id: str, request: Request):
    """Clear state items but keep the template binding."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    cleared = await store.reset_to_template_empty(conversation_id)
    return {"status": "ok", "cleared": cleared}


# --- Memory Mount Presets API ---

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


# --- Import / Export API ---

@router.get("/admin/memory-libraries/{library_id}/export")
async def export_memory_library(library_id: str):
    """Export a memory library with all its cards as JSON."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import init_cards_db
    import aiosqlite

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
    from app.core.state import get_config
    from app.storage.sqlite_cards import create_memory_library, insert_card, insert_card_version

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
        imported += 1

    return {"status": "ok", "library_id": new_library_id, "imported_cards": imported}


@router.get("/admin/state/templates/{template_id}/export")
async def export_state_template(template_id: str):
    """Export a state board template with tabs and fields as JSON."""
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    template = await store.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    return {
        "format": "kokoromemo_template_v1",
        "template": _template_to_dict(template),
    }


@router.post("/admin/state/templates/import")
async def import_state_template(data: dict = Body(...)):
    """Import a state board template from exported JSON."""
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    template_data = data.get("template", data)
    # Clear template_id so a new one is generated
    template_data.pop("template_id", None)
    template_data["is_builtin"] = False

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    template_id = await store.save_template(_template_from_payload(template_data))
    return {"status": "ok", "template_id": template_id}


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
    from app.core.state import get_config
    from app.storage.sqlite_cards import create_mount_preset
    import json as json_mod

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


# --- Conversation Import/Export ---


@router.get("/admin/memory-graph")
async def get_memory_graph(
    request: Request,
    library_id: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
):
    """Return graph data (nodes + edges) for visualization."""
    _require_admin(request)
    import aiosqlite
    from app.core.state import get_config

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    nodes = []
    edges = []

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT card_id, card_type, content, importance, confidence, scope FROM memory_cards WHERE status = 'approved'"
            params: list = []
            if library_id:
                query += " AND library_id = ?"
                params.append(library_id)
            query += " ORDER BY importance DESC LIMIT ?"
            params.append(limit)

            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            card_ids = set()
            for row in rows:
                card_ids.add(row["card_id"])
                nodes.append({
                    "id": row["card_id"],
                    "label": row["content"][:60],
                    "type": row["card_type"],
                    "importance": row["importance"],
                    "confidence": row["confidence"],
                    "scope": row["scope"],
                })

            if card_ids:
                placeholders = ",".join("?" * len(card_ids))
                cursor = await db.execute(
                    f"SELECT source_card_id, target_card_id, edge_type, weight, confidence "
                    f"FROM memory_edges WHERE status = 'active' "
                    f"AND (source_card_id IN ({placeholders}) OR target_card_id IN ({placeholders}))",
                    list(card_ids) + list(card_ids),
                )
                for row in await cursor.fetchall():
                    edges.append({
                        "source": row["source_card_id"],
                        "target": row["target_card_id"],
                        "type": row["edge_type"],
                        "weight": row["weight"],
                        "confidence": row["confidence"],
                    })
    except Exception:
        pass

    return {"nodes": nodes, "edges": edges}


@router.post("/admin/import/sillytavern")
async def import_sillytavern(request: Request, data: dict = Body(...)):
    """Import a SillyTavern JSONL chat log."""
    _require_admin(request)
    from app.core.ids import generate_id
    from app.core.state import get_config
    from app.importers.sillytavern import parse_sillytavern_jsonl
    from app.storage.sqlite_app import init_app_db, upsert_conversation
    from app.storage.sqlite_conversation import init_chat_db, save_turn_and_messages

    cfg = get_config()
    text = data.get("content", "")
    if not text:
        raise HTTPException(status_code=400, detail="content is required (JSONL text)")

    conv = parse_sillytavern_jsonl(text)
    if not conv.turns:
        return {"status": "error", "message": "No valid turns found in input"}

    user_id = data.get("user_id", "default")
    character_id = data.get("character_id") or None
    conversation_id = data.get("conversation_id") or generate_id("conv_import_")

    from pathlib import Path
    conv_dir = str(Path(cfg.storage.root_dir, "conversations", conversation_id))
    chat_db_path = str(Path(conv_dir, "chat.sqlite"))

    await init_app_db(cfg.storage.sqlite.app_db)
    await init_chat_db(chat_db_path)
    await upsert_conversation(
        cfg.storage.sqlite.app_db, conversation_id,
        user_id, character_id, "sillytavern_import", conv_dir,
    )

    messages = []
    if conv.system_prompt:
        messages.append({"role": "system", "content": conv.system_prompt})
    for turn in conv.turns:
        messages.append({"role": turn.role, "content": turn.content})

    turn_id = generate_id("turn_")
    await save_turn_and_messages(chat_db_path, turn_id, conversation_id, messages)

    return {
        "status": "ok",
        "conversation_id": conversation_id,
        "turns_imported": len(conv.turns),
        "character_name": conv.character_name,
    }


@router.post("/admin/import/{conversation_id}/extract-memories")
async def extract_memories_from_import(conversation_id: str, request: Request, data: dict = Body(default={})):
    """Batch-extract memories from an imported conversation."""
    _require_admin(request)
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.memory.card_extractor import extract_and_route
    from app.memory.judge import MemoryJudgeConfigView
    from app.storage.sqlite_conversation import get_all_messages

    cfg = get_config()
    from pathlib import Path
    chat_db_path = str(Path(cfg.storage.root_dir, "conversations", conversation_id, "chat.sqlite"))

    if not Path(chat_db_path).exists():
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await get_all_messages(chat_db_path, conversation_id)
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(messages) - 1:
        if messages[i].get("role") == "user" and messages[i + 1].get("role") == "assistant":
            pairs.append((messages[i]["content"], messages[i + 1]["content"]))
            i += 2
        else:
            i += 1

    if not pairs:
        return {"status": "ok", "extracted_pairs": 0, "message": "No user-assistant pairs found"}

    user_id = data.get("user_id", "default")
    character_id = data.get("character_id") or None
    ep = get_embedding_provider(cfg)
    store = get_lancedb_store(cfg)

    judge_config = None
    if cfg.memory.judge.enabled and cfg.memory.judge.model:
        judge_config = MemoryJudgeConfigView(
            provider=cfg.memory.judge.provider,
            base_url=cfg.memory.judge.base_url or cfg.llm.base_url,
            api_key=cfg.memory.judge.get_api_key() or cfg.llm.get_api_key(),
            model=cfg.memory.judge.model or cfg.llm.model,
            timeout_seconds=cfg.memory.judge.timeout_seconds,
            temperature=cfg.memory.judge.temperature,
            mode=cfg.memory.judge.mode,
            user_rules=cfg.memory.judge.user_rules,
            prompt=cfg.memory.judge.prompt,
        )

    max_pairs = data.get("max_pairs", 50)
    extracted_count = 0
    for user_msg, assistant_msg in pairs[:max_pairs]:
        try:
            await extract_and_route(
                db_path=cfg.storage.sqlite.memory_db,
                user_message=user_msg,
                assistant_message=assistant_msg,
                user_id=user_id,
                character_id=character_id,
                conversation_id=conversation_id,
                embedding_provider=ep,
                lancedb_store=store,
                judge_config=judge_config,
                lang=cfg.language,
            )
            extracted_count += 1
        except Exception:
            continue

    return {"status": "ok", "extracted_pairs": extracted_count, "total_pairs": len(pairs)}
