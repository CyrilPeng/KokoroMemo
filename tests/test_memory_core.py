from __future__ import annotations

import sqlite3
import shutil
import uuid
from pathlib import Path

import pytest

from app.core.variables import relative_time_label
from app.memory.card_retriever import retrieve_cards
from app.memory.card_extractor import extract_and_route
from app.memory.judge import MemoryJudgeConfigView, judge_memories_with_llm
from app.memory.graph import insert_edge
from app.memory.query_builder import RetrievalQuery
from app.memory.review_policy import auto_review
from app.providers.embedding_dummy import DummyEmbeddingProvider
from app.storage.sqlite_app import init_app_db
from app.storage.sqlite_cards import (
    DEFAULT_MEMORY_LIBRARY_ID,
    create_memory_library,
    get_conversation_mounts,
    init_cards_db,
    insert_card,
    list_memory_libraries,
    set_conversation_mounts,
)
from app.storage.sqlite_conversation import init_chat_db, save_raw_request


class FakeLanceDBStore:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def search(self, query_vector, where=None, top_k=30, select_columns=None):
        return self.rows[:top_k]


def make_test_dir() -> Path:
    root = Path(".test_tmp") / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def cleanup_test_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def test_relative_time_accepts_local_sqlite_timestamp():
    now_text = sqlite3.connect(":memory:").execute("SELECT datetime('now', 'localtime')").fetchone()[0]
    assert relative_time_label(now_text) == "\u521a\u624d"


@pytest.mark.asyncio
async def test_sqlite_defaults_use_localtime_and_writes_explicit_localtime():
    test_dir = make_test_dir()
    app_db = test_dir / "app.sqlite"
    chat_db = test_dir / "chat.sqlite"
    try:
        await init_app_db(str(app_db))
        await init_chat_db(str(chat_db))
        await save_raw_request(str(chat_db), "req1", "conv1", "{}")

        for db_path in (app_db, chat_db):
            with sqlite3.connect(db_path) as conn:
                schemas = "\n".join(row[0] or "" for row in conn.execute("SELECT sql FROM sqlite_master WHERE type='table'"))
            assert "datetime('now'))" not in schemas
            assert "datetime('now', 'localtime')" in schemas

        with sqlite3.connect(chat_db) as conn:
            created_at = conn.execute("SELECT created_at FROM raw_requests WHERE request_id = 'req1'").fetchone()[0]
            local_now = conn.execute("SELECT datetime('now', 'localtime')").fetchone()[0]
        assert created_at[:13] == local_now[:13]
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_schema_initializes_card_and_chat_tables():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    chat_db = test_dir / "chat.sqlite"

    try:
        await init_cards_db(str(memory_db))
        await init_chat_db(str(chat_db))

        with sqlite3.connect(memory_db) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"memory_cards", "memory_card_versions", "review_actions", "jobs", "memory_libraries", "conversation_memory_mounts"} <= tables
        libraries = await list_memory_libraries(str(memory_db))
        assert libraries[0]["library_id"] == DEFAULT_MEMORY_LIBRARY_ID

        with sqlite3.connect(chat_db) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "injected_memory_logs" in tables
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_memory_library_mounts_and_preset_copy():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        await init_cards_db(str(memory_db))
        await insert_card(
            str(memory_db), "card_base", "u1", None, None,
            "global", "preference", "用户喜欢安静的叙事", status="approved",
        )
        lib_id = await create_memory_library(
            str(memory_db), "跑团 A", "测试库", source_library_ids=[DEFAULT_MEMORY_LIBRARY_ID],
        )
        await set_conversation_mounts(str(memory_db), "conv1", [DEFAULT_MEMORY_LIBRARY_ID, lib_id], write_library_id=lib_id)
        mounts = await get_conversation_mounts(str(memory_db), "conv1")
        assert [mount["library_id"] for mount in mounts] == [lib_id, DEFAULT_MEMORY_LIBRARY_ID]
        with sqlite3.connect(memory_db) as conn:
            copied = conn.execute("SELECT COUNT(*) FROM memory_cards WHERE library_id = ?", (lib_id,)).fetchone()[0]
        assert copied == 1
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_old_cards_schema_migrates_library_columns_before_indexes():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        with sqlite3.connect(memory_db) as conn:
            conn.executescript("""
            CREATE TABLE memory_cards (
              card_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              character_id TEXT,
              conversation_id TEXT,
              scope TEXT NOT NULL,
              card_type TEXT NOT NULL,
              content TEXT NOT NULL,
              importance REAL NOT NULL DEFAULT 0.5,
              confidence REAL NOT NULL DEFAULT 0.7,
              status TEXT NOT NULL DEFAULT 'approved',
              is_pinned INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
              access_count INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO memory_cards (card_id, user_id, scope, card_type, content)
            VALUES ('old_card', 'u1', 'global', 'preference', '旧卡片');
            """)
        await init_cards_db(str(memory_db))
        with sqlite3.connect(memory_db) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_cards)")}
            library_id = conn.execute("SELECT library_id FROM memory_cards WHERE card_id = 'old_card'").fetchone()[0]
            indexes = {row[1] for row in conn.execute("PRAGMA index_list(memory_cards)")}
        assert "library_id" in columns
        assert library_id == DEFAULT_MEMORY_LIBRARY_ID
        assert "idx_cards_library" in indexes
    finally:
        cleanup_test_dir(test_dir)


