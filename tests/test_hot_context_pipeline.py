from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import AppConfig
from app.core.state import set_config
from app.main import app
from app.memory.card_retriever import MemoryCandidate
from app.memory.state_schema import StateTableRow
from app.storage.sqlite_state import SQLiteStateStore
from tests._fakes import FakeChatProvider


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
    cfg.embedding.enabled = True
    cfg.memory.extraction_enabled = False
    cfg.memory.state_updater.enabled = False
    cfg.memory.retrieval_gate.vector_search_on_new_session = False
    set_config(cfg)
    return cfg


async def seed_state_table_row(db_path: str, conversation_id: str, content: str) -> None:
    store = SQLiteStateStore(db_path)
    await store.ensure_conversation_config(conversation_id)
    template = await store.get_conversation_table_template(conversation_id)
    assert template is not None
    table = next((item for item in template.tables if item.table_key == "current_interaction"), template.tables[0])
    values = {}
    if any(column.column_key == "topic" for column in table.columns):
        values["topic"] = content
    else:
        values[table.columns[0].column_key] = content
    await store.upsert_table_row(StateTableRow(
        row_id=None,
        conversation_id=conversation_id,
        template_id=template.template_id or "",
        table_id=table.table_id or "",
        table_key=table.table_key,
        priority=80,
        confidence=0.9,
        source="test",
    ), values=values)


