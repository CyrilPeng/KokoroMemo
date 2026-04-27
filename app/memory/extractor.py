"""Rule-based memory extraction from conversation turns."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("kokoromemo.extractor")

# Patterns that suggest user is expressing something worth remembering
_MEMORY_PATTERNS = [
    (r"记住|以后|从现在开始|从今天起", "preference", 0.7),
    (r"我喜欢|我不喜欢|我讨厌|我爱", "preference", 0.75),
    (r"不要再|别再|你不能|你不要|禁止", "boundary", 0.8),
    (r"你应该|你要|你必须|你得", "preference", 0.65),
    (r"叫我|称呼我|我的名字是|我是", "preference", 0.8),
    (r"我们约好|答应我|你保证|约定", "promise", 0.75),
    (r"我.*?岁|我的生日|我住在|我的工作", "preference", 0.6),
    (r"我们之前|上次我们|你还记得", "event", 0.5),
]


@dataclass
class ExtractedMemory:
    scope: str
    memory_type: str
    content: str
    importance: float
    confidence: float
    tags: list[str]


def extract_memories_rule_based(
    user_message: str,
    assistant_message: str,
    character_id: str | None = None,
    min_importance: float = 0.45,
    min_confidence: float = 0.55,
) -> list[ExtractedMemory]:
    """Extract memories using pattern matching rules."""
    results = []

    if not user_message or len(user_message.strip()) < 4:
        return results

    for pattern, mem_type, base_importance in _MEMORY_PATTERNS:
        if re.search(pattern, user_message):
            # Extract a concise memory from user message
            content = user_message.strip()
            if len(content) > 200:
                content = content[:200] + "..."

            # Determine scope
            scope = "character" if character_id else "global"

            importance = base_importance
            confidence = 0.7  # Rule-based extraction has moderate confidence

            if importance < min_importance or confidence < min_confidence:
                continue

            tags = [mem_type]
            results.append(ExtractedMemory(
                scope=scope,
                memory_type=mem_type,
                content=content,
                importance=importance,
                confidence=confidence,
                tags=tags,
            ))
            break  # One memory per user message in rule-based mode

    return results
