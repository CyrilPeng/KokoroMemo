from __future__ import annotations

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
