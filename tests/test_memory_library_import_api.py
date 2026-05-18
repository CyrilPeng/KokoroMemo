from __future__ import annotations

import shutil
import sqlite3
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import AppConfig
from app.core.state import set_config
from app.main import app


def make_test_dir() -> Path:
    root = Path(".test_tmp") / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def cleanup_test_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


class FakeEmbeddingProvider:
    model = "fake-embedding"
    dimension = 3

    async def embed_text(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class FakeVectorStore:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def upsert(self, rows: list[dict]) -> None:
        self.rows.extend(rows)


@pytest.mark.asyncio
async def test_import_memory_library_records_versions_and_syncs_vectors(monkeypatch):
    test_dir = make_test_dir()
    try:
        cfg = AppConfig()
        cfg.storage.root_dir = str(test_dir)
        cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
        cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
        set_config(cfg)

        fake_store = FakeVectorStore()
        monkeypatch.setattr("app.core.services.get_embedding_provider", lambda cfg: FakeEmbeddingProvider())
        monkeypatch.setattr("app.core.services.get_lancedb_store", lambda cfg: fake_store)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/admin/memory-libraries/import", json={
                "library": {"name": "imported"},
                "cards": [{
                    "user_id": "u1",
                    "scope": "global",
                    "card_type": "preference",
                    "content": "imported memory",
                    "summary": "summary",
                    "importance": 0.8,
                    "confidence": 0.9,
                    "status": "approved",
                }],
            })

        assert resp.status_code == 200
        assert resp.json()["imported_cards"] == 1
        assert len(fake_store.rows) == 1
        assert fake_store.rows[0]["content"] == "imported memory"

        with sqlite3.connect(cfg.storage.sqlite.memory_db) as conn:
            card = conn.execute(
                "SELECT card_id, vector_synced, embedding_model FROM memory_cards"
            ).fetchone()
            version_count = conn.execute(
                "SELECT COUNT(*) FROM memory_card_versions WHERE card_id = ?",
                (card[0],),
            ).fetchone()[0]

        assert card[1] == 1
        assert card[2] == "fake-embedding"
        assert version_count == 1
    finally:
        cleanup_test_dir(test_dir)