def test_preference_defaults_to_pending_review():
    assert auto_review("preference", importance=0.8, confidence=0.9, risk_level="low") == "pending"


def test_model_suggested_auto_approve_can_approve_low_risk_preference():
    assert auto_review(
        "preference",
        importance=0.9,
        confidence=0.9,
        risk_level="low",
        tags=["suggested_action:auto_approve"],
    ) == "approve"


def test_roleplay_speech_style_can_auto_approve():
    assert auto_review(
        "preference",
        importance=0.9,
        confidence=0.9,
        risk_level="low",
        tags=["roleplay_rule", "speech_style"],
    ) == "approve"


@pytest.mark.asyncio
async def test_vector_retrieval_filters_deprecated_cards():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        await init_cards_db(str(memory_db))
        await insert_card(str(memory_db), "card_old", "u1", "c1", "conv1", "character", "preference", "旧称呼", status="deprecated")

        query = RetrievalQuery("称呼", "称呼", "user: 称呼", {"user_id": "u1", "character_id": "c1", "conversation_id": "conv1"})
        store = FakeLanceDBStore([{"memory_id": "card_old", "_distance": 0.1}])
        results = await retrieve_cards(query, DummyEmbeddingProvider(8), store, str(memory_db))

        assert results == []
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_graph_expands_constrains_card():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        await init_cards_db(str(memory_db))
        await insert_card(str(memory_db), "card_seed", "u1", "c1", "conv1", "character", "preference", "用户喜欢被叫哥哥", status="approved")
        await insert_card(str(memory_db), "card_limit", "u1", "c1", "conv1", "character", "boundary", "不要在严肃场景使用亲昵称呼", status="approved")
        await insert_edge(str(memory_db), "card_seed", "card_limit", "constrains")

        query = RetrievalQuery("称呼", "称呼", "user: 称呼", {"user_id": "u1", "character_id": "c1", "conversation_id": "conv1"})
        store = FakeLanceDBStore([{"memory_id": "card_seed", "_distance": 0.1}])
        results = await retrieve_cards(query, DummyEmbeddingProvider(8), store, str(memory_db), final_top_k=5)

        assert {r.card_id for r in results} == {"card_seed", "card_limit"}
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_retrieval_only_uses_mounted_memory_libraries():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        await init_cards_db(str(memory_db))
        lib_a = await create_memory_library(str(memory_db), "游戏 A")
        lib_b = await create_memory_library(str(memory_db), "游戏 B")
        await insert_card(
            str(memory_db), "card_a", "u1", "c1", "conv1",
            "character", "preference", "A 设定", status="approved", library_id=lib_a,
        )
        await insert_card(
            str(memory_db), "card_b", "u1", "c1", "conv1",
            "character", "preference", "B 设定", status="approved", library_id=lib_b,
        )
        await set_conversation_mounts(str(memory_db), "conv1", [lib_a], write_library_id=lib_a)

        query = RetrievalQuery("设定", "设定", "user: 设定", {"user_id": "u1", "character_id": "c1", "conversation_id": "conv1"})
        store = FakeLanceDBStore([
            {"memory_id": "card_b", "library_id": lib_b, "_distance": 0.01},
            {"memory_id": "card_a", "library_id": lib_a, "_distance": 0.02},
        ])
        results = await retrieve_cards(query, DummyEmbeddingProvider(8), store, str(memory_db), final_top_k=5)
        assert [result.card_id for result in results] == ["card_a"]
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_extraction_disabled_without_judge_config():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        await init_cards_db(str(memory_db))
        store = FakeLanceDBStore([])
        store.upserted = []
        store.upsert = lambda rows: store.upserted.extend(rows)

        await extract_and_route(
            db_path=str(memory_db),
            user_message="从现在起叫我主人",
            assistant_message="好的，主人。",
            user_id="u1",
            character_id="c1",
            conversation_id="conv1",
            embedding_provider=DummyEmbeddingProvider(8),
            lancedb_store=store,
        )

        with sqlite3.connect(memory_db) as conn:
            card_count = conn.execute("SELECT COUNT(*) FROM memory_cards").fetchone()[0]
            inbox_count = conn.execute("SELECT COUNT(*) FROM memory_inbox").fetchone()[0]
        assert card_count == 0
        assert inbox_count == 0
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_llm_memory_judge_extracts_addressing(monkeypatch):
    class FakeProvider:
        async def chat(self, body, timeout):
            return {
                "choices": [{"message": {"content": '{"memories":[{"should_remember":true,"scope":"character","memory_type":"preference","content":"用户希望被称呼为“主人”。","importance":0.9,"confidence":0.9,"risk_level":"low","suggested_action":"auto_approve","tags":["preference","addressing"]}]}'}}]
            }

    monkeypatch.setattr("app.memory.judge.create_llm_provider", lambda **kwargs: FakeProvider())
    memories = await judge_memories_with_llm(
        "从现在起叫我主人",
        "好的，主人。",
        "c1",
        MemoryJudgeConfigView("openai_compatible", "http://judge", "key", "cheap-model"),
    )
    assert len(memories) == 1
    assert memories[0].content == "用户希望被称呼为“主人”。"
    assert "addressing" in memories[0].tags
    assert "suggested_action:auto_approve" in memories[0].tags


