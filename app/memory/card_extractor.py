"""Card-based memory extraction. Produces candidates -> inbox or direct approve."""

from __future__ import annotations

import json
import logging

from app.core.ids import generate_id
from app.memory.judge import MemoryJudgeConfigView, judge_memories_with_llm
from app.memory.review_policy import auto_review, determine_risk_level
from app.storage.sqlite_cards import (
    card_exists_with_content,
    insert_card,
    insert_card_version,
    insert_inbox_item,
    get_write_library_id,
)
from app.storage.vector_sync import enqueue_card_vector_sync, sync_card_vector

logger = logging.getLogger("kokoromemo.card_extractor")


async def extract_and_route(
    db_path: str,
    user_message: str,
    assistant_message: str,
    user_id: str,
    character_id: str | None,
    conversation_id: str,
    embedding_provider=None,
    lancedb_store=None,
    min_importance: float = 0.45,
    min_confidence: float = 0.55,
    judge_config: MemoryJudgeConfigView | None = None,
    lang: str = "zh",
) -> None:
    """Extract candidate memory cards and route through review policy.

    Flow:
    1. Memory judge model → candidate cards
    2. review_policy.auto_review() for each
    3. auto_approve → write card(approved) + embed + LanceDB
    4. pending → write inbox item
    5. reject → discard (log only)
    """
    if not judge_config:
        return

    try:
        extracted = await judge_memories_with_llm(
            user_message,
            assistant_message,
            character_id,
            judge_config,
            min_importance=min_importance,
            min_confidence=min_confidence,
            lang=lang,
        )
    except Exception as e:
        logger.warning("Memory judge failed: %s", e)
        return

    if not extracted:
        return

    library_id = await get_write_library_id(db_path, conversation_id)

    for mem in extracted:
        # 去重：如果已存在相同内容则跳过
        if await card_exists_with_content(db_path, user_id, mem.content):
            logger.debug("Skipping duplicate card: %s", mem.content[:50])
            continue

        # 语义去重：通过向量相似度跳过近似内容
        if embedding_provider and lancedb_store:
            if await _is_semantic_duplicate(embedding_provider, lancedb_store, user_id, mem.content):
                logger.debug("Skipping semantic near-duplicate: %s", mem.content[:50])
                continue

        risk_level = _risk_level_from_tags(mem.tags) or determine_risk_level(mem.memory_type, mem.confidence)
        decision = auto_review(
            card_type=mem.memory_type,
            importance=mem.importance,
            confidence=mem.confidence,
            risk_level=risk_level,
            tags=mem.tags,
        )

        card_payload = {
            "library_id": library_id,
            "user_id": user_id,
            "character_id": character_id,
            "conversation_id": conversation_id,
            "scope": mem.scope,
            "card_type": mem.memory_type,
            "content": mem.content,
            "importance": mem.importance,
            "confidence": mem.confidence,
            "tags": mem.tags,
            "evidence_text": user_message[:300],
        }

        if decision == "approve":
            # 直接批准：写入 memory_cards 并同步向量
            card_id = generate_id("card_")
            await insert_card(
                db_path,
                card_id=card_id,
                library_id=library_id,
                user_id=user_id,
                character_id=character_id,
                conversation_id=conversation_id,
                scope=mem.scope,
                card_type=mem.memory_type,
                content=mem.content,
                importance=mem.importance,
                confidence=mem.confidence,
                status="approved",
                evidence_text=user_message[:300],
            )
            await insert_card_version(
                db_path,
                card_id=card_id,
                content=mem.content,
                card_type=mem.memory_type,
                importance=mem.importance,
                confidence=mem.confidence,
            )

            # 向量同步
            if embedding_provider and lancedb_store:
                try:
                    await sync_card_vector(db_path, card_id, embedding_provider, lancedb_store)
                    logger.info("Auto-approved card: %s (type=%s)", card_id, mem.memory_type)
                    await _emit_card_event("card_approved", card_id, mem)
                except Exception as e:
                    await enqueue_card_vector_sync(db_path, card_id, str(e))
                    logger.warning("Vector sync failed for card %s: %s", card_id, e)
            else:
                logger.info("Auto-approved card (no vector): %s", card_id)

        elif decision == "pending":
            # 写入待审核列表供用户复核
            inbox_id = generate_id("inbox_")
            await insert_inbox_item(
                db_path,
                inbox_id=inbox_id,
                candidate_type="card",
                payload_json=json.dumps(card_payload, ensure_ascii=False),
                user_id=user_id,
                character_id=character_id,
                conversation_id=conversation_id,
                suggested_action="approve",
                risk_level=risk_level,
                reason=f"记忆判断模型: {mem.memory_type}",
                status="pending",
                library_id=library_id,
            )
            logger.info("Card sent to inbox: %s (type=%s, risk=%s)", inbox_id, mem.memory_type, risk_level)
            await _emit_card_event("inbox_new", inbox_id, mem)

        else:
            # 被策略拒绝，直接丢弃
            logger.debug("Card rejected by policy: type=%s, importance=%.2f", mem.memory_type, mem.importance)


def _risk_level_from_tags(tags: list[str]) -> str | None:
    for tag in tags:
        if tag in {"risk:low", "risk:medium", "risk:high"}:
            return tag.split(":", 1)[1]
    return None


async def _is_semantic_duplicate(embedding_provider, lancedb_store, user_id: str, content: str, threshold: float = 0.92) -> bool:
    """Check if content is semantically near-duplicate to existing cards."""
    try:
        vectors = await embedding_provider.embed_texts([content])
        if not vectors or not vectors[0]:
            return False
        results = await lancedb_store.search(
            vectors[0],
            top_k=3,
            where=f"user_id = '{user_id}' AND status = 'approved'",
        )
        if not results:
            return False
        for r in results:
            distance = r.get("_distance", 1.0)
            similarity = 1.0 - distance
            if similarity >= threshold:
                return True
    except Exception:
        pass
    return False


async def _emit_card_event(event_type: str, card_id: str, mem) -> None:
    """Emit a WebSocket event for card extraction activity."""
    try:
        from app.core.events import emit
        await emit(event_type, {
            "card_id": card_id,
            "content": mem.content[:100],
            "memory_type": mem.memory_type,
            "importance": mem.importance,
        })
    except Exception:
        pass
