from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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
            unauthorized = await client.get("/admin/conversations/conv1/state/tables")
            assert unauthorized.status_code == 401

            authorized = await client.get(
                "/admin/conversations/conv1/state/tables",
                headers={"Authorization": "Bearer secret"},
            )
            assert authorized.status_code == 200
            data = authorized.json()
            assert data["conversation_id"] == "conv1"
            assert data["source"] == "table"
            assert "rows" in data
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_admin_middleware_rejects_remote_without_token():
    test_dir = make_test_dir()
    try:
        cfg = AppConfig()
        cfg.server.host = "0.0.0.0"
        cfg.server.allow_remote_access = False
        cfg.storage.root_dir = str(test_dir)
        cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
        cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
        set_config(cfg)

        transport = ASGITransport(app=app, client=("203.0.113.10", 12345))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/config")

        assert resp.status_code == 403
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_retrieval_profiles_api_lists_builtin_profiles():
    test_dir = make_test_dir()
    try:
        cfg = AppConfig()
        cfg.storage.root_dir = str(test_dir)
        cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
        cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
        set_config(cfg)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/admin/retrieval-profiles")

        assert resp.status_code == 200
        items = resp.json()["items"]
        profile_ids = {item["profile_id"] for item in items}
        assert {"balanced", "high_recall", "state_first", "memory_first"} <= profile_ids
        assert all("vector_top_k" in item and "max_injected_chars" in item for item in items)
    finally:
        cleanup_test_dir(test_dir)