@pytest.mark.asyncio
async def test_non_stream_request_injects_state_board(monkeypatch):
    test_dir = make_test_dir()
    try:
        cfg = configure_app(test_dir)
        provider = FakeChatProvider()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)
        cfg.embedding.enabled = False
        await seed_state_table_row(cfg.storage.sqlite.memory_db, "conv1", "测试状态内容")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions", json={
                "model": "fake-model",
                "messages": [
                    {"role": "system", "content": "你是 Yuki。"},
                    {"role": "user", "content": "继续"},
                ],
                "metadata": {"conversation_id": "conv1"},
            })
        assert resp.status_code == 200
        contents = [message["content"] for message in provider.captured_bodies[-1]["messages"]]
        assert any("KokoroMemo 会话状态板" in content for content in contents)
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_state_only_policy_skips_memory_retrieval(monkeypatch):
    test_dir = make_test_dir()
    try:
        cfg = configure_app(test_dir)
        provider = FakeChatProvider()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)
        cfg.embedding.enabled = True
        store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
        await store.set_default_conversation_config({"profile_id": "rimtalk_colony"})
        await store.ensure_conversation_config("conv_state_only")

        def fail_embedding(_self, _cfg):
            raise AssertionError("memory retrieval should be skipped by state_only policy")

        monkeypatch.setattr("app.core.services.ServiceRegistry.get_embedding_provider", fail_embedding)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions", json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "殖民地今天发生了什么？"}],
                "metadata": {"conversation_id": "conv_state_only"},
            })
        assert resp.status_code == 200
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_short_text_skips_vector_retrieval(monkeypatch):
    test_dir = make_test_dir()
    try:
        configure_app(test_dir)
        provider = FakeChatProvider()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)

        def fail_embedding(_self, _cfg):
            raise AssertionError("embedding should be skipped")

        monkeypatch.setattr("app.core.services.ServiceRegistry.get_embedding_provider", fail_embedding)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions", json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "嗯"}],
                "metadata": {"conversation_id": "conv_short"},
            })
        assert resp.status_code == 200
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_keyword_triggers_vector_retrieval(monkeypatch):
    test_dir = make_test_dir()
    called = {"embedding": False, "retrieve": False}
    try:
        configure_app(test_dir)
        provider = FakeChatProvider()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)

        def fake_embedding(_self, _cfg):
            called["embedding"] = True
            return object()

        async def fake_retrieve_cards(*args, **kwargs):
            called["retrieve"] = True
            return []

        monkeypatch.setattr("app.core.services.ServiceRegistry.get_embedding_provider", fake_embedding)
        monkeypatch.setattr("app.core.services.ServiceRegistry.get_lancedb_store", lambda _self, _cfg: object())
        monkeypatch.setattr("app.memory.card_retriever.retrieve_cards", fake_retrieve_cards)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions", json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "你还记得上次的约定吗"}],
                "metadata": {"conversation_id": "conv_keyword"},
            })
        assert resp.status_code == 200
        assert called == {"embedding": True, "retrieve": True}
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_retrieval_profile_controls_retrieval_limits(monkeypatch):
    test_dir = make_test_dir()
    captured: dict[str, object] = {}
    try:
        cfg = configure_app(test_dir)
        provider = FakeChatProvider()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)

        store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
        await store.set_conversation_config({
            "conversation_id": "conv_high_recall",
            "profile_id": "airp_roleplay",
            "retrieval_profile_id": "high_recall",
        })

        def fake_embedding(_self, _cfg):
            return object()

        async def fake_retrieve_cards(*args, **kwargs):
            captured.update(kwargs)
            return []

        monkeypatch.setattr("app.core.services.ServiceRegistry.get_embedding_provider", fake_embedding)
        monkeypatch.setattr("app.core.services.ServiceRegistry.get_lancedb_store", lambda _self, _cfg: object())
        monkeypatch.setattr("app.memory.card_retriever.retrieve_cards", fake_retrieve_cards)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions", json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "please recall the detailed setting we discussed before"}],
                "metadata": {"conversation_id": "conv_high_recall"},
            })
        assert resp.status_code == 200
        assert captured["vector_top_k"] == 50
        assert captured["final_top_k"] == 10
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_retrieval_trace_records_selected_candidates(monkeypatch):
    test_dir = make_test_dir()
    try:
        configure_app(test_dir)
        provider = FakeChatProvider()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)

        def fake_embedding(_self, _cfg):
            return object()

        async def fake_retrieve_cards(*args, **kwargs):
            return [MemoryCandidate(
                card_id="card_trace_1",
                content="用户喜欢热茶",
                scope="global",
                card_type="preference",
                importance=0.8,
                confidence=0.9,
                vector_score=0.88,
                final_score=0.86,
                source="vector",
                library_id="lib_default",
                source_conversation_id="conv_source",
                source_character_id="char_source",
                importance_score=0.8,
                recency_score=0.7,
                scope_score=0.7,
                confidence_score=0.9,
            )]

        monkeypatch.setattr("app.core.services.ServiceRegistry.get_embedding_provider", fake_embedding)
        monkeypatch.setattr("app.core.services.ServiceRegistry.get_lancedb_store", lambda _self, _cfg: object())
        monkeypatch.setattr("app.memory.card_retriever.retrieve_cards", fake_retrieve_cards)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions", json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "你还记得我的偏好吗"}],
                "metadata": {"conversation_id": "conv_trace", "character_id": "char_trace"},
            })
            assert resp.status_code == 200

            traces_resp = await client.get("/admin/conversations/conv_trace/retrieval-traces")
            assert traces_resp.status_code == 200
            traces = traces_resp.json()["items"]
            assert len(traces) == 1
            assert traces[0]["final_injected_count"] == 1
            assert traces[0]["retrieval_profile_id"] == "balanced"

            detail_resp = await client.get(f"/admin/retrieval-traces/{traces[0]['trace_id']}")
            assert detail_resp.status_code == 200
            assert '"final_top_k": 6' in detail_resp.json()["retrieval_profile_json"]
            candidates = detail_resp.json()["candidates"]
            assert len(candidates) == 1
            assert candidates[0]["card_id"] == "card_trace_1"
            assert candidates[0]["library_id"] == "lib_default"
            assert candidates[0]["selected"] == 1
            assert candidates[0]["injection_reason"] == "selected_for_injection"
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_stream_request_injects_state_board(monkeypatch):
    test_dir = make_test_dir()
    try:
        cfg = configure_app(test_dir)
        provider = FakeChatProvider()
        FakeChatProvider.captured_bodies.clear()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)
        cfg.embedding.enabled = False
        await seed_state_table_row(cfg.storage.sqlite.memory_db, "conv_stream", "测试状态内容")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions", json={
                "model": "fake-model",
                "stream": True,
                "messages": [
                    {"role": "system", "content": "你是助手。"},
                    {"role": "user", "content": "继续"},
                ],
                "metadata": {"conversation_id": "conv_stream"},
            })
        assert resp.status_code == 200
        contents = [message["content"] for message in provider.captured_bodies[-1]["messages"]]
        assert any("KokoroMemo 会话状态板" in content for content in contents)
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_new_session_triggers_retrieval(monkeypatch):
    test_dir = make_test_dir()
    called = {"embedding": False, "retrieve": False}
    try:
        cfg = configure_app(test_dir)
        cfg.memory.retrieval_gate.vector_search_on_new_session = True
        provider = FakeChatProvider()
        FakeChatProvider.captured_bodies.clear()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)

        def fake_embedding(_self, _cfg):
            called["embedding"] = True
            return object()

        async def fake_retrieve_cards(*args, **kwargs):
            called["retrieve"] = True
            return []

        monkeypatch.setattr("app.core.services.ServiceRegistry.get_embedding_provider", fake_embedding)
        monkeypatch.setattr("app.core.services.ServiceRegistry.get_lancedb_store", lambda _self, _cfg: object())
        monkeypatch.setattr("app.memory.card_retriever.retrieve_cards", fake_retrieve_cards)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions", json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "你好啊今天天气不错"}],
                "metadata": {"conversation_id": "conv_new_session"},
            })
        assert resp.status_code == 200
        assert called["embedding"] is True
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_embedding_failure_allows_state_injection(monkeypatch):
    test_dir = make_test_dir()
    try:
        cfg = configure_app(test_dir)
        provider = FakeChatProvider()
        FakeChatProvider.captured_bodies.clear()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)

        def fail_embedding(_self, _cfg):
            raise RuntimeError("embedding service down")

        monkeypatch.setattr("app.core.services.ServiceRegistry.get_embedding_provider", fail_embedding)
        await seed_state_table_row(cfg.storage.sqlite.memory_db, "conv_emb_fail", "测试状态内容")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions", json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "还记得上次吗"}],
                "metadata": {"conversation_id": "conv_emb_fail"},
            })
        assert resp.status_code == 200
        contents = [message["content"] for message in provider.captured_bodies[-1]["messages"]]
        assert any("KokoroMemo 会话状态板" in content for content in contents)
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_state_updater_failure_doesnt_affect_chat(monkeypatch):
    test_dir = make_test_dir()
    try:
        cfg = configure_app(test_dir)
        cfg.memory.state_updater.enabled = True
        cfg.embedding.enabled = False
        provider = FakeChatProvider()
        FakeChatProvider.captured_bodies.clear()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)

        async def fail_updater(*args, **kwargs):
            raise RuntimeError("state updater crashed")

        monkeypatch.setattr("app.pipeline.chat.fill_conversation_state_tables", fail_updater)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions", json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "我们去车站吧"}],
                "metadata": {"conversation_id": "conv_upd_fail"},
            })
        assert resp.status_code == 200
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_resolved_state_item_not_injected(monkeypatch):
    test_dir = make_test_dir()
    try:
        cfg = configure_app(test_dir)
        provider = FakeChatProvider()
        FakeChatProvider.captured_bodies.clear()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)
        cfg.embedding.enabled = False

        store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
        template = await store.get_default_table_template()
        assert template is not None
        table = template.tables[0]
        row = StateTableRow(
            row_id=None,
            conversation_id="conv_resolve",
            template_id=template.template_id or "",
            table_id=table.table_id or "",
            table_key=table.table_key,
            status="active",
            confidence=0.9,
        )
        first_col = next(col for col in table.columns if col.include_in_prompt)
        row_id = await store.upsert_table_row(row, {first_col.column_key: "秘密基地"})
        await store.update_table_row_status(row_id, "resolved", "场景结束")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/chat/completions", json={
                "model": "fake-model",
                "messages": [
                    {"role": "system", "content": "你是助手。"},
                    {"role": "user", "content": "继续"},
                ],
                "metadata": {"conversation_id": "conv_resolve"},
            })
        assert resp.status_code == 200
        contents = [message["content"] for message in provider.captured_bodies[-1]["messages"]]
        assert not any("秘密基地" in content for content in contents)
    finally:
        cleanup_test_dir(test_dir)
