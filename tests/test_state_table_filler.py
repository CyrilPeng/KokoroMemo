from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from app.memory.state_filler import StateFillerConfigView
from app.memory.state_table_filler import fill_conversation_state_tables
from app.storage.sqlite_state import SQLiteStateStore


class FakeProvider:
    def __init__(self):
        self.calls = []

    async def chat(self, body: dict, timeout: int) -> dict:
        self.calls.append((body, timeout))
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "operations": [
                                    {
                                        "op": "upsert_row",
                                        "table_key": "current_interaction",
                                        "values": {
                                            "topic": "讲一个猫娘段子",
                                            "mood": "轻松幽默",
                                            "next_step": "继续猫娘风格互动",
                                        },
                                        "confidence": 0.9,
                                        "reason": "本轮对话更新当前互动状态",
                                    },
                                    {
                                        "op": "upsert_row",
                                        "table_key": "roleplay_rules",
                                        "values": {
                                            "rule": "角色以猫娘方式说话，每句话末尾加上'喵~'",
                                            "scope": "口癖",
                                        },
                                        "confidence": 0.9,
                                        "reason": "用户要求持续使用固定口癖",
                                    },
                                ]
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }


def make_test_dir() -> Path:
    root = Path(".test_tmp") / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def cleanup_test_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


@pytest.mark.asyncio
async def test_state_table_filler_writes_rows_with_project_provider_api(monkeypatch):
    test_dir = make_test_dir()
    try:
        db_path = str(test_dir / "memory.sqlite")
        conversation_id = "conv_table_filler"
        store = SQLiteStateStore(db_path)
        await store.ensure_conversation_config(conversation_id)

        provider = FakeProvider()
        monkeypatch.setattr("app.memory.state_table_filler.create_llm_provider", lambda **kwargs: provider)

        result = await fill_conversation_state_tables(
            db_path=db_path,
            conversation_id=conversation_id,
            user_message="现在你是一只猫娘，每句话末尾都要加上喵~",
            assistant_message="好的喵~ 我会讲一个猫娘段子喵~",
            config=StateFillerConfigView(
                provider="openai_compatible",
                base_url="http://fake",
                api_key="test-key",
                model="fake-model",
                timeout_seconds=17,
                min_confidence=0.5,
            ),
            lang="zh",
        )

        assert result.applied == 2
        assert provider.calls
        body, timeout = provider.calls[0]
        assert timeout == 17
        assert body["model"] == "fake-model"
        assert body["messages"][0]["role"] == "system"

        template = await store.get_conversation_table_template(conversation_id)
        rows = await store.list_table_rows(conversation_id, template.template_id)
        values_by_table = {row.table_key: {key: cell.value for key, cell in row.cells.items()} for row in rows}
        assert values_by_table["current_interaction"]["topic"] == "讲一个猫娘段子"
        assert values_by_table["current_interaction"]["mood"] == "轻松幽默"
        assert values_by_table["roleplay_rules"]["rule"] == "角色以猫娘方式说话，每句话末尾加上'喵~'"
    finally:
        cleanup_test_dir(test_dir)
