from __future__ import annotations

import shutil
import sqlite3
import uuid
from pathlib import Path

import pytest

from app.memory.query_builder import RetrievalQuery
from app.memory.retrieval_gate import RetrievalGateInput, decide_retrieval
from app.memory.state_injector import inject_state_board
from app.memory.state_renderer import HOT_CONTEXT_HEADER, render_state_board
from app.memory.state_schema import ConversationStateItem, StateRenderOptions
from app.storage.sqlite_state import SQLiteStateStore, init_state_db


def make_test_dir() -> Path:
    root = Path(".test_tmp") / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def cleanup_test_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def make_query(text: str) -> RetrievalQuery:
    return RetrievalQuery(text, text, f"user: {text}", {"user_id": "u1", "character_id": "c1", "conversation_id": "conv1"})


@pytest.mark.asyncio
async def test_state_schema_initializes_tables():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        await init_state_db(str(memory_db))
        with sqlite3.connect(memory_db) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"conversation_state_items", "conversation_state_events", "retrieval_decisions"} <= tables
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_state_store_upsert_list_resolve_and_decision():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        store = SQLiteStateStore(str(memory_db))
        item_id = await store.upsert_item(
            ConversationStateItem(
                item_id=None,
                conversation_id="conv1",
                user_id="u1",
                character_id="c1",
                category="scene",
                title="地点",
                content="两人正在旧图书馆调查线索",
                confidence=0.9,
                priority=3,
            )
        )

        items = await store.list_active_items("conv1")
        assert len(items) == 1
        assert items[0].item_id == item_id
        assert items[0].metadata == {}

        decision_id = await store.record_retrieval_decision(
            conversation_id="conv1",
            mode="auto",
            should_retrieve=False,
            reason="state_sufficient",
            reasons=["state_sufficient"],
            latest_user_text="继续",
            state_item_count=1,
            avg_state_confidence=0.9,
        )
        assert decision_id.startswith("gate_")

        await store.resolve_item(item_id, "完成调查")
        assert await store.list_active_items("conv1") == []
    finally:
        cleanup_test_dir(test_dir)


def test_state_renderer_empty_returns_empty():
    assert render_state_board([], StateRenderOptions()) == ""


def test_state_renderer_respects_order_and_budget():
    items = [
        ConversationStateItem(None, "conv1", "scene", "正在雨夜码头等待联系人", confidence=0.8),
        ConversationStateItem(None, "conv1", "boundary", "不要替用户决定角色行动", confidence=0.9),
    ]
    rendered = render_state_board(
        items,
        StateRenderOptions(
            max_chars=500,
            section_order=["boundary", "scene"],
            include_sections={"boundary": True, "scene": True},
            max_items_per_section={"boundary": 1, "scene": 1},
        ),
    )
    assert rendered.startswith(HOT_CONTEXT_HEADER)
    assert rendered.index("稳定边界") < rendered.index("当前场景")


def test_state_injector_preserves_original_system_prompt():
    messages = [
        {"role": "system", "content": "原始设定"},
        {"role": "user", "content": "继续"},
    ]
    injected = inject_state_board(messages, HOT_CONTEXT_HEADER)
    assert injected[0]["content"] == "原始设定"
    assert injected[1]["content"] == HOT_CONTEXT_HEADER
    assert injected[2]["role"] == "user"


def test_retrieval_gate_keyword_triggers():
    decision = decide_retrieval(
        RetrievalGateInput(
            query=make_query("你还记得上次的约定吗"),
            state_items=[ConversationStateItem(None, "conv1", "scene", "正在聊天")],
            turn_index=3,
            trigger_keywords=["还记得", "约定"],
        )
    )
    assert decision.should_retrieve is True
    assert decision.reason.startswith("keyword:")


def test_retrieval_gate_short_text_skips():
    decision = decide_retrieval(
        RetrievalGateInput(
            query=make_query("嗯"),
            state_items=[],
            turn_index=3,
            vector_search_on_new_session=False,
            trigger_keywords=[],
            skip_when_latest_user_text_chars_below=4,
        )
    )
    assert decision.should_retrieve is False
    assert decision.reason == "short_latest_user_text"


def test_retrieval_gate_low_confidence_triggers():
    decision = decide_retrieval(
        RetrievalGateInput(
            query=make_query("继续推进剧情"),
            state_items=[ConversationStateItem(None, "conv1", "scene", "地点不确定", confidence=0.3)],
            turn_index=3,
            vector_search_on_new_session=False,
            trigger_keywords=[],
            vector_search_when_state_confidence_below=0.65,
        )
    )
    assert decision.should_retrieve is True
    assert decision.reason == "low_state_confidence"
