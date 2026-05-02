from __future__ import annotations

import json
import shutil
import sqlite3
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
    set_config(cfg)
    return cfg


async def seed_inbox(memory_db: str, inbox_id: str) -> None:
    await init_cards_db(memory_db)
    payload = {
        "user_id": "u1",
        "character_id": "c1",
        "conversation_id": "conv1",
        "scope": "character",
        "card_type": "preference",
        "content": "用户喜欢安静的叙事。",
        "importance": 0.8,
        "confidence": 0.9,
    }
    await insert_inbox_item(
        memory_db,
        inbox_id=inbox_id,
        candidate_type="card",
        payload_json=json.dumps(payload, ensure_ascii=False),
        user_id="u1",
        character_id="c1",
        conversation_id="conv1",
    )


@pytest.mark.asyncio
async def test_reject_inbox_accepts_json_object_note():
    test_dir = make_test_dir()
    try:
        cfg = make_config(test_dir)
        await seed_inbox(cfg.storage.sqlite.memory_db, "inbox_reject")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/admin/inbox/inbox_reject/reject", json={"note": "不是长期记忆"})

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        with sqlite3.connect(cfg.storage.sqlite.memory_db) as conn:
            row = conn.execute(
                "SELECT status, review_note FROM memory_inbox WHERE inbox_id = ?",
                ("inbox_reject",),
            ).fetchone()
        assert row == ("rejected", "不是长期记忆")
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_approving_same_inbox_twice_is_idempotent():
    test_dir = make_test_dir()
    try:
        cfg = make_config(test_dir)
        await seed_inbox(cfg.storage.sqlite.memory_db, "inbox_approve")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post("/admin/inbox/inbox_approve/approve")
            second = await client.post("/admin/inbox/inbox_approve/approve")

        assert first.status_code == 200
        assert first.json()["status"] == "ok"
        assert second.status_code == 200
        assert second.json()["status"] == "error"
        assert "already" in second.json()["message"]
        with sqlite3.connect(cfg.storage.sqlite.memory_db) as conn:
            card_count = conn.execute("SELECT COUNT(*) FROM memory_cards").fetchone()[0]
            inbox_status = conn.execute(
                "SELECT status FROM memory_inbox WHERE inbox_id = ?",
                ("inbox_approve",),
            ).fetchone()[0]
        assert card_count == 1
        assert inbox_status == "approved"
    finally:
        cleanup_test_dir(test_dir)
