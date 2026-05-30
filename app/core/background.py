"""Supervised background task runner with bounded concurrency and graceful shutdown."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger("kokoromemo.background")


class BackgroundRunner:
    """
    Holds strong references to spawned tasks, caps concurrency, and drains on shutdown.

    Replaces ad-hoc `asyncio.get_event_loop().create_task(...)` patterns to avoid
    silently lost exceptions and unbounded task accumulation under load.
    """

    def __init__(self, max_concurrency: int = 8) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closed = False

    def spawn(self, coro: Coroutine[Any, Any, Any], *, name: str | None = None) -> asyncio.Task[Any] | None:
        """Spawn a supervised background task. Returns None if runner is closed."""
        if self._closed:
            coro.close()
            logger.warning("BackgroundRunner is closed; task %s rejected", name or "<unnamed>")
            return None

        async def _runner() -> None:
            async with self._semaphore:
                try:
                    await coro
                except Exception:
                    logger.exception("Background task %s failed", name or "<unnamed>")

        task = asyncio.create_task(_runner(), name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def drain(self, timeout: float = 30.0) -> None:
        """Wait for in-flight tasks to finish, with a timeout. Idempotent."""
        self._closed = True
        if not self._tasks:
            return
        pending = list(self._tasks)
        logger.info("Draining %d background task(s) with timeout=%.1fs", len(pending), timeout)
        done, still_pending = await asyncio.wait(pending, timeout=timeout)
        if still_pending:
            logger.warning("%d background task(s) did not finish within timeout; cancelling", len(still_pending))
            for task in still_pending:
                task.cancel()
            await asyncio.gather(*still_pending, return_exceptions=True)

    @property
    def in_flight(self) -> int:
        return len(self._tasks)


_runner: BackgroundRunner | None = None


def set_background_runner(runner: BackgroundRunner | None) -> None:
    global _runner
    _runner = runner


def get_background_runner() -> BackgroundRunner | None:
    return _runner


def spawn_background(coro: Coroutine[Any, Any, Any], *, name: str | None = None) -> asyncio.Task[Any] | None:
    """Spawn a task on the active runner, falling back to a bare task if none is registered."""
    runner = _runner
    if runner is None:
        logger.debug("No BackgroundRunner registered; falling back to asyncio.create_task for %s", name or "<unnamed>")

        async def _wrap() -> None:
            try:
                await coro
            except Exception:
                logger.exception("Unmanaged background task %s failed", name or "<unnamed>")

        return asyncio.create_task(_wrap(), name=name)
    return runner.spawn(coro, name=name)
