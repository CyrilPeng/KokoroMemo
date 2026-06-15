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
from app.memory.state_schema import StateTableColumn, StateTableRow, StateTableSchema, StateTableTemplate
from app.storage.sqlite_app import init_app_db, upsert_character, upsert_conversation
from app.storage.sqlite_cards import init_cards_db, insert_card, insert_inbox_item
from app.storage.sqlite_state import SQLiteStateStore


def make_test_dir() -> Path:
    root = Path(".test_tmp") / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def cleanup_test_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def make_config(test_dir: Path) -> AppConfig:
    cfg = AppConfig()
    cfg.storage.root_dir = str(test_dir)
    cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
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
async def test_airp_first_run_status_empty_config():
    test_dir = make_test_dir()
    try:
        make_config(test_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/airp-first-run-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["ready"] is False
        assert data["progress"]["done"] == 0
        assert data["next_step"]["key"] == "config"
        steps = {item["key"]: item for item in data["steps"]}
        assert steps["config"]["target"] == "/settings"
        assert steps["benchmark"]["optional"] is True
        assert steps["benchmark"]["done"] is False
        assert steps["benchmark"]["command"] == (
            "python benchmarks/run_airp_benchmark.py --smoke --enforce-thresholds "
            "--report-dir benchmarks/reports/first-run"
        )
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_airp_first_run_status_ready_path():
    test_dir = make_test_dir()
    try:
        cfg = make_config(test_dir)
        cfg.llm.base_url = "https://api.example.com/v1"
        cfg.llm.api_key = "test-key"
        cfg.llm.model = "test-model"
        cfg.memory.extraction_enabled = True
        cfg.memory.judge.enabled = True
        cfg.memory.judge.base_url = "https://api.example.com/v1"
        cfg.memory.judge.api_key = "test-key"
        cfg.memory.judge.model = "judge-model"
        set_config(cfg)

        await init_app_db(cfg.storage.sqlite.app_db)
        await init_cards_db(cfg.storage.sqlite.memory_db)
        await upsert_character(cfg.storage.sqlite.app_db, "char_1", "user_1", display_name="测试角色")
        await upsert_conversation(
            cfg.storage.sqlite.app_db,
            "conv_1",
            "user_1",
            "char_1",
            "test-client",
            str(test_dir / "conversations" / "conv_1"),
        )
        await insert_inbox_item(
            cfg.storage.sqlite.memory_db,
            inbox_id="inbox_1",
            candidate_type="card",
            payload_json='{"content":"请叫我小凛"}',
            user_id="user_1",
            character_id="char_1",
            conversation_id="conv_1",
        )
        await insert_card(
            cfg.storage.sqlite.memory_db,
            card_id="card_1",
            user_id="user_1",
            character_id="char_1",
            conversation_id="conv_1",
            scope="character",
            card_type="preference",
            content="用户喜欢安静一点的叙事节奏",
            status="approved",
        )

        store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
        template = await store.save_table_template(
            StateTableTemplate(
                template_id="tpl_airp_acceptance",
                name="AIRP 验收模板",
                tables=[
                    StateTableSchema(
                        table_id=None,
                        template_id="tpl_airp_acceptance",
                        table_key="scene",
                        name="当前场景",
                        columns=[
                            StateTableColumn(
                                column_id=None,
                                table_id="",
                                column_key="content",
                                name="内容",
                            )
                        ],
                    )
                ],
            )
        )
        table = template.tables[0]
        await store.set_conversation_config(
            {
                "conversation_id": "conv_1",
                "profile_id": "airp_roleplay",
                "table_template_id": template.template_id,
                "memory_write_policy": "candidate",
                "state_update_policy": "auto",
                "injection_policy": "mixed",
                "retrieval_profile_id": "balanced",
            }
        )
        await store.upsert_table_row(
            StateTableRow(
                row_id="state_row_1",
                conversation_id="conv_1",
                template_id=template.template_id or "",
                table_id=table.table_id or "",
                table_key=table.table_key,
                status="active",
            ),
            {"content": "当前场景在旧图书馆"},
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/airp-first-run-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True
        assert data["progress"] == {"done": 6, "total": 6, "percentage": 100}
        assert data["next_step"] is None
        steps = {item["key"]: item for item in data["steps"]}
        for key in ["config", "role", "conversation", "candidate", "approved", "state", "benchmark"]:
            assert steps[key]["done"] is True
        assert steps["benchmark"]["optional"] is True
        assert steps["benchmark"]["command"] == (
            "python benchmarks/run_airp_benchmark.py --smoke --enforce-thresholds "
            "--report-dir benchmarks/reports/first-run"
        )
        assert data["summary"]["role_count"] == 1
        assert data["summary"]["active_conversation_count"] == 1
        assert data["summary"]["pending_memory_count"] == 1
        assert data["summary"]["approved_memory_count"] == 1
        assert data["summary"]["state_row_count"] == 1
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
                payload_json=json.dumps(
                    {
                        "content": f"记忆 {i}",
                        "card_type": "preference",
                        "scope": "global",
                        "importance": 0.8,
                        "confidence": 0.9,
                    }
                ),
                user_id="u",
                character_id="c",
                conversation_id="v",
            )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/admin/inbox/batch",
                json={
                    "action": "approve",
                    "inbox_ids": ["batch_approve_0", "batch_approve_1"],
                },
            )
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
            payload_json=json.dumps(
                {
                    "content": "test",
                    "card_type": "event",
                    "scope": "global",
                    "importance": 0.5,
                    "confidence": 0.6,
                }
            ),
            user_id="u",
            character_id="c",
            conversation_id="v",
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/admin/inbox/batch",
                json={
                    "action": "reject",
                    "inbox_ids": ["batch_reject"],
                    "note": "非长期记忆",
                },
            )
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
            resp = await client.post(
                "/admin/inbox/batch",
                json={
                    "action": "invalid",
                    "inbox_ids": ["some_id"],
                },
            )
        assert resp.status_code == 400
    finally:
        cleanup_test_dir(test_dir)
