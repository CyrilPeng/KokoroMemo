from __future__ import annotations

import sqlite3
import shutil
import uuid
from pathlib import Path

import pytest

from app.memory.card_retriever import retrieve_cards
from app.memory.graph import insert_edge
from app.memory.query_builder import RetrievalQuery
from app.memory.review_policy import auto_review
from app.providers.embedding_dummy import DummyEmbeddingProvider
from app.storage.sqlite_cards import init_cards_db, insert_card
from app.storage.sqlite_conversation import init_chat_db


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
        assert {"memory_cards", "memory_card_versions", "review_actions", "jobs"} <= tables

        with sqlite3.connect(chat_db) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "injected_memory_logs" in tables
    finally:
        cleanup_test_dir(test_dir)


def test_preference_defaults_to_pending_review():
    assert auto_review("preference", importance=0.8, confidence=0.9, risk_level="low") == "pending"


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
