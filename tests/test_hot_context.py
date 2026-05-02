from __future__ import annotations

import shutil
import sqlite3
import uuid
from pathlib import Path

import pytest

from app.memory.query_builder import RetrievalQuery
from app.memory.retrieval_gate import RetrievalGateInput, decide_retrieval
from app.memory.state_projector import project_cards_to_state
from app.memory.state_filler import StateFillerConfigView, fill_conversation_state
from app.memory.state_updater import rule_based_state_updates
from app.memory.state_injector import inject_state_board
from app.memory.state_renderer import HOT_CONTEXT_HEADER, render_state_board

HOT_CONTEXT_HEADER_ZH = HOT_CONTEXT_HEADER["zh"]
from app.memory.state_schema import ConversationStateItem, StateRenderOptions
from app.storage.sqlite_state import SQLiteStateStore, init_state_db
from app.storage.sqlite_cards import init_cards_db, insert_card


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
        assert {
            "conversation_state_items",
            "conversation_state_events",
            "retrieval_decisions",
            "state_board_templates",
            "state_board_tabs",
            "state_board_fields",
            "conversation_state_boards",
        } <= tables
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_old_state_schema_migrates_field_columns_before_indexes():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        with sqlite3.connect(memory_db) as conn:
            conn.executescript("""
            CREATE TABLE conversation_state_items (
              item_id TEXT PRIMARY KEY,
              user_id TEXT,
              character_id TEXT,
              conversation_id TEXT NOT NULL,
              world_id TEXT,
              category TEXT NOT NULL,
              item_key TEXT,
              title TEXT,
              content TEXT NOT NULL,
              item_value TEXT,
              status TEXT NOT NULL DEFAULT 'active',
              priority INTEGER NOT NULL DEFAULT 50,
              confidence REAL NOT NULL DEFAULT 0.8,
              source TEXT NOT NULL DEFAULT 'manual',
              metadata_json TEXT,
              ttl_turns INTEGER,
              created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
              last_seen_at TEXT,
              expires_at TEXT
            );
            INSERT INTO conversation_state_items (item_id, conversation_id, category, content)
            VALUES ('old_state', 'conv1', 'scene', '旧状态');
            CREATE TABLE conversation_state_events (
              event_id TEXT PRIMARY KEY,
              item_id TEXT,
              conversation_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              payload_json TEXT,
              created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            CREATE TABLE retrieval_decisions (
              decision_id TEXT PRIMARY KEY,
              conversation_id TEXT NOT NULL,
              mode TEXT NOT NULL DEFAULT 'auto',
              should_retrieve INTEGER NOT NULL,
              reason TEXT,
              reasons_json TEXT,
              latest_user_text TEXT,
              state_item_count INTEGER NOT NULL DEFAULT 0,
              avg_state_confidence REAL,
              turn_index INTEGER,
              created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            """)
        await init_state_db(str(memory_db))
        with sqlite3.connect(memory_db) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(conversation_state_items)")}
            indexes = {row[1] for row in conn.execute("PRAGMA index_list(conversation_state_items)")}
        assert "field_id" in columns
        assert "idx_state_items_unique_field" in indexes
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
        assert items[0].content == "两人正在旧图书馆调查线索"

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


@pytest.mark.asyncio
async def test_state_store_upsert_same_key():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        store = SQLiteStateStore(str(memory_db))
        await store.upsert_item(
            ConversationStateItem(
                item_id=None,
                conversation_id="conv1",
                user_id="u1",
                category="scene",
                item_key="current_scene",
                content="在图书馆",
                confidence=0.8,
            )
        )
        await store.upsert_item(
            ConversationStateItem(
                item_id=None,
                conversation_id="conv1",
                user_id="u1",
                category="scene",
                item_key="current_scene",
                content="前往车站",
                confidence=0.9,
            )
        )
        items = await store.list_active_items("conv1")
        assert len(items) == 1
        assert items[0].content == "前往车站"
        assert items[0].confidence == 0.9
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
    assert rendered.startswith(HOT_CONTEXT_HEADER_ZH)
    assert rendered.index("稳定边界") < rendered.index("当前场景")


