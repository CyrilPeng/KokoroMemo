"""Memory card routes: CRUD, diagnostics, deprecation, vector index, graph."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, Body, HTTPException, Query, Request

from app.api.admin._helpers import _require_admin

router = APIRouter()


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
    import aiosqlite

    from app.core.state import get_config
    from app.storage.sqlite_cards import init_cards_db

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
                memories.append(
                    {
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
                    }
                )

            return {"memories": memories, "total": total, "limit": limit, "offset": offset}
    except Exception:
        return {"memories": [], "total": 0, "limit": limit, "offset": offset}


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
    import aiosqlite

    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.storage.sqlite_cards import insert_card_version, mark_card_vector_unsynced
    from app.storage.vector_sync import enqueue_card_vector_sync, sync_card_vector

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    allowed_fields = {
        "library_id",
        "content",
        "card_type",
        "scope",
        "importance",
        "confidence",
        "title",
        "summary",
        "is_pinned",
    }
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
    import aiosqlite

    from app.core.services import get_lancedb_store
    from app.core.state import get_config

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
        with contextlib.suppress(Exception):
            store.delete(f"memory_id = '{card_id}'")

    return {"status": "ok"}


@router.get("/admin/memory-diagnostics")
async def memory_diagnostics_api(
    character_id: str | None = Query(default=None),
    conversation_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """按角色或会话查看相关记忆，便于排查记忆污染。"""
    from app.core.state import get_config
    from app.storage.sqlite_cards import list_memory_diagnostics

    if not character_id and not conversation_id:
        raise HTTPException(status_code=400, detail="请至少提供角色 ID 或会话 ID")
    cfg = get_config()
    data = await list_memory_diagnostics(
        cfg.storage.sqlite.memory_db,
        character_id=character_id,
        conversation_id=conversation_id,
        limit=limit,
    )
    return data


@router.post("/admin/memories/{card_id}/deprecate")
async def deprecate_memory_card(card_id: str, note: str = Body(default="")):
    """Mark a memory card as deprecated so it is no longer recalled by default."""
    import aiosqlite

    from app.core.services import get_lancedb_store
    from app.core.state import get_config
    from app.storage.sqlite_cards import insert_review_action

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
        with contextlib.suppress(Exception):
            store.delete(f"memory_id = '{card_id}'")

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
        cfg.storage.sqlite.memory_db,
        store,
        ep,
        batch_size=cfg.embedding.batch_size,
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


@router.post("/admin/start-index-migration")
async def start_index_migration_api(request: Request, data: dict = Body(default=None)):
    """Start an asynchronous embedding index migration with the current config."""
    _require_admin(request)
    from app.core.services import (
        get_index_migration_status,
        start_index_migration,
    )
    from app.core.state import get_config

    current = get_index_migration_status()
    if current and current.get("status") == "running":
        return {"status": "error", "message": "Migration already running"}

    payload = data or {}
    cfg = get_config()
    old_model = payload.get("old_model") or cfg.embedding.model
    old_dimension = payload.get("old_dimension") or cfg.embedding.dimension
    start_index_migration(cfg, old_model, old_dimension)
    return {"status": "ok", "message": "Migration started"}


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
                nodes.append(
                    {
                        "id": row["card_id"],
                        "label": row["content"][:60],
                        "type": row["card_type"],
                        "importance": row["importance"],
                        "confidence": row["confidence"],
                        "scope": row["scope"],
                    }
                )

            if card_ids:
                placeholders = ",".join("?" * len(card_ids))
                cursor = await db.execute(
                    f"SELECT source_card_id, target_card_id, edge_type, weight, confidence "
                    f"FROM memory_edges WHERE status = 'active' "
                    f"AND (source_card_id IN ({placeholders}) OR target_card_id IN ({placeholders}))",
                    list(card_ids) + list(card_ids),
                )
                for row in await cursor.fetchall():
                    edges.append(
                        {
                            "source": row["source_card_id"],
                            "target": row["target_card_id"],
                            "type": row["edge_type"],
                            "weight": row["weight"],
                            "confidence": row["confidence"],
                        }
                    )
    except Exception:  # noqa: S110
        pass

    return {"nodes": nodes, "edges": edges}
