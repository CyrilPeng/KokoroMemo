"""Template variable resolution engine.

Supports {{variable}} placeholders in system prompts and injection templates.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

from app.core.time_util import datetime_now, naive_local_now

# 中文星期名称
_WEEKDAYS_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def resolve_variables(
    text: str,
    username: str = "用户",
    character_name: str | None = None,
    model_name: str = "",
    conversation_id: str = "",
    memory_count: int = 0,
    total_memories: int = 0,
    session_turns: int = 0,
    days_since_last: int = 0,
    tz_offset_hours: float | None = None,
) -> str:
    """Replace all {{variable}} placeholders in text."""
    if tz_offset_hours is not None:
        now = datetime.now(timezone(timedelta(hours=tz_offset_hours)))
    else:
        now = datetime_now()

    variables = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "datetime": f"{now.strftime('%Y-%m-%d %H:%M')} ({_WEEKDAYS_CN[now.weekday()]})",
        "weekday": _WEEKDAYS_CN[now.weekday()],
        "username": username,
        "character_name": character_name or "",
        "model_name": model_name,
        "conversation_id": conversation_id,
        "memory_count": str(memory_count),
        "total_memories": str(total_memories),
        "session_turns": str(session_turns),
        "days_since_last": str(days_since_last),
    }

    def replacer(match: re.Match) -> str:
        key = match.group(1)
        return variables.get(key, match.group(0))  # 未知时保留原值

    return _VAR_PATTERN.sub(replacer, text)


def relative_time_label(created_at: str | None) -> str:
    """Convert an ISO timestamp to a human-readable relative time label."""
    if not created_at:
        return ""
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            now = datetime.now(dt.tzinfo)
        else:
            now = naive_local_now()
        delta = now - dt
        seconds = delta.total_seconds()

        if seconds < 60:
            return "刚才"
        if seconds < 3600:
            return f"{int(seconds // 60)}分钟前"
        if seconds < 86400:
            return f"{int(seconds // 3600)}小时前"
        days = int(seconds // 86400)
        if days == 1:
            return "昨天"
        if days <= 7:
            return f"{days}天前"
        if days <= 30:
            weeks = days // 7
            return f"{weeks}周前"
        if days <= 365:
            months = days // 30
            return f"{months}个月前"
        return f"{days // 365}年前"
    except Exception:
        return ""