def test_websocket_requires_token_when_configured(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    set_config(AppConfig())

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect("/ws"):
            pass
        assert exc_info.value.code == 1008


def test_websocket_accepts_query_token_when_configured(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    set_config(AppConfig())

    with TestClient(app) as client, client.websocket_connect("/ws?token=secret") as ws:
        assert ws is not None


def test_websocket_accepts_bearer_token_when_configured(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    set_config(AppConfig())

    with TestClient(app) as client, client.websocket_connect("/ws", headers={"Authorization": "Bearer secret"}) as ws:
        assert ws is not None


@pytest.mark.asyncio
async def test_import_conversation_state_bundle_accepts_exported_rows_shape():
    test_dir = make_test_dir()
    try:
        cfg = AppConfig()
        cfg.storage.root_dir = str(test_dir)
        cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
        cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
        set_config(cfg)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            base_resp = await client.get("/admin/conversations/export_src/state/tables")
            assert base_resp.status_code == 200
            template = base_resp.json()["template"]
            table = template["tables"][0]
            first_col = next(c["column_key"] for c in table["columns"] if c["include_in_prompt"])

            resp = await client.post("/admin/conversations/import", json={
                "conversation_id": "export_src",
                "target_conversation_id": "export_dst",
                "template": template,
                "rows": [{
                    "table_key": table["table_key"],
                    "values": {first_col: "测试导入值"},
                    "priority": 70,
                    "confidence": 0.8,
                }],
            })
            assert resp.status_code == 200
            assert resp.json()["imported_rows"] == 1

            verify = await client.get("/admin/conversations/export_dst/state/tables")
            assert verify.status_code == 200
            rows = verify.json()["rows"]
            assert any(row["values"].get(first_col) == "测试导入值" for row in rows)
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_state_preview_returns_injection_summary():
    test_dir = make_test_dir()
    try:
        cfg = AppConfig()
        cfg.storage.root_dir = str(test_dir)
        cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
        cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
        set_config(cfg)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            base_resp = await client.get("/admin/conversations/preview_summary/state/tables")
            assert base_resp.status_code == 200
            template = base_resp.json()["template"]
            table = template["tables"][0]
            first_col = next(column["column_key"] for column in table["columns"] if column["include_in_prompt"])

            row_resp = await client.post(
                f"/admin/conversations/preview_summary/state/tables/{table['table_key']}/rows",
                json={"values": {first_col: "summary value"}, "priority": 80, "confidence": 0.9},
            )
            assert row_resp.status_code == 200

            preview_resp = await client.get("/admin/conversations/preview_summary/state/preview")
            assert preview_resp.status_code == 200
            data = preview_resp.json()
            assert data["summary"]["template_id"] == template["template_id"]
            assert any(
                item["table_key"] == table["table_key"]
                and item["included"]
                and item["selected_row_count"] == 1
                for item in data["summary"]["tables"]
            )
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_conversation_config_mount_preset_updates_write_library():
    test_dir = make_test_dir()
    try:
        cfg = AppConfig()
        cfg.storage.root_dir = str(test_dir)
        cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
        cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
        set_config(cfg)

        from app.storage.sqlite_cards import create_memory_library, create_mount_preset, get_conversation_mounts

        lib_id = await create_memory_library(cfg.storage.sqlite.memory_db, "剧情库", "")
        preset_id = await create_mount_preset(
            cfg.storage.sqlite.memory_db,
            "剧情挂载",
            ["lib_default", lib_id],
            write_library_id=lib_id,
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/admin/conversations/conv_preset/config",
                json={"mount_preset_id": preset_id, "memory_write_policy": "candidate"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["config"]["mounted_library_ids"] == [lib_id, "lib_default"]
        assert data["config"]["write_library_id"] == lib_id
        assert data["config"]["template_name"] == data["config"]["table_template_name"]
        assert data["config"]["state_item_count"] == data["config"]["state_row_count"]

        mounts = await get_conversation_mounts(cfg.storage.sqlite.memory_db, "conv_preset")
        assert [mount["library_id"] for mount in mounts] == [lib_id, "lib_default"]
        assert next(mount["library_id"] for mount in mounts if mount["is_write_target"]) == lib_id
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_apply_character_defaults_expands_mount_preset():
    test_dir = make_test_dir()
    try:
        cfg = AppConfig()
        cfg.storage.root_dir = str(test_dir)
        cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
        cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
        set_config(cfg)

        from app.storage.sqlite_app import init_app_db, set_character_defaults, upsert_character, upsert_conversation
        from app.storage.sqlite_cards import create_memory_library, create_mount_preset, get_conversation_mounts

        character_id = "char_preset"
        await init_app_db(cfg.storage.sqlite.app_db)
        await upsert_character(cfg.storage.sqlite.app_db, character_id, "default")
        await upsert_conversation(
            cfg.storage.sqlite.app_db,
            "conv_char_preset",
            "default",
            character_id,
            "test",
            str(test_dir / "conversations" / "conv_char_preset"),
        )
        lib_id = await create_memory_library(cfg.storage.sqlite.memory_db, "角色库", "")
        preset_id = await create_mount_preset(
            cfg.storage.sqlite.memory_db,
            "角色挂载",
            ["lib_default", lib_id],
            write_library_id=lib_id,
        )
        await set_character_defaults(
            cfg.storage.sqlite.app_db,
            character_id,
            mount_preset_id=preset_id,
            retrieval_profile_id="high_recall",
            library_ids=["lib_default"],
            write_library_id="lib_default",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/admin/characters/{character_id}/apply-defaults", json={"apply_mounts": True})
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1

        mounts = await get_conversation_mounts(cfg.storage.sqlite.memory_db, "conv_char_preset")
        assert [mount["library_id"] for mount in mounts] == [lib_id, "lib_default"]
        assert next(mount["library_id"] for mount in mounts if mount["is_write_target"]) == lib_id

        from app.storage.sqlite_state import SQLiteStateStore

        config = await SQLiteStateStore(cfg.storage.sqlite.memory_db).get_conversation_config("conv_char_preset")
        assert config is not None
        assert config.retrieval_profile_id == "high_recall"
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_character_defaults_save_expands_mount_preset_for_display():
    test_dir = make_test_dir()
    try:
        cfg = AppConfig()
        cfg.storage.root_dir = str(test_dir)
        cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
        cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
        set_config(cfg)

        from app.storage.sqlite_app import init_app_db
        from app.storage.sqlite_cards import create_memory_library, create_mount_preset

        await init_app_db(cfg.storage.sqlite.app_db)
        lib_id = await create_memory_library(cfg.storage.sqlite.memory_db, "展示库", "")
        preset_id = await create_mount_preset(
            cfg.storage.sqlite.memory_db,
            "展示挂载",
            ["lib_default", lib_id],
            write_library_id=lib_id,
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            save_resp = await client.put(
                "/admin/characters/char_display/defaults",
                json={
                    "mount_preset_id": preset_id,
                    "retrieval_profile_id": "memory_first",
                    "library_ids": ["lib_default"],
                    "write_library_id": "lib_default",
                },
            )
            get_resp = await client.get("/admin/characters/char_display/defaults")
        assert save_resp.status_code == 200
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["mount_preset_id"] == preset_id
        assert data["retrieval_profile_id"] == "memory_first"
        assert data["library_ids"] == ["lib_default", lib_id]
        assert data["write_library_id"] == lib_id
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_state_table_template_tab_and_column_editing():
    test_dir = make_test_dir()
    try:
        cfg = AppConfig()
        cfg.storage.root_dir = str(test_dir)
        cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
        cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
        set_config(cfg)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            base_resp = await client.get("/admin/state/table-templates")
            assert base_resp.status_code == 200
            base_id = base_resp.json()["items"][0]["template_id"]

            clone_resp = await client.post(f"/admin/state/table-templates/{base_id}/clone", json={"name": "测试模板"})
            assert clone_resp.status_code == 200
            template_id = clone_resp.json()["template"]["template_id"]

            add_resp = await client.post(
                f"/admin/state/table-templates/{template_id}/tables",
                json={"name": "任务", "table_key": "quests"},
            )
            assert add_resp.status_code == 200
            added_table = next(table for table in add_resp.json()["template"]["tables"] if table["table_key"] == "quests")
            assert [column["name"] for column in added_table["columns"]] == ["任务"]

            rename_resp = await client.patch(
                f"/admin/state/table-templates/{template_id}/tables/quests",
                json={"name": "任务列表", "description": "主线与支线"},
            )
            assert rename_resp.status_code == 200
            renamed_table = next(table for table in rename_resp.json()["template"]["tables"] if table["table_key"] == "quests")
            assert renamed_table["name"] == "任务列表"

            column_resp = await client.patch(
                f"/admin/state/table-templates/{template_id}/tables/quests/columns/quests",
                json={"name": "任务名称", "max_chars": 500},
            )
            assert column_resp.status_code == 200
            edited_table = next(table for table in column_resp.json()["template"]["tables"] if table["table_key"] == "quests")
            assert edited_table["columns"][0]["name"] == "任务名称"
            assert edited_table["columns"][0]["max_chars"] == 500

            delete_resp = await client.delete(f"/admin/state/table-templates/{template_id}/tables/quests")
            assert delete_resp.status_code == 200
            assert all(table["table_key"] != "quests" for table in delete_resp.json()["template"]["tables"])
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
    cfg.memory.judge.api_key = "config-judge-key"
    cfg.memory.state_updater.api_key = "config-state-key"
    cfg.memory.judge.user_rules = ["称呼变化生成 preference"]
    set_config(cfg)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm"]["api_key"] == ""
    assert data["llm"]["api_key_set"] is True
    assert data["embedding"]["api_key"] == ""
    assert data["embedding"]["api_key_set"] is True
    assert data["rerank"]["api_key"] == ""
    assert data["rerank"]["api_key_set"] is True
    assert data["memory"]["judge"]["enabled"] is True
    assert data["memory"]["judge"]["api_key"] == ""
    assert data["memory"]["judge"]["api_key_set"] is True
    assert data["memory"]["judge"]["mode"] == "model_only"
    assert data["memory"]["judge"]["user_rules"] == ["称呼变化生成 preference"]
    assert data["memory"]["state_updater"]["api_key"] == ""
    assert data["memory"]["state_updater"]["api_key_set"] is True


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
            resp = await client.get("/admin/conversations/conv_test/config")
            assert resp.status_code == 200
            data = resp.json()
            assert data["conversation_id"] == "conv_test"
            assert "lib_default" in data["mounted_library_ids"]
            assert data["write_library_id"] == "lib_default"
            assert data["table_template_id"] is not None
            assert data["state_row_count"] == 0
            assert data["is_new_session"] is True

            resp = await client.post("/admin/conversations/conv_test/config", json={
                "library_ids": ["lib_default"],
                "write_library_id": "lib_default",
                "table_template_id": "tpl_ttrpg_story_tables",
            })
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

            resp = await client.get("/admin/conversations/conv_test/config")
            data = resp.json()
            assert data["table_template_id"] == "tpl_ttrpg_story_tables"
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_state_table_row_crud_api():
    test_dir = make_test_dir()
    try:
        cfg = AppConfig()
        cfg.storage.root_dir = str(test_dir)
        cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
        cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
        set_config(cfg)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/admin/conversations/conv_rows/config")

            resp = await client.get("/admin/conversations/conv_rows/state/tables")
            assert resp.status_code == 200
            template = resp.json()["template"]
            table_key = template["tables"][0]["table_key"]
            first_col = next(c["column_key"] for c in template["tables"][0]["columns"] if c["include_in_prompt"])

            resp = await client.post(
                f"/admin/conversations/conv_rows/state/tables/{table_key}/rows",
                json={"values": {first_col: "测试场景"}},
            )
            assert resp.status_code == 200
            row_id = resp.json()["row_id"]

            resp = await client.get("/admin/conversations/conv_rows/state/tables")
            rows = resp.json()["rows"]
            assert any(r["row_id"] == row_id for r in rows)

            resp = await client.delete(f"/admin/state/table-rows/{row_id}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
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
