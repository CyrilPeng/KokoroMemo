"""Card-based memory extraction. Produces candidates -> inbox or direct approve."""

from __future__ import annotations

import json
import logging

from app.core.ids import generate_id
from app.memory.judge import MemoryJudgeConfigView, judge_memories_with_llm
from app.memory.review_policy import auto_review, determine_risk_level
from app.storage.sqlite_cards import (
    find_card_id_by_content,
    get_write_library_id,
    insert_card,
    insert_card_version,
    insert_inbox_item,
    trim_discarded_inbox,
)
from app.storage.vector_sync import enqueue_card_vector_sync, sync_card_vector

logger = logging.getLogger("kokoromemo.card_extractor")

# 证据文本截断长度：保留用户最近消息的前 N 个字符作为记忆卡证据来源
_EVIDENCE_TEXT_MAX_CHARS = 300

# WebSocket 事件推送中卡片内容预览的最大字符数
_EVENT_CONTENT_PREVIEW_MAX_CHARS = 100


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
    semantic_dedup_threshold: float = 0.92,
    judge_config: MemoryJudgeConfigView | None = None,
    lang: str = "zh",
    discarded_keep_limit: int = 200,
) -> None:
    """Extract candidate memory cards and route through review policy.

    Flow:
    1. Memory judge model → candidate cards
    2. review_policy.auto_review() for each
    3. auto_approve → write card(approved) + embed + LanceDB
    4. pending → write inbox item
    5. reject / dedup → write inbox item with status='discarded' + discard_reason
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
    discarded_written = False

    for mem in extracted:
        risk_level = _risk_level_from_tags(mem.tags) or determine_risk_level(mem.memory_type, mem.confidence)
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
            "evidence_text": user_message[:_EVIDENCE_TEXT_MAX_CHARS],
        }

        # 去重：精确文本匹配 → 写入 discarded
        related_card_id = await find_card_id_by_content(db_path, user_id, mem.content)
        if related_card_id:
            await _write_discarded(
                db_path,
                card_payload=card_payload,
                user_id=user_id,
                character_id=character_id,
                conversation_id=conversation_id,
                risk_level=risk_level,
                library_id=library_id,
                discard_reason="exact_duplicate",
                reason="与已有卡片内容完全相同",
                related_card_id=related_card_id,
            )
            discarded_written = True
            logger.debug("Discarded duplicate card: %s", mem.content[:50])
            continue

        # 语义去重：通过向量相似度
        if embedding_provider and lancedb_store:
            sem_match = await _find_semantic_duplicate(
                embedding_provider,
                lancedb_store,
                user_id,
                mem.content,
                threshold=semantic_dedup_threshold,
            )
            if sem_match:
                await _write_discarded(
                    db_path,
                    card_payload=card_payload,
                    user_id=user_id,
                    character_id=character_id,
                    conversation_id=conversation_id,
                    risk_level=risk_level,
                    library_id=library_id,
                    discard_reason="semantic_duplicate",
                    reason=f"与已有卡片语义近似（相似度 {sem_match[1]:.2f}）",
                    related_card_id=sem_match[0],
                )
                discarded_written = True
                logger.debug("Discarded semantic near-duplicate: %s", mem.content[:50])
                continue

        decision = auto_review(
            card_type=mem.memory_type,
            importance=mem.importance,
            confidence=mem.confidence,
            risk_level=risk_level,
            tags=mem.tags,
        )

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
                evidence_text=user_message[:_EVIDENCE_TEXT_MAX_CHARS],
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
            # 被自动审核策略拒绝：写入 discarded 供查阅与恢复
            await _write_discarded(
                db_path,
                card_payload=card_payload,
                user_id=user_id,
                character_id=character_id,
                conversation_id=conversation_id,
                risk_level=risk_level,
                library_id=library_id,
                discard_reason="auto_rejected",
                reason=f"自动审核拒绝: type={mem.memory_type}, importance={mem.importance:.2f}",
                related_card_id=None,
            )
            discarded_written = True
            logger.debug("Card rejected by policy: type=%s, importance=%.2f", mem.memory_type, mem.importance)

    if discarded_written and discarded_keep_limit > 0:
        try:
            removed = await trim_discarded_inbox(db_path, discarded_keep_limit)
            if removed:
                logger.debug("Trimmed %s old discarded inbox items", removed)
        except Exception as e:
            logger.warning("Failed to trim discarded inbox: %s", e)


async def _write_discarded(
    db_path: str,
    *,
    card_payload: dict,
    user_id: str,
    character_id: str | None,
    conversation_id: str,
    risk_level: str,
    library_id: str,
    discard_reason: str,
    reason: str,
    related_card_id: str | None,
) -> None:
    inbox_id = generate_id("inbox_")
    await insert_inbox_item(
        db_path,
        inbox_id=inbox_id,
        candidate_type="card",
        payload_json=json.dumps(card_payload, ensure_ascii=False),
        user_id=user_id,
        character_id=character_id,
        conversation_id=conversation_id,
        suggested_action="reject",
        risk_level=risk_level,
        reason=reason,
        status="discarded",
        library_id=library_id,
        discard_reason=discard_reason,
        related_card_id=related_card_id,
    )


def _risk_level_from_tags(tags: list[str]) -> str | None:
    for tag in tags:
        if tag in {"risk:low", "risk:medium", "risk:high"}:
            return tag.split(":", 1)[1]
    return None


async def _find_semantic_duplicate(
    embedding_provider,
    lancedb_store,
    user_id: str,
    content: str,
    threshold: float = 0.92,
) -> tuple[str, float] | None:
    """Return (card_id, similarity) of the most similar existing card if above threshold."""
    try:
        vectors = await embedding_provider.embed_texts([content])
        if not vectors or not vectors[0]:
            return None
        safe_user_id = user_id.replace("'", "''")
        results = await lancedb_store.search(
            vectors[0],
            top_k=3,
            where=f"user_id = '{safe_user_id}' AND status = 'approved'",
        )
        if not results:
            return None
        best: tuple[str, float] | None = None
        for r in results:
            distance = r.get("_distance", 1.0)
            similarity = 1.0 - distance
            if similarity >= threshold:
                card_id = r.get("card_id") or r.get("id") or ""
                if best is None or similarity > best[1]:
                    best = (card_id, similarity)
        return best
    except Exception:
        return None


async def _emit_card_event(event_type: str, card_id: str, mem) -> None:
    """Emit a WebSocket event for card extraction activity."""
    try:
        from app.core.events import emit
        await emit(event_type, {
            "card_id": card_id,
            "content": mem.content[:_EVENT_CONTENT_PREVIEW_MAX_CHARS],
            "memory_type": mem.memory_type,
            "importance": mem.importance,
        })
    except Exception:  # noqa: S110
        pass
