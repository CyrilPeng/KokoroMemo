"""Helpers for syncing approved memory cards to the vector store."""

from __future__ import annotations

import json

from app.providers.embedding_base import EmbeddingProvider
from app.storage.sqlite_cards import (
    enqueue_job,
    get_cards_by_ids,
    get_pending_jobs,
    mark_card_vector_synced,
    update_job_status,
)


async def sync_card_vector(
    db_path: str,
    card_id: str,
    embedding_provider: EmbeddingProvider,
    lancedb_store,
) -> None:
    cards = await get_cards_by_ids(db_path, [card_id])
    card = cards.get(card_id)
    if not card or card.get("status") != "approved":
        return

    vec = await embedding_provider.embed_text(card["content"])
    lancedb_store.upsert([{
        "memory_id": card["card_id"],
        "library_id": card.get("library_id") or "lib_default",
        "user_id": card["user_id"],
        "character_id": card.get("character_id") or "",
        "conversation_id": card.get("conversation_id") or "",
        "scope": card["scope"],
        "memory_type": card["card_type"],
        "content": card["content"],
        "summary": card.get("summary") or "",
        "tags_json": "",
        "importance": card["importance"],
        "confidence": card["confidence"],
        "status": "active",
        "created_at": card.get("created_at") or "",
        "updated_at": card.get("updated_at") or "",
        "embedding_model": embedding_provider.model,
        "vector": vec,
    }])
    await mark_card_vector_synced(db_path, card_id, embedding_provider.model, embedding_provider.dimension)


async def enqueue_card_vector_sync(db_path: str, card_id: str, error: str | None = None) -> str:
    return await enqueue_job(
        db_path,
        job_type="card_vector_sync",
        payload_json=json.dumps({"card_id": card_id}, ensure_ascii=False),
        last_error=error,
    )


async def retry_card_vector_sync_jobs(
    db_path: str,
    embedding_provider: EmbeddingProvider,
    lancedb_store,
    limit: int = 50,
) -> dict:
    jobs = await get_pending_jobs(db_path, job_type="card_vector_sync", limit=limit)
    success = 0
    failed = 0
    for job in jobs:
        try:
            payload = json.loads(job["payload_json"])
            await sync_card_vector(db_path, payload["card_id"], embedding_provider, lancedb_store)
            await update_job_status(db_path, job["job_id"], "done")
            success += 1
        except Exception as exc:
            await update_job_status(db_path, job["job_id"], "failed", str(exc))
            failed += 1
    return {"status": "ok", "total": len(jobs), "success": success, "failed": failed}
