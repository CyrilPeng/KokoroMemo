from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import AppConfig
from app.proxy.request_parser import resolve_context
from app.storage.sqlite_app import init_app_db, upsert_conversation


def _make_cfg(root: Path) -> AppConfig:
    cfg = AppConfig()
    cfg.storage.root_dir = str(root)
    cfg.storage.sqlite.app_db = str(root / "app.sqlite")
    cfg.storage.sqlite.memory_db = str(root / "memory.sqlite")
    cfg.conversation.auto_new_session_gap_minutes = 0
    cfg.conversation.detect_message_count_reset = False
    return cfg


def _make_request(headers: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(headers=headers or {})


@pytest.mark.asyncio
async def test_existing_conversation_character_binding_wins_without_explicit_header():
    root = Path(".test_tmp") / uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    try:
        cfg = _make_cfg(root)
        await init_app_db(cfg.storage.sqlite.app_db)
        await upsert_conversation(
            cfg.storage.sqlite.app_db,
            conversation_id="conv_existing_binding",
            user_id="default",
            character_id="canonical-character",
            client_name="test-client",
            conv_path=str(root / "conversations" / "conv_existing_binding"),
        )

        ctx = await resolve_context(
            _make_request(),
            {
                "model": "test-model",
                "messages": [
                    {"role": "assistant", "name": "raw-assistant-id", "content": "hello"},
                    {"role": "user", "content": "hi"},
                ],
                "metadata": {"conversation_id": "conv_existing_binding"},
            },
            str(root),
            cfg,
        )

        assert ctx.conversation_id == "conv_existing_binding"
        assert ctx.character_id == "canonical-character"
    finally:
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
