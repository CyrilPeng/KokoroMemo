"""Resolve conversation/user/character context from incoming requests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _metadata_value(meta: dict, *keys: str) -> str | None:
    for key in keys:
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _stable_system_prompt(messages: list[dict]) -> str:
    system_contents: list[str] = []
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                system_contents.append(content.strip())
    return "\n\n".join(system_contents)


def _assistant_name(messages: list[dict]) -> str | None:
    for msg in messages:
        if msg.get("role") == "assistant":
            name = msg.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


async def resolve_context(request: Request, body: dict, root_dir: str, cfg=None) -> RequestContext:
    """Extract user/character/conversation identifiers from request."""
    headers = request.headers

    # 用户 ID
    user_id = headers.get("x-user-id") or body.get("user") or "default"
    user_id = sanitize_id(user_id)

    meta = body.get("metadata", {})
    if not isinstance(meta, dict):
        meta = {}
    messages = body.get("messages", [])
    if not isinstance(messages, list):
        messages = []

    # 会话 ID
    conversation_id = _first_text(headers.get("x-conversation-id"), headers.get("x-chat-id"), headers.get("x-session-id"))
    if not conversation_id:
        conversation_id = _metadata_value(meta, "conversation_id", "chat_id", "session_id", "chat_session_id", "thread_id")
    explicit_conv_id = bool(conversation_id)

    # 角色 ID
    character_id = _first_text(
        headers.get("x-character-id"),
        _metadata_value(meta, "character_id", "char_id", "character_name", "char_name", "persona", "bot_name"),
        _assistant_name(messages),
    )
    if not character_id:
        system_prompt = _stable_system_prompt(messages)
        if system_prompt:
            character_id = f"char_{_hash_short(system_prompt)}"
    if character_id:
        character_id = sanitize_id(character_id)

    if explicit_conv_id and cfg:
        existing_character_id = await _existing_character_for_conversation(cfg.storage.sqlite.app_db, sanitize_id(conversation_id))
        if existing_character_id:
            character_id = existing_character_id
    if not conversation_id:
        seed = f"{user_id}_{character_id or 'none'}"
        conversation_id = f"conv_{_hash_short(seed)}"
    conversation_id = sanitize_id(conversation_id)

    # 智能会话检测：未显式提供 ID 时，检查是否需要开启新会话
    if not explicit_conv_id and cfg:
        conversation_id = await _maybe_new_session(
            conversation_id, user_id, character_id, body, root_dir, cfg
        )

    # 客户端名称
    client_name = _first_text(headers.get("x-client-name"), _metadata_value(meta, "client_name", "app", "source"))

    # 路径
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


async def _maybe_new_session(
    base_conv_id: str,
    user_id: str,
    character_id: str | None,
    body: dict,
    root_dir: str,
    cfg,
) -> str:
    """Detect if this should be a new session based on time gap and message count."""
    import aiosqlite
    from datetime import datetime

    conv_config = getattr(cfg, "conversation", None)
    if not conv_config:
        return base_conv_id

    gap_minutes = getattr(conv_config, "auto_new_session_gap_minutes", 0)
    detect_msg_reset = getattr(conv_config, "detect_message_count_reset", False)

    if not gap_minutes and not detect_msg_reset:
        return base_conv_id

    app_db = cfg.storage.sqlite.app_db
    try:
        async with aiosqlite.connect(app_db) as db:
            cursor = await db.execute(
                "SELECT last_seen_at FROM conversations WHERE conversation_id = ?",
                (base_conv_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return base_conv_id

            last_seen = row[0]
            if gap_minutes and last_seen:
                try:
                    last_dt = datetime.fromisoformat(last_seen)
                    now = datetime.now()
                    diff_minutes = (now - last_dt).total_seconds() / 60
                    if diff_minutes > gap_minutes:
                        return _allocate_new_session_id(base_conv_id, app_db, db)
                except (ValueError, TypeError):
                    pass

            if detect_msg_reset:
                messages = body.get("messages", [])
                non_system = [m for m in messages if m.get("role") != "system"]
                if len(non_system) <= 1:
                    chat_db = str(Path(root_dir, "conversations", base_conv_id, "chat.sqlite"))
                    if Path(chat_db).exists():
                        async with aiosqlite.connect(chat_db) as chat:
                            cursor2 = await chat.execute("SELECT COUNT(*) FROM turns")
                            count_row = await cursor2.fetchone()
                            if count_row and count_row[0] > 5:
                                return _allocate_new_session_id(base_conv_id, app_db, db)
    except Exception:
        pass

    return base_conv_id


def _allocate_new_session_id(base_conv_id: str, app_db: str, db) -> str:
    """Generate a new sequential session ID based on the base conversation ID."""
    import time
    suffix = hex(int(time.time()) % 0xFFFFFF)[2:]
    return f"{base_conv_id}_{suffix}"


async def _existing_character_for_conversation(app_db: str, conversation_id: str) -> str | None:
    """Reuse the character already bound to an explicit conversation ID."""
    try:
        import aiosqlite
        from app.storage.sqlite_app import init_app_db

        await init_app_db(app_db)
        async with aiosqlite.connect(app_db) as db:
            cursor = await db.execute(
                "SELECT character_id FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            )
            row = await cursor.fetchone()
            if row and row[0]:
                return sanitize_id(row[0])
    except Exception:
        return None
    return None
