"""Tests for v0.5.x feature additions: scopes filtering, character defaults, retrieval gate
keyword_only mode, WebSocket event bus, and memory-graph endpoint."""

from __future__ import annotations

import asyncio
import shutil
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


def _make_cfg(test_dir: Path) -> AppConfig:
    cfg = AppConfig()
    cfg.storage.root_dir = str(test_dir)
    cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
    cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
    cfg.embedding.enabled = False
    cfg.memory.enabled = False
    return cfg


# --- 1. SillyTavern import ---


@pytest.mark.asyncio
async def test_sillytavern_import_creates_conversation_and_extracts_memories():
    test_dir = make_test_dir()
    try:
        cfg = _make_cfg(test_dir)
        set_config(cfg)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            jsonl = (
                '{"name": "System", "is_user": false, "is_system": true, "mes": "You are an assistant."}\n'
                '{"name": "User", "is_user": true, "mes": "Hello"}\n'
                '{"name": "Aria", "is_user": false, "mes": "Hi there!"}\n'
            )
            resp = await client.post(
                "/admin/import/sillytavern",
                json={"content": jsonl, "user_id": "default"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["turns_imported"] >= 2
            conversation_id = data["conversation_id"]
            assert conversation_id.startswith("conv_import_")

            # extract-memories with embedding disabled — should still respond gracefully
            resp2 = await client.post(
                f"/admin/import/{conversation_id}/extract-memories",
                json={"max_pairs": 5},
            )
            assert resp2.status_code == 200
            assert resp2.json()["status"] == "ok"
    finally:
        cleanup_test_dir(test_dir)


# --- 2. Character defaults / discovered characters ---


@pytest.mark.asyncio
async def test_upsert_character_lazy_insert_and_discovered_endpoint():
    test_dir = make_test_dir()
    try:
        cfg = _make_cfg(test_dir)
        set_config(cfg)

        from app.storage.sqlite_app import init_app_db, upsert_character, upsert_conversation
        await init_app_db(cfg.storage.sqlite.app_db)
        await upsert_conversation(
            cfg.storage.sqlite.app_db,
            conversation_id="conv_a",
            user_id="default",
            character_id="char_aria",
            client_name="test",
            conv_path=str(test_dir / "conv_a"),
        )
        await upsert_character(
            cfg.storage.sqlite.app_db,
            character_id="char_aria",
            user_id="default",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # /admin/characters returns from characters table (now populated)
            resp = await client.get("/admin/characters")
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert any(c["character_id"] == "char_aria" for c in items)

            # /admin/discovered-characters derives from conversations
            resp2 = await client.get("/admin/discovered-characters")
            assert resp2.status_code == 200
            discovered = resp2.json()["items"]
            assert any(c["character_id"] == "char_aria" and c["conversation_count"] == 1 for c in discovered)

            # set defaults
            resp3 = await client.post(
                "/admin/characters/char_aria/defaults",
                json={"template_id": "tpl_x", "library_ids": ["lib_default"], "auto_apply": True},
            )
            assert resp3.json()["status"] == "ok"
            resp4 = await client.get("/admin/discovered-characters")
            updated = resp4.json()["items"]
            assert any(c["character_id"] == "char_aria" and c["template_id"] == "tpl_x" for c in updated)
    finally:
        cleanup_test_dir(test_dir)


# --- 3. retrieval_gate keyword_only mode ---


def test_retrieval_gate_keyword_only_mode_matches_keyword():
    from app.memory.retrieval_gate import RetrievalGateInput, decide_retrieval
    from app.memory.query_builder import RetrievalQuery

    query = RetrievalQuery(
        query_text="还记得那个人吗",
        latest_user_text="还记得那个人吗",
        recent_context_text="",
        scope_filter={"user_id": "default"},
    )
    decision = decide_retrieval(RetrievalGateInput(
        query=query,
        mode="keyword_only",
        trigger_keywords=["还记得", "上次"],
    ))
    assert decision.should_retrieve is True
    assert decision.mode == "keyword_only"
    assert decision.reason.startswith("keyword:")


def test_retrieval_gate_keyword_only_mode_no_match_skips():
    from app.memory.retrieval_gate import RetrievalGateInput, decide_retrieval
    from app.memory.query_builder import RetrievalQuery

    query = RetrievalQuery(
        query_text="hello there",
        latest_user_text="hello there",
        recent_context_text="",
        scope_filter={"user_id": "default"},
    )
    decision = decide_retrieval(RetrievalGateInput(
        query=query,
        mode="keyword_only",
        trigger_keywords=["还记得"],
    ))
    assert decision.should_retrieve is False
    assert decision.reason == "no_keyword_match"


# --- 4. WebSocket event bus ---


@pytest.mark.asyncio
async def test_event_bus_publish_subscribe():
    from app.core.events import emit, subscribe, unsubscribe

    received: list[tuple[str, dict]] = []

    async def listener(event_type: str, payload: dict) -> None:
        received.append((event_type, payload))

    subscribe(listener)
    try:
        await emit("inbox_new", {"card_id": "c1", "content": "hello"})
        await asyncio.sleep(0.05)
        assert any(e == "inbox_new" and p.get("card_id") == "c1" for e, p in received)
    finally:
        unsubscribe(listener)


# --- 5. Memory graph endpoint ---


@pytest.mark.asyncio
async def test_admin_memory_graph_returns_nodes_and_edges():
    test_dir = make_test_dir()
    try:
        cfg = _make_cfg(test_dir)
        set_config(cfg)

        from app.memory.graph import insert_edge
        from app.storage.sqlite_cards import init_cards_db, insert_card
        await init_cards_db(cfg.storage.sqlite.memory_db)
        await insert_card(
            cfg.storage.sqlite.memory_db,
            card_id="card_a", library_id="lib_default", user_id="default",
            character_id=None, conversation_id=None, scope="global",
            card_type="preference", content="prefers tea", importance=0.8,
            confidence=0.9, status="approved",
        )
        await insert_card(
            cfg.storage.sqlite.memory_db,
            card_id="card_b", library_id="lib_default", user_id="default",
            character_id=None, conversation_id=None, scope="global",
            card_type="boundary", content="no spoilers", importance=0.7,
            confidence=0.85, status="approved",
        )
        await insert_edge(
            cfg.storage.sqlite.memory_db,
            source_card_id="card_a", target_card_id="card_b",
            edge_type="related", weight=0.6, confidence=0.7,
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/memory-graph")
            assert resp.status_code == 200
            data = resp.json()
            node_ids = {n["id"] for n in data["nodes"]}
            assert "card_a" in node_ids and "card_b" in node_ids
            assert any(e["source"] == "card_a" and e["target"] == "card_b" for e in data["edges"])
    finally:
        cleanup_test_dir(test_dir)


# --- 6. Scopes filtering in retriever ---


def test_retrieve_cards_returns_empty_when_all_scopes_disabled():
    """allowed_scopes=set() should short-circuit and return [] without hitting DB."""
    import asyncio as _asyncio
    from app.memory.card_retriever import retrieve_cards
    from app.memory.query_builder import RetrievalQuery

    query = RetrievalQuery(
        query_text="anything",
        latest_user_text="anything",
        recent_context_text="",
        scope_filter={"user_id": "default", "character_id": None, "conversation_id": None},
    )
    # No DB calls should happen — pass None for embedding/store/path; they're never used
    result = _asyncio.run(
        retrieve_cards(
            query=query,
            embedding_provider=None,  # type: ignore
            lancedb_store=None,  # type: ignore
            cards_db_path="",
            allowed_scopes=set(),
        )
    )
    assert result == []
