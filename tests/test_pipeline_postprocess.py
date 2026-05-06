import asyncio
from types import SimpleNamespace

import pytest

from app.core.conversation_locks import wait_for_conversation_idle
from app.pipeline import chat


@pytest.mark.asyncio
async def test_scheduled_post_process_holds_conversation_lock(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()

    async def fake_update(*args, **kwargs):
        started.set()
        await release.wait()
        completed.set()

    monkeypatch.setattr(chat, "_update_state_and_extract_memories", fake_update)
    ctx = SimpleNamespace(conversation_id="conv_lock_test")

    await chat._schedule_post_process_turn(
        ctx,
        SimpleNamespace(),
        [],
        "assistant",
        "turn_1",
        1,
        name="test_post_process_lock",
    )
    await started.wait()

    waiter = asyncio.create_task(wait_for_conversation_idle(ctx.conversation_id))
    await asyncio.sleep(0.05)
    assert not waiter.done()

    release.set()
    await completed.wait()
    await asyncio.wait_for(waiter, timeout=1)
