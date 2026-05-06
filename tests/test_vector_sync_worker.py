from __future__ import annotations

import shutil
import sqlite3
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.services import ServiceRegistry
from app.storage.sqlite_cards import enqueue_job, init_cards_db, insert_card
from app.storage.vector_sync import VectorSyncWorker


class DummyEmbeddingProvider:
    model = "dummy-embedding"
    dimension = 4

    async def embed_text(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]


class DummyVectorStore:
    def __init__(self) -> None:
        self.records = []

    def upsert(self, records):
        self.records.extend(records)


def _make_test_dir() -> Path:
    path = Path(".test_vector_sync") / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.mark.asyncio
async def test_vector_sync_worker_drains_pending_jobs(monkeypatch):
    test_dir = _make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    vector_store = DummyVectorStore()
    try:
        await init_cards_db(str(memory_db))
        await insert_card(
            str(memory_db),
            "card_worker_sync",
            "u1",
            "c1",
            "conv1",
            "character",
            "preference",
            "用户喜欢安静",
            status="approved",
        )
        await enqueue_job(str(memory_db), "card_vector_sync", '{"card_id":"card_worker_sync"}')

        registry = ServiceRegistry()
        monkeypatch.setattr(registry, "get_embedding_provider", lambda _cfg: DummyEmbeddingProvider())
        monkeypatch.setattr(registry, "get_lancedb_store", lambda _cfg: vector_store)

        cfg = SimpleNamespace(storage=SimpleNamespace(sqlite=SimpleNamespace(memory_db=str(memory_db))))
        result = await VectorSyncWorker(cfg, service_registry=registry, interval_seconds=999).run_once()

        assert result == {"status": "ok", "total": 1, "success": 1, "failed": 0}
        assert vector_store.records[0]["memory_id"] == "card_worker_sync"
        with sqlite3.connect(memory_db) as conn:
            card = conn.execute(
                "SELECT vector_synced, embedding_model FROM memory_cards WHERE card_id = ?",
                ("card_worker_sync",),
            ).fetchone()
            job = conn.execute("SELECT status FROM jobs").fetchone()
        assert card == (1, "dummy-embedding")
        assert job == ("done",)
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
