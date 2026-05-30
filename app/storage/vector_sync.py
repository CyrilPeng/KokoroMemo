"""Helpers for syncing approved memory cards to the vector store."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging

from app.core.services import ServiceRegistry, get_service_registry
from app.providers.embedding_base import EmbeddingProvider

logger = logging.getLogger("kokoromemo.vector_sync")
from app.storage.sqlite_cards import (
    enqueue_job,
    get_cards_by_ids,
    get_pending_jobs,
    mark_card_vector_synced,
    update_job_status,
)


class VectorSyncWorker:
    """Periodically drains pending card vector sync jobs."""

    def __init__(self, cfg, *, service_registry: ServiceRegistry | None = None, interval_seconds: float = 30.0, batch_limit: int = 50) -> None:
        self._cfg = cfg
        self._services = service_registry or get_service_registry()
        self._interval_seconds = interval_seconds
        self._batch_limit = batch_limit
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self) -> asyncio.Task:
        if self._task and not self._task.done():
            return self._task
        self._task = asyncio.create_task(self.run(), name="vector_sync_worker")
        return self._task

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task and not self._task.done():
            await self._task

    async def run(self) -> None:
        await self.run_once()
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                await self.run_once()

    async def run_once(self) -> dict:
        ep = self._services.get_embedding_provider(self._cfg)
        store = self._services.get_lancedb_store(self._cfg)
        if not ep or not store:
            return {"status": "skipped", "message": "Embedding or vector store not configured"}
        try:
            result = await retry_card_vector_sync_jobs(
                self._cfg.storage.sqlite.memory_db,
                ep,
                store,
                limit=self._batch_limit,
            )
            if result.get("total"):
                logger.info(
                    "Vector sync worker drained %d job(s): success=%d failed=%d",
                    result.get("total", 0),
                    result.get("success", 0),
                    result.get("failed", 0),
                )
            return result
        except Exception as exc:
            logger.warning("Vector sync worker run failed: %s", exc)
            return {"status": "error", "message": str(exc)}


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
    upsert_result = lancedb_store.upsert([{
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
    if inspect.isawaitable(upsert_result):
        await upsert_result
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
