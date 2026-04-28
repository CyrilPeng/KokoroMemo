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


async def _fetch_models_from_remote(base_url: str, api_key: str):
    """Fetch available models from a remote /v1/models endpoint."""
    if not api_key:
        return {"status": "error", "message": "未提供 API Key", "models": []}

    url = base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                body = resp.text[:200]
                return {"status": "error", "message": f"远端返回 HTTP {resp.status_code}: {body}", "models": []}
            data = resp.json()

            # OpenAI format: { "data": [{"id": "model-name", ...}] }
            models = []
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
    return await _fetch_models_from_remote(data.get("base_url", ""), data.get("api_key", ""))


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
        "server": {"host": cfg.server.host, "port": cfg.server.port, "webui_port": cfg.server.webui_port},
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
                "prompt": cfg.memory.judge.prompt,
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

    allowed_fields = {"content", "card_type", "scope", "importance", "confidence", "title", "summary", "is_pinned"}
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
        insert_review_action,
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
    await insert_card(
        db_path,
        card_id=card_id,
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