@pytest.mark.asyncio
async def test_llm_memory_judge_extracts_catgirl_speech_rule(monkeypatch):
    captured = {}

    class FakeProvider:
        async def chat(self, body, timeout):
            captured["system"] = body["messages"][0]["content"]
            return {
                "choices": [{"message": {"content": '{"memories":[{"should_remember":true,"scope":"character","memory_type":"speech_style","content":"用户要求角色以猫娘身份互动，并在每句话末尾加上“喵~”。","importance":0.9,"confidence":0.9,"risk_level":"low","tags":["roleplay_rule","speech_style"]}]}'}}]
            }

    monkeypatch.setattr("app.memory.judge.create_llm_provider", lambda **kwargs: FakeProvider())
    memories = await judge_memories_with_llm(
        "从现在开始，你是一只猫娘，你的每句话末尾都要加上`喵~`",
        "好的喵~",
        "c1",
        MemoryJudgeConfigView("openai_compatible", "http://judge", "key", "cheap-model"),
    )
    assert "猫娘" in captured["system"]
    assert len(memories) == 1
    assert memories[0].memory_type == "preference"
    assert "猫娘" in memories[0].content
    assert "speech_style" in memories[0].tags


@pytest.mark.asyncio
async def test_memory_judge_injects_user_rules(monkeypatch):
    captured = {}

    class FakeProvider:
        async def chat(self, body, timeout):
            captured["system"] = body["messages"][0]["content"]
            return {"choices": [{"message": {"content": '{"memories":[]}'}}]}

    monkeypatch.setattr("app.memory.judge.create_llm_provider", lambda **kwargs: FakeProvider())
    await judge_memories_with_llm(
        "继续",
        "好的。",
        "c1",
        MemoryJudgeConfigView(
            "openai_compatible",
            "http://judge",
            "key",
            "cheap-model",
            mode="model_with_user_rules",
            user_rules=["用户要求改变称呼时生成 preference。"],
        ),
    )
    assert "用户自定义辅助规则" in captured["system"]
    assert "用户要求改变称呼时生成 preference" in captured["system"]


@pytest.mark.asyncio
async def test_llm_memory_judge_routes_to_approved_card(monkeypatch):
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        await init_cards_db(str(memory_db))
        store = FakeLanceDBStore([])
        store.upserted = []
        store.upsert = lambda rows: store.upserted.extend(rows)

        class FakeProvider:
            async def chat(self, body, timeout):
                return {
                    "choices": [{"message": {"content": '{"memories":[{"should_remember":true,"scope":"character","memory_type":"preference","content":"用户希望被称呼为“主人”。","importance":0.9,"confidence":0.9,"risk_level":"low","suggested_action":"auto_approve","tags":["preference","addressing"]}]}'}}]
                }

        monkeypatch.setattr("app.memory.judge.create_llm_provider", lambda **kwargs: FakeProvider())
        await extract_and_route(
            db_path=str(memory_db),
            user_message="以后都这么称呼我",
            assistant_message="好的，主人。",
            user_id="u1",
            character_id="c1",
            conversation_id="conv1",
            embedding_provider=DummyEmbeddingProvider(8),
            lancedb_store=store,
            judge_config=MemoryJudgeConfigView("openai_compatible", "http://judge", "key", "cheap-model"),
        )

        with sqlite3.connect(memory_db) as conn:
            row = conn.execute("SELECT content, status, vector_synced FROM memory_cards").fetchone()
        assert row == ("用户希望被称呼为“主人”。", "approved", 1)
    finally:
        cleanup_test_dir(test_dir)
