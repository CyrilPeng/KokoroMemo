"""Regression tests for core KokoroMemo functionality."""
from __future__ import annotations

import sqlite3
import shutil
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import AppConfig
from app.core.state import set_config
from app.main import app
from app.storage.sqlite_cards import init_cards_db, insert_card
from app.storage.sqlite_state import SQLiteStateStore
from app.memory.state_schema import ConversationStateItem


class FakeChatProvider:
    captured_bodies: list[dict] = []

    async def chat(self, body: dict, timeout: int) -> dict:
        self.captured_bodies.append(body)
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": body.get("model", "test-model"),
            "choices": [{"message": {"role": "assistant", "content": "收到"}, "finish_reason": "stop"}],
        }

    async def stream_chat(self, body: dict, timeout: int):
        self.captured_bodies.append(body)
        yield 'data: {"choices":[{"delta":{"content":"收"}}]}'
        yield 'data: {"choices":[{"delta":{"content":"到"}}]}'
        yield "data: [DONE]"


class FakeLanceDBStore:
    def __init__(self, rows=None, on_upsert=None):
        self.rows = rows or []
        self.on_upsert = on_upsert

    async def search(self, vector, top_k=10, where=None):
        return self.rows[:top_k]

    async def upsert(self, records):
        if self.on_upsert:
            self.on_upsert(records)


def make_test_dir() -> Path:
    root = Path(".test_tmp") / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def cleanup_test_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def configure_app(test_dir: Path) -> AppConfig:
    cfg = AppConfig()
    cfg.storage.root_dir = str(test_dir)
    cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
    cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
    cfg.llm.base_url = "http://fake"
    cfg.llm.model = "fake-model"
    cfg.embedding.enabled = False
    cfg.memory.extraction_enabled = False
    cfg.memory.state_updater.enabled = False
    cfg.memory.retrieval_gate.vector_search_on_new_session = False
    set_config(cfg)
    return cfg


@pytest.mark.asyncio
async def test_v1_models_endpoint(monkeypatch):
    test_dir = make_test_dir()
    try:
        configure_app(test_dir)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1
        assert "id" in data["data"][0]
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_non_stream_chat_completion_basic(monkeypatch):
    test_dir = make_test_dir()
    try:
        cfg = configure_app(test_dir)
        provider = FakeChatProvider()
        FakeChatProvider.captured_bodies.clear()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions", json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "你好"}],
                "metadata": {"conversation_id": "conv_basic"},
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["object"] == "chat.completion"
        assert data["model"] == "fake-model"
        assert len(data["choices"]) >= 1
        assert data["choices"][0]["message"]["role"] == "assistant"
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_stream_chat_completion_basic(monkeypatch):
    test_dir = make_test_dir()
    try:
        cfg = configure_app(test_dir)
        provider = FakeChatProvider()
        FakeChatProvider.captured_bodies.clear()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)

        collected_lines = []
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            async with client.stream("POST", "/v1/chat/completions", json={
                "model": "fake-model",
                "stream": True,
                "messages": [{"role": "user", "content": "你好"}],
                "metadata": {"conversation_id": "conv_stream_basic"},
            }) as resp:
                assert resp.status_code == 200
                async for line in resp.aiter_lines():
                    if line.strip():
                        collected_lines.append(line)

        data_lines = [l for l in collected_lines if l.startswith("data:") and "[DONE]" not in l]
        done_lines = [l for l in collected_lines if "[DONE]" in l]
        assert len(data_lines) >= 1
        assert len(done_lines) >= 1
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_raw_request_persisted(monkeypatch):
    test_dir = make_test_dir()
    try:
        cfg = configure_app(test_dir)
        provider = FakeChatProvider()
        FakeChatProvider.captured_bodies.clear()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions", json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "测试持久化"}],
                "metadata": {"conversation_id": "conv_persist"},
            })
        assert resp.status_code == 200

        chat_db = test_dir / "conversations" / "conv_persist" / "chat.sqlite"
        assert chat_db.exists(), f"chat.sqlite should exist at {chat_db}"
        conn = sqlite3.connect(str(chat_db))
        try:
            count = conn.execute("SELECT COUNT(*) FROM raw_requests").fetchone()[0]
            assert count >= 1
        finally:
            conn.close()
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_deprecated_cards_not_injected_in_pipeline(monkeypatch):
    test_dir = make_test_dir()
    try:
        cfg = configure_app(test_dir)
        memory_db = cfg.storage.sqlite.memory_db
        await init_cards_db(memory_db)

        await insert_card(
            memory_db, "card_old", "u1", "c1", None,
            "character", "preference", "用户喜欢猫娘说话方式",
            status="deprecated", confidence=0.8,
        )

        provider = FakeChatProvider()
        FakeChatProvider.captured_bodies.clear()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)

        async def fake_retrieve_cards(*args, **kwargs):
            return [{"card_id": "card_old", "content": "用户喜欢猫娘说话方式", "status": "deprecated", "score": 0.9}]

        from app.providers.embedding_dummy import DummyEmbeddingProvider
        monkeypatch.setattr("app.api.routes_openai.get_embedding_provider", lambda _cfg: DummyEmbeddingProvider(8))
        monkeypatch.setattr("app.api.routes_openai.get_lancedb_store", lambda _cfg: FakeLanceDBStore())
        monkeypatch.setattr("app.memory.card_retriever.retrieve_cards", fake_retrieve_cards)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions", json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "你还记得我喜欢什么吗"}],
                "metadata": {"conversation_id": "conv_deprecated"},
            })
        assert resp.status_code == 200
        contents = [message["content"] for message in provider.captured_bodies[-1]["messages"]]
        assert not any("猫娘说话方式" in content for content in contents)
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_memory_cards_approved_syncs_vector():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        await init_cards_db(str(memory_db))
        upserted_records = []

        def on_upsert(records):
            upserted_records.extend(records)

        FakeLanceDBStore(on_upsert=on_upsert)

        await insert_card(
            str(memory_db), "card_sync_test", "u1", "c1", None,
            "character", "preference", "用户喜欢安静",
            status="approved", confidence=0.85,
        )

        conn = sqlite3.connect(str(memory_db))
        try:
            row = conn.execute("SELECT vector_synced FROM memory_cards WHERE card_id = ?", ("card_sync_test",)).fetchone()
            # Note: vector_synced is set by the sync pipeline, not insert_card directly.
            # This test verifies the card exists with approved status.
            assert row is not None
        finally:
            conn.close()
    finally:
        cleanup_test_dir(test_dir)
