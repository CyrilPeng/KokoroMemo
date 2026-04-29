"""Conversation state updater for maintaining hot memory."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.core.ids import generate_id
from app.core.prompts import (
    LONG_TERM_ROUTE_REASON,
    RULE_CONTENT_TEMPLATES,
    RULE_TITLES,
    STATE_UPDATER_USER_MSG,
    get_prompt,
    get_text,
)
from app.memory.state_schema import ConversationStateItem, StateUpdate, StateUpdateResult
from app.proxy.llm_providers import create_llm_provider
from app.storage.sqlite_cards import enqueue_job, insert_inbox_item
from app.storage.sqlite_state import SQLiteStateStore

logger = logging.getLogger("kokoromemo.state_updater")


@dataclass
class StateUpdaterContext:
    db_path: str
    user_id: str
    character_id: str | None
    conversation_id: str
    turn_id: str | None = None
    mode: str = "rule_only"
    min_confidence: float = 0.55
    llm_provider: str = "openai_compatible"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: int = 120
    lang: str = "zh"


async def update_conversation_state(
    context: StateUpdaterContext,
    user_message: str,
    assistant_message: str,
) -> StateUpdateResult:
    """Update hot-state from the completed user/assistant turn."""
    store = SQLiteStateStore(context.db_path)
    result = StateUpdateResult()
    try:
        updates = rule_based_state_updates(user_message, assistant_message, context.min_confidence, context.lang)
        if context.mode in {"llm", "llm_first", "hybrid"}:
            updates.extend(await llm_state_updates(context, user_message, assistant_message))
        result.upserts = _dedupe_updates([u for u in updates if u.confidence >= context.min_confidence])

        for update in result.upserts:
            item_id = await store.upsert_item(
                ConversationStateItem(
                    item_id=None,
                    user_id=context.user_id,
                    character_id=context.character_id,
                    conversation_id=context.conversation_id,
                    category=update.category,
                    item_key=update.item_key,
                    title=update.title,
                    content=update.content,
                    confidence=update.confidence,
                    status=update.status,
                    priority=update.priority,
                    source="state_updater",
                    source_turn_id=context.turn_id,
                    source_turn_ids=[context.turn_id] if context.turn_id else [],
                    metadata={"reason": update.reason, **(update.metadata or {})},
                )
            )
            update.metadata["item_id"] = item_id
            result.created += 1

        await _route_long_term_candidates(context, result.upserts, user_message, assistant_message)
        await store.record_state_event(
            context.conversation_id,
            "state_updater_completed",
            payload={"upserts": len(result.upserts), "mode": context.mode},
        )
    except Exception as exc:
        logger.warning("State updater failed: %s", exc)
        await store.record_state_event(
            context.conversation_id,
            "state_updater_failed",
            payload={"error": str(exc), "mode": context.mode},
        )
        await enqueue_job(
            context.db_path,
            "state_updater_failed",
            json.dumps(
                {
                    "conversation_id": context.conversation_id,
                    "user_id": context.user_id,
                    "character_id": context.character_id,
                    "error": str(exc),
                },
                ensure_ascii=False,
            ),
            last_error=str(exc),
        )
        result.notes.append(str(exc))
    return result


def rule_based_state_updates(user_message: str, assistant_message: str, min_confidence: float = 0.55, lang: str = "zh") -> list[StateUpdate]:
    """Extract a conservative first-pass hot-state from common Chinese role-play phrasing."""
    text = f"{user_message}\n{assistant_message}".strip()
    updates: list[StateUpdate] = []
    titles = RULE_TITLES.get(lang, RULE_TITLES["zh"])
    templates = RULE_CONTENT_TEMPLATES.get(lang, RULE_CONTENT_TEMPLATES["zh"])
    location = _extract_location(text)
    if location:
        updates.append(StateUpdate(
            category="location",
            item_key="current_location",
            title=titles["location"],
            content=templates["location"].format(value=location),
            confidence=0.72,
            priority=85,
            reason="location_rule",
        ))
        updates.append(StateUpdate(
            category="scene",
            item_key="current_scene",
            title=titles["scene"],
            content=templates["scene"].format(value=location),
            confidence=0.65,
            priority=80,
            reason="scene_from_location_rule",
        ))

    quest = _extract_quest(text)
    if quest:
        updates.append(StateUpdate(
            category="main_quest",
            item_key="current_goal",
            title=titles["goal"],
            content=quest,
            confidence=0.68,
            priority=78,
            reason="quest_rule",
        ))

    promise = _extract_promise(text)
    if promise:
        updates.append(StateUpdate(
            category="promise",
            item_key=_stable_key("promise", promise),
            title=titles["promise"],
            content=promise,
            confidence=0.74,
            priority=82,
            reason="promise_rule",
        ))

    boundary = _extract_boundary(text)
    if boundary:
        updates.append(StateUpdate(
            category="boundary",
            item_key=_stable_key("boundary", boundary),
            title=titles["boundary"],
            content=boundary,
            confidence=0.82,
            priority=95,
            reason="boundary_rule",
            metadata={"candidate_long_term": True},
        ))

    return [update for update in updates if update.confidence >= min_confidence]


async def llm_state_updates(
    context: StateUpdaterContext,
    user_message: str,
    assistant_message: str,
) -> list[StateUpdate]:
    """Ask the configured chat model for strict JSON state updates."""
    if not context.llm_base_url or not context.llm_model:
        return []
    provider = create_llm_provider(
        provider=context.llm_provider,
        base_url=context.llm_base_url,
        api_key=context.llm_api_key,
        model=context.llm_model,
    )
    body = {
        "model": context.llm_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": get_prompt("state_updater", context.lang)},
            {"role": "user", "content": get_text(STATE_UPDATER_USER_MSG, context.lang, user=user_message, assistant=assistant_message)},
        ],
    }
    response = await provider.chat(body, context.llm_timeout_seconds)
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    payload = _parse_json_object(content)
    updates: list[StateUpdate] = []
    for item in payload.get("upserts", []):
        if not isinstance(item, dict):
            continue
        category = item.get("category")
        item_key = item.get("item_key")
        item_value = item.get("item_value") or item.get("content")
        if not category or not item_key or not item_value:
            continue
        updates.append(StateUpdate(
            category=category,
            item_key=item_key,
            title=item.get("title"),
            content=item_value,
            confidence=float(item.get("confidence", 0.7)),
            priority=int(item.get("priority", 50)),
            reason=item.get("reason") or "llm_state_updater",
        ))
    return updates


async def _route_long_term_candidates(
    context: StateUpdaterContext,
    updates: list[StateUpdate],
    user_message: str,
    assistant_message: str,
) -> None:
    """Send long-term-worthy state facts to memory_inbox, never directly to approved cards."""
    for update in updates:
        if update.category not in {"boundary", "preference"}:
            continue
        if not update.metadata.get("candidate_long_term") and update.category != "boundary":
            continue
        payload = {
            "user_id": context.user_id,
            "character_id": context.character_id,
            "conversation_id": context.conversation_id,
            "scope": "character" if context.character_id else "global",
            "card_type": update.category,
            "content": update.content,
            "importance": 0.75 if update.category == "boundary" else 0.65,
            "confidence": update.confidence,
            "evidence_text": get_text(STATE_UPDATER_USER_MSG, context.lang, user=user_message, assistant=assistant_message)[:1000],
            "source": "state_updater",
        }
        await insert_inbox_item(
            context.db_path,
            inbox_id=generate_id("inbox_"),
            candidate_type="card",
            payload_json=json.dumps(payload, ensure_ascii=False),
            user_id=context.user_id,
            character_id=context.character_id,
            conversation_id=context.conversation_id,
            suggested_action="approve",
            risk_level="medium" if update.category == "boundary" else "low",
            reason=get_text(LONG_TERM_ROUTE_REASON, context.lang),
        )


def _extract_location(text: str) -> str | None:
    patterns = [
        r"(?:去|到|前往|抵达|回到|进入|来到)([^，。！？\n]{1,18}?)(?:吧|。|，|！|？|$)",
        r"(?:在|位于)([^，。！？\n]{1,18}?)(?:里|内|旁|附近|。|，|！|？|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return None


def _extract_quest(text: str) -> str | None:
    patterns = [
        r"(?:接下来|下一步|现在|目前).{0,8}(?:需要|要|准备|打算)([^。！？\n]{2,60})",
        r"(?:目标|任务|计划)(?:是|：|:)([^。！？\n]{2,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0).strip(" ，。！？」\n")
    return None


def _extract_promise(text: str) -> str | None:
    patterns = [
        r"(?:我|我们|你)(?:会|答应|保证|约定|说好)([^。！？\n]{2,80})",
        r"(?:别忘了|记得)([^。！？\n]{2,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0).strip(" ，。！？」\n")
    return None


def _extract_boundary(text: str) -> str | None:
    patterns = [
        r"(?:不要|别|不许)([^。！？\n]{2,80})",
        r"(?:我不喜欢|我讨厌|我接受不了)([^。！？\n]{2,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0).strip(" ，。！？」\n")
    return None


def _stable_key(prefix: str, content: str) -> str:
    return f"{prefix}_{abs(hash(content)) % 10_000_000}"


def _dedupe_updates(updates: list[StateUpdate]) -> list[StateUpdate]:
    deduped: dict[tuple[str, str], StateUpdate] = {}
    for update in updates:
        key = (update.category, update.item_key or _stable_key(update.category, update.content))
        update.item_key = key[1]
        old = deduped.get(key)
        if old is None or update.confidence >= old.confidence:
            deduped[key] = update
    return list(deduped.values())


def _parse_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"upserts": []}
    if not isinstance(payload, dict):
        return {"upserts": []}
    return payload
