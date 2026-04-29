"""Model-driven filler for template-based conversation state boards."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.prompts import (
    STATE_FILLER_EMPTY,
    STATE_FILLER_TEMPLATE_HEADER,
    STATE_FILLER_USER_MSG,
    get_prompt,
    get_text,
)
from app.memory.state_schema import ConversationStateItem, StateBoardField, StateBoardTemplate
from app.proxy.llm_providers import create_llm_provider
from app.storage.sqlite_state import SQLiteStateStore


@dataclass
class StateFillerConfigView:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 30
    temperature: float = 0.0
    min_confidence: float = 0.55
    prompt: str = ""


@dataclass
class FilledStateUpdate:
    field_key: str
    value: str
    confidence: float = 0.7
    reason: str = ""


@dataclass
class StateFillResult:
    updates: list[FilledStateUpdate] = field(default_factory=list)
    applied: int = 0
    skipped: int = 0
    notes: list[str] = field(default_factory=list)


async def fill_conversation_state(
    *,
    db_path: str,
    conversation_id: str,
    user_message: str,
    assistant_message: str,
    config: StateFillerConfigView,
    lang: str = "zh",
    user_id: str | None = None,
    character_id: str | None = None,
    turn_id: str | None = None,
) -> StateFillResult:
    """Ask a lightweight model to update user-defined state board fields."""
    result = StateFillResult()
    if not config.base_url or not config.model or not assistant_message:
        result.notes.append("state_filler_not_configured")
        return result

    store = SQLiteStateStore(db_path)
    template = await store.get_conversation_template(conversation_id)
    if not template:
        result.notes.append("template_not_found")
        return result

    fields = _writable_fields(template)
    if not fields:
        result.notes.append("no_writable_fields")
        return result

    current_items = await store.list_active_items(conversation_id)
    locked_field_ids = {item.field_id for item in current_items if item.user_locked and item.field_id}
    current_by_field = {item.field_id: item for item in current_items if item.field_id}
    prompt = _build_prompt(config.prompt, template, fields, current_by_field, lang)
    provider = create_llm_provider(
        provider=config.provider,
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
    )
    user_content = get_text(STATE_FILLER_USER_MSG, lang, user=user_message, assistant=assistant_message)
    response = await provider.chat(
        {
            "model": config.model,
            "temperature": config.temperature,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ],
        },
        config.timeout_seconds,
    )
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    payload = _parse_json(content)
    field_by_key = {field.field_key: field for field in fields}
    tab_by_id = {tab.tab_id: tab for tab in template.tabs}

    for raw_item in payload.get("updates") or payload.get("items") or []:
        if not isinstance(raw_item, dict):
            result.skipped += 1
            continue
        field_key = str(raw_item.get("field_key") or raw_item.get("key") or "").strip()
        value = str(raw_item.get("value") or raw_item.get("content") or "").strip()
        if not field_key or not value:
            result.skipped += 1
            continue
        field = field_by_key.get(field_key)
        if not field or field.field_id in locked_field_ids:
            result.skipped += 1
            continue
        confidence = _safe_float(raw_item.get("confidence"), 0.7)
        if confidence < config.min_confidence:
            result.skipped += 1
            continue
        tab = tab_by_id.get(field.tab_id)
        await store.upsert_item(ConversationStateItem(
            item_id=None,
            template_id=template.template_id,
            tab_id=field.tab_id,
            field_id=field.field_id,
            field_key=field.field_key,
            user_id=user_id,
            character_id=character_id,
            conversation_id=conversation_id,
            category=_category_for_field(field.field_key),
            item_key=field.field_key,
            title=field.label,
            content=value[:1000],
            confidence=confidence,
            priority=70,
            source="state_filler",
            source_turn_id=turn_id,
            metadata={"reason": raw_item.get("reason", ""), "tab_label": tab.label if tab else ""},
        ))
        result.updates.append(FilledStateUpdate(field_key=field.field_key, value=value, confidence=confidence, reason=str(raw_item.get("reason", ""))))
        result.applied += 1

    await store.record_state_event(
        conversation_id,
        "state_filler",
        payload={"applied": result.applied, "skipped": result.skipped, "notes": result.notes},
    )
    return result


def _writable_fields(template: StateBoardTemplate) -> list[StateBoardField]:
    fields: list[StateBoardField] = []
    for tab in template.tabs:
        for field in tab.fields:
            if field.status == "active" and field.ai_writable:
                fields.append(field)
    return fields


def _build_prompt(
    custom_prompt: str,
    template: StateBoardTemplate,
    fields: list[StateBoardField],
    current_by_field: dict[str | None, ConversationStateItem],
    lang: str = "zh",
) -> str:
    if custom_prompt.strip():
        base = custom_prompt.strip()
    else:
        base = get_prompt("state_filler", lang)
    empty_text = get_text(STATE_FILLER_EMPTY, lang)
    field_lines = []
    for field in fields:
        current = current_by_field.get(field.field_id)
        current_text = current.content if current else field.default_value
        field_lines.append(
            f"- field_key={field.field_key}; label={field.label}; description={field.description}; current={current_text or empty_text}"
        )
    header = get_text(STATE_FILLER_TEMPLATE_HEADER, lang, name=template.name)
    return f"{base}{header}" + "\n".join(field_lines)


def _parse_json(text: str) -> dict[str, Any]:
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
        return {"updates": []}
    return payload if isinstance(payload, dict) else {"updates": []}


def _safe_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _category_for_field(field_key: str) -> str:
    mapping = {
        "user_addressing": "preference",
        "character_addressing": "preference",
        "current_mood": "mood",
        "current_task": "main_quest",
        "speech_habit": "preference",
        "roleplay_persona": "preference",
        "relationship_state": "relationship",
        "user_preference": "preference",
        "stable_boundary": "boundary",
        "unfinished_promise": "promise",
        "current_scene": "scene",
        "current_location": "location",
        "recent_summary": "recent_summary",
        "protagonist": "key_person",
        "supporting_characters": "key_person",
        "npcs": "key_person",
        "faction_relations": "relationship",
        "main_quest": "main_quest",
        "side_quests": "side_quest",
        "open_clues": "open_loop",
        "open_loops": "open_loop",
        "important_items": "item",
        "world_state": "world_state",
    }
    return mapping.get(field_key, "scene")
