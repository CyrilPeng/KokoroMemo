"""Process-local registry for non-fatal degradation events."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from app.core.time_util import datetime_now

_MAX_CHANNELS = 200
_MAX_ERROR_CHARS = 500
_MAX_CONTEXT_VALUE_CHARS = 200
_SENSITIVE_CONTEXT_MARKERS = ("key", "token", "authorization", "secret", "password", "cookie")


@dataclass
class DegradationRecord:
    channel: str
    count: int = 0
    first_at: str = ""
    last_at: str = ""
    last_error: str = ""
    last_context: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "count": self.count,
            "first_at": self.first_at,
            "last_at": self.last_at,
            "last_error": self.last_error,
            "last_context": dict(self.last_context),
        }


_records: dict[str, DegradationRecord] = {}
_lock = Lock()


def _sanitize_context(context: dict[str, Any]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in context.items():
        key_text = str(key)
        if any(marker in key_text.lower() for marker in _SENSITIVE_CONTEXT_MARKERS):
            cleaned[key_text] = "[redacted]"
            continue
        text = str(value)
        cleaned[key_text] = text[:_MAX_CONTEXT_VALUE_CHARS]
    return cleaned


def record_degradation(channel: str, error: BaseException | str, **context: Any) -> None:
    """Record a handled failure without changing control flow."""
    now = datetime_now().isoformat(timespec="seconds")
    clean_channel = str(channel)[:120]
    with _lock:
        record = _records.get(clean_channel)
        if record is None:
            if len(_records) >= _MAX_CHANNELS:
                return
            record = DegradationRecord(channel=clean_channel, first_at=now)
            _records[clean_channel] = record
        record.count += 1
        record.last_at = now
        record.last_error = str(error)[:_MAX_ERROR_CHARS]
        record.last_context = _sanitize_context(context)


def get_degradation_snapshot() -> dict[str, Any]:
    with _lock:
        items = sorted(_records.values(), key=lambda record: record.last_at, reverse=True)
        channels = [record.to_dict() for record in items]
    return {
        "status": "ok",
        "total_events": sum(record["count"] for record in channels),
        "channel_count": len(channels),
        "channels": channels,
    }


def reset_degradation_records() -> None:
    with _lock:
        _records.clear()
