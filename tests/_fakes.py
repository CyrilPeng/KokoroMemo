"""Shared fake objects for testing.

Provides FakeChatProvider and FakeLanceDBStore used across
multiple test files, replacing the duplicated local copies.
"""

from __future__ import annotations

from typing import Any


class FakeChatProvider:
    """Fake LLM provider for testing chat completions (non-streaming + streaming)."""

    captured_bodies: list[dict] = []

    async def chat(self, body: dict, timeout: int) -> dict:
        self.captured_bodies.append(body)
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": body.get("model", "test-model"),
            "choices": [{"message": {"role": "assistant", "content": "收到"}, "finish_reason": "stop"}],
        }

    async def stream_chat(self, body: dict, timeout: int):
        self.captured_bodies.append(body)
        yield 'data: {"choices":[{"delta":{"content":"收"}}]}'
        yield 'data: {"choices":[{"delta":{"content":"到"}}]}'
        yield "data: [DONE]"


class FakeLanceDBStore:
    """Fake LanceDB store for testing vector retrieval."""

    def __init__(self, rows: list[dict] | None = None, on_upsert: Any = None):
        self.rows = rows or []
        self.on_upsert = on_upsert

    def search(
        self, query_vector: Any, where: str | None = None, top_k: int = 30, select_columns: list | None = None
    ) -> list[dict]:
        return self.rows[:top_k]

    async def upsert(self, records: list[dict]) -> None:
        if self.on_upsert:
            self.on_upsert(records)
