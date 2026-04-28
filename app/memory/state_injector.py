"""Inject rendered conversation hot-state into chat messages."""

from __future__ import annotations


def inject_state_board(messages: list[dict], state_text: str) -> list[dict]:
    """Insert hot-state system message after the original system prompt."""
    if not state_text.strip():
        return messages

    result = list(messages)
    insert_idx = 0
    for index, message in enumerate(result):
        if message.get("role") == "system":
            insert_idx = index + 1
            break
    result.insert(insert_idx, {"role": "system", "content": state_text})
    return result
