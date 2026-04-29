"""Simple in-process event bus for real-time notifications."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger("kokoromemo.events")

_listeners: list[Callable[[str, dict], Coroutine]] = []


def subscribe(listener: Callable[[str, dict], Coroutine]) -> None:
    """Register an async listener for all events."""
    _listeners.append(listener)


def unsubscribe(listener: Callable[[str, dict], Coroutine]) -> None:
    """Remove a listener."""
    try:
        _listeners.remove(listener)
    except ValueError:
        pass


async def emit(event_type: str, payload: dict[str, Any] | None = None) -> None:
    """Broadcast an event to all listeners."""
    data = payload or {}
    for listener in _listeners:
        try:
            asyncio.create_task(listener(event_type, data))
        except Exception as e:
            logger.debug("Event listener error: %s", e)
