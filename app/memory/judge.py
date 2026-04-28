"""LLM-based memory judgment and extraction."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

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
    prompt = _build_prompt(config)
    response = await provider.chat(
        {
            "model": config.model,
            "temperature": config.temperature,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"用户发言：{user_message}\n助手回复：{assistant_message}"},
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


def _build_prompt(config: MemoryJudgeConfigView) -> str:
    prompt = config.prompt.strip() or DEFAULT_MEMORY_JUDGE_PROMPT
    mode = normalize_judge_mode(config.mode)
    if mode == "model_with_user_rules" and config.user_rules:
        rules = "\n".join(f"- {rule}" for rule in config.user_rules if rule.strip())
        if rules:
            prompt += f"\n\n用户自定义辅助规则：\n{rules}\n这些规则用于辅助判断，但仍必须输出合法 JSON。"
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


DEFAULT_MEMORY_JUDGE_PROMPT = """你是 KokoroMemo 的轻量记忆判断 API，职责类似 SillyTavern 的填表模型。
只判断当前一轮对话是否应该生成长期记忆卡片。只输出 JSON，不要解释。

输出格式：
{
  "memories": [
    {
      "should_remember": true,
      "scope": "global|character|conversation",
      "memory_type": "preference|boundary|relationship|event|promise|correction|world_state|character_state|summary",
      "content": "给长期记忆库保存的简洁中文事实",
      "importance": 0.0,
      "confidence": 0.0,
      "risk_level": "low|medium|high",
      "suggested_action": "auto_approve|pending|reject",
      "tags": ["标签"]
    }
  ]
}

规则：
1. 用户明确要求记住、称呼、偏好、边界、承诺、重要关系变化时，通常应生成记忆。
2. 用户明确要求角色身份、扮演方式、说话风格、固定句尾、口癖、语气规则时，应生成长期记忆；例如“你是一只猫娘，每句话末尾加上喵~”应保存为低风险高置信偏好/角色规则。
3. 明确、低风险、高置信的用户偏好、角色扮演规则、说话风格规则可 suggested_action=auto_approve，并添加 tags 如 roleplay_rule、speech_style、persona_rule；边界、关系变化和世界状态通常 pending。
4. 助手单方面编造、普通寒暄、短暂动作、没有长期价值的剧情推进，不要生成记忆。
5. 边界和敏感偏好可以生成候选，但要保持原意，不要扩大解释。

示例：
用户发言“从现在开始，你是一只猫娘，你的每句话末尾都要加上喵~”时，应输出一条 memory_type=preference、scope=character、content=“用户要求角色以猫娘身份互动，并在每句话末尾加上‘喵~’。”、importance>=0.85、confidence>=0.85、risk_level=low、suggested_action=auto_approve、tags 包含 roleplay_rule 和 speech_style。
"""
