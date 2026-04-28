"""Timezone-aware datetime helpers.

All timestamp generation in the project should use these helpers
instead of bare datetime.now() to ensure consistent local time.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

_configured_tz: timezone | None = None


def set_configured_timezone(tz_name: str | None) -> None:
    """Set the application-wide timezone from config.

    Args:
        tz_name: IANA timezone name (e.g. 'Asia/Shanghai'), or None/empty for system local.
    """
    global _configured_tz
    if tz_name:
        try:
            _configured_tz = ZoneInfo(tz_name)
        except (KeyError, Exception):
            _configured_tz = None
    else:
        _configured_tz = None


def get_configured_timezone() -> timezone | None:
    """Return the configured timezone, or None for system local."""
    return _configured_tz


def datetime_now() -> datetime:
    """Return the current local datetime, always timezone-aware.

    Uses the configured timezone if set, otherwise system local time.
    This is the recommended replacement for bare datetime.now().
    """
    if _configured_tz is not None:
        return datetime.now(_configured_tz)
    return datetime.now().astimezone()


def naive_local_now() -> datetime:
    """Return the current local datetime as a naive (no tzinfo) object.

    Use this when you need to compare with naive timestamps stored in SQLite
    (which uses datetime('now', 'localtime')). Prefer datetime_now() when possible.
    """
    return datetime_now().replace(tzinfo=None)
