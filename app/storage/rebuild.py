"""Rebuild LanceDB vector index from SQLite memory data."""

from __future__ import annotations

import logging

from app.providers.embedding_base import EmbeddingProvider
from app.storage.lancedb_store import LanceDBStore
from app.storage.sqlite_memory import get_active_memories

logger = logging.getLogger("kokoromemo.rebuild")


async def rebuild_vector_index(
    memory_db_path: str,
    lancedb_store: LanceDBStore,
    embedding_provider: EmbeddingProvider,
    batch_size: int = 16,
) -> dict:
    """Rebuild entire LanceDB index from SQLite memories."""
    memories = await get_active_memories(memory_db_path)
    if not memories:
        return {"status": "ok", "rebuilt": 0}

    logger.info("Rebuilding index: %d memories to process", len(memories))
    lancedb_store.drop_and_recreate()

    success_count = 0
    for i in range(0, len(memories), batch_size):
        batch = memories[i:i + batch_size]
        texts = [m["content"] for m in batch]

        try:
            vectors = await embedding_provider.embed_batch(texts)
        except Exception as e:
            logger.error("Embedding batch failed at offset %d: %s", i, e)
            continue

        rows = []
        for mem, vec in zip(batch, vectors):
            rows.append({
                "memory_id": mem["memory_id"],
                "user_id": mem["user_id"],
                "character_id": mem.get("character_id") or "",
                "conversation_id": mem.get("conversation_id") or "",
                "scope": mem["scope"],
                "memory_type": mem["memory_type"],
                "content": mem["content"],
                "summary": mem.get("summary") or "",
                "tags_json": mem.get("tags_json") or "",
                "importance": mem["importance"],
                "confidence": mem["confidence"],
                "status": mem["status"],
                "created_at": mem["created_at"],
                "updated_at": mem["updated_at"],
                "embedding_model": embedding_provider.model,
                "vector": vec,
            })

        try:
            lancedb_store.upsert(rows)
            success_count += len(rows)
        except Exception as e:
            logger.error("LanceDB upsert failed at offset %d: %s", i, e)

    logger.info("Rebuild complete: %d/%d memories indexed", success_count, len(memories))
    return {"status": "ok", "rebuilt": success_count, "total": len(memories)}
