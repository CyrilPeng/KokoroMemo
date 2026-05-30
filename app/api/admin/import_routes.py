"""Import routes: SillyTavern chat import and memory extraction."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from app.api.admin._helpers import _require_admin

router = APIRouter()


@router.post("/admin/import/sillytavern")
async def import_sillytavern(request: Request, data: dict = Body(...)):
    """Import a SillyTavern JSONL chat log."""
    _require_admin(request)
    from app.core.ids import generate_id
    from app.core.state import get_config
    from app.importers.sillytavern import parse_sillytavern_jsonl
    from app.storage.sqlite_app import init_app_db, upsert_conversation
    from app.storage.sqlite_conversation import init_chat_db, save_turn_and_messages

    cfg = get_config()
    text = data.get("content", "")
    if not text:
        raise HTTPException(status_code=400, detail="content is required (JSONL text)")

    conv = parse_sillytavern_jsonl(text)
    if not conv.turns:
        return {"status": "error", "message": "No valid turns found in input"}

    user_id = data.get("user_id", "default")
    character_id = data.get("character_id") or None
    conversation_id = data.get("conversation_id") or generate_id("conv_import_")

    from pathlib import Path

    conv_dir = str(Path(cfg.storage.root_dir, "conversations", conversation_id))
    chat_db_path = str(Path(conv_dir, "chat.sqlite"))

    await init_app_db(cfg.storage.sqlite.app_db)
    await init_chat_db(chat_db_path)
    await upsert_conversation(
        cfg.storage.sqlite.app_db,
        conversation_id,
        user_id,
        character_id,
        "sillytavern_import",
        conv_dir,
    )

    messages = []
    if conv.system_prompt:
        messages.append({"role": "system", "content": conv.system_prompt})
    for turn in conv.turns:
        messages.append({"role": turn.role, "content": turn.content})

    turn_id = generate_id("turn_")
    request_id = generate_id("req_import_")
    await save_turn_and_messages(
        chat_db_path,
        turn_id,
        conversation_id,
        user_id,
        character_id,
        request_id,
        0,
        messages,
    )

    return {
        "status": "ok",
        "conversation_id": conversation_id,
        "turns_imported": len(conv.turns),
        "character_name": conv.character_name,
    }


@router.post("/admin/import/{conversation_id}/extract-memories")
async def extract_memories_from_import(conversation_id: str, request: Request, data: dict = Body(default={})):
    """Batch-extract memories from an imported conversation."""
    _require_admin(request)
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.memory.card_extractor import extract_and_route
    from app.memory.judge import MemoryJudgeConfigView
    from app.storage.sqlite_conversation import get_all_messages

    cfg = get_config()
    from pathlib import Path

    chat_db_path = str(Path(cfg.storage.root_dir, "conversations", conversation_id, "chat.sqlite"))

    if not Path(chat_db_path).exists():
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await get_all_messages(chat_db_path, conversation_id)
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(messages) - 1:
        if messages[i].get("role") == "user" and messages[i + 1].get("role") == "assistant":
            pairs.append((messages[i]["content"], messages[i + 1]["content"]))
            i += 2
        else:
            i += 1

    if not pairs:
        return {"status": "ok", "extracted_pairs": 0, "message": "No user-assistant pairs found"}

    user_id = data.get("user_id", "default")
    character_id = data.get("character_id") or None
    ep = get_embedding_provider(cfg)
    store = get_lancedb_store(cfg)

    judge_config = None
    if cfg.memory.judge.enabled and cfg.memory.judge.model:
        judge_config = MemoryJudgeConfigView(
            provider=cfg.memory.judge.provider,
            base_url=cfg.memory.judge.base_url or cfg.llm.base_url,
            api_key=cfg.memory.judge.get_api_key() or cfg.llm.get_api_key(),
            model=cfg.memory.judge.model or cfg.llm.model,
            timeout_seconds=cfg.memory.judge.timeout_seconds,
            temperature=cfg.memory.judge.temperature,
            mode=cfg.memory.judge.mode,
            user_rules=cfg.memory.judge.user_rules,
            prompt=cfg.memory.judge.prompt,
        )

    max_pairs = data.get("max_pairs", 50)
    extracted_count = 0
    for user_msg, assistant_msg in pairs[:max_pairs]:
        try:
            await extract_and_route(
                db_path=cfg.storage.sqlite.memory_db,
                user_message=user_msg,
                assistant_message=assistant_msg,
                user_id=user_id,
                character_id=character_id,
                conversation_id=conversation_id,
                embedding_provider=ep,
                lancedb_store=store,
                min_importance=cfg.memory.extraction.min_importance,
                min_confidence=cfg.memory.extraction.min_confidence,
                semantic_dedup_threshold=cfg.memory.extraction.semantic_dedup_threshold,
                judge_config=judge_config,
                lang=cfg.language,
                discarded_keep_limit=cfg.memory.extraction.discarded_keep_limit,
            )
            extracted_count += 1
        except Exception:  # noqa: S112
            continue

    return {"status": "ok", "extracted_pairs": extracted_count, "total_pairs": len(pairs)}
