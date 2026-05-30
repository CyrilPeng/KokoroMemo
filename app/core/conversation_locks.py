"""Conversation-scoped async locks for ordered background processing."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

_locks: dict[str, asyncio.Lock] = {}
_registry_lock: asyncio.Lock | None = None


def _get_registry_lock() -> asyncio.Lock:
    global _registry_lock
    if _registry_lock is None:
        _registry_lock = asyncio.Lock()
    return _registry_lock


async def get_conversation_lock(conversation_id: str) -> asyncio.Lock:
    async with _get_registry_lock():
        lock = _locks.get(conversation_id)
        if lock is None:
            lock = asyncio.Lock()
            _locks[conversation_id] = lock
        return lock


@asynccontextmanager
async def conversation_lock(conversation_id: str) -> AsyncIterator[None]:
    lock = await get_conversation_lock(conversation_id)
    async with lock:
        yield


async def wait_for_conversation_idle(conversation_id: str) -> None:
    async with conversation_lock(conversation_id):
        return
