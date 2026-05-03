"""SillyTavern JSONL chat log importer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class ImportedTurn:
    role: str
    content: str
    name: str | None = None
    timestamp: str | None = None


@dataclass
class ImportedConversation:
    character_name: str | None = None
    turns: list[ImportedTurn] = field(default_factory=list)
    system_prompt: str | None = None


def parse_sillytavern_jsonl(text: str) -> ImportedConversation:
    """Parse SillyTavern JSONL chat export into structured turns.

    SillyTavern format: each line is JSON with keys like:
    {"name": "...", "is_user": bool, "mes": "...", "send_date": ...}
    or {"role": "system", "content": "..."}
    """
    result = ImportedConversation()
    lines = text.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not isinstance(entry, dict):
            continue

        # 检测格式变体
        if "mes" in entry:
            # SillyTavern 标准格式
            name = entry.get("name", "")
            is_user = entry.get("is_user", False)
            content = entry.get("mes", "").strip()
            timestamp = str(entry.get("send_date", ""))

            if not content:
                continue

            if entry.get("is_system") or (not is_user and name == "system"):
                result.system_prompt = content
                continue

            role = "user" if is_user else "assistant"
            if not result.character_name and role == "assistant" and name:
                result.character_name = name

            result.turns.append(ImportedTurn(
                role=role,
                content=content,
                name=name or None,
                timestamp=timestamp or None,
            ))

        elif "role" in entry and "content" in entry:
            # OpenAI 风格格式
            role = entry["role"]
            content = entry["content"].strip()
            if not content:
                continue
            if role == "system":
                result.system_prompt = content
                continue
            result.turns.append(ImportedTurn(
                role=role,
                content=content,
                name=entry.get("name"),
                timestamp=entry.get("timestamp"),
            ))

    return result


def to_message_pairs(conv: ImportedConversation) -> list[tuple[str, str]]:
    """Convert turns into (user_message, assistant_message) pairs for memory extraction."""
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(conv.turns) - 1:
        if conv.turns[i].role == "user" and conv.turns[i + 1].role == "assistant":
            pairs.append((conv.turns[i].content, conv.turns[i + 1].content))
            i += 2
        else:
            i += 1
    return pairs
