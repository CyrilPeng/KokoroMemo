import asyncio
from types import SimpleNamespace

import pytest

from app.core.conversation_locks import conversation_lock, get_conversation_lock
from app.core.services import ServiceRegistry
from app.pipeline import chat, postprocess


@pytest.mark.asyncio
async def test_scheduled_post_process_runs_under_conversation_lock(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()
    locked_states = []

    async def fake_update(*args, **kwargs):
        started.set()
        lock = await get_conversation_lock("conv_lock_test")
        locked_states.append(lock.locked())
        await release.wait()
        completed.set()

    monkeypatch.setattr(postprocess, "_update_state_and_extract_memories", fake_update)
    ctx = SimpleNamespace(conversation_id="conv_lock_test")

    await chat._schedule_post_process_turn(
        ctx,
        SimpleNamespace(),
        ServiceRegistry(),
        [],
        "assistant",
        "turn_1",
        1,
        name="test_post_process_lock",
    )
    await started.wait()

    release.set()
    await completed.wait()
    assert locked_states == [True]


@pytest.mark.asyncio
async def test_scheduling_post_process_does_not_wait_for_lock(monkeypatch):
    release = asyncio.Event()
    completed = asyncio.Event()

    async def fake_update(*args, **kwargs):
        await release.wait()
        completed.set()

    monkeypatch.setattr(postprocess, "_update_state_and_extract_memories", fake_update)
    ctx = SimpleNamespace(conversation_id="conv_nonblocking_schedule")

    async with conversation_lock(ctx.conversation_id):
        await asyncio.wait_for(
            chat._schedule_post_process_turn(
                ctx,
                SimpleNamespace(),
                ServiceRegistry(),
                [],
                "assistant",
                "turn_1",
                1,
                name="test_nonblocking_schedule",
            ),
            timeout=0.2,
        )

    release.set()
    await asyncio.wait_for(completed.wait(), timeout=1)


@pytest.mark.asyncio
async def test_truncated_response_skips_state_and_memory_processing(monkeypatch):
    state_calls = []
    memory_calls = []

    async def fake_state(*args, **kwargs):
        state_calls.append((args, kwargs))

    async def fake_extract(*args, **kwargs):
        memory_calls.append((args, kwargs))

    monkeypatch.setattr(postprocess, "fill_conversation_state_tables", fake_state)
    monkeypatch.setattr("app.memory.card_extractor.extract_and_route", fake_extract)

    ctx = SimpleNamespace(conversation_id="conv_truncated", user_id="u1", character_id=None)
    await postprocess._update_state_and_extract_memories(
        ctx,
        SimpleNamespace(),
        ServiceRegistry(),
        [{"role": "user", "content": "你好"}],
        "回答被截断",
        "turn_1",
        1,
        finish_reason="length",
    )

    assert state_calls == []
    assert memory_calls == []


@pytest.mark.asyncio
async def test_non_stream_proxy_propagates_length_finish_reason(monkeypatch):
    class FakeProvider:
        async def chat(self, body, timeout):
            return {
                "choices": [{"message": {"role": "assistant", "content": "被截断的回答"}, "finish_reason": "length"}]
            }

    captured = {}

    async def fake_persist(*args, finish_reason=None, **kwargs):
        captured["persist"] = finish_reason
        return "turn_1", 1

    async def fake_schedule(*args, finish_reason=None, **kwargs):
        captured["schedule"] = finish_reason

    monkeypatch.setattr(chat, "_persist_response_turn", fake_persist)
    monkeypatch.setattr(chat, "_schedule_post_process_turn", fake_schedule)

    response = await chat._non_stream_proxy(
        FakeProvider(),
        {},
        1,
        SimpleNamespace(chat_db_path="chat.sqlite", request_id="req_1", conversation_id="conv_1"),
        SimpleNamespace(),
        [{"role": "user", "content": "你好"}],
        ServiceRegistry(),
    )

    assert response.status_code == 200
    assert captured == {"persist": "length", "schedule": "length"}


@pytest.mark.asyncio
async def test_stream_proxy_propagates_length_finish_reason(monkeypatch):
    class FakeStreamProvider:
        async def stream_chat(self, body, timeout):
            yield 'data: {"choices":[{"delta":{"content":"被截断的回答"}}]}'
            yield 'data: {"choices":[{"delta":{},"finish_reason":"length"}]}'
            yield "data: [DONE]"

    captured = {}

    async def fake_persist(*args, finish_reason=None, **kwargs):
        captured["persist"] = finish_reason
        return "turn_1", 1

    async def fake_schedule(*args, finish_reason=None, **kwargs):
        captured["schedule"] = finish_reason

    monkeypatch.setattr(chat, "_persist_response_turn", fake_persist)
    monkeypatch.setattr(chat, "_schedule_post_process_turn", fake_schedule)

    chunks = [
        chunk
        async for chunk in chat._stream_proxy(
            FakeStreamProvider(),
            {},
            1,
            SimpleNamespace(chat_db_path="chat.sqlite", request_id="req_1", conversation_id="conv_1"),
            SimpleNamespace(),
            [{"role": "user", "content": "你好"}],
            ServiceRegistry(),
        )
    ]

    assert chunks
    assert captured == {"persist": "length", "schedule": "length"}
