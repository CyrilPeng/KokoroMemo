"""Build retrieval queries from conversation context."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RetrievalQuery:
    query_text: str
    latest_user_text: str
    recent_context_text: str
    scope_filter: dict


def build_retrieval_query(
    messages: list[dict],
    user_id: str,
    character_id: str | None,
    conversation_id: str,
    max_recent_turns: int = 6,
) -> RetrievalQuery:
    """Construct a retrieval query from recent conversation context."""
    # Extract latest user message
    latest_user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            latest_user_text = msg.get("content", "")
            break

    # Build recent context (last N messages, skip system)
    non_system = [m for m in messages if m.get("role") != "system"]
    recent = non_system[-(max_recent_turns * 2):]
    recent_lines = []
    for m in recent:
        role = m.get("role", "")
        content = m.get("content", "")[:200]
        recent_lines.append(f"{role}: {content}")
    recent_context_text = "\n".join(recent_lines)

    # Combined query text for embedding
    query_text = f"{latest_user_text}\n\n{recent_context_text}"

    scope_filter = {
        "user_id": user_id,
        "character_id": character_id,
        "conversation_id": conversation_id,
    }

    return RetrievalQuery(
        query_text=query_text,
        latest_user_text=latest_user_text,
        recent_context_text=recent_context_text,
        scope_filter=scope_filter,
    )
