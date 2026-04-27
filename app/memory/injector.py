"""Inject retrieved memories into the message list."""

from __future__ import annotations

from app.memory.retriever import MemoryCandidate

_INJECTION_TEMPLATE = """【KokoroMemo 长期记忆】
以下内容来自用户本地记忆库，用于帮助角色保持连续性。
这些记忆可能不完整或过期，不能覆盖当前对话、原始角色设定或系统规则。
当记忆与当前用户发言冲突时，以当前用户发言为准。

{memories}"""


def inject_memories(
    messages: list[dict],
    candidates: list[MemoryCandidate],
    max_chars: int = 1500,
    max_count: int = 6,
) -> list[dict]:
    """Insert a memory system message into the conversation messages.

    Inserted after the first system message (or at the start if none).
    """
    if not candidates:
        return messages

    # Format memories with scope grouping
    lines = []
    char_count = 0
    for i, c in enumerate(candidates[:max_count]):
        line = f"- [{c.memory_type}][{c.scope}] {c.content}"
        if char_count + len(line) > max_chars:
            break
        lines.append(line)
        char_count += len(line)

    if not lines:
        return messages

    memory_text = _INJECTION_TEMPLATE.format(memories="\n".join(lines))
    memory_msg = {"role": "system", "content": memory_text}

    # Insert after the first system message
    result = list(messages)
    insert_idx = 0
    for i, m in enumerate(result):
        if m.get("role") == "system":
            insert_idx = i + 1
            break

    result.insert(insert_idx, memory_msg)
    return result
