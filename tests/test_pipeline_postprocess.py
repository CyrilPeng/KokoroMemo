import asyncio
from types import SimpleNamespace

import pytest

from app.core.conversation_locks import conversation_lock, get_conversation_lock
from app.core.services import ServiceRegistry
from app.pipeline import chat


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

    monkeypatch.setattr(chat, "_update_state_and_extract_memories", fake_update)
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

    monkeypatch.setattr(chat, "_update_state_and_extract_memories", fake_update)
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
