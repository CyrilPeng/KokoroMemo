"""LLM-based memory judgment and extraction."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.core.prompts import (
    JUDGE_USER_PREFIX,
    JUDGE_USER_RULES_SUFFIX,
    get_prompt,
    get_text,
)
from app.proxy.llm_providers import create_llm_provider


@dataclass
class ExtractedMemory:
    scope: str
    memory_type: str
    content: str
    importance: float
    confidence: float
    tags: list[str]


@dataclass
class MemoryJudgeConfigView:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 30
    temperature: float = 0.0
    mode: str = "model_only"
    user_rules: list[str] | None = None
    prompt: str = ""


async def judge_memories_with_llm(
    user_message: str,
    assistant_message: str,
    character_id: str | None,
    config: MemoryJudgeConfigView,
    min_importance: float = 0.45,
    min_confidence: float = 0.55,
    lang: str = "zh",
) -> list[ExtractedMemory]:
    """Use a cheap/fast model to decide which memory cards to create."""
    if not config.base_url or not config.model:
        return []

    provider = create_llm_provider(
        provider=config.provider,
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
    )
    prompt = _build_prompt(config, lang)
    user_content = get_text(JUDGE_USER_PREFIX, lang, user=user_message, assistant=assistant_message)
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
    memories: list[ExtractedMemory] = []
    for item in payload.get("memories") or payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("should_remember") is False:
            continue
        memory_type = normalize_memory_type(item.get("memory_type") or item.get("card_type") or "preference")
        memory_content = item.get("content") or item.get("memory") or ""
        importance = float(item.get("importance", 0.5))
        confidence = float(item.get("confidence", 0.6))
        if not memory_content or importance < min_importance or confidence < min_confidence:
            continue
        tags = item.get("tags") or [memory_type]
        if not isinstance(tags, list):
            tags = [str(tags)]
        suggested_action = item.get("suggested_action")
        if suggested_action:
            tags.append(f"suggested_action:{suggested_action}")
        risk_level = item.get("risk_level")
        if risk_level:
            tags.append(f"risk:{risk_level}")
        memories.append(ExtractedMemory(
            scope=item.get("scope") or ("character" if character_id else "global"),
            memory_type=memory_type,
            content=memory_content[:500],
            importance=importance,
            confidence=confidence,
            tags=[str(tag) for tag in tags],
        ))
    return memories


def _parse_json(text: str) -> dict:
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
        return {"memories": []}
    return payload if isinstance(payload, dict) else {"memories": []}


def _build_prompt(config: MemoryJudgeConfigView, lang: str = "zh") -> str:
    prompt = config.prompt.strip() or get_prompt("memory_judge", lang)
    mode = normalize_judge_mode(config.mode)
    if mode == "model_with_user_rules" and config.user_rules:
        rules = "\n".join(f"- {rule}" for rule in config.user_rules if rule.strip())
        if rules:
            prompt += get_text(JUDGE_USER_RULES_SUFFIX, lang, rules=rules)
    return prompt


def normalize_judge_mode(mode: str) -> str:
    if mode in {"model_with_user_rules", "rule_then_llm", "user_rules_then_model"}:
        return "model_with_user_rules"
    return "model_only"


def normalize_memory_type(memory_type: str) -> str:
    normalized = str(memory_type or "").strip().lower()
    aliases = {
        "speech_style": "preference",
        "speaking_style": "preference",
        "speech_habit": "preference",
        "口癖": "preference",
        "roleplay_rule": "preference",
        "persona_rule": "preference",
        "character_persona": "character_state",
        "character_setting": "character_state",
        "role_setting": "character_state",
    }
    return aliases.get(normalized, normalized or "preference")