def test_state_renderer_budget_limit():
    items = [
        ConversationStateItem(None, "conv1", "scene", f"场景描述{i}" * 10, confidence=0.8)
        for i in range(15)
    ]
    rendered = render_state_board(
        items,
        StateRenderOptions(
            max_chars=200,
            section_order=["scene"],
            include_sections={"scene": True},
            max_items_per_section={"scene": 15},
        ),
    )
    assert len(rendered) <= 200


@pytest.mark.asyncio
async def test_builtin_template_renders_field_tabs():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        store = SQLiteStateStore(str(memory_db))
        template = await store.get_conversation_template("conv1")
        field = template.tabs[0].fields[0]
        item_id = await store.upsert_item(ConversationStateItem(
            item_id=None,
            conversation_id="conv1",
            template_id=template.template_id,
            tab_id=template.tabs[0].tab_id,
            field_id=field.field_id,
            field_key=field.field_key,
            category="preference",
            item_key="user_addressing",
            title=field.label,
            content="用户希望被称为主人",
            confidence=0.92,
        ))
        items = await store.list_active_items("conv1")
        rendered = render_state_board(items, StateRenderOptions(max_chars=500), template)
        assert item_id
        assert "通用角色扮演" in rendered
        assert "称呼用户为：用户希望被称为主人" in rendered
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_template_field_default_value_is_not_rendered_as_state():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        store = SQLiteStateStore(str(memory_db))
        template = await store.get_conversation_template("conv1")
        with sqlite3.connect(memory_db) as db:
            db.execute(
                "UPDATE state_board_fields SET default_value = ? WHERE field_key = ?",
                ("测试值123", "user_addressing"),
            )
            db.commit()
        template = await store.get_conversation_template("conv1")
        rendered = render_state_board([], StateRenderOptions(max_chars=500), template)
        assert rendered == ""
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_builtin_template_has_roleplay_and_speech_fields():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        template = await SQLiteStateStore(str(memory_db)).get_conversation_template("conv1")
        field_keys = {field.field_key for tab in template.tabs for field in tab.fields}
        assert "roleplay_persona" in field_keys
        assert "speech_habit" in field_keys
    finally:
        cleanup_test_dir(test_dir)


class FakeStateFillerProvider:
    def __init__(self, content: str):
        self.content = content
        self.bodies: list[dict] = []

    async def chat(self, body: dict, timeout: int) -> dict:
        self.bodies.append(body)
        return {"choices": [{"message": {"content": self.content}}]}

    async def stream_chat(self, body: dict, timeout: int):
        yield "data: [DONE]"


