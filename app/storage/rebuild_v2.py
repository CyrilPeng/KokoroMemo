"""Rebuild vector index from approved cards + active summaries only."""

from __future__ import annotations

import logging

from app.providers.embedding_base import EmbeddingProvider
from app.storage.sqlite_cards import get_approved_cards

logger = logging.getLogger("kokoromemo.rebuild_v2")


async def rebuild_vector_index_v2(
    cards_db_path: str,
    lancedb_store,
    embedding_provider: EmbeddingProvider,
    batch_size: int = 16,
    atomic: bool = True,
) -> dict:
    """Rebuild LanceDB from approved memory_cards only.

    When atomic=True (default), writes go to a staging table first; the live table is
    dropped and the staging is renamed only after all batches succeed. A mid-flight failure
    leaves the live index untouched. Falls back to drop_and_recreate when the LanceDB
    backend does not support rename_table.
    """
    cards = await get_approved_cards(cards_db_path)
    if not cards:
        return {"status": "ok", "rebuilt": 0, "total": 0}

    logger.info("Rebuilding v2 index: %d approved cards (atomic=%s)", len(cards), atomic)

    staging_name: str | None = None
    use_atomic = atomic and hasattr(lancedb_store, "create_staging_table")
    if use_atomic:
        staging_name = f"{lancedb_store.table_name}_staging"
        try:
            lancedb_store.create_staging_table(staging_name)
        except Exception as e:
            logger.warning("Atomic rebuild unavailable, falling back to drop_and_recreate: %s", e)
            use_atomic = False
            staging_name = None

    if not use_atomic:
        lancedb_store.drop_and_recreate()

    success_count = 0
    try:
        for i in range(0, len(cards), batch_size):
            batch = cards[i:i + batch_size]
            texts = [c["content"] for c in batch]

            try:
                vectors = await embedding_provider.embed_batch(texts)
            except Exception as e:
                logger.error("Embedding batch failed at offset %d: %s", i, e)
                continue

            rows = []
            for card, vec in zip(batch, vectors):
                rows.append({
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
                })

            try:
                if use_atomic and staging_name:
                    lancedb_store.upsert_into(staging_name, rows)
                else:
                    lancedb_store.upsert(rows)
                success_count += len(rows)
            except Exception as e:
                logger.error("LanceDB upsert failed at offset %d: %s", i, e)
    except Exception as e:
        # 发生未预期错误时回滚临时表
        if use_atomic and staging_name:
            try:
                lancedb_store.drop_staging(staging_name)
            except Exception:
                pass
        raise

    if use_atomic and staging_name:
        if success_count == 0:
            # 不要用空的临时表覆盖正式表
            lancedb_store.drop_staging(staging_name)
            logger.warning("Staging table empty after rebuild — keeping live index unchanged")
        else:
            lancedb_store.promote_staging(staging_name)

    logger.info("Rebuild v2 complete: %d/%d cards indexed", success_count, len(cards))
    return {"status": "ok", "rebuilt": success_count, "total": len(cards)}
