from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
import yaml
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


@pytest.mark.asyncio
async def test_admin_state_api_requires_token_when_configured():
    test_dir = make_test_dir()
    try:
        cfg = AppConfig()
        cfg.server.admin_token = "secret"
        cfg.storage.root_dir = str(test_dir)
        cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
        cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
        set_config(cfg)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            unauthorized = await client.get("/admin/conversations/conv1/state")
            assert unauthorized.status_code == 401

            created = await client.post(
                "/admin/conversations/conv1/state",
                headers={"Authorization": "Bearer secret"},
                json={"category": "scene", "item_key": "current_scene", "item_value": "正在车站", "priority": 80},
            )
            assert created.status_code == 200
            assert created.json()["status"] == "ok"

            listed = await client.get("/admin/conversations/conv1/state", headers={"Authorization": "Bearer secret"})
            assert listed.status_code == 200
            assert listed.json()["items"][0]["item_key"] == "current_scene"
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_cors_allows_vite_dev_origin():
    cfg = AppConfig()
    cfg.server.admin_token = ""
    set_config(cfg)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.asyncio
async def test_admin_config_returns_direct_config_keys(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "env-llm-key")
    monkeypatch.setenv("MODELARK_API_KEY", "env-modelark-key")
    cfg = AppConfig()
    cfg.llm.api_key = "config-llm-key"
    cfg.embedding.api_key = "config-embedding-key"
    cfg.rerank.api_key = "config-rerank-key"
    cfg.memory.judge.user_rules = ["称呼变化生成 preference"]
    set_config(cfg)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm"]["api_key"] == "config-llm-key"
    assert data["embedding"]["api_key"] == "config-embedding-key"
    assert data["rerank"]["api_key"] == "config-rerank-key"
    assert data["memory"]["judge"]["enabled"] is True
    assert data["memory"]["judge"]["mode"] == "model_only"
    assert data["memory"]["judge"]["user_rules"] == ["称呼变化生成 preference"]


@pytest.mark.asyncio
async def test_admin_config_save_keeps_existing_api_keys_when_form_empty(monkeypatch):
    test_dir = make_test_dir()
    try:
        config_path = test_dir / "config.yaml"
        config_path.write_text(
            yaml.dump({
                "server": {"port": 14514},
                "storage": {"root_dir": str(test_dir / "data")},
                "llm": {"api_key": "saved-llm", "model": "old-model"},
                "embedding": {"api_key": "saved-embedding"},
                "rerank": {"api_key": "saved-rerank"},
                "memory": {
                    "judge": {"api_key": "saved-judge"},
                    "state_updater": {"api_key": "saved-state"},
                },
            }, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        monkeypatch.setenv("KOKOROMEMO_CONFIG_PATH", str(config_path))
        cfg = AppConfig()
        cfg.config_path = str(config_path)
        cfg.storage.root_dir = str(test_dir / "data")
        cfg.llm.api_key = "saved-llm"
        cfg.embedding.api_key = "saved-embedding"
        cfg.rerank.api_key = "saved-rerank"
        cfg.memory.judge.api_key = "saved-judge"
        cfg.memory.state_updater.api_key = "saved-state"
        set_config(cfg)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/admin/config", json={
                "llm": {"api_key": "", "model": "new-model"},
                "embedding": {"api_key": ""},
                "rerank": {"api_key": ""},
                "memory": {
                    "judge": {"api_key": ""},
                    "state_updater": {"api_key": ""},
                },
            })
        assert resp.status_code == 200
        saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert saved["llm"]["api_key"] == "saved-llm"
        assert saved["llm"]["model"] == "new-model"
        assert saved["embedding"]["api_key"] == "saved-embedding"
        assert saved["rerank"]["api_key"] == "saved-rerank"
        assert saved["memory"]["judge"]["api_key"] == "saved-judge"
        assert saved["memory"]["state_updater"]["api_key"] == "saved-state"
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_conversation_config_summary_api():
    test_dir = make_test_dir()
    try:
        cfg = AppConfig()
        cfg.storage.root_dir = str(test_dir)
        cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
        cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
        set_config(cfg)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # GET config for a new conversation (should auto-create default mounts)
            resp = await client.get("/admin/conversations/conv_test/config")
            assert resp.status_code == 200
            data = resp.json()
            assert data["conversation_id"] == "conv_test"
            assert "lib_default" in data["mounted_library_ids"]
            assert data["write_library_id"] == "lib_default"
            assert data["template_id"] is not None
            assert data["state_item_count"] == 0
            assert data["is_new_session"] is True

            # POST config to set mounts and template
            resp = await client.post("/admin/conversations/conv_test/config", json={
                "library_ids": ["lib_default"],
                "write_library_id": "lib_default",
                "template_id": "tpl_trpg_story",
            })
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

            # Verify template changed
            resp = await client.get("/admin/conversations/conv_test/config")
            data = resp.json()
            assert data["template_id"] == "tpl_trpg_story"
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_state_clear_api():
    test_dir = make_test_dir()
    try:
        cfg = AppConfig()
        cfg.storage.root_dir = str(test_dir)
        cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
        cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
        set_config(cfg)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create some state items
            await client.post("/admin/conversations/conv_clear/state", json={
                "category": "scene", "item_key": "scene1", "item_value": "场景一",
            })
            await client.post("/admin/conversations/conv_clear/state", json={
                "category": "scene", "item_key": "scene2", "item_value": "场景二",
            })

            # Verify items exist
            resp = await client.get("/admin/conversations/conv_clear/state?status=active")
            assert resp.json()["total"] == 2

            # Clear state
            resp = await client.post("/admin/conversations/conv_clear/state/clear")
            assert resp.status_code == 200
            assert resp.json()["cleared"] == 2

            # Verify active items are gone (soft-deleted)
            resp = await client.get("/admin/conversations/conv_clear/state?status=active")
            assert resp.json()["total"] == 0
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_mount_presets_crud():
    test_dir = make_test_dir()
    try:
        cfg = AppConfig()
        cfg.storage.root_dir = str(test_dir)
        cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
        cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
        set_config(cfg)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create preset
            resp = await client.post("/admin/memory-mount-presets", json={
                "name": "TRPG 预设",
                "description": "用于跑团会话",
                "library_ids": ["lib_default"],
                "write_library_id": "lib_default",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            preset_id = data["preset_id"]

            # List presets
            resp = await client.get("/admin/memory-mount-presets")
            items = resp.json()["items"]
            assert len(items) == 1
            assert items[0]["name"] == "TRPG 预设"

            # Update preset
            resp = await client.put(f"/admin/memory-mount-presets/{preset_id}", json={
                "name": "TRPG 预设 v2",
            })
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

            # Verify update
            resp = await client.get("/admin/memory-mount-presets")
            assert resp.json()["items"][0]["name"] == "TRPG 预设 v2"

            # Delete preset
            resp = await client.delete(f"/admin/memory-mount-presets/{preset_id}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

            # Verify deletion
            resp = await client.get("/admin/memory-mount-presets")
            assert len(resp.json()["items"]) == 0
    finally:
        cleanup_test_dir(test_dir)
