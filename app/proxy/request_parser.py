"""Resolve conversation/user/character context from incoming requests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from app.core.ids import sanitize_id, generate_id


@dataclass
class RequestContext:
    request_id: str
    user_id: str
    character_id: str | None
    conversation_id: str
    client_name: str | None
    chat_db_path: str
    conv_dir: str


def _hash_short(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


async def resolve_context(request: Request, body: dict, root_dir: str) -> RequestContext:
    """Extract user/character/conversation identifiers from request."""
    headers = request.headers

    # User ID
    user_id = headers.get("x-user-id") or body.get("user") or "default"
    user_id = sanitize_id(user_id)

    # Character ID
    character_id = headers.get("x-character-id") or None
    if not character_id:
        # Try to derive from system prompt hash
        messages = body.get("messages", [])
        system_msgs = [m for m in messages if m.get("role") == "system"]
        if system_msgs:
            sp_hash = _hash_short(system_msgs[0].get("content", ""))
            model = body.get("model", "unknown")
            character_id = f"char_{_hash_short(f'{sp_hash}_{model}')}"
    if character_id:
        character_id = sanitize_id(character_id)

    # Conversation ID
    conversation_id = headers.get("x-conversation-id") or None
    if not conversation_id:
        meta = body.get("metadata", {})
        if isinstance(meta, dict):
            conversation_id = meta.get("conversation_id")
    if not conversation_id:
        # Generate from user + character
        seed = f"{user_id}_{character_id or 'none'}"
        conversation_id = f"conv_{_hash_short(seed)}"
    conversation_id = sanitize_id(conversation_id)

    # Client name
    client_name = headers.get("x-client-name") or None

    # Paths
    conv_dir = str(Path(root_dir, "conversations", conversation_id))
    chat_db_path = str(Path(conv_dir, "chat.sqlite"))

    request_id = generate_id("req_")

    return RequestContext(
        request_id=request_id,
        user_id=user_id,
        character_id=character_id,
        conversation_id=conversation_id,
        client_name=client_name,
        chat_db_path=chat_db_path,
        conv_dir=conv_dir,
    )
