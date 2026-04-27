"""Layered memory card injection with template variables and relative time."""

from __future__ import annotations

from app.core.variables import resolve_variables, relative_time_label
from app.memory.card_retriever import MemoryCandidate

_INJECTION_TEMPLATE = """【KokoroMemo 长期记忆】
当前时间: {{datetime}}
以下内容来自用户本地记忆库，用于帮助角色保持连续性。
优先级：原始系统设定 > 当前用户发言 > 当前对话上下文 > 长期记忆。
当记忆与当前对话冲突时，以当前对话为准。
{sections}"""

# card_type → display category mapping
_TYPE_TO_SECTION = {
    "boundary": "稳定边界",
    "preference": "用户偏好",
    "relationship": "关系状态",
    "event": "当前剧情",
    "world_state": "当前剧情",
    "character_state": "当前剧情",
    "promise": "未完成承诺",
    "correction": "用户偏好",
    "summary": "当前相关记忆",
}

# Section display order (higher priority first)
_SECTION_ORDER = [
    "稳定边界",
    "用户偏好",
    "关系状态",
    "当前剧情",
    "未完成承诺",
    "当前相关记忆",
]


def inject_cards(
    messages: list[dict],
    candidates: list[MemoryCandidate],
    max_chars: int = 1500,
    max_count: int = 8,
    username: str = "用户",
    character_name: str | None = None,
    model_name: str = "",
    conversation_id: str = "",
    total_memories: int = 0,
    session_turns: int = 0,
    days_since_last: int = 0,
) -> list[dict]:
    """Inject memory cards as a layered system message with variables resolved.

    Cards are grouped by type into sections, displayed in priority order.
    Each card is prefixed with relative time when available.
    """
    if not candidates:
        return messages

    # Group candidates by section
    sections: dict[str, list[MemoryCandidate]] = {s: [] for s in _SECTION_ORDER}

    for c in candidates[:max_count]:
        section = _TYPE_TO_SECTION.get(c.card_type, "当前相关记忆")
        if section in sections:
            sections[section].append(c)
        else:
            sections["当前相关记忆"].append(c)

    # Build section text with relative time labels
    section_texts: list[str] = []
    char_count = 0

    for section_name in _SECTION_ORDER:
        items = sections.get(section_name, [])
        if not items:
            continue

        lines = [f"\n[{section_name}]"]
        for c in items:
            # Add relative time prefix if card has created_at
            time_label = ""
            if hasattr(c, "created_at") and c.created_at:
                rel = relative_time_label(c.created_at)
                if rel:
                    time_label = f"({rel}) "
            line = f"- {time_label}{c.content}"
            if char_count + len(line) > max_chars:
                break
            lines.append(line)
            char_count += len(line)

        if len(lines) > 1:
            section_texts.append("\n".join(lines))

        if char_count >= max_chars:
            break

    if not section_texts:
        return messages

    raw_text = _INJECTION_TEMPLATE.format(sections="\n".join(section_texts))

    # Resolve template variables
    full_text = resolve_variables(
        raw_text,
        username=username,
        character_name=character_name,
        model_name=model_name,
        conversation_id=conversation_id,
        memory_count=len(candidates),
        total_memories=total_memories,
        session_turns=session_turns,
        days_since_last=days_since_last,
    )

    memory_msg = {"role": "system", "content": full_text}

    # Insert after first system message
    result = list(messages)
    insert_idx = 0
    for i, m in enumerate(result):
        if m.get("role") == "system":
            insert_idx = i + 1
            break
    result.insert(insert_idx, memory_msg)
    return result
