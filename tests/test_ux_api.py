from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import AppConfig
from app.core.state import set_config
from app.main import app
from app.storage.sqlite_cards import init_cards_db, insert_inbox_item


def make_test_dir() -> Path:
    root = Path(".test_tmp") / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def cleanup_test_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def make_config(test_dir: Path) -> AppConfig:
    cfg = AppConfig()
    cfg.storage.root_dir = str(test_dir)
    cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
    cfg.embedding.enabled = False
    cfg.server.allow_remote_access = True
    set_config(cfg)
    return cfg


@pytest.mark.asyncio
async def test_config_status_empty_config():
    test_dir = make_test_dir()
    try:
        make_config(test_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/config-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "health_score" in data
        assert data["health_score"] < 100
        assert data["components"]["llm"]["configured"] is False
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_config_status_with_llm_configured():
    test_dir = make_test_dir()
    try:
        cfg = make_config(test_dir)
        cfg.llm.base_url = "https://api.example.com/v1"
        cfg.llm.api_key = "test-key"
        cfg.llm.model = "test-model"
        set_config(cfg)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/config-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["components"]["llm"]["configured"] is True
        assert data["components"]["llm"]["required"] is True
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_connectivity_test_skips_unconfigured_provider():
    test_dir = make_test_dir()
    try:
        make_config(test_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/admin/connectivity-test", json={"target": "llm"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["results"]["llm"]["status"] == "skipped"
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_connectivity_test_all_skips_unconfigured():
    test_dir = make_test_dir()
    try:
        make_config(test_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/admin/connectivity-test", json={"target": "all"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        for provider in ["llm", "embedding", "rerank", "judge", "state_filler"]:
            assert data["results"][provider]["status"] == "skipped"
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_action_items_empty_db():
    test_dir = make_test_dir()
    try:
        cfg = make_config(test_dir)
        await init_cards_db(cfg.storage.sqlite.memory_db)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/action-items")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["items"] == []
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_action_items_reports_pending_inbox():
    test_dir = make_test_dir()
    try:
        cfg = make_config(test_dir)
        await init_cards_db(cfg.storage.sqlite.memory_db)
        await insert_inbox_item(
            cfg.storage.sqlite.memory_db,
            inbox_id="pending_test",
            candidate_type="card",
            payload_json='{"content":"test"}',
            user_id="u",
            character_id="c",
            conversation_id="v",
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/action-items")
        assert resp.status_code == 200
        data = resp.json()
        pending_items = [i for i in data["items"] if i["key"] == "inbox_pending"]
        assert len(pending_items) == 1
        assert pending_items[0]["count"] == 1
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_inbox_batch_approve():
    test_dir = make_test_dir()
    try:
        cfg = make_config(test_dir)
        await init_cards_db(cfg.storage.sqlite.memory_db)
        for i in range(2):
            await insert_inbox_item(
                cfg.storage.sqlite.memory_db,
                inbox_id=f"batch_approve_{i}",
                candidate_type="card",
                payload_json=json.dumps({
                    "content": f"记忆 {i}",
                    "card_type": "preference",
                    "scope": "global",
                    "importance": 0.8,
                    "confidence": 0.9,
                }),
                user_id="u",
                character_id="c",
                conversation_id="v",
            )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/admin/inbox/batch", json={
                "action": "approve",
                "inbox_ids": ["batch_approve_0", "batch_approve_1"],
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["ok"] == 2
        assert data["failed"] == 0
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_inbox_batch_reject():
    test_dir = make_test_dir()
    try:
        cfg = make_config(test_dir)
        await init_cards_db(cfg.storage.sqlite.memory_db)
        await insert_inbox_item(
            cfg.storage.sqlite.memory_db,
            inbox_id="batch_reject",
            candidate_type="card",
            payload_json=json.dumps({
                "content": "test",
                "card_type": "event",
                "scope": "global",
                "importance": 0.5,
                "confidence": 0.6,
            }),
            user_id="u",
            character_id="c",
            conversation_id="v",
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/admin/inbox/batch", json={
                "action": "reject",
                "inbox_ids": ["batch_reject"],
                "note": "非长期记忆",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["ok"] == 1
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_inbox_batch_rejects_invalid_action():
    test_dir = make_test_dir()
    try:
        make_config(test_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/admin/inbox/batch", json={
                "action": "invalid",
                "inbox_ids": ["some_id"],
            })
        assert resp.status_code == 400
    finally:
        cleanup_test_dir(test_dir)