@pytest.mark.asyncio
async def test_state_filler_updates_template_field(monkeypatch):
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        provider = FakeStateFillerProvider('{"updates":[{"field_key":"user_addressing","value":"用户希望被称为主人","confidence":0.91}]}')
        monkeypatch.setattr("app.memory.state_filler.create_llm_provider", lambda **kwargs: provider)
        result = await fill_conversation_state(
            db_path=str(memory_db),
            conversation_id="conv1",
            user_message="从现在起叫我主人",
            assistant_message="好的，主人。",
            config=StateFillerConfigView(provider="openai_compatible", base_url="http://fake", api_key="key", model="cheap-model"),
        )
        assert result.applied == 1
        items = await SQLiteStateStore(str(memory_db)).list_active_items("conv1")
        assert items[0].field_key == "user_addressing"
        assert items[0].content == "用户希望被称为主人"
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_state_filler_does_not_treat_field_default_as_current(monkeypatch):
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        store = SQLiteStateStore(str(memory_db))
        await store.get_conversation_template("conv1")
        with sqlite3.connect(memory_db) as db:
            db.execute(
                "UPDATE state_board_fields SET default_value = ? WHERE field_key = ?",
                ("测试值123", "user_addressing"),
            )
            db.commit()

        provider = FakeStateFillerProvider('{"updates":[]}')
        monkeypatch.setattr("app.memory.state_filler.create_llm_provider", lambda **kwargs: provider)
        await fill_conversation_state(
            db_path=str(memory_db),
            conversation_id="conv1",
            user_message="你好",
            assistant_message="你好。",
            config=StateFillerConfigView(provider="openai_compatible", base_url="http://fake", api_key="key", model="cheap-model"),
        )

        system_prompt = provider.bodies[0]["messages"][0]["content"]
        assert "测试值123" not in system_prompt
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_state_filler_updates_catgirl_speech_rule(monkeypatch):
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        provider = FakeStateFillerProvider('{"updates":[{"field_key":"roleplay_persona","value":"角色当前扮演猫娘。","confidence":0.92},{"field_key":"speech_habit","value":"每句话末尾加上“喵~”。","confidence":0.93}]}')
        monkeypatch.setattr("app.memory.state_filler.create_llm_provider", lambda **kwargs: provider)
        result = await fill_conversation_state(
            db_path=str(memory_db),
            conversation_id="conv1",
            user_message="从现在开始，你是一只猫娘，你的每句话末尾都要加上`喵~`",
            assistant_message="好的喵~",
            config=StateFillerConfigView(provider="openai_compatible", base_url="http://fake", api_key="key", model="cheap-model"),
        )
        items = await SQLiteStateStore(str(memory_db)).list_active_items("conv1")
        by_key = {item.field_key: item.content for item in items}
        assert result.applied == 2
        assert by_key["roleplay_persona"] == "角色当前扮演猫娘。"
        assert by_key["speech_habit"] == "每句话末尾加上“喵~”。"
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_state_filler_skips_locked_field(monkeypatch):
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        store = SQLiteStateStore(str(memory_db))
        template = await store.get_conversation_template("conv1")
        field = template.tabs[0].fields[0]
        await store.upsert_item(ConversationStateItem(
            item_id=None,
            conversation_id="conv1",
            template_id=template.template_id,
            tab_id=template.tabs[0].tab_id,
            field_id=field.field_id,
            field_key=field.field_key,
            category="preference",
            item_key=field.field_key,
            title=field.label,
            content="用户希望被称为指挥官",
            user_locked=True,
        ))
        provider = FakeStateFillerProvider('{"updates":[{"field_key":"user_addressing","value":"用户希望被称为主人","confidence":0.99}]}')
        monkeypatch.setattr("app.memory.state_filler.create_llm_provider", lambda **kwargs: provider)
        result = await fill_conversation_state(
            db_path=str(memory_db),
            conversation_id="conv1",
            user_message="从现在起叫我主人",
            assistant_message="好的。",
            config=StateFillerConfigView(provider="openai_compatible", base_url="http://fake", api_key="key", model="cheap-model"),
        )
        items = await store.list_active_items("conv1")
        assert result.applied == 0
        assert items[0].content == "用户希望被称为指挥官"
    finally:
        cleanup_test_dir(test_dir)


def test_state_injector_preserves_original_system_prompt():
    messages = [
        {"role": "system", "content": "原始设定"},
        {"role": "user", "content": "继续"},
    ]
    injected = inject_state_board(messages, HOT_CONTEXT_HEADER_ZH)
    assert injected[0]["content"] == "原始设定"
    assert injected[1]["content"] == HOT_CONTEXT_HEADER_ZH
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


def test_retrieval_gate_new_session():
    decision = decide_retrieval(
        RetrievalGateInput(
            query=make_query("你好啊今天天气不错"),
            state_items=[],
            turn_index=0,
            vector_search_on_new_session=True,
            trigger_keywords=[],
            skip_when_latest_user_text_chars_below=4,
        )
    )
    assert decision.should_retrieve is True
    assert "new_session" in decision.reason


def test_state_updater_rule_location_and_promise():
    updates = rule_based_state_updates("我们去车站吧，我答应会买票", "好，下一步需要确认发车时间。")
    categories = {update.category for update in updates}
    assert "location" in categories
    assert "promise" in categories
    assert "main_quest" in categories


def test_state_updater_rule_boundary():
    updates = rule_based_state_updates("不要替我决定角色行动", "明白。")
    assert any(update.category == "boundary" for update in updates)


@pytest.mark.asyncio
async def test_project_approved_boundary_card_to_state():
    test_dir = make_test_dir()
    memory_db = test_dir / "memory.sqlite"
    try:
        await init_cards_db(str(memory_db))
        await init_state_db(str(memory_db))
        await insert_card(
            str(memory_db), "card_boundary", "u1", "c1", None,
            "character", "boundary", "不要替用户决定角色行动", status="approved", confidence=0.9,
        )
        result = await project_cards_to_state(str(memory_db), "conv1", user_id="u1", character_id="c1")
        assert result["projected"] == 1
        items = await SQLiteStateStore(str(memory_db)).list_active_items("conv1")
        assert items[0].linked_card_ids == ["card_boundary"]
    finally:
        cleanup_test_dir(test_dir)
