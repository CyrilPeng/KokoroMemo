from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import AppConfig
from app.core.services import get_lancedb_store, reset_services
from app.core.state import set_config
from app.main import app


def _configure_vector_store(tmp_path) -> AppConfig:
    cfg = AppConfig()
    cfg.storage.root_dir = str(tmp_path)
    cfg.storage.sqlite.app_db = str(tmp_path / "app.sqlite")
    cfg.storage.sqlite.memory_db = str(tmp_path / "memory.sqlite")
    cfg.storage.vector_store = "sqlite"
    cfg.embedding.enabled = True
    cfg.embedding.dimension = 8
    set_config(cfg)
    reset_services()
    return cfg


def _vector_row(memory_id: str, vector: list[float]) -> dict:
    return {
        "memory_id": memory_id,
        "library_id": "lib_default",
        "user_id": "u1",
        "character_id": "",
        "conversation_id": "",
        "scope": "global",
        "memory_type": "preference",
        "content": "health check",
        "summary": "",
        "tags_json": "",
        "importance": 0.8,
        "confidence": 0.9,
        "status": "active",
        "created_at": "2026-01-01 00:00:00",
        "updated_at": "2026-01-01 00:00:00",
        "embedding_model": "test",
        "vector": vector,
    }


@pytest.mark.asyncio
async def test_vector_backend_status_empty_sqlite_index(tmp_path):
    cfg = _configure_vector_store(tmp_path)
    store = get_lancedb_store(cfg)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/admin/vector-backend-status")

        assert response.status_code == 200
        data = response.json()
        assert data["configured_mode"] == "sqlite"
        assert data["effective_backend"] == "sqlite"
        assert data["indexed_rows"] == 0
        assert data["filtered_search_ok"] is True
        assert data["status"] == "ok"
    finally:
        if getattr(store, "_conn", None):
            store._conn.close()
        reset_services()


@pytest.mark.asyncio
async def test_vector_backend_status_reports_indexed_rows(tmp_path):
    cfg = _configure_vector_store(tmp_path)
    store = get_lancedb_store(cfg)
    store.upsert([_vector_row("card_ok", [1.0] + [0.0] * 7)])
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/admin/vector-backend-status")

        assert response.status_code == 200
        data = response.json()
        assert data["indexed_rows"] == 1
        assert data["filtered_search_rows"] == 1
        assert data["filtered_search_ok"] is True
        assert data["status"] == "ok"
    finally:
        if getattr(store, "_conn", None):
            store._conn.close()
        reset_services()


@pytest.mark.asyncio
async def test_vector_backend_status_flags_broken_metadata_filter(tmp_path, monkeypatch):
    _configure_vector_store(tmp_path)

    class BrokenStore:
        backend_name = "lancedb"

        def count(self):
            return 1

        def search(self, vector, where=None, top_k=30, select_columns=None):
            return []

    monkeypatch.setattr("app.core.services.get_lancedb_store", lambda _cfg: BrokenStore())
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/admin/vector-backend-status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["filtered_search_ok"] is False
        assert data["filtered_search_rows"] == 0
        assert "sqlite" in data["warning"]
    finally:
        reset_services()
